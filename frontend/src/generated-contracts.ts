// 自动生成：frontend/tools/generate_contracts.py；请修改后端模型后重新生成。
// 这是 model_dump 后有效配置/响应的类型，含已补齐的默认值；不是宽松输入类型。

/** 显式注册表中的算法 ID；不接受任意 Python 路径。 */
export type AdapterSelection = { layout: string; vision: string; refraction: string; wave: string; acoustic: string; fusion: string }

/** 相机坐标 x 右、y 下、z 前；相机朝向用世界目标点定义。 */
export type CameraCalibration = { camera_id: string; position_m: [number, number, number]; look_at_m: [number, number, number]; width_px: number; height_px: number; fx_px: number; fy_px: number; cx_px: number; cy_px: number }

/** JSONL、REST 和 WebSocket 共用事件外壳。 */
export type EventEnvelope = { scenario_id: string; run_id: string; sim_time_s: number; event_seq: number; event_type: string; schema_version: "1.0"; payload: Record<string, unknown> }

/** 对同一观测批次运行的独立对照估计器。 */
export type ExperimentConfig = { comparison_vision_ids: Array<string> }

/** 融合标定；已知时钟映射为 t_sim=scale*t_source+offset，不估计设备时钟。 */
export type FusionContext = { schema_version: "1.0"; coordinate_frame: "LOCAL_TANK_RH"; anchors_world_m: Record<string, [number, number, number]>; sensor_extrinsics: Record<string, Array<Array<number>>>; clock_offsets_s: Record<string, number>; clock_scales: Record<string, number>; error_models: Record<string, ObservationErrorModel>; alignment_tolerance_s: number }

/** 研究员可配置的观测误差声明；UNSPECIFIED 不冒充已知高斯模型。 */
export type ObservationErrorModel = { distribution: "UNSPECIFIED" | "GAUSSIAN" | "EMPIRICAL"; unit: "m" | "px" | "s" | "m/s" | "dimensionless"; stddev: number | null; bias: number; description: string; evidence_status: "DEMO_UNCALIBRATED" }

/** 单一水空气界面的折射率。 */
export type OpticsConfig = { n_air: number; n_water: number }

/** 完整场景只传给调度/生成器，不能传给估计器。 */
export type ScenarioConfig = { schema_version: "1.0"; scenario_id: string; name: string; evidence_status: "DEMO_UNCALIBRATED"; coordinate_frame: "LOCAL_TANK_RH"; mode: "IDEAL_NO_REFRACTION" | "FLAT_SNELL_REFRACTION" | "WAVY_SNELL_REFRACTION"; seed: number; dt_s: number; duration_s: number; tank: TankConfig; cameras: Array<CameraCalibration>; targets: Array<TargetConfig>; optics: OpticsConfig; wave: WaveConfig; pixel_noise_std_px: number; adapters: AdapterSelection; experiments: ExperimentConfig; anchors_world_m: Record<string, [number, number, number]>; fusion_context: FusionContext }

/** 矩形水池尺寸，深度是正值。 */
export type TankConfig = { length_m: number; width_m: number; depth_m: number }

/** 水平圆轨迹，仅用于生成运动真值。 */
export type TargetConfig = { target_id: string; radius_m: number; depth_m: number; period_s: number; phase_rad: number; center_xy_m: [number, number] }

/** 后端权威的水面显示网格，与光学使用同一波场实例，不传给估计器。 */
export type WaterSurfaceSnapshot = { schema_version: "1.0"; surface_id: "water"; coordinate_frame: "LOCAL_TANK_RH"; sim_time_s: number; rows: number; columns: number; x_bounds_m: [number, number]; y_bounds_m: [number, number]; heights_m: Array<number>; normals_world: Array<[number, number, number]>; model_kind: string; evidence_status: "DEMO_UNCALIBRATED" }

/** 运动波面；振幅总和是波高绝对值上界，并非显著波高。 */
export type WaveConfig = { amplitude_m: number; wavelengths_m: Array<number>; periods_s: Array<number>; directions_rad: Array<number> }
