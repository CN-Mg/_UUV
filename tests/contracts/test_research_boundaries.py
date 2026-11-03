"""课题 2.1～2.3 交接边界与后端权威波面回归。"""

import json
from pathlib import Path

import numpy as np
import pytest
from app.adapters.baselines import FixedLayoutAdapter, NoOpFusion
from app.adapters.registry import DESCRIPTORS, REGISTRY, register_adapter
from app.adapters.validation import (
    validate_estimate_result,
    validate_layout_result,
    validate_measurement_calibration,
)
from app.adapters.vision import LeastSquaresLocalizer
from app.contracts import (
    AcousticRangeObservation,
    CalibrationContext,
    FusionBatch,
    FusionContext,
    FusionEstimate,
    LayoutRequest,
    LayoutResult,
    ScenarioConfig,
    VisionEstimate,
    VisionRequest,
    WaterSurfaceSnapshot,
)
from app.simulation.engine import SimulationEngine
from pydantic import ValidationError


@pytest.mark.parametrize('mode', ['IDEAL_NO_REFRACTION', 'FLAT_SNELL_REFRACTION', 'WAVY_SNELL_REFRACTION'])
def test_surface_event_same_physical_wave_and_flat_controls(mode):
    engine = SimulationEngine(ScenarioConfig(mode=mode))
    events = engine.step(0)
    payload = next(p for kind, p in events if kind == 'water_surface')
    first = WaterSurfaceSnapshot.model_validate(payload)
    later = WaterSurfaceSnapshot.model_validate(next(p for k, p in engine.step(1) if k == 'water_surface'))
    assert first.rows == first.columns == 21
    assert len(first.heights_m) == len(first.normals_world) == 441
    # 非对称的网格位置验证行列方向，避免只在中心验证而漏掉转置。
    for row, column in [(3, 7), (0, 20), (20, 0), (10, 10)]:
        x = first.x_bounds_m[0]+column*(first.x_bounds_m[1]-first.x_bounds_m[0])/(first.columns-1)
        y = first.y_bounds_m[0]+row*(first.y_bounds_m[1]-first.y_bounds_m[0])/(first.rows-1)
        direct = engine.surface.sample(x, y, first.sim_time_s)
        index = row*first.columns+column
        assert first.heights_m[index] == pytest.approx(direct.height_m, abs=1e-12)
        np.testing.assert_allclose(first.normals_world[index], direct.normal_world, atol=1e-12)
    if mode == 'WAVY_SNELL_REFRACTION':
        assert engine.surface is engine.projection.surface
        assert first.heights_m != later.heights_m
        assert max(abs(h) for h in first.heights_m) <= engine.config.wave.amplitude_m
    else:
        assert first.heights_m == later.heights_m == [0.]*441
    assert engine.water_surface_snapshot(0) == first  # 调用顺序不改变波场。


def test_surface_shape_and_wrong_schema_rejected():
    snapshot = SimulationEngine(ScenarioConfig()).water_surface_snapshot(0).model_dump()
    with pytest.raises(ValidationError):
        WaterSurfaceSnapshot.model_validate({**snapshot, 'heights_m': [0]})
    with pytest.raises(ValidationError):
        WaterSurfaceSnapshot.model_validate({**snapshot, 'schema_version': '2.0'})
    with pytest.raises(ValidationError):
        WaterSurfaceSnapshot.model_validate({**snapshot, 'normals_world': [(0, 0, -1)]*441})


def test_layout_constraints_enforced_without_invented_optimization():
    config = ScenarioConfig()
    request = LayoutRequest(tank=config.tank, cameras=config.cameras,
        camera_count=3, height_bounds_m=(2, 3), position_bounds_m=[(-2.5, -2.5, 1), (2.5, 2.5, 3)])
    result = FixedLayoutAdapter().optimize(request)
    assert result.optimization_status == 'INVALID_LAYOUT'
    assert '架高' in result.reason
    fake = result.model_copy(update={'optimization_status': 'OPTIMIZED'})
    with pytest.raises(ValueError, match='违反约束'):
        validate_layout_result(request, fake)
    with pytest.raises(ValidationError):
        LayoutRequest(tank=config.tank, cameras=config.cameras, position_bounds_m=[(1, 1, 3), (-1, -1, 1)])
    valid = LayoutRequest(tank=config.tank, cameras=config.cameras, height_bounds_m=(1, 2), camera_count=3)
    assert validate_layout_result(valid, FixedLayoutAdapter().optimize(valid)).evaluation.precision_metric is None


def test_calibration_timestamp_and_estimate_contracts():
    fixtures = Path(__file__).parent / 'fixtures'
    request = VisionRequest.model_validate_json((fixtures / 'vision-request.json').read_text(encoding='utf-8'))
    wrong = request.model_dump()
    wrong['observations'][0]['camera_id'] = 'missing'
    with pytest.raises(ValidationError):
        VisionRequest.model_validate(wrong)
    wrong = request.model_dump()
    wrong['prior_estimate'] = {'target_id': 'someone_else', 'algorithm_id': 'test', 'sim_time_s': 0}
    with pytest.raises(ValidationError):
        VisionRequest.model_validate(wrong)
    with pytest.raises(ValidationError):
        CalibrationContext.model_validate({**request.calibration.model_dump(), 'coordinate_frame': 'ENU'})
    estimate = LeastSquaresLocalizer().localize(request)
    for changes in [{'schema_version': '9.0'}, {'target_id': 'wrong'}, {'sim_time_s': 100},
                    {'position_m': None}, {'position_covariance_m2': [(-1., 0., 0.), (0., 1., 0.), (0., 0., 1.)]}]:
        with pytest.raises(ValueError):
            validate_estimate_result(request.target_id, request.sim_time_s, estimate.model_copy(update=changes))
    with pytest.raises(ValueError, match='版本'):
        validate_estimate_result(request.target_id, request.sim_time_s, estimate, expected_algorithm_version='9.9.9')


