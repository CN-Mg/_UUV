# M1 开发启动提示词

使用方式：将本文件正文作为下一次开发任务提示词。在用户明确要求启动实现时执行；本文件本身不代表系统已经实现。

---

请在 `D:\_UUV` 实现“微型 UUV 视觉定位仿真系统”的 M1 可运行 Web 垂直切片。请完成代码、中文文档、测试和本地可运行演示，不要停留在方案或空接口。先阅读根目录 `AGENTS.md`，只读检查现有 `assets/`、`docs/`、`tools/` 和 Git 状态，再开始新增文件；绝不覆盖现有 UUV-001 资产、原始要求文档和方案图，不执行现有资产重建脚本。

## 一、项目目的、分工与复杂度

这是科研软件原型。M1 证明“配置化场景 → UUV 真值 → 多相机解析角点 → 折射/波纹扰动 → 视觉位置估计 → 评价 → 实时显示 → JSONL 回放”的完整数据链路。

后续课题 2.1、2.2、2.3 由其他同学负责。本次主要交付 2.4 的显控仿真底座、可运行物理基线，以及可替换、可测试的算法接口：

- 2.1 同学接入布局评价与优化算法。
- 2.2 同学接入视觉定位、折射校正和波纹抑制算法；需要时替换误差生成模型。
- 2.3 同学接入时空对齐、误差模型和融合定位算法。

M1 采用单进程 FastAPI 后端和 Vue 前端、小型显式适配器注册表；不建设通用插件平台。默认只演示 1 艘 UUV，目标列表、事件和接口从一开始包含 `target_id`，以两目标的小型测试验证数据不会串流。复杂阵型、实际图像识别、流体动力学和正式研究算法留到后续。

固定布局输出 `NOT_OPTIMIZED`，`NoOpFusion` 输出 `PASSTHROUGH_NOT_FUSED`。它们是可运行占位实现，不代表完成 2.1 或 2.3。界面、日志、配置、运行元数据和实验材料统一显示 `DEMO_UNCALIBRATED`，不得宣称真实定位精度、真实水动力学、真实图像检测或实装控制能力。

## 二、技术栈与目录

- 后端：Python 3.12、FastAPI、Pydantic v2、NumPy、SciPy、PyYAML、SQLite、pytest、Ruff。
- 前端：Vue 3、TypeScript、Vite、Three.js、ECharts、Vitest。
- Three.js 用于局部水池场景。提供适合 VSCode 的启动、调试和停止说明。
- 后端固定使用 `D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe`，通过该解释器安装依赖、启动和检查，不另建 `.venv`；前端使用锁文件。记录实际版本与依赖许可证，不修改用户其他科研环境。

建议结构如下，允许在不改变职责边界的前提下做小幅调整：

```text
AGENTS.md
backend/
  pyproject.toml
  app/
    main.py
    contracts/          # 场景、标定、测量、估计、事件等公开模型
    adapters/           # 六类接口、M1 实现、小型注册表
    simulation/         # 运动真值、观测生成、固定步长调度
    services/           # 运行控制、测量缓冲与路由、评价
    api/                # REST、WebSocket
    storage/            # YAML、JSONL、SQLite 索引
frontend/
scenarios/
data/runs/
tests/
  backend/
  contracts/
docs/
assets/                 # 保留现有资产
tools/                  # 保留现有工具，可新增独立的启动/检查工具
```

后端是唯一仿真计算权威。前端只配置、控制、显示与回放，可进行显示坐标转换和动画插值，不重新计算定位、折射、波纹或误差指标。公开模型字段、公开函数、参数意义、关键公式、坐标转换均有中文说明。

## 三、先建立可交接的算法接口

在 `backend/app/contracts/` 定义 Pydantic v2 输入输出模型，在 `backend/app/adapters/` 定义可调用的 `Protocol` 或抽象基类。接口必须有 M1 实现、注册入口、示例、契约测试，不能只有类名或 `pass`。

