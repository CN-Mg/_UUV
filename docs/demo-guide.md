# 本地演示与联调

本演示为 `DEMO_UNCALIBRATED`。初次使用先启动后端、前端，再在界面启动运行。默认 60 s 场景的数学时间由固定步长推进，运行节奏可能因计算耗时降低。

## 环境

用户指定并已用于依赖安装的解释器：

```text
D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe
```

不需要另建虚拟环境。重新安装后端依赖时，在项目根目录执行：

```powershell
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pip install -e './backend[dev]'
```

前端使用 Node.js 20.18.0 和 npm，安装依赖使用 `frontend/package-lock.json`：

```powershell
Set-Location D:\_UUV\frontend
npm ci
```

## 启动与停止

默认后端端口 8010、前端端口 5180，保留已有项目的 8000/5173 服务。本次不停止其他项目服务；端口占用时明确失败，不自动漂移到另一个端口。

分别在两个终端执行：

```powershell
# 后端，根目录
powershell -ExecutionPolicy Bypass -File D:\_UUV\tools\start_backend.ps1

# 前端，另一个终端
powershell -ExecutionPolicy Bypass -File D:\_UUV\tools\start_frontend.ps1
```

对应的直接命令：

```powershell
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m uvicorn app.main:app --app-dir D:\_UUV\backend --host 127.0.0.1 --port 8010

Set-Location D:\_UUV\frontend
npm run dev -- --port 5180 --strictPort
```

访问 `http://127.0.0.1:5180`。后端健康检查 `http://127.0.0.1:8010/api/health` 会返回实际 Python 路径；交互式接口文档在 `/docs`。结束服务在各终端按 Ctrl+C。VSCode 选择上述解释器，并使用两个集成终端执行即可。

## 基础链路操作

1. 加载默认场景，查看模式、种子和未标定标识，确认 UUV 与场景资产加载状态。
2. 启动运行，观察真值、视觉估计轨迹、误差与事件持续更新。
3. 测试暂停、继续、倍速和停止；倍速不改变数学步长。暂停请求后允许正在计算的一个步完成。
4. 修改相机位置或朝向，先预览，再停止旧运行并创建新运行；核对新配置哈希和误差变化。只修改显示而未启动新配置，不算改变后端相机。
5. 选择历史运行回放，按事件序号查看已记录轨迹；导出有效 YAML、元数据、JSONL 和 CSV。

前端中的水面与视锥是显示示意；折射和定位由后端计算。固定布局和 NoOpFusion 状态明确可见，不把占位模块报告为研究算法。

## 测量联调

运行中可向 `POST /api/runs/{run_id}/measurements` 发送：

```json
{
  "event_type": "acoustic_range",
  "payload": {
    "measurement_id": "manual-range-001",
    "target_id": "UUV-001",
    "anchor_id": "A1",
    "range_m": 2.0,
    "variance_m2": 0.01,
    "measurement_time_s": 0.0,
    "received_sim_time_s": 0.0,
    "valid": true
  }
}
```

应使用实际运行当前时刻和已配置锚点。服务将接收时刻改为当前仿真时间，拒绝重复测量、未知目标、超出缓冲时间窗等输入；具体校验以 API 返回为准。M1 的 NoOpFusion 接收数据但不对其融合计权。设备时钟同步与真实硬件驱动尚未实现。

`GET /api/runs/{id}/events?after_seq=0` 返回原事件；`/replay` 为同一事实序列；`/metrics` 返回后端统计。导出路径为 `/export/scenario.yaml`、`metadata.json`、`events.jsonl`、`metrics.csv`。

## 检查

```powershell
# 根目录，指定解释器
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pytest
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m ruff check .

# frontend 目录
npm run test -- --run
npm run build
```

这些是可复现命令，不是本页对测试通过的声明；实际执行结果、浏览器交互证据和实验产物见交付记录与 `experiments.md`。已有 Blender 专用资产生成脚本的静态检查范围以根目录 Ruff 配置为准。
