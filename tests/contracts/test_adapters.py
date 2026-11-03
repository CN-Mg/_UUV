"""公开契约、真值隔离和最小替换联调。"""

import copy

import pytest
from app.adapters.baselines import BufferedRangeSource, FixedLayoutAdapter, NoOpFusion
from app.adapters.interfaces import (
    AcousticRangeSource,
    FusionLocalizer,
    LayoutOptimizer,
    RefractionModel,
    VisionLocalizer,
    WaveSurfaceModel,
)
from app.adapters.refraction import SnellRefraction
from app.adapters.registry import REGISTRY, catalog, create_adapter
from app.adapters.vision import LeastSquaresLocalizer
from app.adapters.wave import FlatSurface
from app.contracts import (
    AcousticRangeObservation,
    CameraObservation,
    FusionBatch,
    FusionContext,
    LayoutRequest,
    ScenarioConfig,
    VisionRequest,
)
from app.simulation.engine import SimulationEngine
from pydantic import ValidationError


def test_protocols_are_callable_and_registry_rejects_unknown():
    assert isinstance(FixedLayoutAdapter(), LayoutOptimizer)
    assert isinstance(LeastSquaresLocalizer(), VisionLocalizer)
    assert isinstance(SnellRefraction(), RefractionModel)
    assert isinstance(FlatSurface(), WaveSurfaceModel)
    assert isinstance(BufferedRangeSource(), AcousticRangeSource)
    assert isinstance(NoOpFusion(), FusionLocalizer)
    assert {x['role'] for x in catalog()} == set(REGISTRY)
    with pytest.raises(ValueError, match='未知适配器'):
        create_adapter('vision', 'unregistered')


def test_strict_contract_disallows_truth_and_serialization_is_stable():
    engine = SimulationEngine(ScenarioConfig())
    events = engine.step(0)
    observations = [CameraObservation.model_validate(p) for k, p in events if k == 'camera_observation']
    request = VisionRequest(target_id='UUV-001', sim_time_s=0, observations=observations, calibration=engine.calibration)
    assert VisionRequest.model_validate_json(request.model_dump_json()) == request
    for key in ['truth', 'scenario', 'seed', 'wave', 'position_m']:
        data = request.model_dump()
        data[key] = {'position_m': [100, 100, -100]}
        with pytest.raises(ValidationError):
            VisionRequest.model_validate(data)
    sample = observations[0].model_dump()
    sample['ideal_corners_px'] = [[0, 0]]*4
    with pytest.raises(ValidationError):
        CameraObservation.model_validate(sample)
    # 旁路真值任意变化，不改变白名单请求和估计结果。
    expected = LeastSquaresLocalizer().localize(request)
    changed_events = copy.deepcopy(events)
    for kind, payload in changed_events:
        if kind == 'uuv_truth':
            payload['position_m'] = [99, 99, 99]
            payload['yaw_rad'] = -99
    assert LeastSquaresLocalizer().localize(request) == expected


def test_measurement_shape_finite_and_fixed_layout_state():
    with pytest.raises(ValidationError):
        AcousticRangeObservation(measurement_id='r', target_id='UUV-001', measurement_time_s=0,
                                 received_sim_time_s=0, anchor_id='A1', range_m=float('nan'))
    config = ScenarioConfig()
    result = FixedLayoutAdapter().optimize(LayoutRequest(tank=config.tank, cameras=config.cameras, camera_count=3))
    assert result.optimization_status == 'NOT_OPTIMIZED'
    assert result.evaluation.multi_view_coverage <= result.evaluation.single_view_coverage
    invalid = FixedLayoutAdapter().optimize(LayoutRequest(tank=config.tank, cameras=config.cameras, camera_count=2))
    assert invalid.optimization_status == 'INVALID_LAYOUT'


def test_acoustic_single_delivery_and_noop_does_not_claim_fusion():
    source = BufferedRangeSource()
    observation = AcousticRangeObservation(measurement_id='r1', target_id='UUV-001',
        measurement_time_s=0, received_sim_time_s=.1, anchor_id='A1', range_m=1.3)
    source.push(observation)
    assert source.read_until(0) == []
    assert source.read_until(.1) == [observation]
    assert source.read_until(.2) == []
    engine = SimulationEngine(ScenarioConfig())
    engine.push_measurement({'event_type': 'acoustic_range', **observation.model_dump()})
    assert not any(k == 'acoustic_range' for k, p in engine.step(0))
    events = engine.step(1)
    fusion = next(p for k, p in events if k == 'fusion_estimate')
    assert fusion['fusion_status'] == 'PASSTHROUGH_NOT_FUSED'
    assert fusion['used_sources'] == ['vision']
    assert fusion['received_measurement_types'] == ['vision', 'acoustic']
    assert 'r1' not in fusion['used_measurement_ids']
    f = NoOpFusion()
    f.reset(FusionContext())
    # 尚未接收的测量先由批次契约拒绝；接收后 NoOp 仍不能从距离伪造位置。
    with pytest.raises(ValidationError):
        FusionBatch(target_id='UUV-001', sim_time_s=0, acoustic=[observation])
    assert not f.update(FusionBatch(target_id='UUV-001', sim_time_s=.1, acoustic=[observation])).valid


def test_registered_replacement_used_without_engine_changes(monkeypatch):
    class CustomLocalizer(LeastSquaresLocalizer):
        """接入示例继承已知基线，作为契约路由测试而非科研成果。"""
        def __init__(self):
            super().__init__('classmate_demo_v1', correction=False)

    monkeypatch.setitem(REGISTRY['vision'], 'classmate_demo_v1', lambda **kw: CustomLocalizer())
    config = ScenarioConfig()
    config.adapters.vision = 'classmate_demo_v1'
    engine = SimulationEngine(config)
    assert any(k == 'vision_estimate' and p['algorithm_id'] == 'classmate_demo_v1' for k, p in engine.step(0))
