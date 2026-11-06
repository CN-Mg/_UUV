<script setup lang="ts">
import { nextTick, computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import SceneView from './SceneView.vue'
import DockPanel from './DockPanel.vue'
import ErrorChart from './ErrorChart.vue'
import { api, post } from './api'
import { controlsFor, measurementDisplayStatus, metricRows, orderedEvents, parseEvent, vector3 } from './events'
import type { CameraCalibration, ErrorPoint, EventEnvelope, PoseDisplay, RunInfo, ScenarioConfig, Vector3, WaterSurfaceSnapshot } from './contracts'
import { parseWaterSurface } from './waterSurface'

const config = ref<ScenarioConfig | null>(null)
const scenarios = ref<{ scenario_id: string; name: string }[]>([])
type AdapterRole = keyof ScenarioConfig['adapters']
interface AdapterDescriptor { role: AdapterRole; algorithm_id: string; algorithm_version: string; schema_version: string; status: string }
const adapterRoles: AdapterRole[] = ['layout', 'vision', 'refraction', 'wave', 'acoustic', 'fusion']
const adapterLabels: Record<AdapterRole, string> = { layout: '布局 · 2.1', vision: '视觉定位 · 2.2', refraction: '折射模型 · 2.2', wave: '波面模型 · 2.2', acoustic: '测距数据 · 2.3', fusion: '融合定位 · 2.3' }
const adapterCatalog = ref<AdapterDescriptor[]>([])
const selectedScenario = ref('demo_uncalibrated')
const selectedCamera = ref('C1')
const run = ref<RunInfo | null>(null)
const status = ref('idle'), connected = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const simTime = ref(0), seq = ref(0), speed = ref(1), configHash = ref('尚未创建运行')
const actualSpeed = ref<number | null>(null)
const metrics = ref<Record<string, unknown>>({})
const rows = computed(() => metricRows(metrics.value))
const assets = reactive<Record<string, string>>({ 'UUV-001': '加载中', 'Blender 场景': '加载中', 'Blender 相机': '加载中' })
const poses = reactive<Record<string, PoseDisplay>>({})
const trails = reactive<Record<string, Vector3[]>>({})
const errors = ref<ErrorPoint[]>([])
const recentEvents = ref<EventEnvelope[]>([])
const waterSurface = shallowRef<WaterSurfaceSnapshot | null>(null)
const showWater = ref(true), waterExaggeration = ref(1)
const lastObservation = ref<Record<string, unknown> | null>(null)
const lastRange = ref<Record<string, unknown> | null>(null), lastCommunication = ref<Record<string, unknown> | null>(null)
const rangeStatus = computed(() => measurementDisplayStatus(lastRange.value, simTime.value))
const communicationStatus = computed(() => measurementDisplayStatus(lastCommunication.value, simTime.value))
const savedRuns = ref<RunInfo[]>([]), replayRun = ref(''), replayMode = ref(false), replayPlaying = ref(false), replayCursor = ref(0), replayLength = ref(0)
const sceneView = ref<InstanceType<typeof SceneView>>()
const selectedPayload = ref<EventEnvelope | null>(null)
const controls = computed(() => controlsFor(status.value))
const editable = computed(() => controls.value.edit && !replayMode.value && !busy.value)
const camera = computed(() => config.value?.cameras.find(c => c.camera_id === selectedCamera.value))
const progress = computed(() => config.value ? Math.min(100, simTime.value / config.value.duration_s * 100) : 0)
const currentPose = computed(() => Object.values(poses).find(p => !p.algorithm_id))
const latestCorrected = computed(() => rows.value.find(r => r.algorithm_id.includes('flat') && !r.algorithm_id.includes('smooth')) ?? rows.value[0])
const statusLabels: Record<string, string> = { idle: '待启动', created: '初始化', running: '运行中', paused: '已暂停', stopped: '已停止', completed: '已完成', failed: '运行失败', replay: '日志回放' }
const modeLabels: Record<string, string> = { IDEAL_NO_REFRACTION: '理想针孔', FLAT_SNELL_REFRACTION: '平面 Snell', WAVY_SNELL_REFRACTION: '波纹 Snell' }
let socket: WebSocket | undefined, reconnect: ReturnType<typeof setTimeout> | undefined, refreshTimer: ReturnType<typeof setInterval> | undefined, replayTimer: ReturnType<typeof setInterval> | undefined
let replayData: EventEnvelope[] = [], replaySummary: Record<string, unknown> = {}, disposed = false
let eventTimer: ReturnType<typeof setTimeout> | undefined
const pendingEvents: string[] = []

/** 清空展示状态，不生成替代事件，也不改变后端运行。 */
function clearDisplay() {
  for (const key of Object.keys(poses)) delete poses[key]
  for (const key of Object.keys(trails)) delete trails[key]
  simTime.value = 0; seq.value = 0; errors.value = []; recentEvents.value = []; metrics.value = {}
  lastObservation.value = null; lastRange.value = null; lastCommunication.value = null
  waterSurface.value = null
  actualSpeed.value = null
  selectedPayload.value = null
}

/** 接收后端事实事件，前端只将其映射为绘图状态。 */
function consume(value: unknown, replay = false) {
  const event = parseEvent(value)
  if (!replay && event.event_seq <= seq.value) return
  seq.value = event.event_seq; simTime.value = event.sim_time_s
  const payload = event.payload
  if (event.event_type === 'water_surface') waterSurface.value = parseWaterSurface(payload, event.sim_time_s)
  if (event.event_type === 'run_status' && !replay) status.value = String(payload.status ?? status.value)
  if (event.event_type === 'uuv_truth' || event.event_type === 'vision_estimate') {
    const point = vector3(payload.position_m)
    const target = String(payload.target_id ?? 'UUV-001')
    const algorithm = event.event_type === 'vision_estimate' ? String(payload.algorithm_id ?? 'vision') : ''
    const key = algorithm ? `${algorithm}:${target}` : `truth:${target}`
    if (point && payload.valid !== false) {
      poses[key] = { target_id: target, position_m: point, yaw_rad: Number(payload.yaw_rad ?? 0), ...(algorithm ? { algorithm_id: algorithm } : {}) }
      const q = payload.orientation_wxyz
      if (!algorithm && Array.isArray(q) && q.length === 4 && q.every(x => typeof x === 'number' && Number.isFinite(x))) {
        poses[key].orientation_wxyz = [q[0], q[1], q[2], q[3]]
      }
      ;(trails[key] ??= []).push(point)
      if (trails[key].length > 1500) trails[key].shift()
    } else if (event.event_type === 'vision_estimate') delete poses[key]
  }
  if (event.event_type === 'evaluation_sample') {
    const errorValue = payload.error_m ?? payload.position_error_m
    if (typeof errorValue === 'number' && Number.isFinite(errorValue)) {
      errors.value.push({ time: event.sim_time_s, error: errorValue, algorithm: String(payload.algorithm_id), target: String(payload.target_id) })
      if (errors.value.length > 6000) errors.value.splice(0, errors.value.length - 6000)
    }
    if (payload.metrics && typeof payload.metrics === 'object') metrics.value = payload.metrics as Record<string, unknown>
  }
  if (event.event_type === 'camera_observation') lastObservation.value = payload
  if (event.event_type === 'acoustic_range') lastRange.value = payload
  if (event.event_type === 'communication_observation') lastCommunication.value = payload
  recentEvents.value.unshift(event)
  if (recentEvents.value.length > 70) recentEvents.value.pop()
}

function closeSocket() {
  if (reconnect) clearTimeout(reconnect)
  if (socket) { socket.onclose = null; socket.close(); socket = undefined }
  clearTimeout(eventTimer)
  eventTimer = undefined
  pendingEvents.length = 0
  connected.value = false
}

/** 合并同一显示帧内的 Vue 更新，仍按原序消费每条事件。 */
function flushEvents() {
  eventTimer = undefined
  for (const raw of pendingEvents.splice(0, 512)) {
    try { consume(JSON.parse(raw)) } catch (e) { error.value = String(e) }
  }
  if (pendingEvents.length) eventTimer = setTimeout(flushEvents, 16)
}

/** 断线后按最后已接收序号重连，由后端补齐 JSONL 事件。 */
function connectEvents(id: string) {
  closeSocket()
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${protocol}://${location.host}/ws/runs/${id}?after_seq=${seq.value}`)
  socket.onopen = () => { connected.value = true }
  socket.onmessage = message => {
    pendingEvents.push(message.data)
    if (!eventTimer) eventTimer = setTimeout(flushEvents, 16)
  }
  socket.onclose = () => {
    connected.value = false
    if (!disposed && !replayMode.value && run.value?.run_id === id && ['running', 'paused', 'created'].includes(status.value)) reconnect = setTimeout(() => connectEvents(id), 1200)
  }
  socket.onerror = () => { connected.value = false }
}

async function action(fn: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) { error.value = e instanceof Error ? e.message : String(e) } finally { busy.value = false }
}

