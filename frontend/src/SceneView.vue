<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import type { PoseDisplay, ScenarioConfig, Vector3, WaterSurfaceSnapshot } from './contracts'
import { traceColor } from './theme'
import { surfaceGeometryData } from './waterSurface'

const props = defineProps<{
  config: ScenarioConfig | null
  poses: Record<string, PoseDisplay>
  trails: Record<string, Vector3[]>
  selectedCamera: string
  editable: boolean
  waterSurface: WaterSurfaceSnapshot | null
  showWater: boolean
  waterExaggeration: number
}>()
const emit = defineEmits<{
  'asset-state': [value: { key: string; status: string }]
  'camera-moved': [value: { camera_id: string; position_m: Vector3 }]
}>()
const host = ref<HTMLDivElement>()
let renderer: THREE.WebGLRenderer | undefined
let scene: THREE.Scene, view: THREE.PerspectiveCamera, orbit: OrbitControls, transform: TransformControls
let frame = 0, resize: ResizeObserver, fallbackTank: THREE.Group, tankAsset: THREE.Group | undefined
let cameraTemplate: THREE.Group | undefined, vehicleTemplate: THREE.Group | undefined
let waterGroup: THREE.Group, waterMesh: THREE.Mesh, waterWire: THREE.Mesh
let waterGeometryKey = ''
const cameraGroups = new Map<string, THREE.Group>()
const poseGroups = new Map<string, THREE.Group>()
const lineGroups = new Map<string, THREE.Line>()
let destroyed = false

/** 水面只消费后端采样高度；显示放大使用对象变换，不改变采样或光学解算。 */
function syncWater() {
  if (!waterMesh || !props.config) return
  waterGroup.visible = props.showWater
  waterGroup.scale.z = [1, 3, 5].includes(props.waterExaggeration) ? props.waterExaggeration : 1
  const surface = props.waterSurface
  if (!surface) {
    const key = `mean:${props.config.tank.length_m}:${props.config.tank.width_m}`
    if (waterGeometryKey !== key) {
      waterMesh.geometry.dispose()
      waterMesh.geometry = new THREE.PlaneGeometry(props.config.tank.length_m, props.config.tank.width_m)
      waterWire.geometry = waterMesh.geometry; waterGeometryKey = key
    }
    waterWire.visible = false
    return
  }
  const data = surfaceGeometryData(surface)
  const key = `${surface.rows}:${surface.columns}`
  if (waterGeometryKey !== key) {
    waterMesh.geometry.dispose()
    waterMesh.geometry = new THREE.BufferGeometry()
    waterMesh.geometry.setAttribute('position', new THREE.BufferAttribute(data.positions, 3))
    waterMesh.geometry.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3))
    waterMesh.geometry.setIndex(new THREE.BufferAttribute(data.indices, 1))
    waterWire.geometry = waterMesh.geometry; waterGeometryKey = key
  } else {
    const positions = waterMesh.geometry.getAttribute('position') as THREE.BufferAttribute
    const normals = waterMesh.geometry.getAttribute('normal') as THREE.BufferAttribute
    positions.array.set(data.positions); positions.needsUpdate = true
    normals.array.set(data.normals); normals.needsUpdate = true
  }
  waterWire.visible = true
  waterMesh.geometry.computeBoundingSphere()
}

/** 简化相机模型与 glTF 使用同一光学约定：本地 -Z 朝向目标。 */
function fallbackCamera(): THREE.Group {
  const group = new THREE.Group()
  const body = new THREE.Mesh(new THREE.BoxGeometry(.22, .15, .15), new THREE.MeshStandardMaterial({ color: 0xd2dfe7, metalness: .5, roughness: .4 }))
  group.add(body)
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(.055, .065, .1, 20), new THREE.MeshStandardMaterial({ color: 0x142e45, metalness: .8, roughness: .2 }))
  lens.rotation.x = Math.PI / 2; lens.position.z = -.12; group.add(lens)
  return group
}

