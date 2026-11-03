import { describe, expect, it } from 'vitest'
import { controlsFor, measurementDisplayStatus, metricRows, orderedEvents, parseEvent, vector3 } from './events'
import type { EventEnvelope } from './contracts'

const event = (seq: number): EventEnvelope => ({ scenario_id: 'demo_uncalibrated', run_id: 'run-a', sim_time_s: seq / 10, event_seq: seq, event_type: 'uuv_truth', schema_version: '1.0', payload: { target_id: 'UUV-001', position_m: [0, 0, -1], yaw_rad: 0 } })
describe('后端事件与回放契约', () => {
  it('读取合法事件并拒绝缺字段、非有限时间', () => {
    expect(parseEvent(event(1)).payload.position_m).toEqual([0, 0, -1])
    expect(() => parseEvent({ ...event(1), run_id: undefined })).toThrow()
    expect(() => parseEvent({ ...event(1), sim_time_s: NaN })).toThrow()
  })
  it('按事件序号排序并去重，拒绝跨运行拼接', () => {
    expect(orderedEvents([event(3), event(1), event(3), event(2)]).map(e => e.event_seq)).toEqual([1, 2, 3])
    expect(() => orderedEvents([event(1), { ...event(2), run_id: 'run-b' }])).toThrow()
  })
  it('位置仅接受三个有限数值', () => {
    expect(vector3([1, 2, -1])).toEqual([1, 2, -1])
    expect(vector3([1, 2])).toBeNull()
    expect(vector3([1, Infinity, 0])).toBeNull()
  })
})
describe('运行控制与指标投影', () => {
  it('运行、暂停和结束的控制互斥', () => {
    expect(controlsFor('running')).toEqual({ pause: true, resume: false, stop: true, edit: false })
    expect(controlsFor('PAUSED').resume).toBe(true)
    expect(controlsFor('completed').edit).toBe(true)
  })
  it('直接投影后端指标，不从轨迹计算误差', () => {
    expect(metricRows({ algorithms: { flat: { rmse_m: 0.01, mae_m: 0.008, p95_m: 0.02, valid_rate: 0.95, valid_count: 19 } } })).toEqual([
      { algorithm_id: 'flat', rmse: 0.01, mae: 0.008, p95: 0.02, validRate: 0.95, count: 19 },
    ])
    expect(metricRows({})).toEqual([])
  })
  it('精度显示共同有效帧统计，有效率保留各方法自身分母', () => {
    const result = metricRows({ algorithms: { flat: { rmse_m: .3, valid_rate: .8, valid_count: 8 } }, common_valid_metrics: { flat: { rmse_m: .1, mae_m: .08, p95_m: .2 } } })
    expect(result[0].rmse).toBe(.1)
    expect(result[0].validRate).toBe(.8)
  })
})

describe('多源观测的显示状态', () => {
  it('没有测量时显示等待，显式无效优先于过期判断', () => {
    expect(measurementDisplayStatus(null, 10).label).toBe('等待')
    expect(measurementDisplayStatus({ measurement_time_s: 1, valid: false }, 10).label).toBe('无效')
  })
  it('2 s 边界仍有效，超过 2 s 标为过期', () => {
    const sample = { measurement_time_s: 3, valid: true }
    expect(measurementDisplayStatus(sample, 5)).toEqual({ state: 'fresh', label: '有效', sampleTime_s: 3, age_s: 2 })
    expect(measurementDisplayStatus(sample, 5.001).label).toBe('过期')
  })
  it('未来采样标为待到时，不调整设备或仿真时钟', () => {
    expect(measurementDisplayStatus({ measurement_time_s: 6, valid: true }, 5)).toEqual({ state: 'future', label: '待到时', sampleTime_s: 6, age_s: -1 })
    expect(measurementDisplayStatus({ valid: true }, 5).label).toBe('时刻未知')
  })
  it('状态只随提供的仿真时间变化，暂停与回放使用同一规则', () => {
    const sample = { measurement_time_s: 2, source_time_s: 1234 }
    expect(measurementDisplayStatus(sample, 3)).toEqual(measurementDisplayStatus(sample, 3))
    expect(measurementDisplayStatus(sample, 3).age_s).toBe(1)
    expect(measurementDisplayStatus(sample, 5).label).toBe('过期')
    expect(measurementDisplayStatus(sample, 3).label).toBe('已接收')
  })
})