async function loadScenario() {
  await action(async () => {
    config.value = await api<ScenarioConfig>(`/scenarios/${selectedScenario.value}`)
    selectedCamera.value = config.value.cameras[0]?.camera_id ?? ''
    replayMode.value = false; stopReplay(); clearDisplay(); run.value = null; status.value = 'idle'; configHash.value = '尚未创建运行'
  })
}

async function start() {
  await action(async () => {
    if (!config.value) return
    closeSocket(); stopReplay(); replayMode.value = false; clearDisplay()
    const result = await post<RunInfo>('/runs', { config: config.value, speed: speed.value })
    run.value = result; status.value = result.status; configHash.value = result.config_hash ?? ''
    if (result.config) config.value = result.config
    connectEvents(result.run_id)
    void refreshRuns().catch(() => { /* 运行已启动，历史列表可手动刷新。 */ })
  })
}

async function control(command: string) {
  if (!run.value || busy.value) return
  await action(async () => {
    if (!run.value) return
    const runId = run.value.run_id
    const result = await post<RunInfo>(`/runs/${runId}/${command}`, command === 'speed' ? { speed: Number(speed.value) } : {})
    run.value = result
    if (command === 'speed') return
    if (connected.value) {
      // HTTP 确认先于 WebSocket 队列到达；收到控制事件水位前保持忙碌，状态以 run_status 为准。
      if (!Number.isInteger(result.event_count)) throw new Error('控制已提交，但响应缺少事件水位，尚未确认显示同步。')
      const watermark = result.event_count as number
      const deadline = Date.now() + 5000
      while (seq.value < watermark) {
        if (disposed || run.value?.run_id !== runId) throw new Error('控制已提交，但当前显示运行已切换。')
        if (Date.now() >= deadline) throw new Error('控制已提交，但事件流在 5 秒内未同步到控制事件；请等待重连，勿将当前画面视为已暂停。')
        await new Promise(resolve => setTimeout(resolve, 20))
      }
      await nextTick()
    } else if (result.status) status.value = result.status
  })
}

