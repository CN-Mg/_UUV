# 算法接口与研究员接入指南（v1）

当前代码实现六类接口和可运行基线，位置为 `backend/app/adapters/interfaces.py`；Pydantic 契约集中在 `backend/app/contracts/models.py`。全部默认数据属于 **DEMO_UNCALIBRATED**。下述固定布局和 NoOp 透传不代表完成课题 2.1、2.3。

## 共用规则

- 世界为 `LOCAL_TANK_RH`，水面中心原点，x 长轴、y 宽轴、z 向上，水下 z<0；位置 m、时间 s、角度 rad、像素 px。
- 相机坐标 x 右、y 下、z 前。`camera_rotation(camera)` 给出世界到相机旋转，反向为其转置。垂直朝下时用世界 +Y 构造相机上方向，其他情况用 +Z，避免光轴叉乘退化。
- 姿态四元数为 `[w,x,y,z]`，从机体系到世界；M1 只估计 xyz+yaw，roll/pitch=0 是明确的水平运动假设。
- 公开模型拒绝未知字段和 NaN/Infinity；位置 3 维、像素 2 维、可选位置协方差 3×3 m²。未计算协方差用 `null`。
- `measurement_time_s` 是映射后的观测时刻，`received_sim_time_s` 是映射后的接收时刻；可选 `source_time_s`、`source_clock_id`、`source_frame_id` 保留设备原始信息。M1 不实现真实设备时钟同步。
- 估计结果有 `algorithm_id`、`algorithm_version`、`target_id`、`sim_time_s`、`valid`、`status`、`reason`、`used_measurement_ids`。`valid=false` 时位置为空，不能以真值补位。
- `schema_version=1.0` 是公开请求、估计、事件的实际可校验版本，未知版本返回校验错误。位置请求/结果显式声明 `coordinate_frame=LOCAL_TANK_RH`。相容新增字段同步模型/前端/样例；破坏性字段或语义变化升级版本并提供迁移说明。
- 计算类适配器不操作数据库、事件、WebSocket 或前端；运行服务统一调度、记录与发送。每个运行有独立实例，视觉滤波按目标分开。

## 2.1：LayoutOptimizer

```python
evaluate(request: LayoutEvaluationRequest) -> LayoutEvaluation
optimize(request: LayoutRequest) -> LayoutResult
```

`LayoutEvaluationRequest` 包含 `tank`、`cameras`、`depths_m`（正值 m）、`grid_size`、`optics`。`LayoutRequest` 再增加 `camera_count`、可选 `position_bounds_m`（两端 3 维坐标）、`height_bounds_m`、可选 `camera_template` 及覆盖/精度目标权重。没有初始布局时，正式算法可使用模板和约束搜索；M1 固定布局不执行搜索。

`CameraCalibration` 为：

```json
{"camera_id":"C1","position_m":[-2,-2,1.5],"look_at_m":[0,0,-1],"width_px":1280,"height_px":720,"fx_px":900,"fy_px":900,"cx_px":640,"cy_px":360}
```

结果包含算法 ID/版本、`cameras`、`evaluation`、`optimization_status`、`reason`。当前 `fixed_layout_v1` 只回传给定布局，状态 `NOT_OPTIMIZED`；没有相机、数量不符、超出位置或架高约束为 `INVALID_LAYOUT`。共享 `validate_layout_result(request,result)` 重新检查输出数量、身份与约束；声明有效结果却违反约束会被拒绝。`INVALID_LAYOUT`、`INFEASIBLE`、`FAILED` 可返回诊断布局与原因。

精度关系通过可空 `precision_metric` 留给 2.1 研究员：`kind` 为几何代理或线性化协方差，含 `value`、`unit`、必填 `assumptions` 和可选 `pixel_stddev_px`。正式算法应声明像素噪声、姿态、采样域、线性化和聚合假设；当前基线该字段为空，射线夹角没有伪装成米级精度。目标权重在固定布局中不执行优化。

