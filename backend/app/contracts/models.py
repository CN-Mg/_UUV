"""Pydantic 公共数据模型；估计器输入与仿真真值结构严格分开。"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]
Mode = Literal['IDEAL_NO_REFRACTION', 'FLAT_SNELL_REFRACTION', 'WAVY_SNELL_REFRACTION']
SchemaVersion = Literal['1.0']
WorldFrame = Literal['LOCAL_TANK_RH']


def validate_covariance(value):
    """可选位置协方差必须对称半正定，单位 m²；零方差不表示已标定。"""
    if value is not None:
        matrix = np.asarray(value, dtype=float)
        if matrix.shape != (3, 3) or not np.allclose(matrix, matrix.T, atol=1e-10):
            raise ValueError('位置协方差必须是对称 3×3 矩阵')
        if np.linalg.eigvalsh(matrix).min() < -1e-10:
            raise ValueError('位置协方差必须半正定')
    return value


class Contract(BaseModel):
    """禁止未知字段及非有限浮点数，防止含真值的完整对象混入。"""

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class TankConfig(Contract):
    """矩形水池尺寸，深度是正值。"""

    length_m: float = Field(5, gt=0, description='场地长轴尺寸 m')
    width_m: float = Field(5, gt=0, description='场地宽轴尺寸 m')
    depth_m: float = Field(2, gt=0, description='水池正值深度 m')


class CameraCalibration(Contract):
    """相机坐标 x 右、y 下、z 前；相机朝向用世界目标点定义。"""

    camera_id: str = Field(description='相机唯一标识')
    position_m: Vec3 = Field(description='相机光心世界坐标 m')
    look_at_m: Vec3 = Field((0, 0, -1), description='光轴指向的世界坐标 m')
    width_px: int = Field(1280, gt=0, description='图像宽度 px')
    height_px: int = Field(720, gt=0, description='图像高度 px')
    fx_px: float = Field(900, gt=0, description='水平焦距 px')
    fy_px: float = Field(900, gt=0, description='垂直焦距 px')
    cx_px: float = Field(640, description='主点横坐标 px')
    cy_px: float = Field(360, description='主点纵坐标 px')

    @model_validator(mode='after')
    def nonzero_axis(self):
        """相机位置和指向点不能重合。"""
        if sum((a - b) ** 2 for a, b in zip(self.position_m, self.look_at_m)) < 1e-12:
            raise ValueError('相机光心与朝向点不能重合')
        return self


def default_cameras() -> list[CameraCalibration]:
    """返回三台未标定演示相机。"""
    return [CameraCalibration(camera_id=f'C{i + 1}', position_m=p)
            for i, p in enumerate([(-2, -2, 1.5), (2, -2, 1.5), (0, 2.2, 1.5)])]


class TargetConfig(Contract):
    """水平圆轨迹，仅用于生成运动真值。"""

    target_id: str = Field('UUV-001', description='目标唯一标识')
    radius_m: float = Field(.7, gt=0, description='圆轨迹半径 m')
    depth_m: float = Field(1, gt=0, description='艇体中心正值深度 m')
    period_s: float = Field(60, gt=0, description='圆轨迹周期 s；速度由此推导')
    phase_rad: float = Field(0, description='轨迹起始相位 rad')
    center_xy_m: Vec2 = Field((0, 0), description='轨迹中心水平坐标 m')


class OpticsConfig(Contract):
    """单一水空气界面的折射率。"""

    n_air: float = Field(1.00029, gt=0, description='空气折射率')
    n_water: float = Field(1.333, gt=0, description='水折射率')


class WaveConfig(Contract):
    """运动波面；振幅总和是波高绝对值上界，并非显著波高。"""

    amplitude_m: float = Field(.02, ge=0, le=.08, description='各分量振幅绝对值总和 m')
    wavelengths_m: list[float] = Field(default_factory=lambda: [1.5, 2.0], description='各分量波长 m')
    periods_s: list[float] = Field(default_factory=lambda: [1.0, 1.2], description='各分量周期 s')
    directions_rad: list[float] = Field(default_factory=lambda: [0, 1.2], description='各分量传播方位 rad')

    @model_validator(mode='after')
    def components(self):
        """限制分量数量与最大坡度，M1 不支持陡峭/破碎波。"""
        n = len(self.wavelengths_m)
        if not 1 <= n <= 3 or len(self.periods_s) != n or len(self.directions_rad) != n:
            raise ValueError('波面须有 1～3 个长度一致的分量')
        if min(self.wavelengths_m + self.periods_s) <= 0:
            raise ValueError('波长和周期必须为正')
        if sum(6.28318530718 * self.amplitude_m / n / w for w in self.wavelengths_m) > .5:
            raise ValueError('M1 仅支持最大坡度上界不超过 0.5 的小坡度波面')
        return self


class ObservationErrorModel(Contract):
    """研究员可配置的观测误差声明；UNSPECIFIED 不冒充已知高斯模型。"""

    distribution: Literal['UNSPECIFIED', 'GAUSSIAN', 'EMPIRICAL'] = 'UNSPECIFIED'
    unit: Literal['m', 'px', 's', 'm/s', 'dimensionless'] = 'm'
    stddev: float | None = Field(None, ge=0, description='标量标准差；未知为空')
    bias: float = Field(0, description='同单位的已知常偏；默认未标定零值')
    description: str = '未标定的接口参数'
    evidence_status: Literal['DEMO_UNCALIBRATED'] = 'DEMO_UNCALIBRATED'


class FusionContext(Contract):
    """融合标定；已知时钟映射为 t_sim=scale*t_source+offset，不估计设备时钟。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    anchors_world_m: dict[str, Vec3] = Field(default_factory=lambda: {'A1': (0, 0, -1.8)})
    sensor_extrinsics: dict[str, list[list[float]]] = Field(default_factory=dict, description='T_world_sensor，4×4 刚体变换')
    clock_offsets_s: dict[str, float] = Field(default_factory=dict, description='设备时钟到仿真时钟偏移 s')
    clock_scales: dict[str, float] = Field(default_factory=dict, description='设备时钟到仿真时钟比例，默认 1')
    error_models: dict[str, ObservationErrorModel] = Field(default_factory=dict)
    alignment_tolerance_s: float = Field(1e-6, ge=0, le=1, description='校验已映射时间的一致性容差 s')

    @field_validator('error_models', mode='before')
    @classmethod
    def legacy_error_description(cls, values):
        """兼容早期字符串说明，统一转换为未指定分布的显式模型。"""
        if not isinstance(values, dict):
            raise ValueError('error_models 必须是按观测源命名的对象')
        return {key: {'description': value} if isinstance(value, str) else value
                for key, value in values.items()}

    @model_validator(mode='after')
    def calibration_shape(self):
        """外参必须是有效刚体变换，时间比例必须为正。"""
        for name, transform in self.sensor_extrinsics.items():
            matrix = np.asarray(transform)
            if matrix.shape != (4, 4) or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8):
                raise ValueError(f'{name} 的外参必须是 4×4 齐次变换')
            rotation = matrix[:3, :3]
            if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-6):
                raise ValueError(f'{name} 的外参旋转必须为右手正交矩阵')
        if any(value <= 0 for value in self.clock_scales.values()):
            raise ValueError('时钟比例必须为正')
        return self


