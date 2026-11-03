# 微型 UUV 视觉定位仿真 · M1

`DEMO_UNCALIBRATED` 科研软件原型：配置场景 → UUV 真值 → 解析相机角点与折射/波纹 → 视觉估计 → 误差评价 → 实时显示 → JSONL 回放。这里的链路闭合不代表航行控制闭环或已标定设备精度。

使用指定环境 `D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe`，不创建其他 Python 环境。前端使用 Vue、Three.js 与 ECharts；后端为 FastAPI、NumPy 与 SciPy。

```powershell
# 根目录安装后端
& 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe' -m pip install -e './backend[dev]'

# 在两个终端启动
powershell -ExecutionPolicy Bypass -File D:\_UUV\tools\start_backend.ps1
powershell -ExecutionPolicy Bypass -File D:\_UUV\tools\start_frontend.ps1
```

前端依赖首次安装请在 `frontend/` 执行 `npm ci`。访问 `http://127.0.0.1:5180`；后端健康检查在 `http://127.0.0.1:8010/api/health`，API 文档在 `/docs`。UUV 使用独立的 8010/5180 端口，保留现有其他项目的服务；端口占用时明确失败。

修改相机位置可预览模型；停止并以新配置启动后，后端才采用新位置计算，并产生新的配置哈希。运行产物保存在 `data/runs/{run_id}/`，包含 YAML、元数据、JSONL 与 CSV。

Blender 完整示意文件为 `assets/scenes/m1_tank_scene.blend`，前端使用 GLB 与独立 `camera_unit.glb`。原有 `assets/models/` 文件保持不变。

详细内容见：

- [演示指南](docs/demo-guide.md)
- [架构与数据流](docs/architecture.md)
- [算法接入契约](docs/algorithm-interfaces.md)
- [场景配置](docs/scenario-format.md)
- [事件与回放](docs/event-schema.md)
- [Blender 模型与控制](docs/blender-scene.md)
- [实验记录](docs/experiments.md)
- [限制](docs/known-limitations.md)
- [依赖与许可证](docs/dependencies-and-licenses.md)

M1 的布局模块为固定配置，融合模块为 NoOp 透传；2.1～2.3 正式算法由后续研究员通过适配器接入。自动测试和实际交互结果以交付记录为准，不从构建成功推定科学实验已完成。