### 3.1 六类适配器

| 接口与入口 | 输入内容 | 输出内容 | M1 实现 |
| --- | --- | --- | --- |
| `LayoutOptimizer.evaluate(LayoutEvaluationRequest)` | 场地、指定布局、相机标定、评价深度网格及评价假设 | `LayoutEvaluation`：单相机覆盖、至少双相机覆盖、射线夹角、无效点及指标定义 | 几何点覆盖评价 |
| `LayoutOptimizer.optimize(LayoutRequest)` | 矩形场地、相机数量/内参、位置高度约束及可选初始布局 | `LayoutResult`：相机配置列表、评价、优化状态与原因 | `FixedLayoutAdapter` 回传给定布局并标记 `NOT_OPTIMIZED` |
| `VisionLocalizer.localize(VisionRequest)` | 单目标观测批次、观测时刻、标定上下文、可选上一估计 | `VisionEstimate`：位置、可选姿态/位置协方差、质量、使用观测及状态 | 无校正、平面折射校正、校正后简单滤波 |
| `RefractionModel.project(ProjectionRequest)` | 候选三维点、相机、折射率、允许使用的界面和仿真时刻 | `ProjectionResult`：像素、光路、可见状态/失败原因 | 针孔、单界面 Snell 正向投影 |
| `RefractionModel.backproject(BackprojectionRequest)` | 像素、相机、折射率、允许使用的界面和仿真时刻 | `RayPath`：空气段、界面交点、水中段与状态 | 针孔或单界面折射反向射线 |
| `WaveSurfaceModel.sample(x_m, y_m, sim_time_s)` | 界面水平位置与仿真时刻 | `SurfaceSample`：高度、梯度、归一化向上法向量 | 平面、固定种子的少量正弦波面 |
| `AcousticRangeSource.read_until(sim_time_s)` | 已映射到仿真时钟的读取上界 | 不重复返回的 `AcousticRangeObservation` 列表 | 缓冲/JSONL 数据源，默认可为空 |
| `FusionLocalizer.reset(FusionContext)`；`update(FusionBatch)` | 锚点、外参、时间映射、误差模型等标定；视觉估计、声学距离、通信观测及参考时间 | `FusionEstimate`：位置、时间、可选位置协方差、来源、状态 | `NoOpFusion`，仅透传有效视觉估计 |

对几何点覆盖指标明确注明：它描述指定深度网格的理想视场与几何关系，不等于真实标记可检测率，也不等于标定后的真实定位精度。双相机射线夹角使用水中段，未达到双视角条件的点标为无效；避免把近乎反向或近乎平行的射线误报为良好几何。

M1 固定布局适配器要求请求或有效配置提供布局；缺少布局、数量不符或违反约束时返回明确状态，不伪造优化结果。后续 2.1 实现可以在相同接口下使用可选初始布局或自主搜索。

### 3.2 公开数据契约

至少定义并给出 JSON 示例：

- `ScenarioConfig`、`CameraCalibration`、`MarkerGeometry`、`CalibrationContext`。
- `LayoutRequest`、`LayoutEvaluationRequest`、`LayoutEvaluation`、`LayoutResult`。
- `ProjectionRequest`、`BackprojectionRequest`、`ProjectionResult`、`RayPath`、`SurfaceSample`。
- `CameraObservation`、`AcousticRangeObservation`、`CommunicationObservation`。
- `VisionRequest`、`VisionEstimate`、`FusionContext`、`FusionBatch`、`FusionEstimate`。
- `UuvTruth`、`EvaluationSample`、`EventEnvelope`、`RunMetadata`。

契约规则：