async function changeSpeed() {
  if (!run.value || replayMode.value || !controls.value.stop) return
  await control('speed')
  speed.value = run.value.speed ?? 1
}

async function saveScenario() {
  await action(async () => {
    if (!config.value) return
    const result = await post<ScenarioConfig>('/scenarios', JSON.parse(JSON.stringify(config.value)))
    config.value = result; selectedScenario.value = result.scenario_id
    scenarios.value = await api('/scenarios'); notice.value = '场景已保存，可再次加载或启动。'
  })
}

function moveCamera(value: { camera_id: string; position_m: Vector3 }) {
  if (!editable.value) return
  const target = config.value?.cameras.find(c => c.camera_id === value.camera_id)
  if (target) target.position_m = value.position_m
}

function addCamera() {
  if (!config.value) return
  const ids = new Set(config.value.cameras.map(c => c.camera_id))
  let index = 1; while (ids.has(`C${index}`)) index++
  const next: CameraCalibration = { camera_id: `C${index}`, position_m: [0, -2, 1.5], look_at_m: [0, 0, -1], width_px: 1280, height_px: 720, fx_px: 900, fy_px: 900, cx_px: 640, cy_px: 360 }
  config.value.cameras.push(next); selectedCamera.value = next.camera_id
}

function addTarget() {
  if (!config.value || config.value.targets.length >= 8) return
  const ids = new Set(config.value.targets.map(t => t.target_id))
  let index = 1; while (ids.has(`UUV-${String(index).padStart(3, '0')}`)) index++
  config.value.targets.push({ target_id: `UUV-${String(index).padStart(3, '0')}`, radius_m: .7, depth_m: 1, period_s: 60, phase_rad: config.value.targets.length * Math.PI, center_xy_m: [0, 0] })
}

async function refreshRuns() { savedRuns.value = await api<RunInfo[]>('/runs') }

/** 历史回放只读取事件文件，并使用运行快照显示当时的相机布局。 */
async function loadReplay() {
  await action(async () => {
    if (!replayRun.value) return
    closeSocket(); stopReplay()
    const snapshot = await api<RunInfo>(`/runs/${replayRun.value}`)
    if (snapshot.config) config.value = snapshot.config
    configHash.value = snapshot.config_hash ?? ''; run.value = snapshot
    replayData = orderedEvents(await api<unknown[]>(`/runs/${replayRun.value}/replay`))
    replaySummary = await api(`/runs/${replayRun.value}/metrics`)
    replayMode.value = true; status.value = 'replay'; replayLength.value = replayData.length; replayCursor.value = 0; clearDisplay()
    metrics.value = replaySummary
    notice.value = `已读取 ${replayData.length} 条原始事件，回放不会重新计算定位。`
  })
}

function stopReplay() { if (replayTimer) clearInterval(replayTimer); replayTimer = undefined; replayPlaying.value = false }
function seekReplay(index: number) {
  clearDisplay()
  const count = Math.min(index, replayData.length)
  for (let i = 0; i < count; i++) consume(replayData[i], true)
  replayCursor.value = count
  metrics.value = replaySummary
}

function exitReplay() {
  stopReplay(); replayMode.value = false; run.value = null; status.value = 'idle'; configHash.value = '尚未创建运行'; clearDisplay()
}
function toggleReplay() {
  if (replayPlaying.value) { stopReplay(); return }
  if (replayCursor.value >= replayData.length) seekReplay(0)
  replayPlaying.value = true
  replayTimer = setInterval(() => {
    const limit = Math.min(replayData.length, replayCursor.value + Math.max(1, Math.ceil(15 * speed.value)))
    while (replayCursor.value < limit) consume(replayData[replayCursor.value++], true)
    if (replayCursor.value >= replayData.length) stopReplay()
  }, 50)
}

async function injectDemoRange() {
  await action(async () => {
    if (!run.value || !config.value) return
    const result = await post<Record<string, unknown>>(`/runs/${run.value.run_id}/measurements`, {
      event_type: 'acoustic_range', measurement_id: `manual-range-${Date.now()}`, target_id: config.value.targets[0].target_id,
      anchor_id: 'A1', range_m: 2, variance_m2: .01, measurement_time_s: simTime.value,
      received_sim_time_s: simTime.value, valid: true,
    })
    notice.value = `测距接入已提交（演示输入 2 m，非真值生成；NoOp 未融合）：${JSON.stringify(result).slice(0, 160)}`
  })
}

async function injectDemoCommunication() {
  await action(async () => {
    if (!run.value || !config.value) return
    await post(`/runs/${run.value.run_id}/measurements`, { event_type: 'communication_observation', payload: {
      measurement_id: `manual-radio-${Date.now()}`, target_id: config.value.targets[0].target_id,
      source_id: 'radio1', message_type: 'STATUS', message: '前端通信接口联调样例',
      measurement_time_s: simTime.value, received_sim_time_s: simTime.value,
    } })
    notice.value = '通信状态样例已接入；没有增加独立定位测量。'
  })
}

function format(value: number | null | undefined, digits = 4) { return value == null ? '—' : value.toFixed(digits) }
function sampleAgeText(age: number | null) { return age === null ? '—' : age < 0 ? `未来 ${(-age).toFixed(1)} s` : `${age.toFixed(1)} s` }
function shortAlgorithm(id: string) { return id.includes('smooth') ? '平面校正＋滤波' : id.includes('pinhole') ? '无折射校正' : id.includes('flat') ? '平面 Snell 校正' : id }
function selectedAdapter(role: AdapterRole) { return adapterCatalog.value.find(item => item.role === role && item.algorithm_id === config.value?.adapters[role]) }
const observationCorners = computed(() => {
  const observation = lastObservation.value
  if (!observation) return []
  const direct = observation.corners_px
  if (Array.isArray(direct)) return direct as number[][]
  const markers = observation.markers
  if (Array.isArray(markers)) return markers.flatMap(m => (m as Record<string, unknown>).corners_px as number[][] ?? [])
  return []
})