/** 反向旋转恢复 Blender 的 Z-up 机体系；不修改源资产。 */
function gltfBody(asset: THREE.Group): THREE.Group {
  const wrapper = new THREE.Group()
  wrapper.rotation.x = Math.PI / 2
  wrapper.add(asset.clone(true))
  return wrapper
}

/** 仅绘制空气侧针孔视锥示意，不将其作为水下折射覆盖评价。 */
function frustum(camera: ScenarioConfig['cameras'][number], color: number): THREE.LineSegments {
  const length = 2.2
  const corners = [[0, 0], [camera.width_px, 0], [camera.width_px, camera.height_px], [0, camera.height_px]].map(([u, v]) =>
    new THREE.Vector3((u - camera.cx_px) / camera.fx_px * length, -(v - camera.cy_px) / camera.fy_px * length, -length))
  const points: THREE.Vector3[] = []
  for (let i = 0; i < 4; i++) points.push(new THREE.Vector3(), corners[i], corners[i], corners[(i + 1) % 4])
  return new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color, transparent: true, opacity: .24 }))
}

/** 相机位置来自配置，朝向由显示相机 lookAt 生成，不重算后端外参。 */
function syncScene() {
  if (!scene || !props.config) return
  const config = props.config
  fallbackTank.scale.set(config.tank.length_m / 5, config.tank.width_m / 5, config.tank.depth_m / 2)
  if (tankAsset) tankAsset.scale.set(config.tank.length_m / 5, config.tank.width_m / 5, config.tank.depth_m / 2)
  for (const [id, group] of cameraGroups) if (!config.cameras.some(c => c.camera_id === id)) {
    scene.remove(group); cameraGroups.delete(id)
  }
  for (const calibration of config.cameras) {
    let group = cameraGroups.get(calibration.camera_id)
    if (!group) { group = new THREE.Group(); group.name = calibration.camera_id; cameraGroups.set(calibration.camera_id, group); scene.add(group) }
    if (transform?.dragging && transform.object === group) continue
    group.clear()
    group.position.fromArray(calibration.position_m)
    const displayCamera = new THREE.PerspectiveCamera()
    displayCamera.up.set(0, 0, 1); displayCamera.position.copy(group.position); displayCamera.lookAt(new THREE.Vector3(...calibration.look_at_m))
    group.quaternion.copy(displayCamera.quaternion)
    group.add(cameraTemplate ? gltfBody(cameraTemplate) : fallbackCamera())
    group.add(frustum(calibration, calibration.camera_id === props.selectedCamera ? 0x007acc : 0x638ca7))
  }
  syncTransform()
  syncWater()
}

function syncTransform() {
  if (!transform) return
  const group = cameraGroups.get(props.selectedCamera)
  if (group && props.editable) transform.attach(group)
  else transform.detach()
}

/** 展示姿态由后端事件提供；估计位置使用彩色轮廓点表示。 */
function syncPoses() {
  if (!scene) return
  for (const [key, group] of poseGroups) if (!props.poses[key]) { scene.remove(group); poseGroups.delete(key) }
  for (const [key, pose] of Object.entries(props.poses)) {
    let group = poseGroups.get(key)
    if (!group) {
      group = new THREE.Group()
      if (key.startsWith('truth:')) {
        if (vehicleTemplate) group.add(gltfBody(vehicleTemplate))
        else {
          const hull = new THREE.Mesh(new THREE.CapsuleGeometry(.17, 2.2, 6, 16), new THREE.MeshStandardMaterial({ color: 0xe9aa47, roughness: .4 }))
          hull.rotation.z = Math.PI / 2; group.add(hull)
        }
      } else {
        const material = new THREE.MeshBasicMaterial({ color: traceColor(key), wireframe: true })
        group.add(new THREE.Mesh(new THREE.OctahedronGeometry(.10), material))
      }
      scene.add(group); poseGroups.set(key, group)
    }
    group.position.fromArray(pose.position_m); group.rotation.z = pose.yaw_rad || 0
  }
  for (const [key, line] of lineGroups) if (!props.trails[key]) { scene.remove(line); lineGroups.delete(key) }
  for (const [key, points] of Object.entries(props.trails)) {
    if (points.length < 2) continue
    let line = lineGroups.get(key)
    if (!line) {
      line = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: traceColor(key), transparent: true, opacity: key.startsWith('truth:') ? .5 : .9 }))
      scene.add(line); lineGroups.set(key, line)
    }
    line.geometry.dispose(); line.geometry = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(...p)))
  }
}