class AdapterSelection(Contract):
    """显式注册表中的算法 ID；不接受任意 Python 路径。"""

    layout: str = 'fixed_layout_v1'
    vision: str = 'flat_snell_baseline_v1'
    refraction: str = 'snell_single_interface_v1'
    wave: str = 'seeded_multisine_v1'
    acoustic: str = 'buffered_ranges_v1'
    fusion: str = 'noop_fusion_v1'


class ExperimentConfig(Contract):
    """对同一观测批次运行的独立对照估计器。"""

    comparison_vision_ids: list[str] = Field(default_factory=lambda: ['pinhole_baseline_v1', 'flat_snell_smoothed_v1'])


class ScenarioConfig(Contract):
    """完整场景只传给调度/生成器，不能传给估计器。"""

    schema_version: SchemaVersion = '1.0'
    scenario_id: str = 'demo_uncalibrated'
    name: str = '微型 UUV 基础闭环演示'
    evidence_status: Literal['DEMO_UNCALIBRATED'] = 'DEMO_UNCALIBRATED'
    coordinate_frame: Literal['LOCAL_TANK_RH'] = 'LOCAL_TANK_RH'
    mode: Mode = 'FLAT_SNELL_REFRACTION'
    seed: int = 20261102
    dt_s: float = Field(.1, ge=.01, le=1)
    duration_s: float = Field(60, gt=0, le=3600)
    tank: TankConfig = Field(default_factory=TankConfig)
    cameras: list[CameraCalibration] = Field(default_factory=default_cameras, min_length=1, max_length=16)
    targets: list[TargetConfig] = Field(default_factory=lambda: [TargetConfig()], min_length=1, max_length=8)
    optics: OpticsConfig = Field(default_factory=OpticsConfig)
    wave: WaveConfig = Field(default_factory=WaveConfig)
    pixel_noise_std_px: float = Field(0, ge=0, le=20)
    adapters: AdapterSelection = Field(default_factory=AdapterSelection)
    experiments: ExperimentConfig = Field(default_factory=ExperimentConfig)
    anchors_world_m: dict[str, Vec3] = Field(default_factory=lambda: {'A1': (0, 0, -1.8)}, description='声学锚点世界坐标 m')
    fusion_context: FusionContext = Field(default_factory=FusionContext, description='2.3 的外参、时钟、误差配置；锚点以 anchors_world_m 为权威')

    @model_validator(mode='after')
    def geometry_constraints(self):
        """校验艇体包围球和深度，不只检查轨迹中心。"""
        if len({c.camera_id for c in self.cameras}) != len(self.cameras):
            raise ValueError('相机 ID 必须唯一')
        if len({t.target_id for t in self.targets}) != len(self.targets):
            raise ValueError('目标 ID 必须唯一')
        if any(c.position_m[2] <= self.wave.amplitude_m for c in self.cameras):
            raise ValueError('相机光心必须高于波面上界')
        for target in self.targets:
            if target.depth_m <= .42 + self.wave.amplitude_m or target.depth_m >= self.tank.depth_m - .3:
                raise ValueError('目标深度不能使概念艇体穿越波面或池底')
            for center, size in zip(target.center_xy_m, [self.tank.length_m, self.tank.width_m]):
                if abs(center) + target.radius_m + 1.57 > size / 2:
                    raise ValueError('轨迹加艇体水平包围半径 1.57 m 超出水池')
        return self