onMounted(async () => {
  await action(async () => {
    scenarios.value = await api('/scenarios')
    selectedScenario.value = scenarios.value[0]?.scenario_id ?? 'demo_uncalibrated'
    config.value = await api(`/scenarios/${selectedScenario.value}`)
    selectedCamera.value = config.value?.cameras[0]?.camera_id ?? 'C1'
    await refreshRuns()
    adapterCatalog.value = await api<AdapterDescriptor[]>('/adapters')
  })
  refreshTimer = setInterval(async () => {
    const id = run.value?.run_id
    if (!id || replayMode.value) return
    try {
      const [summary, snapshot] = await Promise.all([
        api<Record<string, unknown>>(`/runs/${id}/metrics`), api<RunInfo>(`/runs/${id}`),
      ])
      if (run.value?.run_id !== id || replayMode.value) return
      metrics.value = summary
      actualSpeed.value = snapshot.actual_speed ?? null
      // 连接正常时不让 HTTP 轮询越过尚未显示的已记录事件。
      if (snapshot.status && (!connected.value || (snapshot.event_count ?? Infinity) <= seq.value)) status.value = snapshot.status
    } catch { /* 连接状态由 WebSocket 展示，避免暂时断线覆盖其他操作错误。 */ }
  }, 750)
})
onBeforeUnmount(() => { disposed = true; closeSocket(); stopReplay(); if (refreshTimer) clearInterval(refreshTimer) })

// 修改空闲场景时清除旧运行的波面快照；未收到新事件时只显示平均平面。
watch(() => config.value ? JSON.stringify([config.value.mode, config.value.tank, config.value.wave]) : '', () => {
  if (editable.value) waterSurface.value = null
})

const panelTitles: Record<string, string> = { config: '场景配置', scene: '三维场景', chart: '定位误差', replay: '运行记录与回放', summary: '实时评价', position: '目标真值', sensor: '多源接入', assets: '资产与运行信息', events: '事件监视' }
const closedPanels = reactive<Record<string, boolean>>({})
const leftWidth = ref(300), rightWidth = ref(310)
let cancelColumnDrag: (() => void) | undefined
try { const saved = JSON.parse(localStorage.getItem('uuv.workspace') || '{}'); for (const id of Object.keys(panelTitles)) closedPanels[id] = saved.closed?.[id] === true; leftWidth.value = Math.max(220, Math.min(520, Number(saved.left) || 300)); rightWidth.value = Math.max(240, Math.min(520, Number(saved.right) || 310)) } catch { /* 损坏的布局记录不影响运行。 */ }
const rightVisible = computed(() => ['summary','position','sensor','assets'].some(id => !closedPanels[id]))
const workspaceColumns = computed(() => `${closedPanels.config ? 0 : leftWidth.value}px ${closedPanels.config ? 0 : 6}px minmax(360px,1fr) ${rightVisible.value ? 6 : 0}px ${rightVisible.value ? rightWidth.value : 0}px`)
function saveLayout() { try { localStorage.setItem('uuv.workspace', JSON.stringify({closed:closedPanels,left:leftWidth.value,right:rightWidth.value})) } catch { /* 仅影响布局记忆。 */ } }
function closePanel(id: string) { closedPanels[id] = true; saveLayout() }
async function openPanel(id: string) { closedPanels[id] = false; saveLayout(); await nextTick(); document.getElementById(`panel-${id}`)?.scrollIntoView({block:'nearest'}) }
function resetLayout() { for (const id of Object.keys(panelTitles)) { closedPanels[id] = false; try { localStorage.removeItem(`uuv.panel.${id}.height`) } catch { /* 可继续使用默认尺寸。 */ } }; leftWidth.value=300;rightWidth.value=310;saveLayout();window.dispatchEvent(new Event('uuv-reset-layout')) }
/** 分隔条只改变显示列宽，不触碰冻结的仿真配置。 */
function resizeColumn(event: PointerEvent, side: 'left'|'right') {
 event.preventDefault(); cancelColumnDrag?.(); const start=event.clientX, initial=side==='left'?leftWidth.value:rightWidth.value
 const move=(e:PointerEvent)=>{ const width=initial+(e.clientX-start)*(side==='left'?1:-1); if(side==='left')leftWidth.value=Math.max(220,Math.min(520,width));else rightWidth.value=Math.max(240,Math.min(520,width)) }
 const end=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);document.body.classList.remove('resizing-columns');saveLayout()}
 cancelColumnDrag=end;document.body.classList.add('resizing-columns');window.addEventListener('pointermove',move);window.addEventListener('pointerup',end,{once:true});window.addEventListener('pointercancel',end,{once:true})
}
onBeforeUnmount(()=>cancelColumnDrag?.())

