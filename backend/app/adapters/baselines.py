"""固定布局、缓冲测距与 NoOp 融合均保留明确占位状态。"""

import itertools

import numpy as np

from app.contracts import (
    AcousticRangeObservation,
    FusionBatch,
    FusionContext,
    FusionEstimate,
    LayoutEvaluation,
    LayoutEvaluationRequest,
    LayoutRequest,
    LayoutResult,
    ProjectionRequest,
)

from .refraction import SnellRefraction
from .validation import layout_constraint_violations


class FixedLayoutAdapter:
    """仅评价并回传已有布局，正式优化由 2.1 研究员接入。"""

    algorithm_id = 'fixed_layout_v1'
    algorithm_version = '1.0.0'

    def evaluate(self, request: LayoutEvaluationRequest) -> LayoutEvaluation:
        """在指定深度网格计算几何点覆盖与水中射线锐交会角。"""
        model = SnellRefraction()
        singles, doubles, count, angles = 0, 0, 0, []
        for x, y, depth in itertools.product(np.linspace(-request.tank.length_m/2, request.tank.length_m/2, request.grid_size),
            np.linspace(-request.tank.width_m/2, request.tank.width_m/2, request.grid_size), request.depths_m):
            rays = []
            count += 1
            for camera in request.cameras:
                projected = model.project(ProjectionRequest(point_world_m=(x, y, -depth), camera=camera, optics=request.optics))
                if projected.valid and projected.in_image:
                    rays.append(np.asarray(projected.ray.water_direction_world))
            singles += len(rays) >= 1
            doubles += len(rays) >= 2
            pairs = [float(np.arccos(np.clip(abs(a@b), 0, 1))) for a, b in itertools.combinations(rays, 2)]
            if pairs:
                angles.append(max(pairs))
        return LayoutEvaluation(single_view_coverage=singles/count if count else 0,
            multi_view_coverage=doubles/count if count else 0,
            median_intersection_angle_rad=float(np.median(angles)) if angles else None,
            invalid_point_count=count-doubles, sample_count=count)

    def optimize(self, request: LayoutRequest) -> LayoutResult:
        """缺少布局/数量不符返回状态，不生成虚构最优解。"""
        reason = '固定布局仅回传配置，尚未实现 2.1 优化'
        violations = layout_constraint_violations(request, request.cameras)
        if violations:
            return LayoutResult(cameras=request.cameras, evaluation=LayoutEvaluation(),
                                optimization_status='INVALID_LAYOUT', reason='；'.join(violations))
        return LayoutResult(cameras=request.cameras, evaluation=self.evaluate(request), reason=reason)


class BufferedRangeSource:
    """只读取已形成的测距；不接触真值和运行事件文件。"""

    algorithm_id = 'buffered_ranges_v1'
    algorithm_version = '1.0.0'

    def __init__(self):
        """每次运行建立新缓冲。"""
        self.pending: list[AcousticRangeObservation] = []

    def push(self, observation: AcousticRangeObservation) -> None:
        """接收入口已经校验的测量。"""
        self.pending.append(observation)

    def read_until(self, sim_time_s: float) -> list[AcousticRangeObservation]:
        """交付一次后移除，不重复返回历史样本。"""
        ready = [o for o in self.pending if o.received_sim_time_s <= sim_time_s]
        self.pending = [o for o in self.pending if o.received_sim_time_s > sim_time_s]
        return sorted(ready, key=lambda o: (o.received_sim_time_s, o.measurement_id))


class NoOpFusion:
    """仅透传视觉；收到声学/通信信息不等于使用这些信息。"""

    algorithm_id = 'noop_fusion_v1'
    algorithm_version = '1.0.0'

    def reset(self, context: FusionContext) -> None:
        """保存无真值标定，不保留跨运行状态。"""
        self.context = context

    def update(self, batch: FusionBatch) -> FusionEstimate:
        """有效视觉原样透传，无视觉时不伪造预测位置。"""
        received = []
        if batch.acoustic:
            received.append('acoustic')
        if batch.communication:
            received.append('communication')
        if batch.vision and batch.vision.valid:
            if abs(batch.vision.sim_time_s-batch.sim_time_s) > 1e-6:
                return FusionEstimate(target_id=batch.target_id, sim_time_s=batch.sim_time_s,
                    algorithm_id=self.algorithm_id, status='TIME_MISMATCH',
                    reason='NoOp 不把旧视觉解当作当前时刻预测', received_measurement_types=['vision', *received])
            fields = batch.vision.model_dump()
            fields.update(algorithm_id=self.algorithm_id, reason='仅透传视觉，未融合声学或通信')
            return FusionEstimate(**fields, used_sources=['vision'], received_measurement_types=['vision', *received])
        return FusionEstimate(target_id=batch.target_id, sim_time_s=batch.sim_time_s,
                              algorithm_id=self.algorithm_id, reason='没有有效视觉解，NoOp 不做预测',
                              received_measurement_types=received)
