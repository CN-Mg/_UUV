# 参考工程 `uuv_simulator` 评估：是否需要并入本仿真引擎

本文评估 `reference/uuv_simulator-master` 与本项目 M1 仿真引擎的关系，回答"要不要把这一套加上"。本文是只读评审记录，不代表已经实现、安装或运行参考工程中的任何组件；文中所有能力判断均来自对参考工程源码与项目现有文档的实际检查。

## 一、结论

1. **不建议作为运行依赖整体引入。** 参考工程是 ROS 1 + Gazebo 的物理级多体仿真栈，本项目的科学目标是"参数级"的水-空气折射视觉定位链路，两者核心能力几乎不重叠，引入后会破坏 `AGENTS.md` 约定的单进程后端与确定性回放。
2. **值得选择性吸收三块内容**，按优先级：
   - **P0 轨迹/阵型生成**——这是当前真实缺口（M1 只有水平圆轨迹），但应自研 NumPy 小模块，不引入 ROS 包；
   - **P1 传感器误差建模参数**——服务于课题 2.3 的声学/通信观测与融合误差模型；
   - **P2 Fossen 六自由度动力学**——可选真值增强，不是 M1/M2 的阻塞项。
3. **如确实需要更高保真真值**，采用"离线旁路"方式：在 WSL2/Ubuntu 内跑 Gazebo 生成轨迹与传感器序列，导出文件后由一个只读适配器喂给本引擎；**不进入主运行链路**，并单独标注证据来源。

## 二、评估对象

| 项目 | 事实 |
| --- | --- |
| 来源 | `github.com/uuvsimulator/uuv_simulator`，EU ECSEL SWARMs 项目衍生的科研原型 |
| 许可证 | Apache-2.0；含第三方组件清单 `3rd-party-licenses.txt` |
| 目标平台 | ROS 1 `kinetic`/`lunar`/`melodic`（Ubuntu），Gazebo 7/8/9 |
| 本快照时间 | 文件修改时间集中于 2020-06-15 |
| 规模 | 633 个文件；C++/Python 源文件 162 个，约 3.4 万行 |
| 顶层包 | `uuv_gazebo_plugins`、`uuv_gazebo_ros_plugins`、`uuv_sensor_plugins`、`uuv_control`、`uuv_descriptions`、`uuv_gazebo_worlds`、`uuv_world_plugins`、`uuv_teleop`、`uuv_assistants`、`uuv_tutorials`、元包 |
| 维护状态 | 官方支持矩阵止于 ROS 1 Melodic；Melodic 已于 2023-05-31 EOL，且矩阵未包含 Noetic/Python 3 与新版 Gazebo |

能力清单（据 `README.md` 与源码目录）：

- **动力学**：Fossen 六自由度方程、附加质量、阻尼、回复力（`HydrodynamicModel.cc`、`Dynamics.cc`、`BuoyantObject.cc`），RK4 积分。
- **推进与操纵**：螺旋桨推力模型（Yoerger 1990、Bessa 2006）、推力分配矩阵、舵/鳍升阻（`FinPlugin.cc`、`LiftDragModel.cc`）、脐带缆（`UmbilicalPlugin.cc`）。
- **环境**：一阶 Gauss-Markov 海流（`GaussMarkovProcess.cc`）、SWARMs 演示海域场景、波浪着色器（`SimpleWaves.frag`，纯渲染）。
- **传感器**：DVL、IMU、压力计、磁力计、GPS、相对位置（RPT）、化学示踪（CPC）、图像声呐、水下相机（`UnderwaterCameraROSPlugin`）。
- **控制**：推力器管理器、PID/滑模/几何跟踪/基于 casadi 的力分配、航点与轨迹跟踪。
- **轨迹生成**（Python，`uuv_trajectory_control`）：航点集、直线段、螺旋段、贝塞尔曲线、Dubins、LIPB、三次样条插值器。
- **载体模型**：`rexrov`、`eca_a9`、`lauv`、`desistek_saga` 的 URDF 与动力学参数。

**关键否定证据**：全仓库检索 `refract`/`snell`，仅命中 DAE 材质文件中的 `index_of_refraction` 属性与 `SimpleWaves.frag` 中的 Fresnel 渲染项；`UnderwaterCameraROSPlugin` 只做颜色衰减与背景色合成（`SimulateUnderwater`），**没有水-空气界面几何折射、没有波面法向与光路求解，也没有相机布局优化**。