</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand-mark">U<span>∿</span>V</div>
      <div class="brand-copy"><div class="eyebrow">UNDERWATER VISION LAB</div><h1>微型 UUV 视觉定位仿真实验台 <span>M1</span></h1></div>
      <div class="header-right"><details class="window-menu"><summary>窗口 ▾</summary><div class="window-options"><label v-for="(title,id) in panelTitles" :key="id"><input type="checkbox" :checked="!closedPanels[id]" @change="closedPanels[id] ? openPanel(String(id)) : closePanel(String(id))">{{ title }}</label><button @click="resetLayout">恢复默认布局</button></div></details><span class="evidence-badge">DEMO_UNCALIBRATED</span><span class="connection"><i :class="{ online: connected }"></i>{{ connected ? '事件流已连接' : run ? '事件流未连接' : '本地科研原型' }}</span></div>
    </header>

    <div v-if="error" class="banner error" role="alert"><b>操作未完成</b><span>{{ error }}</span><button @click="error = ''">×</button></div>
    <div v-if="notice" class="banner notice" role="status"><span>{{ notice }}</span><button @click="notice = ''">×</button></div>

    <div class="workspace" :style="{gridTemplateColumns: workspaceColumns}">
      <DockPanel panel-id="config" :title="panelTitles.config" :closed="!!closedPanels.config" @close="closePanel('config')" class="config-panel panel">
        <div class="panel-heading"><span class="section-number">01</span><h2>场景配置</h2><span class="small-label">LOCAL_TANK_RH</span></div>
        <div class="config-scroll">
          <div class="field"><label for="scenario">实验场景</label><div class="input-action"><select id="scenario" v-model="selectedScenario" :disabled="!editable" @change="loadScenario"><option v-for="item in scenarios" :key="item.scenario_id" :value="item.scenario_id">{{ item.name || item.scenario_id }}</option></select><button title="重新加载" :disabled="!editable" @click="loadScenario">↻</button></div></div>
          <template v-if="config">
            <fieldset :disabled="!editable">
              <div class="field"><label for="mode">观测生成模式</label><select id="mode" v-model="config.mode"><option value="IDEAL_NO_REFRACTION">理想针孔 · 无折射</option><option value="FLAT_SNELL_REFRACTION">平面 Snell 折射</option><option value="WAVY_SNELL_REFRACTION">波纹 Snell 折射</option></select></div>
              <div class="config-section"><h3>水池与时间 <span>m · s</span></h3><div class="three-fields"><label>长 X<input v-model.number="config.tank.length_m" type="number" min="4" step=".5"></label><label>宽 Y<input v-model.number="config.tank.width_m" type="number" min="4" step=".5"></label><label>水深<input v-model.number="config.tank.depth_m" type="number" min="1.5" step=".1"></label></div><div class="two-fields"><label>时长<input v-model.number="config.duration_s" type="number" min=".2" max="600" step="1"></label><label>固定步长<input v-model.number="config.dt_s" type="number" min=".01" max="1" step=".01"></label></div></div>
              <div class="config-section"><div class="section-inline"><h3>相机阵列 <span>{{ config.cameras.length }} 台</span></h3><button class="text-button" @click="addCamera">＋ 添加</button></div>
                <div class="camera-tabs"><button v-for="item in config.cameras" :key="item.camera_id" :class="{ selected: item.camera_id === selectedCamera }" @click="selectedCamera = item.camera_id">{{ item.camera_id }}</button></div>
                <template v-if="camera"><div class="three-fields"><label>X / m<input v-model.number="camera.position_m[0]" :aria-label="`${camera.camera_id} X位置`" type="number" step=".1"></label><label>Y / m<input v-model.number="camera.position_m[1]" :aria-label="`${camera.camera_id} Y位置`" type="number" step=".1"></label><label>高度 / m<input v-model.number="camera.position_m[2]" :aria-label="`${camera.camera_id} 高度`" type="number" min=".05" step=".1"></label></div>
                <label class="range-label">高度调节 <span>{{ Number(camera.position_m[2] || 0).toFixed(2) }} m</span><input v-model.number="camera.position_m[2]" type="range" min=".3" max="4" step=".05" aria-label="相机高度滑块"></label>
                <details><summary>朝向与相机内参</summary><div class="three-fields"><label>目标 X<input v-model.number="camera.look_at_m[0]" type="number" step=".1"></label><label>目标 Y<input v-model.number="camera.look_at_m[1]" type="number" step=".1"></label><label>目标 Z<input v-model.number="camera.look_at_m[2]" type="number" step=".1"></label></div><div class="two-fields"><label>fx / px<input v-model.number="camera.fx_px" type="number" min="10" step="10"></label><label>fy / px<input v-model.number="camera.fy_px" type="number" min="10" step="10"></label><label>宽 / px<input v-model.number="camera.width_px" type="number" min="10"></label><label>高 / px<input v-model.number="camera.height_px" type="number" min="10"></label><label>cx / px<input v-model.number="camera.cx_px" type="number"></label><label>cy / px<input v-model.number="camera.cy_px" type="number"></label></div><button v-if="config.cameras.length > 1" class="text-button danger-text" @click="config.cameras = config.cameras.filter(c => c.camera_id !== selectedCamera); selectedCamera = config.cameras[0].camera_id">移除此相机</button></details></template>
                <p class="hint">选中相机后可拖动三维坐标轴。布局状态：<code>NOT_OPTIMIZED</code></p>
              </div>
              <div class="config-section"><div class="section-inline"><h3>目标与运动 <span>{{ config.targets.length }} 艘</span></h3><button class="text-button" :disabled="config.targets.length >= 8" @click="addTarget">＋ 添加</button></div><div v-for="target in config.targets" :key="target.target_id"><div class="target-id"><i></i>{{ target.target_id }}<span>水平圆轨迹</span></div><div class="three-fields"><label>深度 / m<input v-model.number="target.depth_m" type="number" min=".5" :max="config.tank.depth_m - .5" step=".1"></label><label>半径 / m<input v-model.number="target.radius_m" type="number" min=".1" step=".1"></label><label>周期 / s<input v-model.number="target.period_s" type="number" min="1" step="5"></label></div></div><p class="hint">航向由切线生成；定位器不读取航迹或真值。</p></div>
              <div class="config-section"><h3>波纹与观测</h3><div class="wave-mode-note"><span>{{ config.mode === 'WAVY_SNELL_REFRACTION' ? '波纹模式：后端网格随仿真时间更新' : '当前模式为平面水面，不生成波纹' }}</span><button v-if="config.mode !== 'WAVY_SNELL_REFRACTION'" class="text-button" @click="config.mode = 'WAVY_SNELL_REFRACTION'">启用波纹模式</button></div><div class="two-fields"><label>总振幅上界 / m<input v-model.number="config.wave.amplitude_m" type="number" min="0" max=".08" step=".005"></label><label>角点噪声 σ / px<input v-model.number="config.pixel_noise_std_px" type="number" min="0" max="10" step=".1"></label></div><div class="two-fields"><label>空气折射率<input v-model.number="config.optics.n_air" type="number" min="1" step=".00001"></label><label>水折射率<input v-model.number="config.optics.n_water" type="number" min="1" step=".001"></label></div><label class="field">随机种子<input v-model.number="config.seed" type="number" min="0" step="1"></label></div>
              <details class="adapter-contracts"><summary>算法接入 · 2.1—2.3</summary><label v-for="role in adapterRoles" :key="role" class="adapter-choice">{{ adapterLabels[role] }}<select v-model="config.adapters[role]" :aria-label="adapterLabels[role] + '算法'"><option v-for="item in adapterCatalog.filter(entry => entry.role === role)" :key="item.algorithm_id" :value="item.algorithm_id">{{ item.algorithm_id }}</option></select><small>{{ selectedAdapter(role)?.status ?? '等待注册表' }} · v{{ selectedAdapter(role)?.algorithm_version ?? '—' }} / 契约 {{ selectedAdapter(role)?.schema_version ?? '—' }}</small></label><p class="hint">替换已注册算法后，启动新运行生效。固定布局与 NoOp 为占位基线。</p><a href="/api/adapters" target="_blank" rel="noreferrer">查看已注册接口目录 ↗</a></details><button class="secondary-button full-width" @click="saveScenario">保存场景副本</button>
            </fieldset>
            <p v-if="!editable && !replayMode" class="hint locked-hint">运行配置已冻结。停止后调整相机，再启动新运行。</p>
          </template>
        </div>
      </DockPanel>

      <div v-show="!closedPanels.config" class="column-splitter" role="separator" tabindex="0" aria-orientation="vertical" aria-label="调整配置栏宽度" @pointerdown="resizeColumn($event, 'left')" @keydown.left.prevent="leftWidth = Math.max(220,leftWidth-20); saveLayout()" @keydown.right.prevent="leftWidth = Math.min(520,leftWidth+20); saveLayout()" />
      <main class="main-panel">
        <section class="run-bar panel">
          <div class="run-state"><i :class="status"></i><div><strong>{{ statusLabels[status] || status }}</strong><small>{{ replayMode ? 'JSONL 原始事件' : modeLabels[config?.mode || ''] || '等待场景' }}</small></div></div>
          <div class="run-controls"><button class="primary-button" :disabled="busy || !controls.edit || !config" @click="start">▶ {{ run ? '新建运行' : '启动仿真' }}</button><button :disabled="busy || !controls.pause || replayMode" @click="control('pause')">Ⅱ 暂停</button><button :disabled="busy || !controls.resume || replayMode" @click="control('resume')">▷ 继续</button><button :disabled="busy || !controls.stop || replayMode" @click="control('stop')">■ 停止</button><select v-model.number="speed" aria-label="运行倍速" :disabled="busy" @change="changeSpeed"><option :value=".5">0.5×</option><option :value="1">1×</option><option :value="2">2×</option><option :value="4">4×</option></select></div>
          <div class="time-display"><b>{{ simTime.toFixed(1) }}</b><span>/ {{ config?.duration_s ?? 60 }} s</span><small v-if="status === 'running'" class="actual-speed" title="后端实测的仿真秒 / 墙钟秒">实测 {{ actualSpeed === null ? '—' : actualSpeed.toFixed(2) + '×' }}</small></div>
        </section>

        <DockPanel panel-id="scene" :title="panelTitles.scene" :closed="!!closedPanels.scene" @close="closePanel('scene')" class="scene-panel panel">
          <div class="scene-toolbar"><div><span class="section-number">02</span><h2>三维场景</h2><span class="scene-mode">{{ waterSurface ? (config?.mode === 'WAVY_SNELL_REFRACTION' ? '后端波纹网格' : '后端平面网格') : '平均平面示意' }}</span></div><div class="scene-view-actions"><label><input v-model="showWater" type="checkbox" aria-label="显示水面">水面</label><select v-model.number="waterExaggeration" :disabled="!showWater" aria-label="水面显示放大" title="仅放大显示高度，不修改折射或定位计算"><option :value="1">真实高度 ×1</option><option :value="3">仅显示 ×3</option><option :value="5">仅显示 ×5</option></select><button class="text-button" @click="sceneView?.resetView()">↖ 重置视角</button></div></div>
          <SceneView ref="sceneView" :config="config" :poses="poses" :trails="trails" :selected-camera="selectedCamera" :editable="editable" :water-surface="waterSurface" :show-water="showWater" :water-exaggeration="waterExaggeration" @asset-state="assets[$event.key] = $event.status" @camera-moved="moveCamera" />
          <div class="scene-overlay"><span><i class="dot truth"></i>真值轨迹</span><span><i class="dot raw"></i>无校正</span><span><i class="dot corrected"></i>平面校正</span><span><i class="dot filtered"></i>校正＋滤波</span></div>
          <div class="water-surface-info" role="status"><span v-if="waterSurface">后端采样 {{ waterSurface.rows }}×{{ waterSurface.columns }} · t={{ waterSurface.sim_time_s.toFixed(2) }} s · {{ waterSurface.model_kind }}</span><span v-else>尚无后端水面事件 · 当前显示平均平面示意</span><strong v-if="waterExaggeration !== 1">仅显示放大 ×{{ waterExaggeration }}，解算使用真实振幅</strong><small v-if="!showWater">水面已隐藏</small></div><div class="scene-bottom"><span>X 长轴 · Y 宽轴 · Z 向上</span><span>视锥：空气侧几何示意</span><span>拖动旋转 · 滚轮缩放</span></div>
          <div class="run-progress"><div :style="{ width: `${progress}%` }"></div></div>
        </DockPanel>

        <DockPanel panel-id="chart" :title="panelTitles.chart" :closed="!!closedPanels.chart" @close="closePanel('chart')" class="chart-panel panel"><div class="panel-heading"><span class="section-number">03</span><h2>定位误差</h2><span class="small-label">后端评价样本 · {{ errors.length }} 点</span></div><ErrorChart :points="errors" /><div v-if="!errors.length" class="chart-empty">启动仿真后显示实时误差；所有默认数值均未标定</div></DockPanel>

        <DockPanel panel-id="replay" :title="panelTitles.replay" :closed="!!closedPanels.replay" @close="closePanel('replay')" class="replay-panel panel"><div class="panel-heading"><span class="section-number">04</span><h2>运行记录与回放</h2><button class="text-button" @click="refreshRuns">↻ 刷新</button></div><div class="replay-controls"><select v-model="replayRun" :disabled="!controls.edit || busy" aria-label="历史运行"><option value="">选择历史运行</option><option v-for="item in savedRuns" :key="item.run_id" :value="item.run_id">{{ item.run_id.slice(0, 12) }} · {{ statusLabels[item.status] || item.status }}</option></select><button :disabled="!replayRun || !controls.edit || busy" @click="loadReplay">读取日志</button><button :disabled="!replayMode || !replayLength" @click="toggleReplay">{{ replayPlaying ? 'Ⅱ 暂停回放' : '▷ 播放' }}</button><button v-if="replayMode" @click="exitReplay">退出回放</button></div><div v-if="replayMode" class="replay-scrubber"><input :value="replayCursor" type="range" min="0" :max="replayLength" aria-label="回放事件位置" @input="stopReplay(); seekReplay(Number(($event.target as HTMLInputElement).value))"><span>{{ replayCursor }} / {{ replayLength }}</span></div><div class="export-links"><span>导出运行</span><template v-if="run"><a v-for="artifact in ['scenario.yaml', 'metadata.json', 'events.jsonl', 'metrics.csv']" :key="artifact" :href="`/api/runs/${run.run_id}/export/${artifact}`" :download="artifact">↓ {{ artifact }}</a></template><small v-else>创建运行后可用</small></div></DockPanel>
      </main>

      <div v-show="rightVisible" class="column-splitter" role="separator" tabindex="0" aria-orientation="vertical" aria-label="调整评价栏宽度" @pointerdown="resizeColumn($event, 'right')" @keydown.left.prevent="rightWidth = Math.min(520,rightWidth+20); saveLayout()" @keydown.right.prevent="rightWidth = Math.max(240,rightWidth-20); saveLayout()" />
      <aside v-show="rightVisible" class="results-panel">
        <DockPanel panel-id="summary" :title="panelTitles.summary" :closed="!!closedPanels.summary" @close="closePanel('summary')" class="panel summary-panel"><div class="panel-heading"><span class="section-number">05</span><h2>实时评价</h2><span class="small-label">m</span></div><div class="hero-metric"><span>{{ replayMode ? "历史运行最终汇总 · " : "" }}平面校正 RMSE</span><strong>{{ format(latestCorrected?.rmse) }}<small>m</small></strong><div class="metric-context">MODEL_AWARE_DEMO</div></div><div class="mini-metrics"><div><span>P95 误差</span><b>{{ format(latestCorrected?.p95) }}</b></div><div><span>有效定位率</span><b>{{ latestCorrected?.validRate == null ? '—' : `${(latestCorrected.validRate * 100).toFixed(1)}%` }}</b></div></div><div class="method-row" v-for="row in rows" :key="row.algorithm_id"><div><i :class="['dot', row.algorithm_id.includes('pinhole') ? 'raw' : row.algorithm_id.includes('smooth') ? 'filtered' : 'corrected']"></i><span>{{ shortAlgorithm(row.algorithm_id) }}</span></div><b>{{ format(row.rmse) }} <small>RMSE</small></b></div><p v-if="!rows.length" class="hint metrics-placeholder">等待后端评价数据</p><p class="hint science-note">精度比较采用共同有效帧；有效率保留各方法分母。平面校正使用已知标定与平均水面，近零误差不代表真实定位精度。</p></DockPanel>
        <DockPanel panel-id="position" :title="panelTitles.position" :closed="!!closedPanels.position" @close="closePanel('position')" class="panel position-panel"><div class="panel-heading"><h2>目标真值</h2><span class="small-label">{{ currentPose?.target_id ?? 'UUV-001' }}</span></div><div class="position-grid"><div v-for="(axis, index) in ['X', 'Y', 'Z']" :key="axis"><span>{{ axis }} / m</span><b>{{ currentPose ? currentPose.position_m[index].toFixed(3) : '—' }}</b></div></div><div class="observation-title"><span>最近相机观测</span><b>{{ lastObservation?.camera_id ?? '—' }} · ID {{ lastObservation?.marker_id ?? '—' }}</b></div><svg class="observation-view" viewBox="0 0 1280 720" role="img" aria-label="解析标记角点像素观测"><path d="M640 0V720M0 360H1280" stroke="#c6d7e5" stroke-width="3" stroke-dasharray="10 12"/><polygon v-if="observationCorners.length" :points="observationCorners.map(p => p.join(',')).join(' ')" fill="#11856c18" stroke="#11856c" stroke-width="5"/><circle v-for="(point, index) in observationCorners" :key="index" :cx="point[0]" :cy="point[1]" r="9" fill="#b1760c"/></svg><p class="hint">解析角点 · 已知目标关联 · 非真实图像检测</p></DockPanel>
        <DockPanel panel-id="sensor" :title="panelTitles.sensor" :closed="!!closedPanels.sensor" @close="closePanel('sensor')" class="panel sensor-panel"><div class="panel-heading"><h2>多源接入</h2><span class="small-label">接口联调</span></div><div class="sensor-row"><i :class="'sample-' + rangeStatus.state"></i><div><strong>声学测距 <span :class="['sample-status', 'sample-' + rangeStatus.state]">{{ rangeStatus.label }}</span></strong><small>{{ lastRange ? `最近输入：${lastRange.range_m ?? '—'} m` : '等待测量输入' }}</small><small v-if="lastRange" class="sample-timing">采样 {{ format(rangeStatus.sampleTime_s, 2) }} s · 龄期 {{ sampleAgeText(rangeStatus.age_s) }}</small></div><button :disabled="!run || !controls.stop || busy || replayMode" @click="injectDemoRange">注入样例</button></div><div class="sensor-row"><i :class="'sample-' + communicationStatus.state"></i><div><strong>通信数据 <span :class="['sample-status', 'sample-' + communicationStatus.state]">{{ communicationStatus.label }}</span></strong><small>{{ lastCommunication ? '已接收通信事件' : '等待通信输入' }}</small><small v-if="lastCommunication" class="sample-timing">采样 {{ format(communicationStatus.sampleTime_s, 2) }} s · 龄期 {{ sampleAgeText(communicationStatus.age_s) }}</small></div><button :disabled="!run || !controls.stop || busy || replayMode" @click="injectDemoCommunication">注入样例</button></div><div class="noop-label">NoOpFusion · 仅透传视觉<br><small>龄期按仿真采样时刻显示，超过 2 s 标为过期；不代表融合质量。</small></div></DockPanel>
        <DockPanel panel-id="assets" :title="panelTitles.assets" :closed="!!closedPanels.assets" @close="closePanel('assets')" class="panel status-panel"><div class="panel-heading"><h2>资产与运行信息</h2></div><div class="asset-status" v-for="(value, key) in assets" :key="key"><span>{{ key }}</span><b :class="{ warning: value.includes('失败') || value.includes('不可用') }">{{ value }}</b></div><div class="metadata-block"><span>固定种子</span><code>{{ config?.seed ?? '—' }}</code><span>配置 SHA-256</span><code :title="configHash">{{ configHash.length > 30 ? `${configHash.slice(0, 22)}…` : configHash }}</code><span>运行 / 事件序号</span><code>{{ run?.run_id.slice(0, 14) ?? '—' }} / #{{ seq }}</code><span>主视觉算法</span><code>{{ config?.adapters.vision ?? '—' }}</code></div></DockPanel>
      </aside>
    </div>

    <DockPanel panel-id="events" :title="panelTitles.events" :closed="!!closedPanels.events" @close="closePanel('events')" class="event-panel panel"><div class="panel-heading"><h2>事件监视</h2><span class="small-label">JSONL 事实来源 · 最近 {{ recentEvents.length }} 条</span></div><div class="event-content"><div class="event-table"><div class="event-head"><span>序号</span><span>仿真时间</span><span>事件类型</span><span>目标 / 来源</span></div><button v-for="event in recentEvents.slice(0, 8)" :key="event.event_seq" class="event-row" @click="selectedPayload = event"><span>#{{ event.event_seq }}</span><span>{{ event.sim_time_s.toFixed(2) }} s</span><span>{{ event.event_type }}</span><span>{{ event.payload.target_id ?? event.payload.status ?? '—' }} <small>{{ event.payload.algorithm_id ?? event.payload.camera_id ?? '' }}</small></span></button><p v-if="!recentEvents.length" class="hint empty-events">等待创建运行。JSONL 将记录真值、观测、估计与评价事件。</p></div><pre class="event-detail">{{ selectedPayload ? JSON.stringify(selectedPayload, null, 2) : '{\n  "evidence_status": "DEMO_UNCALIBRATED",\n  "coordinate_frame": "LOCAL_TANK_RH",\n  "units": ["m", "s", "rad", "px"],\n  "pipeline": "真值 → 观测 → 定位 → 评价 → 回放"\n}' }}</pre></div></DockPanel>
    <footer><span>UUV VISUAL LOCALIZATION · RESEARCH PROTOTYPE</span><span>2.1 布局 / 2.2 视觉 / 2.3 融合：通过适配器接入</span></footer>
  </div>
</template>