1. 统一字段名、单位、形状、坐标和时间语义。位置为 3 维 m，像素为 2 维 px，位置协方差可为空、存在时为 3×3 m²；四元数为 `[w,x,y,z]`，表示机体到世界。
2. 观测包含稳定 `measurement_id`、传感器/目标身份、`measurement_time_s`、`received_sim_time_s` 和有效状态。后两个时间均已映射到当前运行的仿真时钟；保留可选原始 `source_time_s`、`source_clock_id`、`source_frame_id`，不丢弃对齐研究需要的信息。
3. `CameraObservation` 包含相机 ID、目标 ID、标记 ID、固定角点顺序、最终观测角点和声明的像素噪声模型；标为 `ANALYTIC_IDEAL_MARKER_OBSERVATION` 和 `SYNTHETIC_KNOWN_ASSOCIATION`，并单独记录折射模式。
4. 声学观测包含锚点 ID、距离 m、可为空的方差 m²；锚点坐标、安装外参等由标定上下文提供，不把距离当作三维位置。
5. 通信观测包含消息类型、来源、时间、目标状态；若携带位置测量，提供坐标、协方差和来源测量 ID。转发视觉结果不能当独立测量重复融合。
6. 估计输出包含 `target_id`、估计参考时间、算法 ID/版本、`valid`、状态、原因、实际使用的测量 ID。无位置时填 `null`，禁止 NaN、Infinity 或以真值补位。
7. 至少区分无观测、几何不足、求解失败、有效解；预测与过期估计单独标识。未计算协方差就填 `null`。
8. 所有契约具有可追溯的版本。v1 交付后，破坏性变化需要新版本和迁移说明；相容新增字段也同步示例、前端类型与测试。
9. 后端模型是契约权威，导出 JSON Schema/OpenAPI；前端类型根据其生成或校验，避免两份互不核对的定义。

### 3.3 注册与交接方式

实现一个显式字典/工厂注册表，YAML 至少能选择：

```yaml
adapters:
  layout: fixed_layout_v1
  vision: flat_snell_baseline_v1
  refraction: snell_single_interface_v1
  wave: seeded_multisine_v1
  acoustic: buffered_ranges_v1
  fusion: noop_fusion_v1
```

每个实现记录 `algorithm_id`、`algorithm_version`、支持的契约版本和参数；配置中的不存在 ID 返回清晰错误，不静默切换为另一个算法。实验模式决定观测生成规则，与估计器选择分开；不能因为选择有波模式就自动把真实波面交给估计器。

`adapters.vision` 选择主估计器；另用 `experiments.comparison_vision_ids` 配置对照实现。同一观测批次分别调用主估计器和所选对照实现，各自持有独立状态，结果携带算法 ID。切换同学提供的主估计器不应改变原始观测或基线配置。

提供至少一个最小适配器替换示例和契约测试：新增实现、在注册表注册、修改 YAML、运行测试后即可接入。无需修改前端、API、事件外壳和回放代码。该样例明确标为接入示例，不作为科研结果。

计算类适配器不直接操作数据库、事件文件或网络。数据源适配器可读取配置指定的观测文件或外部输入，但事件和索引由运行服务统一写入。有状态算法、测量源与滤波器按运行和目标创建；`read_until` 每次只返回尚未交付的数据。重置方式和空输入行为写进文档。

`FusionBatch` 保留各测量自己的观测时刻，不要求所有测量同时发生。框架完成基础校验和坐标/时钟映射，2.3 同学可以在 `FusionLocalizer` 内部替换对齐、误差建模与状态传播方法；`FusionContext` 提供必要标定，不提供真值。融合输出明确其参考时刻。

## 四、真值隔离

真值只进入运动生成、观测生成、评价和显控通道。估计器输入必须由白名单字段构成：

- 允许：相机内外参、标记机体系几何、平均水面与折射率、当前/历史测量、上一估计、声明的运动先验。
- 不允许：真值位置/姿态/速度、完整 `ScenarioConfig`、航迹公式、生成器种子/随机相位、真实瞬时波面、包含真值事件的运行管理器或事件总线。

