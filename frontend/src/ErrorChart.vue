<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ErrorPoint } from './contracts'
import { traceColor } from './theme'
echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
const props = defineProps<{ points: ErrorPoint[] }>()
const host = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined, resize: ResizeObserver, timer: ReturnType<typeof setTimeout> | undefined
function paint() {
  timer = undefined
  const keys = [...new Set(props.points.map(p => `${p.algorithm}|${p.target}`))]
  chart?.setOption({
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#ffffff', borderColor: '#c4d3e1', textStyle: { color: '#33485c' }, valueFormatter: (v: unknown) => typeof v === 'number' ? v.toFixed(4) : String(v) },
    grid: { top: 22, left: 54, right: 18, bottom: 32 },
    xAxis: { type: 'value', name: 's', nameGap: 5, axisLine: { lineStyle: { color: '#aabfce' } }, splitLine: { lineStyle: { color: '#e8eff5' } }, axisLabel: { color: '#657e92' } },
    yAxis: { type: 'value', name: '误差 / m', nameTextStyle: { color: '#657e92', padding: [0, 0, 0, 14] }, axisLabel: { color: '#657e92', formatter: (value: number) => value.toPrecision(2) }, splitLine: { lineStyle: { color: '#e0e9f1', type: 'dashed' } } },
    series: keys.map(key => ({ name: key.replace('|', ' · '), type: 'line', showSymbol: false, itemStyle: { color: traceColor(key) }, lineStyle: { width: 1.8, color: traceColor(key) }, data: props.points.filter(p => `${p.algorithm}|${p.target}` === key).map(p => [p.time, p.error]) })),
  }, true)
}
onMounted(() => { if (!host.value) return; chart = echarts.init(host.value); resize = new ResizeObserver(() => chart?.resize()); resize.observe(host.value); paint() })
watch(() => props.points.length, () => { if (!timer) timer = setTimeout(paint, 200) })
watch(() => props.points, () => { if (!timer) timer = setTimeout(paint, 50) })
onBeforeUnmount(() => { if (timer) clearTimeout(timer); resize?.disconnect(); chart?.dispose() })
</script>
<template><div ref="host" class="error-chart" aria-label="后端发布的实时定位误差曲线"></div></template>
