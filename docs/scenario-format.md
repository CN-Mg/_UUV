# 场景配置

默认场景为 `scenarios/demo_uncalibrated.yaml`，由 Pydantic v2 校验。完整生效配置在启动时保存到运行目录，规范化 JSON 的 SHA-256 与 YAML 注释、键顺序无关。所有默认值均为 `DEMO_UNCALIBRATED`。

| 字段 | 单位与含义 | 默认 |
| --- | --- | --- |
| `scenario_id`、`name` | 场景标识和显示名称 | `demo_uncalibrated` |
| `schema_version` | 配置契约版本 | `1.0` |
| `coordinate_frame` | 水面中心、Z 向上 | `LOCAL_TANK_RH` |
| `mode` | 观测生成模式 | `FLAT_SNELL_REFRACTION` |
| `seed` | 生成器随机种子 | `20261102` |
| `dt_s`、`duration_s` | 固定步长与运行时长，s | 0.1、60 |
| `tank.length_m/width_m/depth_m` | 长、宽、正值水深，m | 5、5、2 |
| `cameras[]` | 相机列表 | 三台 |
| `targets[]` | 目标及圆轨迹参数 | 一艘 UUV-001 |
| `optics.n_air/n_water` | 折射率 | 1.00029、1.333 |
| `wave.amplitude_m` | 分量振幅绝对值之和上界，m | 0.02 |
| `wave.wavelengths_m/periods_s/directions_rad` | 各分量波长、周期、方向 | `[1.5,2]`、`[1,1.2]`、`[0,1.2]` |
| `pixel_noise_std_px` | 可选独立角点像素噪声标准差，px | 0 |
| `adapters` | 六类已注册实现 ID | 见默认 YAML |
| `experiments.comparison_vision_ids` | 独立状态的对照估计器 | 针孔、平面校正后平滑 |

相机字段：`camera_id`、`position_m=[x,y,z]`、`look_at_m`、`width_px/height_px`、`fx_px/fy_px/cx_px/cy_px`。默认位置为 `[-2,-2,1.5]`、`[2,-2,1.5]`、`[0,2.2,1.5]`，朝向 `[0,0,-1]`；默认分辨率 1280×720、焦距 900 px、主点 `[640,360]`。计算坐标为右、下、前，镜头畸变在 M1 中假设为零。

目标字段：`target_id`、`radius_m`、`depth_m`、`period_s`、`phase_rad`、`center_xy_m`。当前轨迹为水平圆，半径默认 0.7 m，中心正值深度 1 m、周期 60 s。航向沿切线，速度由半径和周期推导；M1 尚不支持任意轨迹或完整阵型编辑。

`IDEAL_NO_REFRACTION`、`FLAT_SNELL_REFRACTION`、`WAVY_SNELL_REFRACTION` 切换的是观测生成。主估计器与对照实现另行配置；有波观测不向估计器提供真实瞬时波面。

ID 必须唯一；相机不能与朝向点重合，光心高于波面上界；艇体包围范围不能越过池壁、波面或池底。波面仅支持 1～3 个参数列表长度一致、正波长/周期且坡度受限的分量。校验失败返回原因，不静默修正为其他配置。

`POST /api/scenarios` 保存独立 YAML；同名场景自动产生新后缀，不覆盖已有场景。运行时修改草稿不会修改已启动快照；要让相机位置进入计算，应停止旧运行、修改配置，再创建新运行。
