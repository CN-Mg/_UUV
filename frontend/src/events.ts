import type { EventEnvelope, MetricRow, Vector3 } from './contracts'

/** 校验事件外壳，不在前端推导任何定位或物理量。 */
export function parseEvent(value: unknown): EventEnvelope {
  if (!value || typeof value !== 'object') throw new Error('无效事件对象')
  const event = value as EventEnvelope
  if (typeof event.run_id !== 'string' || typeof event.scenario_id !== 'string' ||
      typeof event.event_type !== 'string' || typeof event.schema_version !== 'string' || !event.schema_version.startsWith('1.') ||
      !Number.isInteger(event.event_seq) || event.event_seq < 0 || !Number.isFinite(event.sim_time_s) || event.sim_time_s < 0 ||
      !event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload)) throw new Error('事件契约不匹配')
  return event
}

/** JSONL 回放以事件序号排序、去重；同一批数据必须来自同一个运行。 */
export function orderedEvents(values: unknown[]): EventEnvelope[] {
  const result = values.map(parseEvent)
  if (new Set(result.map(e => e.run_id)).size > 1) throw new Error('不可混合回放不同运行')
  return [...new Map(result.map(e => [e.event_seq, e])).values()].sort((a, b) => a.event_seq - b.event_seq)
}

/** 三维位置仅验证形状与有限数值，不进行估计。 */
export function vector3(value: unknown): Vector3 | null {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value as Vector3 : null
}

/** 控制按钮状态机，后端仍对每次请求执行最终校验。 */
export function controlsFor(status: string) {
  const state = status.toLowerCase()
  return { pause: state === 'running', resume: state === 'paused', stop: ['running', 'paused', 'created'].includes(state), edit: !['running', 'paused', 'created'].includes(state) }
}

/** 仅按已映射的仿真采样时刻显示龄期，不做设备时钟同步或融合质量判断。 */
export function measurementDisplayStatus(sample: Record<string, unknown> | null, simTime: number) {
  if (!sample) return { state: 'waiting', label: '等待', sampleTime_s: null, age_s: null }
  const sampleTime = numberAt(sample, ['measurement_time_s'])
  const age = sampleTime !== null && Number.isFinite(simTime) ? simTime - sampleTime : null
  const timing = { sampleTime_s: sampleTime, age_s: age }
  if (sample.valid === false) return { state: 'invalid', label: '无效', ...timing }
  if (age === null || (sampleTime !== null && sampleTime < 0)) return { state: 'unknown', label: '时刻未知', ...timing }
  if (age < 0) return { state: 'future', label: '待到时', ...timing }
  if (age > 2) return { state: 'stale', label: '过期', ...timing }
  return { state: 'fresh', label: sample.valid === true ? '有效' : '已接收', ...timing }
}

function numberAt(object: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) if (typeof object[key] === 'number' && Number.isFinite(object[key])) return object[key] as number
  return null
}

/** 将后端统计值映射到展示列；没有数据时保持空值。 */
export function metricRows(raw: Record<string, unknown>): MetricRow[] {
  const source = (raw.algorithms ?? raw.by_algorithm ?? raw.methods ?? raw) as Record<string, unknown>
  const items = Array.isArray(source) ? source.map((v, i) => [String(i), v] as const) : Object.entries(source)
  return items.flatMap(([key, value]) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return []
    const row = value as Record<string, unknown>
    const common = raw.common_valid_metrics as Record<string, Record<string, unknown>> | undefined
    const accuracy = common?.[key] ?? row
    const rmse = numberAt(accuracy, ['rmse_m', 'position_rmse_m', 'rmse'])
    const count = numberAt(row, ['valid_count', 'count', 'samples', 'n_valid'])
    if (rmse === null && count === null && !('valid_rate' in row) && !('valid_fraction' in row)) return []
    return [{ algorithm_id: String(row.algorithm_id ?? key), rmse, mae: numberAt(accuracy, ['mae_m', 'mae']),
      p95: numberAt(accuracy, ['p95_m', 'p95']), validRate: numberAt(row, ['valid_rate', 'valid_fraction', 'success_rate']), count }]
  })
}