`CameraObservation` 不向估计器夹带未扰动理想像素、真值世界角点或仿真诊断光路；仿真诊断数据如需导出，走独立评价通道。机体系标记几何属于已知标定信息，可以使用。

初始位置与航向从观测或固定搜索初值获得，后续可用上一估计，不能用真值初始化。测试在固定观测与固定估计器状态下改变旁路真值，验证估计不变。完整场景和种子可向用户导出，但不作为估计器上下文。

M1 不要求实现真实波面已知的反演。若实现，使用独立请求和显式 `ORACLE_SURFACE_DEMO` 实验，不污染基线输入，也不能以其结果证明实际波纹抑制效果。

## 五、坐标与默认场景

采用 `LOCAL_TANK_RH`：原点在平均水面中心，x 为长轴、y 为宽轴、z 向上，平均水面 z=0，水下位置 z<0；单位 m、s、rad、px。明确正值深度到 z 的转换。

相机坐标 x 向右、y 向下、z 向前。统一 `T_world_body`、`T_camera_world` 方向；世界中的相机位置与朝向、计算外参和 Three.js 显示转换分别验证。

建立 `scenarios/demo_uncalibrated.yaml`：

- 水池：长 5 m、宽 5 m、深 2 m。
- 默认 1 艘 UUV-001，轨迹周期 60 s，`dt_s=0.1`，中心深度 1 m；可用半径 0.7 m 的水平圆轨迹，航向由切线生成。
- M1 可采用水平航行假设，估计 `x,y,z,yaw`，roll/pitch 固定为模型假设的零值；输出注明实际估计自由度，接口仍允许后续完整姿态。不能从真值读取 yaw。
- 轨迹周期与速度保持单一驱动关系：选择周期则速度由轨迹推导；选择速度则反算周期，拒绝相互矛盾的配置。
- 相机位置：`(-2,-2,1.5)`、`(2,-2,1.5)`、`(0,2.2,1.5)`，统一朝向世界点 `(0,0,-1)`；明确相机滚转的构造规则。
- 分辨率 1280×720 px，`fx=fy=900 px`，`cx=640 px`、`cy=360 px`；M1 可假设镜头畸变为零并写明。
- `n_air=1.00029`、`n_water=1.333`；固定演示种子 `20261102`。
- 波面总振幅上界默认 0.02 m，使用少量分量并在 YAML 显式给出每个分量的振幅、波长、周期和方向，随机相位只在初始化生成。
- 上述参数、适配器 ID、实验模式、噪声参数均可配置，统一标记 `DEMO_UNCALIBRATED`。

使用现有 `assets/models/uuv_001.glb`、`uuv_001_metadata.json`，保留资产 SHA-256。读取机体系、四块标记中心和轴向；以 `black_square_size_m=0.12` 重建黑色边界四角，不直接把 `corners_body_m` 的 0.16 m 白板用于定位。

显式处理 GLB 到机体系/显示世界的转换。当前资产约 2.8 m 长，轨迹合法性检查包含艇体包围范围，不只检查中心；不把概念尺寸描述为已标定微型艇尺寸。加载失败时使用简单几何体并显示失败原因。

## 六、M1 物理与定位基线

实现三种观测生成模式：

1. `IDEAL_NO_REFRACTION`：针孔理想投影。
2. `FLAT_SNELL_REFRACTION`：平均平面界面上的 Snell 折射。
3. `WAVY_SNELL_REFRACTION`：小振幅波面、实际界面交点及其局部法向量参与 Snell 光路求解。

多正弦波面采用：

```text
h(x,y,t) = Σ a_j sin(kx_j*x + ky_j*y - omega_j*t + phi_j)
n = normalize((-∂h/∂x, -∂h/∂y, 1))
Σ |a_j| = 0.02 m  # 默认总振幅上界，并非显著波高
```

2～3 个分量即可；各相机共用同一个时变波场。声明这是一种参数化运动波面，不做水动力学能力声明。对极端斜率、多解、无有效光路或数值不收敛返回明确状态，不能静默改用针孔或理想真值。