class MarkerGeometry(Contract):
    """标记机体系标定信息，不含世界真值角点。"""

    marker_id: int
    center_m: Vec3
    u_axis: Vec3
    v_axis: Vec3
    outward_normal: Vec3
    black_square_size_m: float = Field(.12, gt=0, description='黑色编码方块边长 m，不含白色静区')
    surface_radius_m: float | None = Field(None, gt=0, description='沿 v 轴弯曲的圆柱半径 m，空值表示平面')
    corner_order: str = 'bottom-left,bottom-right,top-right,top-left'

    @model_validator(mode='after')
    def marker_axes(self):
        """标记轴向须是与朝外法向量一致的右手正交单位基。"""
        basis = np.array([self.u_axis, self.v_axis, self.outward_normal])
        if not np.allclose(basis @ basis.T, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(basis), 1, atol=1e-5):
            raise ValueError('标记 u、v、outward_normal 必须构成右手正交单位基')
        return self


class CalibrationContext(Contract):
    """白名单标定上下文：没有场景、轨迹、种子或瞬时真实波面。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    cameras: list[CameraCalibration]
    markers: list[MarkerGeometry]
    optics: OpticsConfig = Field(default_factory=OpticsConfig)
    use_refraction: bool = True
    mean_surface_z_m: Literal[0.0] = 0.0

    @model_validator(mode='after')
    def identities(self):
        """拒绝重号标定，防止后续字典转换静默覆盖。"""
        if len({c.camera_id for c in self.cameras}) != len(self.cameras):
            raise ValueError('标定相机 ID 重复')
        if len({m.marker_id for m in self.markers}) != len(self.markers):
            raise ValueError('标定标记 ID 重复')
        return self


class SurfaceSample(Contract):
    """波面高度、梯度与向上法向量。"""

    height_m: float
    gradient: Vec2
    normal_world: Vec3

    @model_validator(mode='after')
    def surface_normal(self):
        """法向量必须与高度梯度一致并指向 +Z。"""
        expected = np.array([-self.gradient[0], -self.gradient[1], 1.])
        expected /= np.linalg.norm(expected)
        if not np.allclose(expected, self.normal_world, atol=1e-6):
            raise ValueError('波面法向量须为 normalize(-hx,-hy,1)')
        return self


class WaterSurfaceSnapshot(Contract):
    """后端权威的水面显示网格，与光学使用同一波场实例，不传给估计器。"""

    schema_version: SchemaVersion = '1.0'
    surface_id: Literal['water'] = 'water'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    sim_time_s: float = Field(ge=0)
    rows: int = Field(21, ge=2, le=101)
    columns: int = Field(21, ge=2, le=101)
    x_bounds_m: Vec2
    y_bounds_m: Vec2
    heights_m: list[float]
    normals_world: list[Vec3]
    model_kind: str
    evidence_status: Literal['DEMO_UNCALIBRATED'] = 'DEMO_UNCALIBRATED'

    @model_validator(mode='after')
    def row_major_shape(self):
        """第 row 行是 y，第 column 列是 x，索引 row*columns+column。"""
        size = self.rows*self.columns
        if len(self.heights_m) != size or len(self.normals_world) != size:
            raise ValueError('水面高度和法向量数量必须等于 rows*columns')
        if self.x_bounds_m[0] >= self.x_bounds_m[1] or self.y_bounds_m[0] >= self.y_bounds_m[1]:
            raise ValueError('水面网格范围必须由小到大')
        normals = np.array(self.normals_world)
        if not np.allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-6) or (normals[:, 2] <= 0).any():
            raise ValueError('水面法向量必须归一化并朝上')
        return self


class ProjectionRequest(Contract):
    """候选点投影；仿真生成时可使用真值点，估计时仅用候选点。"""

    point_world_m: Vec3
    camera: CameraCalibration
    sim_time_s: float = 0
    optics: OpticsConfig = Field(default_factory=OpticsConfig)


class BackprojectionRequest(Contract):
    """像素沿光路反投影到水中射线。"""

    pixel_px: Vec2
    camera: CameraCalibration
    sim_time_s: float = 0
    optics: OpticsConfig = Field(default_factory=OpticsConfig)


class RayPath(Contract):
    """方向均由相机朝目标，界面交点为空表示理想直线模型。"""

    valid: bool = False
    status: str = 'NO_PATH'
    origin_world_m: Vec3 | None = None
    intersection_world_m: Vec3 | None = None
    air_direction_world: Vec3 | None = None
    water_direction_world: Vec3 | None = None


class ProjectionResult(Contract):
    """投影结果不把图像范围外像素冒充可见点。"""

    valid: bool = False
    status: str = 'NO_PATH'
    pixel_px: Vec2 | None = None
    ray: RayPath | None = None
    in_image: bool = False


class Measurement(Contract):
    """测量身份、源时间与接收时间的共同字段。"""

    schema_version: SchemaVersion = '1.0'
    measurement_id: str
    target_id: str
    measurement_time_s: float = Field(ge=0)
    received_sim_time_s: float = Field(ge=0)
    source_time_s: float | None = None
    source_clock_id: str | None = None
    source_frame_id: str | None = None
    valid: bool = True

    @model_validator(mode='after')
    def time_order(self):
        """已映射到同一时钟的接收时刻不能早于观测；原始设备时钟不参与该比较。"""
        if self.received_sim_time_s + 1e-9 < self.measurement_time_s:
            raise ValueError('接收时刻不能早于已映射的观测时刻')
        if (self.source_time_s is None) != (self.source_clock_id is None):
            raise ValueError('source_time_s 与 source_clock_id 必须同时提供或同时省略')
        return self


class CameraObservation(Measurement):
    """解析已知关联角点，只传最终像素，不传理想像素和世界角点。"""

    camera_id: str
    marker_id: int
    corners_px: list[Vec2] = Field(min_length=4, max_length=4)
    corner_order: Literal['bottom-left,bottom-right,top-right,top-left'] = 'bottom-left,bottom-right,top-right,top-left'
    pixel_noise_std_px: float = Field(0, ge=0)
    observation_kind: Literal['ANALYTIC_IDEAL_MARKER_OBSERVATION'] = 'ANALYTIC_IDEAL_MARKER_OBSERVATION'
    association_kind: Literal['SYNTHETIC_KNOWN_ASSOCIATION'] = 'SYNTHETIC_KNOWN_ASSOCIATION'
    refraction_mode: Mode = 'IDEAL_NO_REFRACTION'


class AcousticRangeObservation(Measurement):
    """距离不是三维坐标；锚点位置由 FusionContext 给出。"""

    anchor_id: str
    range_m: float = Field(ge=0)
    variance_m2: float | None = Field(None, gt=0)


class CommunicationObservation(Measurement):
    """状态或有来源的位置消息，避免把转发视觉当独立测量。"""

    source_id: str
    message_type: str = 'STATUS'
    message: str = ''
    position_m: Vec3 | None = None
    position_covariance_m2: list[Vec3] | None = Field(None, min_length=3, max_length=3)
    derived_from_measurement_ids: list[str] = Field(default_factory=list)
    position_frame: WorldFrame = 'LOCAL_TANK_RH'

    _check_covariance = field_validator('position_covariance_m2')(validate_covariance)


class VisionEstimate(Contract):
    """水平航行基线估计 xyz+yaw，协方差未知时为空。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    target_id: str
    sim_time_s: float = Field(ge=0)
    algorithm_id: str
    algorithm_version: str = '1.0.0'
    valid: bool = False
    status: str = 'NO_OBSERVATION'
    reason: str = ''
    position_m: Vec3 | None = None
    yaw_rad: float | None = None
    orientation_wxyz: tuple[float, float, float, float] | None = None
    estimated_dofs: list[str] = Field(default_factory=lambda: ['x', 'y', 'z', 'yaw'])
    position_covariance_m2: list[Vec3] | None = Field(None, min_length=3, max_length=3)
    reprojection_rmse_px: float | None = Field(None, ge=0)
    used_measurement_ids: list[str] = Field(default_factory=list)
    evidence_status: str = 'DEMO_UNCALIBRATED'
    correction_status: str = 'MODEL_AWARE_DEMO'
    filter_lag_nominal_s: float = 0

    _check_covariance = field_validator('position_covariance_m2')(validate_covariance)

    @model_validator(mode='after')
    def estimate_consistency(self):
        """成功解必须有位置；失败不携带伪装为测量的预测位置。"""
        if self.valid != (self.position_m is not None):
            raise ValueError('有效估计必须有位置，无效估计的位置必须为空')
        if self.orientation_wxyz is not None and not np.isclose(np.linalg.norm(self.orientation_wxyz), 1, atol=1e-5):
            raise ValueError('姿态四元数必须归一化，顺序为 w,x,y,z')
        if len(self.used_measurement_ids) != len(set(self.used_measurement_ids)):
            raise ValueError('实际使用的测量 ID 不能重复')
        return self


