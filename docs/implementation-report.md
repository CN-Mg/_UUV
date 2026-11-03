# M1 实现与验收记录

日期：2026-11-02，Asia/Singapore。证据状态：`DEMO_UNCALIBRATED`。

## 可运行入口

- 前端：`http://127.0.0.1:5180`，VSCode 风格浅蓝白界面。
- 后端：`http://127.0.0.1:8010`，接口说明位于 `/docs`。
- 后端解释器固定为 `D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe`，已安装依赖及本项目可编辑包。
- 启动脚本：`tools/start_backend.ps1`、`tools/start_frontend.ps1`，详见 `demo-guide.md`。
- 8000、5173 被既有防空仿真项目占用；未停止或修改该项目服务。UUV 使用独立固定端口，前端严格检查端口，不自动漂移。

## 修改文件与模块

完整新增/修改清单见 `implementation-manifest.json`。主要位置如下。

| 位置 | 内容 |
| --- | --- |
| `AGENTS.md`、`docs/m1-start-prompt.md` | 固定 UUV 环境、接口交接、科学边界和浅蓝白控件要求 |
| `backend/app/contracts/` | 场景、标定、测量、估计、事件、元数据的 Pydantic 契约 |
| `backend/app/adapters/` | 六类真实 Protocol、显式注册表、针孔/Snell/波面/定位基线、布局评价与 NoOp |
| `backend/app/simulation/engine.py` | 固定步长运动生成、观测生成、估计、真值旁路评价 |
| `backend/app/services/runtime.py`、`main.py` | 运行线程、REST、WS、JSONL、SQLite 索引、测量接入与产物导出 |
| `frontend/` | Vue 控件、Three.js 模型与相机拖动、ECharts、回放、导出和派生契约类型 |
| `scenarios/demo_uncalibrated.yaml` | 默认 5×5×2 m、三相机、单艇、60 s 配置 |
| `assets/scenes/`、`tools/build_m1_scene.py` | Blender 新建完整示意场景、独立相机模型、预览和坐标元数据 |
| `tests/`、`pytest.ini`、`ruff.toml` | 物理、协议、REST/WS、时间、隔离、回放与测量接入验收 |
| `tools/run_experiments.py`、`data/experiments/` | 事先固定的九项轻量机制实验与保留的失败/不改善结果 |
| `tools/export_contracts.py`、`docs/contracts.schema.json` | 公开 JSON Schema 导出，前端另有派生类型生成器 |
| `backend/requirements-lock.txt`、`frontend/package-lock.json` | 实际安装依赖锁定 |

没有覆盖原始技术要求、方案图、`tools/build_uuv.py` 或 UUV-001 原有资产；九个原资产 SHA-256 在建模前后均未变化。

## 实际数据流与接入方式

```text
有效 YAML → 不可变运行快照 → 整数 tick / 固定 dt
  → UUV 真值 → 0.12 m 标记角点 → 针孔/平面 Snell/波纹 Snell
  → 最终像素观测 → 白名单标定与观测输入 → xyz+yaw 位置姿态基线
  → 真值旁路评价 → 事件落盘 JSONL → WS → 三维/误差显示
                                      └→ 原事件回放 / CSV / 元数据导出
声学/通信 JSON → 校验/缓冲/接收记录 → FusionBatch → NoOpFusion 视觉透传
```

- 2.1 使用 `LayoutOptimizer`；当前固定布局为 `NOT_OPTIMIZED`。
- 2.2 使用 `VisionLocalizer`、`RefractionModel`、`WaveSurfaceModel`。
- 2.3 使用 `AcousticRangeSource`、`FusionLocalizer` 和时间/坐标/误差上下文；当前 `PASSTHROUGH_NOT_FUSED`。
- 新同学通过新增实现、注册、修改 YAML、运行契约测试接入，不修改显控/事件外壳。接口、样例和无 GUI 联调见 `algorithm-interfaces.md`。

## 中文注释与关键约定

- `geometry.py` 明确机体/世界/相机旋转、0.12 m 编码边界和 Snell 平面交点公式。
- `wave.py`、`refraction.py` 明确波面梯度、法向量、折射率、费马驻点和无光路状态。
- `vision.py` 明确观测初始化、重投影残差、四自由度假设和固定系数平滑滞后。
- `runtime.py` 明确固定数学时间、墙钟节奏、事件落盘顺序和运行隔离；算法不接收整个场景、真值或真实瞬时波面。
- 前端 GLB 包装层说明 Y-up 到 Z-up 映射，前端只渲染与控制，不计算定位或科学评价。

