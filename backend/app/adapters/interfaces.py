"""六类可替换算法协议；计算类适配器不操作存储或网络。"""

from typing import Protocol, runtime_checkable

from app.contracts import (
    AcousticRangeObservation,
    BackprojectionRequest,
    FusionBatch,
    FusionContext,
    FusionEstimate,
    LayoutEvaluation,
    LayoutEvaluationRequest,
    LayoutRequest,
    LayoutResult,
    ProjectionRequest,
    ProjectionResult,
    RayPath,
    SurfaceSample,
    VisionEstimate,
    VisionRequest,
)


@runtime_checkable
class LayoutOptimizer(Protocol):
    """2.1 的布局评价和优化入口。"""

    def evaluate(self, request: LayoutEvaluationRequest) -> LayoutEvaluation:
        """评价给定布局。"""
        ...

    def optimize(self, request: LayoutRequest) -> LayoutResult:
        """返回布局与优化状态。"""
        ...


@runtime_checkable
class VisionLocalizer(Protocol):
    """2.2 的像素观测到目标位置入口。"""

    def localize(self, request: VisionRequest) -> VisionEstimate:
        """仅使用观测、标定和历史估计。"""
        ...


@runtime_checkable
class RefractionModel(Protocol):
    """单界面折射或理想直线的正反投影入口。"""

    def project(self, request: ProjectionRequest) -> ProjectionResult:
        """三维候选点到像素。"""
        ...

    def backproject(self, request: BackprojectionRequest) -> RayPath:
        """像素到水中射线。"""
        ...


@runtime_checkable
class WaveSurfaceModel(Protocol):
    """波面生成入口；真实瞬时波面不能传给基线估计器。"""

    def sample(self, x_m: float, y_m: float, sim_time_s: float) -> SurfaceSample:
        """返回高度、梯度和法向量。"""
        ...


@runtime_checkable
class AcousticRangeSource(Protocol):
    """已形成的测距数据流入口。"""

    def read_until(self, sim_time_s: float) -> list[AcousticRangeObservation]:
        """只返回接收时刻已到且从未交付的测量。"""
        ...


@runtime_checkable
class FusionLocalizer(Protocol):
    """2.3 的异步多源观测融合入口。"""

    def reset(self, context: FusionContext) -> None:
        """新运行重置并接收标定。"""
        ...

    def update(self, batch: FusionBatch) -> FusionEstimate:
        """输出声明参考时刻的估计和实际使用的来源。"""
        ...