评价是深度网格上的 `GEOMETRIC_POINT_COVERAGE`：`single_view_coverage`、`multi_view_coverage`、`median_intersection_angle_rad`、`invalid_point_count`、`sample_count`。交会角使用水中段，以 `acos(abs(dot))` 消除平行/反向的伪良好交会，并在每个点取可用相机对的最佳锐角。这里没有像素噪声传播或真实检测概率，不称作真实定位精度。有限候选搜索算法只能声称候选集内最优。

## 2.2：VisionLocalizer

```python
localize(request: VisionRequest) -> VisionEstimate
```

`VisionRequest` 包含 `target_id`、`sim_time_s`、`observations`、`calibration`、可选 `prior_estimate`。`CalibrationContext` 只有相机列表、标记机体系几何、折射率、平均水面和是否使用折射；不含完整场景、真值、轨迹、波面或种子。

`CameraObservation` 的关键字段如下，完整样例见 `tests/contracts/fixtures/vision-request.json`：

| 字段 | 含义 |
| --- | --- |
| `measurement_id`、`target_id`、`camera_id`、`marker_id` | 唯一测量和已知对应关系 |
| `measurement_time_s`、`received_sim_time_s` | 观测和接收时刻 |
| `corners_px` | 最终扰动后的 4×2 像素角点 |
| `corner_order` | 贴图左下、右下、右上、左上 |
| `pixel_noise_std_px` | 声明的高斯角点噪声标准差，默认 0、未标定 |
| `observation_kind` | `ANALYTIC_IDEAL_MARKER_OBSERVATION`，表示解析角点而非检测器输出 |
| `association_kind` | `SYNTHETIC_KNOWN_ASSOCIATION`，没有验证真实多目标识别 |
| `refraction_mode` | 理想、平面或波纹观测生成模式 |

输出 `VisionEstimate` 含位置、yaw、四元数、实际估计自由度、可空位置协方差、重投影 RMSE、使用的测量 ID 和证据状态。有效解必须有位置、无效解位置必须为空；协方差须对称半正定、四元数须归一化。请求拒绝未知标定身份、其他目标的测量/先验、重复 ID 和未来先验；基线额外要求同步观测。当前三种实现为：

- `pinhole_baseline_v1`：不校正，直线重投影。
- `flat_snell_baseline_v1`：平均平面 Snell 重投影，`MODEL_AWARE_DEMO`。
- `flat_snell_smoothed_v1`：平面校正后 α=0.35 指数平滑；保留名义滞后 `filter_lag_nominal_s=(1-α)/α*dt`。它可能让平滑无噪声轨迹的误差变大，不能只展示有利结果。

M1 对同一批观测分别求解等权像素最小二乘。初值由同名标记角点的多相机射线交会和水平刚体配准得到，后续可用上一估计；不会读取真实航向。至少要求两相机，拒绝病态射线交会或重投影雅可比。状态有 `NO_OBSERVATION`、`INSUFFICIENT_GEOMETRY`、`TIME_MISMATCH`、`SOLVER_FAILED`、`SUCCESS`；当前视觉基线要求相机测量与请求参考时刻同步。理想对照模式中校正器明确使用直线模型。

## 2.2：RefractionModel、WaveSurfaceModel

```python
project(request: ProjectionRequest) -> ProjectionResult
backproject(request: BackprojectionRequest) -> RayPath
sample(x_m: float, y_m: float, sim_time_s: float) -> SurfaceSample
```

`ProjectionRequest` 是候选三维点、相机、仿真时刻和折射率；`BackprojectionRequest` 用像素替代三维点。界面实现由 `SnellRefraction(surface)` 实例持有：生成器可持有真实多正弦波面，基线估计器单独构造平均平面，二者不能共享真实瞬时波面。

`ProjectionResult.valid` 表示数学光路有效，`in_image` 另外判断图像边界；标记正面判断由观测生成器完成。`RayPath` 包含光心、界面交点和由相机朝目标的空气/水中方向。理想模式交点为空。诊断光路不会进入 `CameraObservation`。

平面模型解 `n_air*sin(theta_air)=n_water*sin(theta_water)`；波纹模型以平面解为初值求费马光程 `n_water|Q-P|+n_air|Q-C|` 在波面上的驻点，用实际交点处的梯度求法向量。反投影沿空气射线求界面交点，再用向量 Snell 进入水中。无有效光路返回状态而非改用理想点。