为对应任务书的参数级叠加，记录或解释：

```text
delta_flat = project_flat(P) - project_ideal(P)
delta_wave = project_wavy(P,t) - project_flat(P)
observed = ideal + delta_flat + delta_wave + optional_pixel_noise
```

偏移由传播路径产生，而不是任意经验像素偏置；界面交点必须实际求解，不能用目标正上方的法向量代替。不可见或无投影时，差分为无效值而不是强行填数。

可见性至少包含：相机前方、最终折射投影的图像边界、以水中段方向判断的标记正面。M1 可暂不实现完整网格遮挡、检测概率或真实图像，必须在限制中说明。前端增加简单二维相机观测窗，显示角点与标记编号，帮助核对投影链路。

对同一批观测运行：

- 无折射校正的针孔重投影估计。
- 已知平均平面、折射率与标定条件下的 Snell 重投影估计，标为 `MODEL_AWARE_DEMO`。
- 上述平面校正结果的一种简单时序滤波，可选指数平滑或常速度滤波；报告滤波引入的滞后。

使用有效相机和标记角点的重投影残差做 SciPy 非线性最小二乘；明确最低观测条件、病态几何检测、初值来源和失败状态。在有波模式中，基线估计器仍只知道平均平面，不能知道真实波相位。

先以无噪声验证数值链路，再运行声明像素噪声或标定偏差的轻量敏感性实验。不得把零噪声同模型反演的近零误差解释为真实定位精度。

## 七、事件、存储和时间

由整数 `tick_index` 计算 `sim_time_s=tick_index*dt_s`。墙钟只用于节奏与耗时，不驱动数学状态。暂停不推进仿真；倍速不改变步长或跳过计算。60 s、0.1 s 的起止采样规则写清楚，不重复末尾样本。

每个事件至少包含：

```text
scenario_id, run_id, sim_time_s, event_seq,
event_type, schema_version, payload
```

`event_seq` 在单次运行内严格递增，解决同一时刻多个事件的顺序。必须实现：

```text
run_status
uuv_truth
camera_observation
vision_estimate
evaluation_sample
```

接入测距/通信和 NoOp 透传时，增加 `acoustic_range`、`communication_observation`、`fusion_estimate`。空声学源无需编造观测，NoOp 事件必须明确没有融合测距。

运行目录 `data/runs/{run_id}/` 至少包含：

- `effective-scenario.yaml`：本次实际生效的配置。
- `metadata.json`：种子、配置 SHA-256、资产 SHA-256、软件/依赖版本、算法 ID/版本、证据状态。
- `events.jsonl`：按事件序号追加的运行事实，正常结束、停止和异常都有明确终止状态。
- `metrics.csv`：由已记录的评价样本导出的指标。

配置哈希基于应用默认值后的配置做规范化 JSON 序列化，不受 YAML 注释或键顺序影响；适配器 ID、参数和版本纳入可追溯记录。SQLite 只存场景和运行索引。

回放按 JSONL 的事件序号发送原事件，不重跑算法。重复运行在相同环境、配置和控制脚本下比较科学事件载荷；排除运行 UUID、墙钟及性能耗时等非科学字段，并记录比较口径。

## 八、API 与多源数据接入

实现：

```text
GET  /api/health
GET  /api/scenarios
GET  /api/scenarios/{scenario_id}
POST /api/scenarios                       # 校验并保存新场景，不覆盖原始资料
GET  /api/adapters                        # 已注册 ID、版本、角色和实现状态
POST /api/runs                           # 场景 ID 或有效配置快照
POST /api/runs/{run_id}/pause
POST /api/runs/{run_id}/resume
POST /api/runs/{run_id}/stop
POST /api/runs/{run_id}/speed
POST /api/runs/{run_id}/measurements       # 校验并接入声学/通信测量
GET  /api/runs/{run_id}/events             # 支持按 after_seq 增量读取
GET  /api/runs/{run_id}/replay             # 按事件序号提供已记录数据
GET  /api/runs/{run_id}/metrics
GET  /api/runs/{run_id}/export/{artifact}  # YAML、元数据、JSONL、CSV 的受限枚举
WS   /ws/runs/{run_id}                    # 支持按 after_seq 补齐已落盘事件
```

