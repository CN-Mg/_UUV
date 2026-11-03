import { describe, expect, it } from 'vitest'
import type { WaterSurfaceSnapshot } from './contracts'
import { orderedEvents } from './events'
import { parseWaterSurface, surfaceGeometryData } from './waterSurface'

const snapshot = (): WaterSurfaceSnapshot => ({
  schema_version: '1.0', coordinate_frame: 'LOCAL_TANK_RH', evidence_status: 'DEMO_UNCALIBRATED', surface_id: 'water',
  model_kind: 'seeded_multisine_v1', sim_time_s: .1, rows: 2, columns: 3,
  x_bounds_m: [-2, 2], y_bounds_m: [-1, 1], heights_m: [.01, .02, -.01, -.02, 0, .01],
  normals_world: Array.from({ length: 6 }, () => [0, 0, 1]),
})

describe('后端水面显示契约', () => {
  it('按行优先的 y、x 顺序摆放后端高度，法向量直接复制', () => {
    const surface = parseWaterSurface(snapshot())
    const data = surfaceGeometryData(surface)
    expect(Array.from(data.positions.slice(0, 6))).toEqual([-2, -1, Math.fround(.01), 0, -1, Math.fround(.02)])
    expect(Array.from(data.positions.slice(9, 12))).toEqual([-2, 1, Math.fround(-.02)])
    expect(Array.from(data.normals.slice(0, 3))).toEqual([0, 0, 1])
    expect(data.indices.length).toBe(12)
    expect(snapshot().heights_m).toEqual(surface.heights_m)
  })
  it('平面模式保持后端全零高度，不添加客户端波纹', () => {
    const surface = snapshot(); surface.model_kind = 'flat_surface_v1'; surface.heights_m.fill(0)
    const data = surfaceGeometryData(parseWaterSurface(surface))
    expect(Array.from(data.positions).filter((_, index) => index % 3 === 2)).toEqual([0, 0, 0, 0, 0, 0])
  })
  it('拒绝错版、错误坐标、尺寸和行优先数量不符', () => {
    expect(() => parseWaterSurface({ ...snapshot(), schema_version: '2.0' })).toThrow()
    expect(() => parseWaterSurface(snapshot(), .2)).toThrow()
    expect(() => parseWaterSurface({ ...snapshot(), coordinate_frame: 'Y_UP' })).toThrow()
    expect(() => parseWaterSurface({ ...snapshot(), rows: 2.5 })).toThrow()
    expect(() => parseWaterSurface({ ...snapshot(), heights_m: [0] })).toThrow()
    expect(() => parseWaterSurface({ ...snapshot(), x_bounds_m: [2, -2] })).toThrow()
  })
  it('拒绝非有限高度与无效法向量，不用随机动画补位', () => {
    const bad = snapshot(); bad.heights_m[2] = NaN
    expect(() => parseWaterSurface(bad)).toThrow()
    const badNormal = snapshot(); badNormal.normals_world[1] = [0, 0, 0]
    expect(() => parseWaterSurface(badNormal)).toThrow()
  })
  it('回放相同事件得到相同高度；没有新事件时数据保持不变', () => {
    const first = snapshot(), second = snapshot(); second.sim_time_s = .2; second.heights_m[0] = -.01
    const envelope = (sequence: number, payload: WaterSurfaceSnapshot) => ({ scenario_id: 'demo', run_id: 'run-a', event_seq: sequence, sim_time_s: payload.sim_time_s, schema_version: '1.0', event_type: 'water_surface', payload })
    const events = orderedEvents([envelope(2, second), envelope(1, first)])
    const replayed = events.map(event => parseWaterSurface(event.payload))
    expect(Array.from(surfaceGeometryData(replayed[1]).positions)).toEqual(Array.from(surfaceGeometryData(second).positions))
    expect(replayed[0].heights_m[0]).toBe(.01)
  })
})
