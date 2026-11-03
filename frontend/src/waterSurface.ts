import type { WaterSurfaceSnapshot } from './contracts'

/** 验证后端水面网格，只校验尺寸、坐标和有限数值，不生成波形。 */
export function parseWaterSurface(value: unknown, eventTime?: number): WaterSurfaceSnapshot {
  if (!value || typeof value !== 'object') throw new Error('无效水面事件')
  const surface = value as WaterSurfaceSnapshot
  if (surface.schema_version !== '1.0' || surface.coordinate_frame !== 'LOCAL_TANK_RH' ||
      surface.evidence_status !== 'DEMO_UNCALIBRATED' || typeof surface.surface_id !== 'string' || !surface.surface_id ||
      typeof surface.model_kind !== 'string' || !surface.model_kind || !Number.isFinite(surface.sim_time_s) || surface.sim_time_s < 0) {
    throw new Error('水面事件版本、时间或坐标契约不匹配')
  }
  if (eventTime !== undefined && Math.abs(surface.sim_time_s - eventTime) > 1e-9) throw new Error('水面采样时刻与事件时刻不一致')
  if (!Number.isInteger(surface.rows) || !Number.isInteger(surface.columns) ||
      surface.rows < 2 || surface.columns < 2 || surface.rows > 101 || surface.columns > 101) throw new Error('水面网格尺寸不合法')
  for (const bounds of [surface.x_bounds_m, surface.y_bounds_m]) {
    if (!Array.isArray(bounds) || bounds.length !== 2 || !bounds.every(Number.isFinite) || bounds[0] >= bounds[1]) throw new Error('水面网格范围不合法')
  }
  const count = surface.rows * surface.columns
  if (!Array.isArray(surface.heights_m) || surface.heights_m.length !== count || !surface.heights_m.every(Number.isFinite)) throw new Error('水面高度数量或数值不合法')
  if (!Array.isArray(surface.normals_world) || surface.normals_world.length !== count || !surface.normals_world.every(normal =>
    Array.isArray(normal) && normal.length === 3 && normal.every(Number.isFinite) && normal[2] > 0 && Math.abs(normal.reduce((sum, n) => sum + n * n, 0) - 1) < .005)) {
    throw new Error('水面法向量数量或数值不合法')
  }
  return surface
}

/** 将行优先采样摆放到显示顶点；Z 与法向量直接复制后端数据。 */
export function surfaceGeometryData(surface: WaterSurfaceSnapshot) {
  const { rows, columns, x_bounds_m: xBounds, y_bounds_m: yBounds } = surface
  const positions = new Float32Array(rows * columns * 3)
  const normals = new Float32Array(rows * columns * 3)
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      const index = row * columns + column
      positions[index * 3] = xBounds[0] + column * (xBounds[1] - xBounds[0]) / (columns - 1)
      positions[index * 3 + 1] = yBounds[0] + row * (yBounds[1] - yBounds[0]) / (rows - 1)
      positions[index * 3 + 2] = surface.heights_m[index]
      normals.set(surface.normals_world[index], index * 3)
    }
  }
  const indices = new Uint32Array((rows - 1) * (columns - 1) * 6)
  let offset = 0
  for (let row = 0; row < rows - 1; row++) {
    for (let column = 0; column < columns - 1; column++) {
      const lowerLeft = row * columns + column
      indices.set([lowerLeft, lowerLeft + 1, lowerLeft + columns + 1, lowerLeft, lowerLeft + columns + 1, lowerLeft + columns], offset)
      offset += 6
    }
  }
  return { positions, normals, indices }
}