`SurfaceSample` 是高度、二维梯度、归一化向上法向量。`SeededMultiSineSurface` 只在初始化生成相位，后续采样为时间与位置的纯函数；1～3 分量均分振幅，`Σ|a_j|=amplitude_m`。配置明确波长、周期、传播方向，最大坡度上界限制为 0.5。`flat_surface_v1` 返回 z=0。

波纹实现只求平面初值附近的局部驻值，并在射线内部少量位置检查明显二次穿越；没有证明全局最短光程或完备发现所有多路径。它是 M1 小坡度基线，不是完整光线追踪器或真实水动力学。

## 2.3：AcousticRangeSource、FusionLocalizer

```python
read_until(sim_time_s: float) -> list[AcousticRangeObservation]
reset(context: FusionContext) -> None
update(batch: FusionBatch) -> FusionEstimate
```

测距字段：`anchor_id`、非负 `range_m`、可空正值 `variance_m2`，加上共用测量身份与时刻字段。`buffered_ranges_v1` 只返回接收时刻已到且尚未交付的测量。外部输入先由运行服务校验目标/锚点、去重并进行时间窗处理。

`CommunicationObservation` 包含 `source_id`、`message_type`、`message`，可选位置/协方差及 `derived_from_measurement_ids`。纯状态消息不提供额外定位约束，转发视觉位置不是独立的新传感器。

`FusionContext` 包含 `anchors_world_m`、`sensor_extrinsics`、`clock_offsets_s`、`clock_scales`、`alignment_tolerance_s`、`error_models`。配置保存在场景 `fusion_context`；锚点以场景顶层 `anchors_world_m` 为权威。4×4 外参须有齐次末行和右手正交旋转；时间比例须为正。误差模型为 `ObservationErrorModel`，明确分布（未知/高斯/经验）、单位、可空标准差、偏差和证据状态；早期字符串说明可读入并规范化为未知分布。

已知设备映射使用 `t_sim=clock_scale*t_source+clock_offset`。提供原始时间时必须同时提供时钟 ID，外部输入声明的映射时刻须与已知映射相符；原始坐标系需要对应已知外参。该校验没有估计未知时钟或求解真实标定。`position_m` 是已经转换到 `LOCAL_TANK_RH` 的位置，原始 `source_frame_id` 只保留来源，避免再次重复转换。样例见 `fusion-context.json`。2.3 研究员可在适配器内部研究对齐、状态传播与误差估计。

`FusionBatch` 含目标、输出参考时刻、可选视觉估计、距离列表、通信列表，各观测保留自己的时刻。融合适配器内部可研究时间对齐、状态传播和误差模型，不要求测量严格同时发生。

`FusionEstimate` 在视觉输出基础上增加 `fusion_status`、`used_sources`、`received_measurement_types`。当前 `noop_fusion_v1` 只在参考时刻一致的视觉有效时透传，`used_sources=["vision"]`，明确 `PASSTHROUGH_NOT_FUSED`；声学/通信只记“收到”，未实际使用。视觉过旧返回 `TIME_MISMATCH`，不会重新打时间戳伪装成当前预测。没有视觉解时返回空位置。

## 注册和切换

注册表在 `backend/app/adapters/registry.py`，`catalog()` 可供 `/api/adapters` 查询算法 ID、真实声明版本、支持契约版本、能力列表和占位状态。`create_adapter` 检查工厂返回实例的 Protocol、ID 与版本；不是只检查字符串存在。以下步骤适用于研究员的正式实现：

1. 新建独立算法文件，满足对应 Protocol，复用公共输入输出模型。
2. 给算法唯一 ID 和版本，用 `register_adapter` 显式注册工厂、契约版本与能力；同 ID 替换须主动声明，不无意覆盖。
3. YAML `adapters` 选择主实现；`experiments.comparison_vision_ids` 保留需要的对照。修改时记录新配置哈希。
4. 执行 `tests/contracts/` 和对应物理/API 测试，再用最小联调入口检验。无需变更事件外壳、前端或回放逻辑。

最小接入演示（只复用基线以验证调用，不代表新算法成果）：