class VisionRequest(Contract):
    """估计器仅接收观测、标定和可选历史估计。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    target_id: str
    sim_time_s: float = Field(ge=0)
    observations: list[CameraObservation]
    calibration: CalibrationContext
    prior_estimate: VisionEstimate | None = None

    @model_validator(mode='after')
    def observation_identities(self):
        """请求可携带不同观测时刻，但目标、标定身份与观测编号必须明确。"""
        cameras = {c.camera_id for c in self.calibration.cameras}
        markers = {m.marker_id for m in self.calibration.markers}
        for obs in self.observations:
            if obs.target_id != self.target_id or obs.camera_id not in cameras or obs.marker_id not in markers:
                raise ValueError('视觉观测目标或相机/标记标定身份不匹配')
            if obs.measurement_time_s > self.sim_time_s + 1e-6:
                raise ValueError('视觉观测不能来自请求参考时刻的未来')
        ids = [o.measurement_id for o in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError('视觉请求测量 ID 不能重复')
        if self.prior_estimate and (self.prior_estimate.target_id != self.target_id or self.prior_estimate.sim_time_s > self.sim_time_s):
            raise ValueError('历史估计必须属于当前目标且不能来自未来')
        return self


class FusionBatch(Contract):
    """各测量保留自己的时刻，融合器负责参考时刻的一致性。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    target_id: str
    sim_time_s: float = Field(ge=0)
    vision: VisionEstimate | None = None
    acoustic: list[AcousticRangeObservation] = Field(default_factory=list)
    communication: list[CommunicationObservation] = Field(default_factory=list)

    @model_validator(mode='after')
    def target_and_time(self):
        """不同源允许异步，但不能把其他目标或未来数据接入当前状态。"""
        observations = [*self.acoustic, *self.communication]
        for obs in observations:
            if obs.target_id != self.target_id or obs.received_sim_time_s > self.sim_time_s + 1e-6:
                raise ValueError('融合批次存在其他目标或尚未接收的测量')
        if self.vision and (self.vision.target_id != self.target_id or self.vision.sim_time_s > self.sim_time_s + 1e-6):
            raise ValueError('融合视觉估计属于其他目标或未来时刻')
        ids = [o.measurement_id for o in observations]
        if len(ids) != len(set(ids)):
            raise ValueError('融合批次测量 ID 重复')
        return self


