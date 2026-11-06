# 微型 UUV 与杆装相机

证据状态为 `DEMO_UNCALIBRATED`。Blender 文件包含一艘艇和一套杆装相机，三个 GLB 分别用于艇体、相机壳体和立杆。前端按现有相机外参放置壳体，并将竖直立杆从池底延伸至背部支架接点。相机局部 −Z 为光轴方向，镜头正面位于局部原点。

艇体总长 600 mm、圆柱直径 90 mm。+X 向前，+Y 向左舷，+Z 向上。GLB 导出使用 `(x,z,-y)`，前端恢复机体系后应用后端姿态。默认场景深度为 1 m，设计工作深度上限为 1.5 m。

背光贴膜采用 AprilTag36h11。艇首、艇中、艇尾上方各一个（ID 0–2），左舷两个（ID 3–4），右舷两个（ID 5–6）。70 mm 按展开后的黑边外沿解释，含白色静区的展开宽度为 87.5 mm。贴膜沿半径 45.35 mm 的圆柱弯曲，舷侧贴膜向下偏转 22° 避免与顶部标记相交。JSON 的 `corners_body_m` 记录整片贴膜角点，解析观测使用 `black_square_size_m` 和 `surface_radius_m` 重建曲面编码角点。白色单元使用自发光材质表现背光。

前端在首个真值事件到达前显示配置给出的初始位姿。首尾分段、舵面和推进组件尺寸按参考图比例建模。

艇首和艇尾各有四片舵面。前舵面的周向角从机体 +Z 量起为 ±60°、±135°，顶部空间供头部 ID 0 贴膜使用。其后是由竖直圆柱、梯形板和安装平台组成的导流块。导流块与提手之间的轴向净距为 96 mm，放置含静区宽 87.5 mm 的 ID 1 贴膜。

贴图来自 [AprilRobotics/apriltag-imgs](https://github.com/AprilRobotics/apriltag-imgs)，许可证见 [tags/LICENSE](tags/LICENSE)。当前仿真生成解析角点，默认轨迹是定深水平圆。前端支持显示四元数中的俯仰与横滚。

从项目根目录重建资产：

```powershell
& 'F:\SteamLibrary\steamapps\common\Blender\blender.exe' --background --factory-startup --python-exit-code 1 --python tools/build_micro_uuv.py
```
