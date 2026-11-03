# UUV-001 初版

参考用户图片制作的概念外形，非实测复刻。模型单位为米，机身直径 0.36 m，总长约 2.8 m。

- `uuv_001.blend`：可编辑模型及摄影棚预览场景。
- `uuv_001.glb`：仅机器人，内嵌材质与标记贴图，供仿真导入。
- `uuv_001_preview.png`：渲染预览。
- `uuv_001_metadata.json`：坐标系、标记中心、方向和板面角点。
- `textures/`：ArUco DICT_4X4_50，ID 0–3，原图已通过 OpenCV 解码验证。

机体系：X 向前，Y 向左舷，Z 向上，原点为主圆柱中点。标记安装于右舷、左舷、上方、下方，分别 ID 0、1、2、3。板面边长 0.16 m，其中黑色编码方块边长 0.12 m；OpenCV 位姿估计的 markerLength 应填 0.12，不能填 0.16。JSON 角点是整块白板角点，非黑色编码边界。u、v 是贴图向右和向上的机体系方向。

机身标记适用于外部相机观测机器人；机器人自身导航还需另建环境地标。相机内参、畸变、相机外参、动力学、质量/惯量、浮力、阻力和推进器推力尚未标定，也尚未验证完整导航闭环。

重建：
```powershell
& 'F:\SteamLibrary\steamapps\common\Blender\blender.exe' --background --python D:\_UUV\tools\build_uuv.py
```

MCP 安装依据：https://github.com/ahujasid/mcp-for-blender
Codex 全局已添加 blender stdio 服务；Steam Blender 5.2 用户插件已启用。重启 Codex 加载新工具，打开 Blender 保持运行，插件默认自动监听 localhost:9876。