## 三、本引擎现状（M1）与需求对照

M1 已具备：固定步长确定性事件链（`tick_index`/`dt_s`）、水平圆轨迹真值、解析角点观测、理想/平面 Snell/波纹 Snell 三种投影、三种视觉方法对照评价、NoOp 融合、JSONL 历史与回放、六类算法适配器与契约测试。

技术要求（`微型潜航器视觉定位仿真技术要求-origin.docx`）与两侧能力的对照：

| 需求条目 | 要求要点 | 参考工程 | 本引擎 | 结论 |
| --- | --- | --- | --- | --- |
| 2.1 相机布局优化 | 场地/相机数量/位置/高度约束下自动求解，输出覆盖与几何精度 | 无 | `FixedLayoutAdapter` 占位（`NOT_OPTIMIZED`） | 参考工程帮不上 |
| 2.2 水下视觉定位 | 水-空气折射校正、波纹随机误差抑制、多相机多目标解算 | **无几何折射**；波浪仅着色器 | 已有三种投影模式与对照评价 | 本引擎是更接近需求的一方 |
| 2.3 多传感器融合 | 视觉/声学测距/通信时空对齐与误差建模 | 有各传感器插件与噪声模型，但绑定 ROS 消息与 Gazebo | 已有融合契约与 NoOp 透传占位 | 可借"误差模型参数"，不必借实现 |
| 2.4 显控仿真软件 | 场地、相机、UUV 数量、**阵型、航行轨迹、深度、速度**可配置；**参数级**误差叠加；实时链路 | 物理级推进+渲染，非参数级 | 除阵型/任意轨迹外均覆盖 | **唯一实质缺口是轨迹/阵型** |

技术要求 2.4 明确写的是"采用参数级误差叠加方式（几何投影＋折射系统误差＋波纹随机误差）实现，保证仿真链路实时运行"。参考工程走的是相反的路线（物理级、渲染级、非确定性），因此它解决不了本项目的验收指标，反而会引入风险。

## 四、不建议整体引入的五条理由

1. **科学核心不重叠。** 本项目的贡献点在折射与波纹的光路误差；参考工程没有这个模型（见第二节否定证据）。把它加进来，等于为一个不提供核心能力的依赖付出全套集成成本。
2. **运行环境与项目约定冲突。** ROS 1 Melodic 已 EOL，Windows 无官方 ROS 1 支持；本项目规定单一 Python 3.12 环境、单进程 FastAPI 后端、不引入消息中间件与通用插件平台。双栈会推翻这两条约定。
3. **确定性与回放会被破坏。** 本引擎以 `tick_index`、固定 `dt_s`、种子和 `event_seq` 保证可重复；Gazebo 的物理步进、实时因子与传感器/渲染线程通常不保证跨机器、跨运行的逐步一致，`events.jsonl` 作为运行事实的语义将无法保持。
4. **实时性与验收口径不匹配。** 2.4 要求参数级链路实时运行并导出数据；Gazebo + 渲染在一台普通 Windows 工作站上难以稳定达到 1× 实时，且不是本项目要评估的对象。
5. **维护成本与收益不成比例。** 3 万余行 C++/Python、ROS 消息、URDF/xacro、Gazebo 插件 ABI，任何一处随系统升级失配都要单独排障；而 M1/M2 需要的轨迹与误差模型可以用几百行 Python 覆盖。

## 五、值得吸收的三块（含落点）

### P0 轨迹与阵型（当前真实缺口）

- 需求：2.4 要求"UUV 数量、阵型、航行轨迹、深度、速度"可配置；[known-limitations.md](known-limitations.md) 已承认 M1 只有水平圆轨迹。
- 参考：`uuv_control/uuv_trajectory_control/src/uuv_trajectory_generator/`（`waypoint_set.py`、`line_segment.py`、`helical_segment.py`、`bezier_curve.py`、`dubins_interpolator.py`、`lipb_interpolator.py`、`cs_interpolator.py`）与 `uuv_waypoints/waypoint.py` 的分段/插值组织方式。
- 建议落点：新增 `backend/app/simulation/trajectory.py`，纯 NumPy 实现直线、圆弧、螺旋与航点折线（后续可加样条），维持"周期与速度单一驱动关系"和越界检查；`ScenarioConfig` 的 `targets[]` 增加可选 `trajectory` 字段（默认仍为圆轨迹，`schema_version` 升到 1.1 并保证旧 YAML 可读）；测试覆盖速度一致性、越界、双目标不串流；前端轨迹显示直接读后端真值序列。
- 不引入 ROS 包：参考其几何组织思路即可，避免 `rospy`/`casadi` 依赖。

