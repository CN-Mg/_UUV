# M1 架构

M1 是 `DEMO_UNCALIBRATED` 参数级视觉定位科研原型。它闭合仿真、估计与评价的数据链路，不提供设备控制，也不把估计反馈用于航行控制。

## 模块与数据流

```text
YAML → ScenarioConfig → RunManager/RunState（配置快照、固定步长、独立线程）
  → 运动真值 → 解析角点生成 → 折射/波纹光路 → CameraObservation
  → VisionRequest（白名单标定与观测）→ 主估计器与对照估计器
  → VisionEstimate → NoOpFusion → FusionEstimate
  → 真值旁路评价 → EvaluationSample
  → JSONL → WebSocket/REST → Vue/Three.js/ECharts
```

`backend/app/contracts/` 是公共数据模型；`adapters/` 是六类可替换算法；`simulation/` 负责真值、观测和确定性计算；`services/runtime.py` 负责运行控制、事件落盘、测量缓冲与索引；`main.py` 提供 API。前端只负责配置、显示、控制与读取后端评价。

## 运行与存储

整数 `tick_index` 计算 `sim_time_s=tick_index*dt_s`，采样 `tick=0..ceil(duration/dt)-1`，不重复终点。墙钟只控制显示节奏和性能计时；计算不足时实际运行速度降低，不丢步。

每个运行持有独立引擎、目标状态、事件序号、锁和测量缓冲。计算放在工作线程，不在 HTTP/WS 事件循环中执行 NLS。暂停影响后续数学步；已经在计算的一步可以完成并落盘。结束状态包括 `completed`、`stopped`、`failed`。异常原因保存在元数据与状态事件中。

`events.jsonl` 是运行事实；SQLite 的 `runs`、`scenarios` 表只保存索引。每个 `data/runs/{run_id}/` 保存有效 YAML、元数据、事件与评价 CSV。回放读取原事件，不重新执行估计器。服务重启后的历史运行可以回放，但不能恢复原线程。

## 真值隔离与科学边界

`ScenarioConfig` 只交给运行调度和生成器。估计器只接收 `CalibrationContext`、最终观测与历史估计，不接收完整场景、轨迹、生成器种子、真实波相位或世界真值角点。真值事件供界面与独立评价使用。

固定布局标为 `NOT_OPTIMIZED`；NoOp 透传标为 `PASSTHROUGH_NOT_FUSED`；已知平均平面的校正标为 `MODEL_AWARE_DEMO`。实际研究算法通过显式注册表和配置接入，接口见 `algorithm-interfaces.md`。

## Blender 与交互

`assets/scenes/` 提供完整示意与独立相机模型。前端修改场景草稿中的相机位置，重新启动后端运行时生成新的配置快照和哈希；正在运行的计算不随显示模型拖动而变化。轴转换、模型节点和导出方式见 `blender-scene.md`。
