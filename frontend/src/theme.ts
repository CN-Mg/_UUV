/** 轨迹来源的固定展示颜色，三维、曲线与界面图例共同使用相同语义。 */
export const tracePalette = {
  truth: '#007acc',
  raw: '#c84c67',
  corrected: '#11856c',
  filtered: '#b1760c',
} as const

/** 根据算法来源选色，避免系列顺序或目标数量变化造成图例错配。 */
export function traceColor(key: string): string {
  if (key.startsWith('truth:')) return tracePalette.truth
  if (key.includes('pinhole')) return tracePalette.raw
  if (key.includes('smooth')) return tracePalette.filtered
  return tracePalette.corrected
}