class FusionEstimate(VisionEstimate):
    """透传不代表融合；列出实际使用的来源。"""

    fusion_status: str = 'PASSTHROUGH_NOT_FUSED'
    used_sources: list[str] = Field(default_factory=list)
    received_measurement_types: list[str] = Field(default_factory=list)


class LayoutEvaluationRequest(Contract):
    """深度网格上的几何点覆盖评价，不表示真实检测概率。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    tank: TankConfig
    cameras: list[CameraCalibration]
    depths_m: list[float] = Field(default_factory=lambda: [1.0])
    grid_size: int = Field(7, ge=2, le=30)
    optics: OpticsConfig = Field(default_factory=OpticsConfig)

    @model_validator(mode='after')
    def evaluation_domain(self):
        """评价深度在池内，防止负深度和重号相机产生虚假覆盖。"""
        if not self.depths_m or any(not 0 < depth < self.tank.depth_m for depth in self.depths_m):
            raise ValueError('评价深度须为池内正值深度')
        if len({c.camera_id for c in self.cameras}) != len(self.cameras):
            raise ValueError('布局相机 ID 不能重复')
        if any(c.position_m[2] <= 0 for c in self.cameras):
            raise ValueError('布局相机必须在平均水面上方')
        return self


class LayoutRequest(LayoutEvaluationRequest):
    """正式优化器可使用相机数量、位置和架高约束。"""

    camera_count: int | None = Field(None, gt=0)
    position_bounds_m: list[Vec3] | None = Field(None, min_length=2, max_length=2)
    height_bounds_m: Vec2 | None = None
    camera_template: CameraCalibration | None = None
    coverage_weight: float = Field(1, ge=0, description='布局覆盖目标权重，固定布局不执行优化')
    precision_weight: float = Field(0, ge=0, description='布局精度目标权重，度量及假设由正式算法声明')

    @model_validator(mode='after')
    def ordered_constraints(self):
        """仅检查约束定义；初始布局是否可行由适配器与结果校验器报告。"""
        if self.height_bounds_m and (self.height_bounds_m[0] <= 0 or self.height_bounds_m[0] > self.height_bounds_m[1]):
            raise ValueError('架高约束须为正值且下界不大于上界')
        if self.position_bounds_m and any(lo > hi for lo, hi in zip(*self.position_bounds_m)):
            raise ValueError('位置约束下界不能大于上界')
        if self.coverage_weight+self.precision_weight <= 0:
            raise ValueError('布局目标权重不能同时为零')
        return self


class PrecisionMetric(Contract):
    """正式布局模块可输出的声明性精度指标，M1 基线不伪造该数值。"""

    kind: Literal['GEOMETRIC_PROXY', 'LINEARIZED_COVARIANCE']
    value: float = Field(ge=0)
    unit: Literal['m', 'm2', 'dimensionless']
    assumptions: str = Field(min_length=1, description='噪声、线性化位置、姿态、聚合方法等假设')
    pixel_stddev_px: float | None = Field(None, gt=0)


class LayoutEvaluation(Contract):
    """水中段射线的交会角和几何点覆盖，全部属于未标定演示。"""

    schema_version: SchemaVersion = '1.0'
    single_view_coverage: float = Field(0, ge=0, le=1)
    multi_view_coverage: float = Field(0, ge=0, le=1)
    median_intersection_angle_rad: float | None = None
    invalid_point_count: int = 0
    sample_count: int = 0
    metric_kind: str = 'GEOMETRIC_POINT_COVERAGE'
    evidence_status: str = 'DEMO_UNCALIBRATED'
    precision_metric: PrecisionMetric | None = None

    @model_validator(mode='after')
    def evaluation_consistency(self):
        """覆盖率与计数须自洽，不允许双视角覆盖超过单视角覆盖。"""
        if self.multi_view_coverage > self.single_view_coverage + 1e-12:
            raise ValueError('多视角覆盖不能超过单视角覆盖')
        if not 0 <= self.invalid_point_count <= self.sample_count:
            raise ValueError('无效点数必须在总点数范围内')
        return self


class LayoutResult(Contract):
    """固定布局只回传配置，不宣称优化。"""

    schema_version: SchemaVersion = '1.0'
    coordinate_frame: WorldFrame = 'LOCAL_TANK_RH'
    algorithm_id: str = 'fixed_layout_v1'
    algorithm_version: str = '1.0.0'
    cameras: list[CameraCalibration]
    evaluation: LayoutEvaluation
    optimization_status: str = 'NOT_OPTIMIZED'
    reason: str = '固定布局仅回传配置，尚未实现 2.1 优化'


class UuvTruth(Contract):
    """仅用于生成、评价和显示的真值事件。"""

    target_id: str
    position_m: Vec3
    yaw_rad: float
    orientation_wxyz: tuple[float, float, float, float]
    speed_mps: float
    evidence_status: str = 'DEMO_UNCALIBRATED'


class EvaluationSample(Contract):
    """后端计算的独立评价样本；失败帧仍计入总样本。"""

    target_id: str
    algorithm_id: str
    valid: bool
    error_m: float | None = None
    position_error_m: Vec3 | None = None
    horizontal_error_m: float | None = None
    depth_error_m: float | None = None
    status: str
    evidence_status: str = 'DEMO_UNCALIBRATED'
    tick_index: int = Field(0, ge=0)
    filter_lag_nominal_s: float = Field(0, ge=0)


class EventEnvelope(Contract):
    """JSONL、REST 和 WebSocket 共用事件外壳。"""

    scenario_id: str
    run_id: str
    sim_time_s: float
    event_seq: int = Field(ge=0)
    event_type: str
    schema_version: SchemaVersion = '1.0'
    payload: dict


class RunMetadata(Contract):
    """运行配置、资产和软件的溯源信息。"""

    run_id: str
    scenario_id: str
    seed: int
    config_hash: str
    asset_hashes: dict[str, str]
    effective_config: dict
    software_version: str = '0.1.0'
    schema_version: SchemaVersion = '1.0'
    evidence_status: str = 'DEMO_UNCALIBRATED'
    python_executable: str = ''
    python_version: str = ''
    platform: str = ''
    mode: Mode = 'FLAT_SNELL_REFRACTION'
    algorithms: dict[str, str] = Field(default_factory=dict)
    algorithm_versions: dict[str, str] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    sampling: str = ''
    status: str = 'created'
    sim_time_s: float = 0
    metrics: dict | None = None
    failure: str | None = None


class AdapterDescriptor(Contract):
    """注册时声明能力和版本，不能把占位角色等同于实际能力。"""

    role: Literal['layout', 'vision', 'refraction', 'wave', 'acoustic', 'fusion']
    algorithm_id: str
    algorithm_version: str
    schema_version: SchemaVersion = '1.0'
    supported_schema_versions: list[str] = Field(default_factory=lambda: ['1.0'])
    capabilities: list[str] = Field(default_factory=list)
    status: str = 'BASELINE'
    evidence_status: Literal['DEMO_UNCALIBRATED'] = 'DEMO_UNCALIBRATED'