```python
from app.adapters.registry import register_adapter
from app.adapters.vision import LeastSquaresLocalizer

register_adapter(
    'vision', 'classmate_demo_v1',
    lambda **kwargs: LeastSquaresLocalizer(algorithm_id='classmate_demo_v1', correction=True),
    algorithm_version='1.0.0', supported_schema_versions=['1.0'],
    capabilities=['analytic_marker_xyz_yaw'],
)
# 有效配置中令 adapters.vision='classmate_demo_v1'，再新建一次运行。
```

无需 GUI 的联调命令：

```powershell
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m app.adapters.contract_demo
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pytest tests/contracts
```

前一命令输出给定布局的评价、只用像素与标定的视觉估计、NoOp 透传结果。安装可编辑后端包后可从项目根目录执行。JSON 样例分别在 `tests/contracts/fixtures/`。契约测试含注册替换路由、协议可调用性、真值字段拒绝、序列化、单次测量交付与 NoOp 的来源声明。

## 三位研究员的独立 HTTP 联调

后端启动后可从 OpenAPI `/docs` 调用，或读下面样例文件组成 JSON 请求：

| 模块 | 路径 | 请求外壳与样例 |
| --- | --- | --- |
| 2.1 评价 | `POST /api/layout/evaluate` | `{algorithm_id,request:LayoutEvaluationRequest}` |
| 2.1 求解 | `POST /api/layout/optimize` | `{algorithm_id,request:LayoutRequest}`；`layout-request.json` |
| 2.2 视觉 | `POST /api/vision/localize` | `{algorithm_id,request:VisionRequest}`；`vision-request.json` |
| 2.3 融合 | `POST /api/fusion/update` | `{algorithm_id,context:FusionContext,batch:FusionBatch}`；`fusion-context.json`、`fusion-batch.json` |

单次 HTTP 联调每次新建适配器实例；需要时序状态时使用正常运行链路或 Python 连续调用同一实例。输出统一重新校验；错误目标、时刻、版本、坐标或不存在的测量来源不能进入科学事件。在正常运行中，此类视觉/融合输出记录 `ADAPTER_CONTRACT_VIOLATION` 并保留失败计数，无真值补位。各方法收到的是独立请求副本，错误插件修改自身输入不会污染对照或场景。

`AcousticRangeSource` 只必须实现 `read_until`；外部注入由引擎自己的观测缓冲承接，正式文件/设备数据源不需要偷偷增加 `push` 方法。数据源返回测量须符合契约和接收时刻。

## 后端权威水面显示与回放

每个固定步长发布一个 `water_surface` 事件，`WaterSurfaceSnapshot` 含：

```text
schema_version, surface_id='water', coordinate_frame='LOCAL_TANK_RH',
sim_time_s, rows=21, columns=21, x_bounds_m, y_bounds_m,
heights_m[rows*columns], normals_world[rows*columns][3],
model_kind, evidence_status='DEMO_UNCALIBRATED'
```

行 `row` 从 y 最小值递增，列 `column` 从 x 最小值递增，索引为 `row*columns+column`。高度和法向量均为后端数值，坐标就是水池世界坐标。前端只更新网格，不另算正弦波。网格在 JSONL 中保存，暂停时不产生后续数学步，回放读取原网格而非重新计算。

`SimulationEngine.surface` 与 Snell 观测生成器使用同一个实例；内置 `sample_grid` 只是同一波场的批量加速，逐点结果有回归测试。自定义波面仅实现 `sample` 也可生成网格。理想/平面模式发送全零高度和向上法向量；有波模式的默认多正弦实现随仿真时间变化。21×21 是显示采样，光学仍在实际交点求法向量，不使用显示网格代替折射计算。

默认 YAML 选择有波演示以直接观察动画；`ScenarioConfig()` 的代码默认仍是平面模式，便于无噪声数值对照。界面显示放大仅允许作为有明确倍数的显示效果，不改变后端波高、观测、定位或指标。

导出 `tools/export_contracts.py` 后运行 `--check` 可验证 `docs/contracts.schema.json` 与后端模型一致。契约回归还检查 JSON 样例、实际坏插件、版本拒绝、布局约束、时钟映射、协方差和同源波面。
