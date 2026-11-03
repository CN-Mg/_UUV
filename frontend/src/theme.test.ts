import { describe, expect, it } from 'vitest'
import { traceColor, tracePalette } from './theme'

describe('轨迹来源的展示颜色', () => {
  it('算法顺序或目标身份变化时保持图例和曲线颜色一致', () => {
    expect(traceColor('truth:UUV-001')).toBe(tracePalette.truth)
    expect(traceColor('pinhole_baseline_v1|UUV-002')).toBe(tracePalette.raw)
    expect(traceColor('flat_snell_baseline_v1:UUV-001')).toBe(tracePalette.corrected)
    expect(traceColor('flat_snell_smoothed_v1|UUV-003')).toBe(tracePalette.filtered)
  })
})