function resetView() { if (view && orbit) { view.position.set(7.8, -9, 7); orbit.target.set(0, 0, -.25); orbit.update() } }
defineExpose({ resetView })

onMounted(() => {
  if (!host.value) return
  try {
    scene = new THREE.Scene(); scene.background = new THREE.Color(0xeaf2f8); scene.fog = new THREE.Fog(0xeaf2f8, 16, 32)
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false }); renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.outputColorSpace = THREE.SRGBColorSpace
    host.value.appendChild(renderer.domElement)
    view = new THREE.PerspectiveCamera(43, 1, .05, 100); view.up.set(0, 0, 1)
    orbit = new OrbitControls(view, renderer.domElement); orbit.enableDamping = true; orbit.maxDistance = 22; orbit.minDistance = 2.5; resetView()
    scene.add(new THREE.HemisphereLight(0xf5fbff, 0x6b879b, 1.7))
    const key = new THREE.DirectionalLight(0xffffff, 1.8); key.position.set(3, -4, 8); scene.add(key)
    const fill = new THREE.DirectionalLight(0xc2dff8, 1); fill.position.set(-4, 3, 3); scene.add(fill)
    fallbackTank = new THREE.Group(); scene.add(fallbackTank)
    const bottom = new THREE.Mesh(new THREE.BoxGeometry(5.2, 5.2, .1), new THREE.MeshStandardMaterial({ color: 0xc7dce9, roughness: .8 })); bottom.position.z = -2.05; fallbackTank.add(bottom)
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(5, 5, 2)), new THREE.LineBasicMaterial({ color: 0x6b99b8, transparent: true, opacity: .65 })); edges.position.z = -1; fallbackTank.add(edges)
    waterGroup = new THREE.Group(); waterGroup.name = 'backend_water_surface'; scene.add(waterGroup)
    const waterGeometry = new THREE.PlaneGeometry(5, 5)
    waterMesh = new THREE.Mesh(waterGeometry, new THREE.MeshPhongMaterial({ color: 0x68b3d7, specular: 0xe1f6ff, shininess: 90, transparent: true, opacity: .36, side: THREE.DoubleSide, depthWrite: false, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
    waterMesh.name = 'backend_water_mesh'
    waterWire = new THREE.Mesh(waterGeometry, new THREE.MeshBasicMaterial({ color: 0x398ab7, wireframe: true, transparent: true, opacity: .22, depthWrite: false }))
    waterWire.name = 'backend_water_sampling_grid'; waterGroup.add(waterMesh, waterWire)
    const grid = new THREE.GridHelper(5, 20, 0x6c92ad, 0xa2bdcf); grid.rotation.x = Math.PI / 2; grid.position.z = -1.99; fallbackTank.add(grid)
    const ground = new THREE.GridHelper(20, 40, 0xb5cbdc, 0xd4e1eb); ground.rotation.x = Math.PI / 2; ground.position.z = -2.13; scene.add(ground)
    const axis = new THREE.AxesHelper(.7); axis.position.set(-2.5, -2.5, -1.99); fallbackTank.add(axis)
    transform = new TransformControls(view, renderer.domElement); transform.setMode('translate'); transform.setSpace('world'); transform.setSize(.8); scene.add(transform.getHelper())
    transform.addEventListener('dragging-changed', event => { orbit.enabled = !event.value })
    transform.addEventListener('objectChange', () => {
      if (!transform.object || !props.editable) return
      const pos = transform.object.position
      emit('camera-moved', { camera_id: transform.object.name, position_m: [Number(pos.x.toFixed(3)), Number(pos.y.toFixed(3)), Number(Math.max(.05, pos.z).toFixed(3))] })
    })
    resize = new ResizeObserver(() => { if (!host.value || !renderer) return; const { width, height } = host.value.getBoundingClientRect(); renderer.setSize(width, height); view.aspect = width / Math.max(height, 1); view.updateProjectionMatrix() }); resize.observe(host.value)
    const animate = () => { if (destroyed) return; orbit.update(); renderer?.render(scene, view); frame = requestAnimationFrame(animate) }; animate()
    const loader = new GLTFLoader()
    loader.load('/assets/models/uuv_001.glb', gltf => {
      if (destroyed) return; vehicleTemplate = gltf.scene
      for (const [id, group] of poseGroups) if (id.startsWith('truth:')) { scene.remove(group); poseGroups.delete(id) }
      syncPoses(); emit('asset-state', { key: 'UUV-001', status: 'GLB 已加载' })
    }, undefined, () => emit('asset-state', { key: 'UUV-001', status: '加载失败 · 几何体降级' }))
    loader.load('/assets/scenes/m1_tank_scene.glb', gltf => {
      if (destroyed) return
      gltf.scene.traverse(node => { if (['camera_', 'stand_', 'frustum_', 'label_', 'trajectory_'].some(prefix => node.name.startsWith(prefix)) || node.name === 'uuv_demo' || node.name === 'water_surface') node.visible = false })
      // 仅调整加载副本的展示材质，与源 GLB、几何和后端光学参数无关。
      const displayColors: Record<string, number> = { 'M1 deep blue stage': 0xccdce8, 'M1 pool lining': 0xc4dce9, 'M1 annotation': 0x3e6b85, 'M1 metric grid': 0x7097af, 'M1 waterline cyan': 0x007acc }
      gltf.scene.traverse(node => {
        const mesh = node as THREE.Mesh
        if (!mesh.material) return
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const material of materials) {
          const color = displayColors[material.name]
          if (color !== undefined && 'color' in material) (material as THREE.MeshStandardMaterial).color.setHex(color)
        }
      })
      tankAsset = gltfBody(gltf.scene); scene.add(tankAsset); fallbackTank.visible = false; syncScene()
      emit('asset-state', { key: 'Blender 场景', status: 'GLB 已加载' })
    }, undefined, () => emit('asset-state', { key: 'Blender 场景', status: '加载失败 · 几何体降级' }))
    loader.load('/assets/scenes/camera_unit.glb', gltf => { if (destroyed) return; cameraTemplate = gltf.scene; syncScene(); emit('asset-state', { key: 'Blender 相机', status: 'GLB 已加载' }) }, undefined, () => emit('asset-state', { key: 'Blender 相机', status: '加载失败 · 几何体降级' }))
    syncScene(); syncPoses()
  } catch (error) { emit('asset-state', { key: '三维显示', status: `WebGL 不可用：${String(error)}` }) }
})

watch(() => props.config, syncScene, { deep: true })
watch(() => [props.selectedCamera, props.editable], () => { syncScene(); syncTransform() })
watch(() => [props.poses, props.trails], syncPoses, { deep: true })
watch(() => [props.waterSurface, props.showWater, props.waterExaggeration], syncWater)
onBeforeUnmount(() => {
  destroyed = true; cancelAnimationFrame(frame); resize?.disconnect(); transform?.dispose(); orbit?.dispose()
  scene?.traverse(node => { const object = node as THREE.Mesh; object.geometry?.dispose(); if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => material.dispose()) })
  renderer?.dispose()
})
</script>

<template><div ref="host" class="scene-host" aria-label="UUV 水池三维场景" :data-water-time="waterSurface?.sim_time_s" :data-water-model="waterSurface?.model_kind ?? 'mean-plane-preview'" :data-water-scale="waterExaggeration" :data-water-grid="waterSurface ? `${waterSurface.rows}x${waterSurface.columns}` : 'none'"></div></template>
