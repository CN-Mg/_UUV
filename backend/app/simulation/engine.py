"""每步生成事件载荷；存储、墙钟节奏和网络由运行服务负责。"""

from collections import Counter
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.adapters.geometry import load_markers, marker_corners, yaw_rotation
from app.adapters.refraction import PinholeRefraction
from app.adapters.registry import create_adapter
from app.adapters.validation import validate_estimate_result, validate_measurement_calibration
from app.adapters.wave import FlatSurface
from app.contracts import (
    AcousticRangeObservation,
    CalibrationContext,
    CameraObservation,
    CommunicationObservation,
    EvaluationSample,
    FusionBatch,
    FusionContext,
    FusionEstimate,
    LayoutEvaluationRequest,
    ProjectionRequest,
    ScenarioConfig,
    UuvTruth,
    VisionEstimate,
    VisionRequest,
    WaterSurfaceSnapshot,
)

MICRO_UUV_MARKERS = Path(__file__).resolve().parents[3] / 'assets/models/micro_uuv/marker_geometry.json'


class SimulationEngine:
    """仿真唯一计算权威；估计器只收到单独构造的白名单请求。"""

    def __init__(self, config: ScenarioConfig):
        """每个运行创建独立随机源、估计器、测量缓冲及评价记录。"""
        self.config = config.model_copy(deep=True)
        config = self.config
        self.markers = load_markers(MICRO_UUV_MARKERS)
        self.calibration = CalibrationContext(cameras=config.cameras, markers=self.markers,
            optics=config.optics, use_refraction=config.mode != 'IDEAL_NO_REFRACTION')
        self.rng = np.random.default_rng(config.seed)
        for role, name in config.adapters.model_dump().items():
            # 所有角色在启动时验证存在，即使理想对照模式没有使用真实波面。
            from app.adapters.registry import REGISTRY
            if name not in REGISTRY[role]:
                raise ValueError(f'未知适配器 {role}:{name}')
        surface = (create_adapter('wave', config.adapters.wave, config=config.wave, seed=config.seed)
                   if config.mode == 'WAVY_SNELL_REFRACTION' else FlatSurface())
        self.surface = surface
        self.projection = (PinholeRefraction() if config.mode == 'IDEAL_NO_REFRACTION' else
                           create_adapter('refraction', config.adapters.refraction, surface=surface))
        ids = list(dict.fromkeys([config.adapters.vision, *config.experiments.comparison_vision_ids]))
        self.localizers = {name: create_adapter('vision', name) for name in ids}
        self.fusion = {t.target_id: create_adapter('fusion', config.adapters.fusion) for t in config.targets}
        self.fusion_context = FusionContext.model_validate({**config.fusion_context.model_dump(),
            'anchors_world_m': config.anchors_world_m})
        for f in self.fusion.values():
            f.reset(self.fusion_context.model_copy(deep=True))
        self.acoustic = create_adapter('acoustic', config.adapters.acoustic, context=self.fusion_context)
        self._injected_ranges: list[AcousticRangeObservation] = []
        self.communication: list[CommunicationObservation] = []
        self._measurement_events: list[tuple[str, dict]] = []
        self._previous = {}
        self.samples: dict[str, list[dict]] = {name: [] for name in ids}
        self.layout_adapter = create_adapter('layout', config.adapters.layout)
        layout_request = LayoutEvaluationRequest(
            tank=config.tank, cameras=config.cameras, optics=config.optics,
            depths_m=sorted({t.depth_m for t in config.targets}), grid_size=7)
        from app.contracts import LayoutEvaluation
        evaluated = self.layout_adapter.evaluate(layout_request.model_copy(deep=True))
        raw_layout = evaluated.model_dump() if isinstance(evaluated, BaseModel) else evaluated
        self.layout_evaluation = LayoutEvaluation.model_validate(raw_layout).model_dump(mode='json')

    def push_measurement(self, data: dict) -> None:
        """接收运行服务已校验的声学或通信测量，不接受真值。"""
        data = dict(data)
        event_type = data.pop('event_type')
        if event_type == 'acoustic_range':
            observation = AcousticRangeObservation.model_validate(data)
            if observation.anchor_id not in self.fusion_context.anchors_world_m:
                raise ValueError('未知声学锚点')
        elif event_type == 'communication_observation':
            observation = CommunicationObservation.model_validate(data)
        else:
            raise ValueError('仅支持 acoustic_range 或 communication_observation')
        if observation.target_id not in {target.target_id for target in self.config.targets}:
            raise ValueError('未知测量目标')
        validate_measurement_calibration(observation, self.fusion_context)
        if event_type == 'acoustic_range':
            self._injected_ranges.append(observation)
        else:
            self.communication.append(observation)
        self._measurement_events.append((event_type, observation.model_dump(mode='json')))

    def water_surface_snapshot(self, sim_time_s: float) -> WaterSurfaceSnapshot:
        """每个数学步发布 21×21 权威网格，逐行 y、逐列 x 递增。"""
        tank = self.config.tank
        xs = np.linspace(-tank.length_m/2, tank.length_m/2, 21)
        ys = np.linspace(-tank.width_m/2, tank.width_m/2, 21)
        if hasattr(self.surface, 'sample_grid'):
            heights, normals = self.surface.sample_grid(xs, ys, sim_time_s)
        else:
            samples = [self.surface.sample(float(x), float(y), sim_time_s) for y in ys for x in xs]
            heights = np.array([s.height_m for s in samples]).reshape(len(ys), len(xs))
            normals = np.array([s.normal_world for s in samples]).reshape(len(ys), len(xs), 3)
        return WaterSurfaceSnapshot(sim_time_s=sim_time_s, rows=len(ys), columns=len(xs),
            x_bounds_m=(xs[0], xs[-1]), y_bounds_m=(ys[0], ys[-1]),
            heights_m=np.asarray(heights).ravel().tolist(),
            normals_world=np.asarray(normals).reshape(-1, 3).tolist(),
            model_kind=self.surface.algorithm_id)

    def _observations(self, target_id, truth, tick_index, time):
        observations = []
        rotation = yaw_rotation(truth.yaw_rad)
        for camera in self.config.cameras:
            for marker in self.markers:
                points = marker_corners(marker) @ rotation.T + truth.position_m
                results = [self.projection.project(ProjectionRequest(point_world_m=tuple(p), camera=camera,
                    sim_time_s=time, optics=self.config.optics)) for p in points]
                if not all(r.valid and r.in_image for r in results):
                    continue
                # 标记正面朝向水中段的界面交点；理想模型直接朝光心。
                facing = -np.asarray(results[0].ray.water_direction_world)
                if (rotation @ np.asarray(marker.outward_normal)) @ facing <= 1e-8:
                    continue
                pixels = np.array([r.pixel_px for r in results])
                if self.config.pixel_noise_std_px:
                    pixels += self.rng.normal(0, self.config.pixel_noise_std_px, pixels.shape)
                if not np.all((pixels[:, 0] >= 0) & (pixels[:, 0] < camera.width_px)
                              & (pixels[:, 1] >= 0) & (pixels[:, 1] < camera.height_px)):
                    continue
                observations.append(CameraObservation(measurement_id=f'{tick_index}:{target_id}:{camera.camera_id}:{marker.marker_id}',
                    target_id=target_id, camera_id=camera.camera_id, marker_id=marker.marker_id,
                    measurement_time_s=time, received_sim_time_s=time,
                    corners_px=[tuple(p) for p in pixels], pixel_noise_std_px=self.config.pixel_noise_std_px,
                    refraction_mode=self.config.mode))
        return observations

    def step(self, tick_index: int) -> list[tuple[str, dict]]:
        """固定时刻的生成、估计与评价；不读取墙钟时间。"""
        time = tick_index*self.config.dt_s
        events = [(kind, data) for kind, data in self._measurement_events if data['received_sim_time_s'] <= time]
        events.append(('water_surface', self.water_surface_snapshot(time).model_dump(mode='json')))
        self._measurement_events = [(kind, data) for kind, data in self._measurement_events
                                    if data['received_sim_time_s'] > time]
        acoustic = self.acoustic.read_until(time)
        acoustic = [AcousticRangeObservation.model_validate(o.model_dump() if isinstance(o, BaseModel) else o) for o in acoustic]
        for observation in acoustic:
            if observation.received_sim_time_s > time+1e-6 or observation.anchor_id not in self.fusion_context.anchors_world_m:
                raise ValueError('测距源返回尚未接收的测量或未知锚点')
            validate_measurement_calibration(observation, self.fusion_context)
            events.append(('acoustic_range', observation.model_dump(mode='json')))
        acoustic += [o for o in self._injected_ranges if o.received_sim_time_s <= time]
        self._injected_ranges = [o for o in self._injected_ranges if o.received_sim_time_s > time]
        communication = [o for o in self.communication if o.received_sim_time_s <= time]
        self.communication = [o for o in self.communication if o.received_sim_time_s > time]
        for target in self.config.targets:
            phase = 2*np.pi*time/target.period_s+target.phase_rad
            yaw = phase+np.pi/2
            position = (target.center_xy_m[0]+target.radius_m*np.cos(phase),
                        target.center_xy_m[1]+target.radius_m*np.sin(phase), -target.depth_m)
            truth = UuvTruth(target_id=target.target_id, position_m=position, yaw_rad=yaw,
                orientation_wxyz=(np.cos(yaw/2), 0, 0, np.sin(yaw/2)), speed_mps=2*np.pi*target.radius_m/target.period_s)
            events.append(('uuv_truth', truth.model_dump(mode='json')))
            observations = self._observations(target.target_id, truth, tick_index, time)
            events.extend(('camera_observation', obs.model_dump(mode='json')) for obs in observations)
            estimates = {}
            for name, localizer in self.localizers.items():
                key = (target.target_id, name)
                # 白名单只传观测与标定，不把 config、truth 或生成器传入算法。
                request = VisionRequest(target_id=target.target_id, sim_time_s=time,
                    observations=observations, calibration=self.calibration, prior_estimate=self._previous.get(key)).model_copy(deep=True)
                try:
                    estimate = validate_estimate_result(target.target_id, time, localizer.localize(request),
                        expected_algorithm_id=name, expected_algorithm_version=localizer.algorithm_version,
                        allowed_measurement_ids={o.measurement_id for o in observations})
                except (ValueError, TypeError) as exc:
                    estimate = VisionEstimate(target_id=target.target_id, sim_time_s=time, algorithm_id=name,
                        algorithm_version=localizer.algorithm_version, status='ADAPTER_CONTRACT_VIOLATION', reason=str(exc))
                estimates[name] = estimate
                if estimate.valid:
                    self._previous[key] = estimate
                events.append(('vision_estimate', estimate.model_dump(mode='json')))
                sample = EvaluationSample(target_id=target.target_id, algorithm_id=name,
                                          valid=estimate.valid, status=estimate.status)
                if estimate.valid:
                    error = np.array(estimate.position_m)-truth.position_m
                    sample = sample.model_copy(update={'error_m': float(np.linalg.norm(error)),
                        'position_error_m': tuple(error), 'horizontal_error_m': float(np.linalg.norm(error[:2])),
                        'depth_error_m': float(abs(error[2]))})
                payload = sample.model_dump(mode='json')
                payload['tick_index'] = tick_index
                payload['filter_lag_nominal_s'] = estimate.filter_lag_nominal_s
                self.samples[name].append(payload)
                events.append(('evaluation_sample', payload))
            batch = FusionBatch(target_id=target.target_id, sim_time_s=time,
                vision=estimates[self.config.adapters.vision],
                acoustic=[o for o in acoustic if o.target_id == target.target_id],
                communication=[o for o in communication if o.target_id == target.target_id])
            allowed = {o.measurement_id for o in [*batch.acoustic, *batch.communication]}
            allowed.update(batch.vision.used_measurement_ids)
            try:
                fusion = validate_estimate_result(target.target_id, time, self.fusion[target.target_id].update(batch),
                    model_type=FusionEstimate, expected_algorithm_id=self.config.adapters.fusion,
                    allowed_measurement_ids=allowed,
                    expected_algorithm_version=self.fusion[target.target_id].algorithm_version)
            except (ValueError, TypeError) as exc:
                fusion = FusionEstimate(target_id=target.target_id, sim_time_s=time,
                    algorithm_id=self.config.adapters.fusion, status='ADAPTER_CONTRACT_VIOLATION', reason=str(exc),
                    algorithm_version=self.fusion[target.target_id].algorithm_version, fusion_status='FAILED')
            events.append(('fusion_estimate', fusion.model_dump(mode='json')))
        return events

    @staticmethod
    def _aggregate(samples):
        valid = [s for s in samples if s['valid']]
        errors = np.array([s['error_m'] for s in valid])
        vectors = np.array([s['position_error_m'] for s in valid])
        return {'sample_count': len(samples), 'valid_count': len(valid),
            'valid_rate': len(valid)/len(samples) if samples else 0,
            'rmse_m': float(np.sqrt(np.mean(errors**2))) if valid else None,
            'mae_m': float(np.mean(errors)) if valid else None,
            'p95_m': float(np.percentile(errors, 95)) if valid else None,
            'horizontal_rmse_m': float(np.sqrt(np.mean(np.sum(vectors[:, :2]**2, axis=1)))) if valid else None,
            'depth_rmse_m': float(np.sqrt(np.mean(vectors[:, 2]**2))) if valid else None,
            'mean_error_vector_m': vectors.mean(axis=0).tolist() if valid else None,
            'filter_lag_nominal_s': float(max((s.get('filter_lag_nominal_s', 0) for s in valid), default=0)),
            'failure_counts': dict(Counter(s['status'] for s in samples if not s['valid']))}

    def metrics(self) -> dict:
        """各自有效率与共同有效帧指标分别报告，不删除失败样本。"""
        valid_keys = [set((s['target_id'], s['tick_index']) for s in values if s['valid'])
                      for values in self.samples.values()]
        common = set.intersection(*valid_keys) if valid_keys else set()
        return {'evidence_status': 'DEMO_UNCALIBRATED', 'algorithms': {
            name: self._aggregate(values) for name, values in self.samples.items()},
            'common_valid_metrics': {name: self._aggregate([s for s in values if
                (s['target_id'], s['tick_index']) in common]) for name, values in self.samples.items()},
            'common_valid_count': len(common), 'layout_evaluation': self.layout_evaluation}