## 实际执行命令与结果

下述 Python 命令均通过指定的 UUV 解释器执行，未创建其他虚拟环境。

```powershell
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pip install -e './backend[dev]'
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pip check
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pytest
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m ruff check .
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' tools/export_contracts.py
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' frontend/tools/generate_contracts.py --check
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m app.adapters.contract_demo
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' tools/run_experiments.py

# frontend 目录
npm install
npm run test -- --run
npm run build
```

| 检查 | 实际结果 |
| --- | --- |
| Python 环境 | Python 3.12.16，指定 UUV 路径 |
| 依赖一致性 | `pip check` 无依赖冲突 |
| 后端 pytest | 28 项通过；有一条 Starlette TestClient 关于 HTTPX 的弃用提示 |
| Ruff | 全部通过；旧 Blender 脚本范围外，所有新增 Python 脚本参与检查 |
| 前端 Vitest | 3 文件、10 项通过 |
| 前端生产构建 | TypeScript 检查与 Vite 构建通过；有单包大于 500 kB 提示，未调高阈值隐藏 |
| 契约生成/核对 | 通过；公开类型从后端模型派生 |
| 无 GUI 算法联调 | 实际输出布局、视觉与 NoOp 契约对象 |
| Blender | 5.2.3 后台实际建模、导出、渲染成功；MCP 无运行实例的连接失败已单列记录 |

初次 Ruff 出现的导入排序与闲置导入已修正，未删除测试或排除新增失败代码。许可证、实际版本与资产许可边界见 `dependencies-and-licenses.md`。

## 科学实验与运行证据

- 浏览器启动的默认运行 `9853b9f0-3cb7-4ca9-b7b8-b0d2cbc18dce` 正常完成：600 时刻、8316 事件，完整 JSONL 留在 `data/runs/`。
- 该运行单步计算 P50 约 50.42 ms、P95 约 65.11 ms，当前规模低于 100 ms 计算预算。计时不等于任意规模都能实时。
- 改位运行 `d361ef37-ff71-44cf-a843-76aa159f17e6` 已由浏览器把 C1 改为 `(-1.7,-2,1.8)`；后端配置和哈希确认改变。暂停期间数学时间保持 44.6 s，之后以 0.5× 继续并完成。
- 浏览器注入声学和通信后，JSONL 同时保留接收记录与交付事件；NoOp 实际仍只使用视觉来源。交互记录见 `output/playwright/interaction-report.json`。
- 浅蓝白页面中实际读取并播放默认运行，回放滑块到达 `8316 / 8316`；浏览器最终控制台 0 错误、0 警告，截图见 `output/playwright/m1-light-final.png`。回放没有重新计算定位。
- 浏览器的停止点击尝试发生在对应运行已完成后，按钮按规则禁用，没有成功触发停止；停止/非法恢复已由后端 REST 集成测试验证。一次复合自动化命令因 Windows 引号传递失败，后改用逐项 UI 操作完成其余检查，原工具记录保留。
- 九项预设轻量实验全部完成，原始计划、结果与每次运行均保留。六个有波片段中简单平滑均未改善总 RMSE，不能据此宣称波纹抑制成功。
- 数值、共同有效帧口径、有效率、名义滞后和不改善结果详见 `experiments.md`。无噪声同模型近零误差只证明数值一致性。

## 已知边界与下一步最小任务

- 解析角点与已知目标关联，没有真实图像检测、完整遮挡、实际设备驱动或设备时钟同步。
- 波面求解是平面初值附近的局部驻点，不是完备的全局多路径光学求解；完整航行姿态与水动力学不在本基线内。
- 固定布局、NoOpFusion 仍是占位。2.1、2.2、2.3 的正式算法与独立标定由对应同学继续。
- 下一步最小任务：三位同学分别复制接口样例，先提交一个能通过契约测试的最小实现；2.2 优先针对已保留的波纹/滞后结果建立可检验的改进方法，不以当前同模型近零误差充当实际精度。
