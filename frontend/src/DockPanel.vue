<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ panelId: string; title: string; closed: boolean }>()
const emit = defineEmits<{ close: [] }>()
const height = ref<number | null>(null), maximized = ref(false)
let cancelDrag: (() => void) | undefined
/** 关闭仅隐藏视图，保留相机、回放和运行状态；尺寸独立持久化。 */
function restore() {
  try { const n = Number(localStorage.getItem(`uuv.panel.${props.panelId}.height`)); if (n >= 160 && n <= 2400) height.value = n } catch { /* 存储不可用时仍可使用面板。 */ }
}
function setHeight(value: number) {
  height.value = Math.min(2400, Math.max(160, value))
  try { localStorage.setItem(`uuv.panel.${props.panelId}.height`, String(height.value)) } catch { /* 仅影响布局记忆。 */ }
}
function resize(event: PointerEvent) {
  if (maximized.value) return
  event.preventDefault(); cancelDrag?.()
  const start = event.clientY, initial = (event.currentTarget as HTMLElement).parentElement!.getBoundingClientRect().height
  const move = (e: PointerEvent) => setHeight(initial + e.clientY - start)
  const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); document.body.classList.remove('resizing-rows') }
  cancelDrag = end; document.body.classList.add('resizing-rows')
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', end, { once: true }); window.addEventListener('pointercancel', end, { once: true })
}
function autoHeight() { height.value = null; try { localStorage.removeItem(`uuv.panel.${props.panelId}.height`) } catch { /* 无需存储也可还原。 */ } }
function reset() { autoHeight(); maximized.value = false }
function escape(event: KeyboardEvent) { if (event.key === 'Escape') maximized.value = false }
onMounted(() => { restore(); window.addEventListener('keydown', escape); window.addEventListener('uuv-reset-layout', reset) })
onBeforeUnmount(() => { cancelDrag?.(); window.removeEventListener('keydown', escape); window.removeEventListener('uuv-reset-layout', reset) })
</script>

<template>
  <section v-show="!closed" :id="`panel-${panelId}`" class="dock-panel" :class="{ 'is-maximized': maximized, 'has-custom-height': height !== null }" :style="height && !maximized ? { height: `${height}px` } : {}" :aria-label="title + '面板'">
    <header class="dock-titlebar" @dblclick="maximized = !maximized">
      <span class="dock-tab">{{ title }}</span><div class="dock-actions">
        <button :aria-label="`${maximized ? '还原' : '最大化'}${title}`" :title="maximized ? '还原（Esc）' : '最大化（双击标题栏）'" @click="maximized = !maximized">{{ maximized ? '❐' : '□' }}</button>
        <button :aria-label="`关闭${title}`" title="关闭面板，可从顶部“窗口”菜单恢复" @click="maximized = false; emit('close')">×</button>
      </div>
    </header>
    <div class="dock-body"><slot /></div>
    <div class="row-splitter" role="separator" tabindex="0" aria-orientation="horizontal" :aria-label="`调整${title}高度`" :aria-valuenow="height ?? undefined" @pointerdown="resize" @keydown.up.prevent="setHeight((height ?? 400) - 20)" @keydown.down.prevent="setHeight((height ?? 400) + 20)" @dblclick="autoHeight" title="上下拖动调整高度，双击恢复自动高度" />
  </section>
</template>