def test_typed_fusion_error_clock_and_rigid_transform():
    context = FusionContext(clock_offsets_s={'acoustic_clock': -10},
        error_models={'acoustic': {'distribution': 'GAUSSIAN', 'unit': 'm', 'stddev': .1}},
        sensor_extrinsics={'A1': np.eye(4).tolist()})
    observation = AcousticRangeObservation(measurement_id='a1', target_id='UUV-001',
        anchor_id='A1', range_m=1.4, variance_m2=.01, measurement_time_s=.2, received_sim_time_s=.3,
        source_time_s=10.2, source_clock_id='acoustic_clock', source_frame_id='A1')
    validate_measurement_calibration(observation, context)
    with pytest.raises(ValueError, match='不一致'):
        validate_measurement_calibration(observation.model_copy(update={'source_time_s': 11}), context)
    with pytest.raises(ValueError, match='时钟'):
        validate_measurement_calibration(observation, FusionContext())
    for value in [None, [], {'acoustic': {'stddev': -.1}}]:
        with pytest.raises(ValidationError):
            FusionContext(error_models=value)
    with pytest.raises(ValidationError):
        FusionContext(sensor_extrinsics={'A1': [[1, 0], [0, 1]]})
    with pytest.raises(ValidationError):
        AcousticRangeObservation.model_validate({**observation.model_dump(), 'received_sim_time_s': .1})


def test_noop_refuses_to_retimestamp_old_vision():
    old = VisionEstimate(target_id='UUV-001', algorithm_id='test', sim_time_s=0,
                         valid=True, status='SUCCESS', position_m=(0, 0, -1))
    adapter = NoOpFusion()
    adapter.reset(FusionContext())
    estimate = adapter.update(FusionBatch(target_id='UUV-001', sim_time_s=1, vision=old))
    assert not estimate.valid and estimate.position_m is None and estimate.status == 'TIME_MISMATCH'


def test_registration_version_and_real_bad_plugin_failure(monkeypatch):
    monkeypatch.setattr('app.adapters.registry.DESCRIPTORS', dict(DESCRIPTORS))
    monkeypatch.setitem(REGISTRY, 'vision', dict(REGISTRY['vision']))
    with pytest.raises(ValueError, match='1.0'):
        register_adapter('vision', 'future', lambda **kw: None, algorithm_version='1', supported_schema_versions=['9.0'])

    class BadVision(LeastSquaresLocalizer):
        """返回错误目标的研究员实现，用来测试真实调度拒绝污染数据。"""
        def __init__(self):
            super().__init__('bad_peer_v1')

        def localize(self, request):
            return VisionEstimate(target_id='wrong', sim_time_s=request.sim_time_s, algorithm_id=self.algorithm_id,
                valid=True, status='SUCCESS', position_m=(0, 0, -1))

    register_adapter('vision', 'bad_peer_v1', lambda **kw: BadVision(), algorithm_version='1.0.0', capabilities=['test_only'])
    config = ScenarioConfig()
    config.adapters.vision = 'bad_peer_v1'
    engine = SimulationEngine(config)
    output = next(p for k, p in engine.step(0) if k == 'vision_estimate' and p['algorithm_id'] == 'bad_peer_v1')
    assert output['status'] == 'ADAPTER_CONTRACT_VIOLATION' and output['position_m'] is None
    assert engine.metrics()['algorithms']['bad_peer_v1']['sample_count'] == 1
    assert engine.metrics()['algorithms']['bad_peer_v1']['valid_count'] == 0


def test_plugin_mutation_does_not_change_other_algorithms_or_scene(monkeypatch):
    class MutatingVision(LeastSquaresLocalizer):
        """错误修改请求的插件不能改变后续对照收到的标定。"""
        def __init__(self):
            super().__init__('mutating_peer_v1')

        def localize(self, request):
            request.calibration.cameras[0].position_m = (99, 99, 99)
            return VisionEstimate(target_id=request.target_id, sim_time_s=request.sim_time_s, algorithm_id=self.algorithm_id)

    monkeypatch.setitem(REGISTRY['vision'], 'mutating_peer_v1', lambda **kw: MutatingVision())
    config = ScenarioConfig()
    config.adapters.vision = 'mutating_peer_v1'
    engine = SimulationEngine(config)
    engine.step(0)
    assert engine.calibration.cameras[0].position_m == config.cameras[0].position_m
    assert engine.config.cameras[0].position_m == config.cameras[0].position_m


def test_exported_schema_and_all_public_fixtures_are_current():
    from tools.export_contracts import build_schemas
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root / 'docs/contracts.schema.json').read_text(encoding='utf-8')) == build_schemas()
    types = {'vision-request': VisionRequest, 'vision-estimate': VisionEstimate, 'layout-request': LayoutRequest,
             'layout-result': LayoutResult, 'fusion-context': FusionContext, 'fusion-batch': FusionBatch,
             'fusion-estimate': FusionEstimate, 'water-surface': WaterSurfaceSnapshot}
    for name, model in types.items():
        model.model_validate_json((Path(__file__).parent/'fixtures'/f'{name}.json').read_text(encoding='utf-8'))
