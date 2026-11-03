# 依赖与许可证

以下版本和许可证来自本次指定 Python 环境的安装元数据与前端 `node_modules/*/package.json`，不以记忆中的版本代替实际安装情况。完整精确依赖以安装记录、前端锁文件与运行元数据为准。

Python：`D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe`，3.12.16。Node.js：20.18.0；npm：11.21.0。

| Python 直接依赖/开发工具 | 本次版本 | 元数据许可证 |
| --- | --- | --- |
| FastAPI | 0.162.0 | MIT |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| Pydantic | 2.14.2 | MIT |
| NumPy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| SciPy | 1.18.1 | BSD 许可正文及 bundled libraries 声明，详见已安装 dist-info/LICENSE* |
| PyYAML | 6.0.3 | MIT |
| websockets | 16.1.1 | BSD-3-Clause |
| pytest | 9.2.0 | MIT |
| pytest-asyncio | 1.4.1.post1 | Apache-2.0 |
| HTTPX | 0.28.1 | BSD-3-Clause |
| Ruff | 0.17.3 | MIT |

SQLite 使用 Python 标准库 `sqlite3`。项目没有另行安装 SQLite Python 包。轮子中打包的数学库等可能有附加许可文本，对外分发时需连同相应 NOTICE/LICENSE 保留。

| 前端直接依赖/开发工具 | 本次版本 | 元数据许可证 |
| --- | --- | --- |
| Vue | 3.5.44 | MIT |
| Three.js | 0.171.0 | MIT |
| ECharts | 6.1.0 | Apache-2.0 |
| Vite | 6.4.5 | MIT |
| Vitest | 4.1.12 | MIT |
| TypeScript | 5.7.3 | Apache-2.0 |
| @vitejs/plugin-vue | 5.2.4 | MIT |
| vue-tsc | 3.3.14 | MIT |
| @types/three | 0.171.0 | MIT |

建模工具使用用户已有的 Blender 5.2.3 LTS。软件本身与本项目生成的模型资产是不同许可对象；本页没有替项目作者设定新的开源许可证。

`assets/models/` 的 UUV-001 沿用原有概念资产与参考来源说明，未改写。`assets/scenes/` 中水池、外壳、支架和标签由本次脚本生成，没有下载第三方场景模型或纹理；其中完整场景引用了原有 UUV-001。原始参考图、ArUco 纹理来源及项目整体对外分发许可尚需项目负责人确认，不因依赖软件开源而自动视为已授权。