### P1 传感器误差建模参数（服务 2.3）

- 参考：`uuv_sensor_plugins/uuv_sensor_ros_plugins/src/` 下 `DVLROSPlugin.cc`（四波束、波束方向与噪声）、`IMUROSPlugin.cc`（白噪声+偏置）、`SubseaPressureROSPlugin.cc`（深度→压力换算）。
- 用途：为 `AcousticRangeSource` 的合成测量与 `FusionBatch` 的误差模型提供量级参考（不是直接搬运数值，参数仍需标定）。
- 注意：必须维持 `DEMO_UNCALIBRATED` 标识；未知噪声参数按未标定数据处理，不得把参考工程默认值当作已标定设备参数。

### P2 Fossen 六自由度动力学（可选，后置）

- 参考：`HydrodynamicModel.cc`（附加质量、阻尼、回复力）、`Dynamics.cc`（RK4）、`BuoyantObject.cc`（浮力）、`GaussMarkovProcess.cc`（海流）、`uuv_descriptions` 中 `eca_a9`/`rexrov` 的参数块。
- 建议落点：实现为可选"真值动力学"模块，输出仍是 `UuvTruth`，估计器接口不变；在文档中明确标为未标定参数演示，不宣称完整水动力学能力。
- 触发条件：当且仅当需要评估"机动/海流下的视觉定位退化"或"估计器对真实加速度的适应性"时再做。M1/M2 的参数级链路不需要它。

## 六、如果一定要"加上"：两种集成方式

| 方式 | 做法 | 评价 |
| --- | --- | --- |
| A. 离线旁路（推荐） | WSL2 + Ubuntu 20.04 + ROS Noetic + Gazebo 11（headless；参考工程需少量移植补丁）跑载体与场景，导出真值位姿/传感器序列为 CSV/JSONL；新增只读适配器 `ExternalTruthSource`，按实验需要喂给评价或回放 | 不破坏单进程与确定性；可复现（同一导出文件）；成本约 1～2 人日搭环境 + 0.5 人日适配器（估算） |
| B. 在线桥接（不推荐） | `rosbridge`/自定义桥接把 Gazebo 话题实时转发给 FastAPI | 引入第二运行时、非确定性、实时性无保证，与 `AGENTS.md` 约定冲突 |

无论哪种，都必须：给数据打独立证据标签（例如 `EXTERNAL_GAZEBO_REFERENCE`），写清未标定/未验证，且不替换已有的 `DEMO_UNCALIBRATED` 主链路。

## 七、许可与合规

- 参考工程主体为 Apache-2.0，允许查阅、改写与再分发，但需保留版权与 NOTICE；若翻译其公式或参数表，应在 [dependencies-and-licenses.md](dependencies-and-licenses.md) 增加条目并注明来源与版本。
- `uuv_gazebo_worlds` 的模型网格/纹理另有第三方来源（见其 `3rd-party-licenses.txt`），不要直接复制进本项目资产。
- 本项目现有资产与文档不因本评估被修改。

## 八、下一步最小任务

1. **P0**：新增 `backend/app/simulation/trajectory.py` 与配置字段扩展（直线/圆弧/螺旋/航点），补契约测试，前端场景面板加入轨迹类型选择；完成后再评估是否支持阵型模板。
2. **P1**：在 [algorithm-interfaces.md](algorithm-interfaces.md) 或独立文档中补充传感器误差参数约定，供 2.3 研究员接入使用。
3. **P2**：仅在实验需求明确时实现可选 Fossen 动力学真值源。
4. **P3**：如确需 Gazebo 对照，按第六节 A 方案做一次离线实验，并单独记录证据。

## 九、本次检查范围

- 只读检查了参考工程的 `README.md`、包目录、插件与轨迹生成器源码、许可证清单，以及本项目 [README.md](../README.md)、[architecture.md](architecture.md)、[known-limitations.md](known-limitations.md)、[scenario-format.md](scenario-format.md)、[m1-start-prompt.md](m1-start-prompt.md) 与技术要求 DOCX 正文。
- **未**安装依赖、**未**运行 ROS/Gazebo、**未**修改参考工程或本项目代码；文件数与行数来自本次目录扫描，平台与 EOL 结论来自仓库 `README.md` 的支持矩阵。