用一次声学和通信 JSON 测量注入测试，验证“校验 → 缓冲 → 事件 → 显示/状态 → FusionBatch”通路。M1 只承诺基于已映射仿真时间的接入，不实现设备驱动或真实设备时钟同步。

定义过期、乱序、未来时刻、未知目标/锚点和重复测量 ID 的处理规则。M1 可采用简单时间窗与有界缓冲，遇到不支持的情况明确拒绝或标为未使用，不需要复杂乱序滤波。

`NoOpFusion` 仅透传有效视觉解，列出实际使用的视觉测量来源，并注明声学/通信没有参与融合；视觉无效时返回无有效融合解。不能把真值当预测值或用声学存在这一事实宣称精度已提升。

## 九、前端演示

界面参照用户后续提供的 VSCode Light 截图：中性浅灰标题栏和侧栏、白色内容区、深色文字和蓝色选中状态，避免整体过淡。主要面板可拖动调整尺寸、最大化、关闭及从窗口菜单恢复；控件采用一致的细边框与编辑器式标签/状态栏。

实现：

- 场景参数面板：水池、相机、目标列表、轨迹/深度/周期或速度、模式、种子、波纹与噪声参数；保存和加载场景。
- 启动、暂停、继续、停止、倍速控制；非法状态有明确反馈。
- Three.js 水池、水面、相机视锥、UUV、真值与估计轨迹；标识所显示的视锥是空气侧示意还是水下折射覆盖。
- 简单二维相机角点观测窗；不把三维模型画面描述为实际检测输入。
- ECharts 显示后端发布的实时误差、有效率、失败计数和已记录统计，不在前端重算定位指标。
- 声学/通信最近观测、更新时间、有效/过期状态；NoOp 占位状态可见。
- 事件状态、历史运行选择、JSONL 回放、多目标轨迹分组和数据导出。
- 当前模式、固定种子、配置哈希、算法 ID/版本、`DEMO_UNCALIBRATED` 与资产加载状态持续可见。

前端断线重连按最后事件序号补齐并去重；若从当前运行中途加入，需要先补齐历史或读取后端状态快照，避免错误显示完整运行指标。

M1 水面可用标注为示意的平均平面显示；如显示真实仿真波形，由后端发送采样网格，前端只渲染，不另建波纹计算模型。

## 十、实验、测试与实际验收

### 10.1 轻量实验

- 理想无噪声：验证坐标、观测、估计与数值容差，容差在测试中明确说明。
- 平面折射：在相同观测上比较无校正与平面校正，报告平均误差向量及位置误差。
- 波纹：总振幅上界 0、0.01、0.02 m；有波档位至少 3 个预先固定的种子，比较平面校正与简单滤波。默认演示仍使用 `20261102`。
- 一项轻量敏感性检查，例如非零角点噪声或小幅相机外参偏差。参数标为未标定，不根据结果反复挑选“好种子”。

至少报告：三维欧氏 RMSE/MAE/P95、水平/深度误差、平均误差向量、有效定位率、失败原因计数、滤波滞后与计算耗时。方法间精度在共同有效帧比较，并单独列出各自有效率；无有效样本时指标为空并说明原因。

### 10.2 后端和契约测试

覆盖：

