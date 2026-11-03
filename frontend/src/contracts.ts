/** 公开配置和事件由后端 Pydantic 模型生成，下面只定义展示层状态。 */
import type { CameraCalibration as BackendCamera } from './generated-contracts'
export type { CameraCalibration, TargetConfig, ScenarioConfig, EventEnvelope, WaterSurfaceSnapshot } from './generated-contracts'
import type { ScenarioConfig } from './generated-contracts'
export type Vector3 = BackendCamera['position_m']
export interface RunInfo {
  run_id: string; status: string; config_hash?: string; config?: ScenarioConfig
  scenario_id?: string; sim_time_s?: number; event_count?: number; speed?: number; actual_speed?: number | null
}
export interface PoseDisplay { target_id: string; position_m: Vector3; yaw_rad: number; algorithm_id?: string }
export interface ErrorPoint { time: number; error: number; algorithm: string; target: string }
export interface MetricRow { algorithm_id: string; rmse: number | null; mae: number | null; p95: number | null; validRate: number | null; count: number | null }
