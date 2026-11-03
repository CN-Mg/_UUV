# Blender 场景资产与前端控制

本次创建的是 `DEMO_UNCALIBRATED` 场景示意，不是相机安装结构或水动力学模型。原有 `assets/models/` 中 9 个文件在构建前后逐一比较 SHA-256，内容未变。

## 产物

| 文件 | 用途 |
| --- | --- |
| `assets/scenes/m1_tank_scene.blend` | 可编辑完整水池、相机、支架、示意视锥与 UUV 场景 |
| `assets/scenes/m1_tank_scene.glb` | Web 场景底座 |
| `assets/scenes/camera_unit.glb` | 独立相机外壳，可按任意数量实例化 |
| `assets/scenes/m1_scene_metadata.json` | 坐标、节点角色、控制方式及原始资产哈希 |
| `assets/scenes/m1_tank_preview.png` | 已实际渲染并检查的场景预览 |
| `assets/scenes/build-log.txt` | Blender 构建和渲染日志 |

使用已安装的 Blender 5.2.3 LTS。先尝试 Blender MCP 的状态和场景读取，但当时没有运行中的 Blender/9876 监听，MCP 返回连接失败；随后调用实际 Blender 可执行程序完成构建、导出和渲染。没有把失败的 MCP 调用报告为成功。

```powershell
& 'F:\SteamLibrary\steamapps\common\Blender\blender.exe' --background --python 'D:\_UUV\tools\build_m1_scene.py'
```

脚本新建 `M1_Tank_Schematic` 场景，不删除已有场景，不运行 `tools/build_uuv.py`。相机单体和完整 GLB 只导出活动场景，避免混入其他场景的启动 Cube。最终单体 GLB 为 6 个节点，完整 GLB 为 193 个节点；灯光和预览相机只保留在可编辑 BLEND 内。

## 坐标与控制节点

Blender 采用 `LOCAL_TANK_RH`：x 沿长轴、y 沿宽轴、z 向上，平均水面为 z=0，水下为负。glTF 导出为 Y-up：

```text
(x,y,z)_gltf = (x,z,-y)_tank
```

Three.js 在外层 `Group` 上执行 `rotation.x=+Math.PI/2` 恢复水池坐标。原有 UUV GLB 同样需要这一显示转换；此转换不参与后端定位计算。

- `camera_C1`、`camera_C2`、`camera_C3`：完整场景中的独立相机父节点。
- `stand_C1` 等：静态示意支架。
- `frustum_C1` 等：空气侧针孔视锥示意，不能称为折射后的实际覆盖。
- `uuv_demo`、`trajectory_schematic`：静态示意目标和轨迹，实时界面应隐藏并用后端事件替代。
- `tank_stage`：水池、池底网格与边框。
- `water_surface`：透明平均平面，只作显示，不承担波纹或折射计算。

前端可以隐藏元数据 `frontend_hide_roots` 列出的节点，保留水池底座，再用 `camera_unit.glb` 和原有 UUV GLB 构建动态对象。

相机单体的原生局部轴为右 +X、上 +Y、光轴 -Z，与 `THREE.Camera` 约定一致。单体内部先做 glTF 到 Blender 轴的逆变换，再由外层节点设置世界位置和相机朝向。可用 `THREE.PerspectiveCamera`、`camera.up.set(0,0,1)` 和 `lookAt` 生成显示四元数。

## 前端编辑的计算语义

编辑相机 x/y/z 或朝向时先预览显示；停止当前运行并以新配置启动后，后端以新的相机外参生成观测与估计，形成新的配置哈希和运行目录。运行中的配置快照不被偷偷改写。单纯移动模型而没有提交后端，不能报告为改变了定位计算。

相机外壳、支架与透明水池均为自行创建的概念示意几何，不是设备尺寸标定。原始 UUV 资产来源说明沿用 `assets/models/README.md`；对外分发前仍需核实其参考素材许可。