- 坐标转换往返、四元数顺序、显示资产轴向映射。
- 0.12 m 编码标记角点与 0.16 m 白板角点的区别。
- 针孔投影、相机前后方、正面与图像边界判断。
- Snell 正入射、互易性、折射率相等时退化为直线、无有效光路状态。
- 固定种子波面可重复、法向量正确、同一波场多相机一致。
- 真值隔离、无真值初始化、失败时不回填真值。
- 适配器输入输出序列化、单位/形状、版本和替换路由；NoOp 没有虚报测量参与。
- 两目标数据按 `target_id` 隔离，有状态实现不会跨运行残留。
- 同配置科学事件重复性、JSONL 回放顺序和停止后可读。
- REST、WebSocket 补发/去重、暂停/恢复/停止/倍速。
- 声学/通信注入、时刻校验、乱序/过期处理和未使用状态。

### 10.3 前端测试与浏览器交互

Vitest 覆盖事件解析、后端契约样例、运行控制、后端指标到图表的映射、回放顺序、去重及目标分组。构建包含 TypeScript 类型检查。

启动本地前后端，用实际浏览器验证：默认场景启动、资产状态、运行控制、轨迹/误差更新、测量状态、结束后回放和导出。记录实际交互证据；浏览器工具不可用时如实标记未执行，不能用 Vitest 或构建成功替代交互验证。

### 10.4 必须执行的命令

先验证指定的 UUV Python 3.12 环境和 Node/npm 可用性，通过该解释器安装后端，前端使用锁文件。项目提供配置，使以下命令在对应目录可运行：

```powershell
# 项目根目录；固定使用用户指定的 UUV 环境
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pytest
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m ruff check .

# frontend 目录
npm run test -- --run
npm run build
```

保留并报告命令、工作目录、解释器/工具版本、退出码、通过/失败数量及原因。静态检查覆盖新增代码；如果现有 Blender 专用脚本不纳入检查，明确配置范围和理由。不删除失败测试，不排除失败的新代码，不把未运行的检查报告为通过。

实时运行以单目标、三相机、0.1 s 步长的默认场景实测，给出测试机与单步耗时 P50/P95、实际运行速率；若未达到 1× 实时，如实标记，不能丢时步或改误差模型来伪装达标。数值重计算和网络发送应避免阻塞控制接口。

## 十一、文档、交付与完成标准

在 `docs/` 补齐：

- `architecture.md`：模块职责、数据流、真值隔离、运行生命周期。
- `algorithm-interfaces.md`：六类接口、数据模型、单位、版本、失败状态、JSON 示例及同学接入步骤。
- `event-schema.md`：事件外壳、各 payload、排序、时间语义与回放。
- `scenario-format.md`：全部参数、默认值、单位、约束、适配器选择及保存加载。
- `demo-guide.md`：安装、启动、控制、测量注入、导出、回放、停止方法及 VSCode 使用说明。
- `experiments.md`：实验配置、比较口径、实际数据与失败记录；未执行实验明确标记。
- `known-limitations.md`：未标定、解析观测/已知关联、平均波面校正、遮挡近似、固定布局、NoOpFusion、通信与设备接入边界。
- `dependencies-and-licenses.md`：实际依赖版本、许可证及资产来源/许可状态，未确认许可明确写待核实。

为三位同学提供不依赖运行 GUI 的最小联调入口和样例输入输出：

1. 2.1：给定场地、相机约束与配置，返回布局和评价；M1 固定布局状态可见。
2. 2.2：给定合成观测与标定，不读取真值，返回位置、时间、状态。
3. 2.3：给定视觉、距离、通信样例和标定，返回融合契约对象；M1 透传状态可见。

最终汇报必须列出：修改文件、已实现功能与占位模块、实际数据流、关键中文注释、算法接入位置与替换方式、依赖与许可证、实际执行命令和测试结果、浏览器交互证据、运行产物路径、已知限制及下一步最小任务。

完成标准是：默认演示能运行，事件能记录和回放，科学边界如实可见，六类接口有实现与契约测试，后续同学能够独立替换算法。不要把 M1 完成表述为整个课题或 2.1～2.3 正式研究已经完成。
