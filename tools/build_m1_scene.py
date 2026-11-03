"""用 Blender 创建独立的 M1 水池场景；不改写原有 UUV-001 资产。"""

import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "assets" / "scenes"
CAMERAS = {
    "C1": (-2.0, -2.0, 1.5),
    "C2": (2.0, -2.0, 1.5),
    "C3": (0.0, 2.2, 1.5),
}


def source_hashes():
    """记录原有模型文件，运行结束时核验其字节内容保持不变。"""
    return {
        str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((PROJECT / "assets" / "models").rglob("*"))
        if path.is_file()
    }


def material(name, color, metallic=0.0, roughness=0.45, alpha=1.0, glow=0.0):
    """设置节点材质；透明度只用于场景示意，不参与定位计算。"""
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    result.diffuse_color = (*color, alpha)
    node = next(n for n in result.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    node.inputs["Base Color"].default_value = (*color, 1.0)
    node.inputs["Metallic"].default_value = metallic
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Alpha"].default_value = alpha
    if "Emission Color" in node.inputs:
        node.inputs["Emission Color"].default_value = (*color, 1.0)
        node.inputs["Emission Strength"].default_value = glow
    return result


def finish(obj, name, mat, parent=None):
    """统一对象命名和父级，使前端可以按角色管理显示。"""
    obj.name = name
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def box(name, location, dimensions, mat, bevel=0.0, parent=None):
    """建立以米为单位的长方体。"""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("Rounded schematic edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return finish(obj, name, mat, parent)


def cylinder(name, a, b, radius, mat, parent=None, vertices=16):
    """用两端点建立圆柱，供相机支架、网格和示意光线使用。"""
    start, end = Vector(a), Vector(b)
    direction = end - start
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=direction.length,
        location=(start + end) / 2.0,
    )
    obj = bpy.context.object
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return finish(obj, name, mat, parent)


def empty(name):
    """建立不带几何的变换节点，供前端按名称整体控制。"""
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def label(name, text, position, size, mat, billboard=False):
    """创建并转为网格的英文示意标签，保证 GLB 中仍可显示。"""
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = position
    if billboard:
        direction = Vector((8.0, -10.0, 8.0)) - obj.location
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj["role"] = "schematic_label"
    return obj


def select_only(objects):
    """只导出指定对象，不把其他场景的对象混入 GLB。"""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)


def main():
    """构建、导出并渲染 M1 场景，原始模型仅作为输入读取。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    old_scene = bpy.context.scene
    scene = bpy.data.scenes.new("M1_Tank_Schematic")
    bpy.context.window.scene = scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene["evidence_status"] = "DEMO_UNCALIBRATED"
    scene["coordinate_frame"] = "LOCAL_TANK_RH"
    scene["preserved_previous_scene"] = old_scene.name

    deck = material("M1 deep blue stage", (0.018, 0.037, 0.065), metallic=0.18)
    pool = material("M1 pool lining", (0.07, 0.15, 0.20), roughness=0.7)
    grid = material("M1 metric grid", (0.19, 0.42, 0.48), glow=0.15)
    cyan = material("M1 waterline cyan", (0.04, 0.72, 0.82), glow=0.8)
    glass = material("M1 transparent tank walls", (0.14, 0.53, 0.62), alpha=0.10)
    water = material("M1 mean water schematic", (0.08, 0.52, 0.66), alpha=0.10)
    metal = material("M1 brushed supports", (0.16, 0.23, 0.29), metallic=0.8)
    dark = material("M1 camera enclosure", (0.025, 0.042, 0.060), metallic=0.5)
    amber = material("M1 camera amber", (1.0, 0.47, 0.07), metallic=0.3, glow=0.3)
    lens = material("M1 camera optics schematic", (0.03, 0.18, 0.24), metallic=0.75)
    white = material("M1 annotation", (0.64, 0.87, 0.91), glow=0.2)

    stage_root = empty("tank_stage")
    stage_root["role"] = "tank_static"
    box("stage_plinth", (0, 0, -2.14), (6.5, 6.5, 0.24), deck, 0.08, stage_root)
    box("tank_bottom", (0, 0, -2.035), (5.0, 5.0, 0.07), pool, 0.02, stage_root)
    for index in range(11):
        location = -2.5 + index * 0.5
        cylinder(
            f"metric_grid_x_{index}",
            (-2.5, location, -1.993),
            (2.5, location, -1.993),
            0.004,
            grid,
            stage_root,
        )
        cylinder(
            f"metric_grid_y_{index}",
            (location, -2.5, -1.993),
            (location, 2.5, -1.993),
            0.004,
            grid,
            stage_root,
        )
    for sign in (-1, 1):
        box(f"tank_wall_x_{sign}", (sign * 2.51, 0, -1.0), (0.025, 5.0, 2.0), glass, parent=stage_root)
        box(f"tank_wall_y_{sign}", (0, sign * 2.51, -1.0), (5.0, 0.025, 2.0), glass, parent=stage_root)
    corners = [(-2.5, -2.5), (2.5, -2.5), (2.5, 2.5), (-2.5, 2.5)]
    for index, (x, y) in enumerate(corners):
        cylinder(f"tank_corner_{index}", (x, y, -2), (x, y, 0), 0.025, metal, stage_root)
        nx, ny = corners[(index + 1) % 4]
        cylinder(f"mean_waterline_{index}", (x, y, 0), (nx, ny, 0), 0.014, cyan, stage_root)
    water_object = box("water_surface", (0, 0, 0), (4.99, 4.99, 0.005), water, parent=stage_root)
    water_object["role"] = "mean_water_surface_schematic"

    # 相机资产局部采用 Blender/Three 相机轴：右 +X、上 +Y、光轴 -Z。
    # 光学位置是父节点原点；外壳形状是示意几何，不是已标定安装外参。
    prototype = empty("camera_unit")
    prototype["role"] = "camera_housing"
    prototype["optical_axis"] = "-Z"
    box("camera_housing", (0, 0, 0.11), (0.26, 0.19, 0.24), dark, 0.025, prototype)
    box("camera_accent", (0, 0.098, 0.11), (0.23, 0.009, 0.17), amber, 0.002, prototype)
    cylinder("camera_lens_barrel", (0, 0, -0.10), (0, 0, 0.02), 0.068, metal, prototype, 32)
    cylinder("camera_lens_front", (0, 0, -0.107), (0, 0, -0.10), 0.058, lens, prototype, 32)
    box("camera_mount", (0, -0.115, 0.12), (0.12, 0.06, 0.13), metal, 0.01, prototype)
    prototype_objects = [prototype, *prototype.children_recursive]
    select_only(prototype_objects)
    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT / "camera_unit.glb"),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_extras=True,
    )

    # 每台相机是独立变换父节点；支架与视锥也单独命名，前端可统一隐藏后重建。
    for camera_id, position in CAMERAS.items():
        root = empty(f"camera_{camera_id}")
        root["role"] = "camera_control_root"
        root["camera_id"] = camera_id
        root.location = position
        root.rotation_euler = (Vector((0, 0, -1)) - root.location).to_track_quat("-Z", "Y").to_euler()
        for source in prototype.children:
            duplicate = source.copy()
            duplicate.data = source.data
            scene.collection.objects.link(duplicate)
            duplicate.parent = root
            duplicate.name = f"{camera_id}_{source.name}"
        stand = empty(f"stand_{camera_id}")
        stand["role"] = "camera_static_stand"
        x, y, z = position
        box(f"{camera_id}_stand_base", (x, y, 0.02), (0.28, 0.28, 0.055), metal, 0.02, stand)
        cylinder(f"{camera_id}_stand_pole", (x, y, 0.04), (x, y, z - 0.12), 0.027, metal, stand)
        frustum = empty(f"frustum_{camera_id}")
        frustum["role"] = "air_side_fov_schematic"
        orientation = root.rotation_euler.to_quaternion()
        far_local = [(-0.71, -0.40, -1.0), (0.71, -0.40, -1.0), (0.71, 0.40, -1.0), (-0.71, 0.40, -1.0)]
        far_world = [root.location + orientation @ (Vector(point) * 2.3) for point in far_local]
        for index, endpoint in enumerate(far_world):
            cylinder(f"{camera_id}_fov_ray_{index}", root.location, endpoint, 0.004, amber, frustum)
            cylinder(f"{camera_id}_fov_edge_{index}", endpoint, far_world[(index + 1) % 4], 0.004, amber, frustum)
        label(f"label_{camera_id}", camera_id, (x, y, z + 0.32), 0.18, amber, billboard=True)

    for obj in prototype_objects:
        scene.collection.objects.unlink(obj)
    # 未挂到场景的原型保留在可编辑文件中，避免额外显示一个原点相机。
    prototype.use_fake_user = True

    # Blender glTF 导入器已经把 Y-up 转回 Blender Z-up，无需再次旋转导入几何。
    previous_objects = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(PROJECT / "assets" / "models" / "uuv_001.glb"))
    imported = set(scene.objects) - previous_objects
    vehicle = empty("uuv_demo")
    vehicle["role"] = "static_demo_vehicle"
    for obj in imported:
        if obj.parent not in imported:
            obj.parent = vehicle
    vehicle.location = (0.7, 0, -1.0)
    vehicle.rotation_euler.z = math.pi / 2.0

    # 圆形航迹只是静态示意；前端的动态轨迹必须来自后端事件。
    orbit = empty("trajectory_schematic")
    orbit["role"] = "static_demo_trajectory"
    for index in range(64):
        a = index * 2.0 * math.pi / 64.0
        b = (index + 1) * 2.0 * math.pi / 64.0
        cylinder(
            f"orbit_segment_{index}",
            (0.7 * math.cos(a), 0.7 * math.sin(a), -1),
            (0.7 * math.cos(b), 0.7 * math.sin(b), -1),
            0.008,
            cyan,
            orbit,
        )
    label("stage_title", "M1 / UUV VISION LAB", (0, -2.89, -2.001), 0.18, white)
    label("stage_warning", "DEMO_UNCALIBRATED  |  5 x 5 x 2 m  |  3 CAMERAS", (0, -3.13, -2.001), 0.065, amber)
    label("depth_label", "MEAN WATER z=0  /  TARGET z=-1m", (0, 2.88, -2.001), 0.085, white)

    world = bpy.data.worlds.new("M1 navy environment")
    world.use_nodes = True
    background = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.035, 0.055, 0.08, 1.0)
    background.inputs["Strength"].default_value = 0.6
    scene.world = world
    for name, position, energy, size in [
        ("M1 key light", (1, -3, 7), 2200, 5),
        ("M1 rim light", (-4, 2, 4), 1800, 4),
        ("M1 fill light", (4, 3, 3), 1200, 3),
    ]:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((0, 0, -0.4)) - light.location).to_track_quat("-Z", "Y").to_euler()
    camera_data = bpy.data.cameras.new("M1 preview camera")
    camera = bpy.data.objects.new("M1 preview camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (8, -10, 8)
    camera.rotation_euler = (Vector((0, 0, -0.2)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 10.0
    scene.camera = camera

    select_only([obj for obj in scene.objects if obj.type not in {"LIGHT", "CAMERA"}])
    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT / "m1_tank_scene.glb"),
        export_format="GLB",
        use_selection=True,
        use_active_scene=True,
        export_extras=True,
    )
    metadata = {
        "schema_version": "1.0",
        "evidence_status": "DEMO_UNCALIBRATED",
        "coordinate_frame": "LOCAL_TANK_RH",
        "units": "m",
        "tank_dimensions_m": [5.0, 5.0, 2.0],
        "mean_surface_z_m": 0.0,
        "blender_to_gltf": "(x,y,z)_gltf=(x,z,-y)_blender",
        "gltf_to_local_tank": "wrapper.rotation.x=+pi/2",
        "camera_unit_local_axes": {"right": "+X", "up": "+Y", "optical_forward": "-Z"},
        "camera_roots": {f"camera_{key}": {"camera_id": key, "position_m": value, "look_at_m": [0, 0, -1]} for key, value in CAMERAS.items()},
        "frontend_hide_roots": ["camera_C1", "camera_C2", "camera_C3", "stand_C1", "stand_C2", "stand_C3", "frustum_C1", "frustum_C2", "frustum_C3", "label_C1", "label_C2", "label_C3", "uuv_demo", "trajectory_schematic"],
        "camera_control": "Outer group at configured tank position, quaternion copied from THREE.Camera lookAt; inner GLB wrapper rotation.x=pi/2.",
        "runtime_authority": "Camera edits preview display, then submit effective config for a new backend run; running config is immutable.",
        "limitations": ["Geometry and camera housing are schematic, not measured hardware", "Mean-plane water rendering does not compute optical propagation", "Frusta show air-side pinhole geometry, not refracted coverage", "No hydrodynamics or image detection"],
        "source_asset_hashes_sha256": before,
        "blender_version": bpy.app.version_string,
    }
    (OUTPUT / "m1_scene_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    after = source_hashes()
    if before != after:
        raise RuntimeError("原有 assets/models 内容发生变化，停止交付")
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    formats = [item.identifier for item in scene.render.image_settings.bl_rna.properties["file_format"].enum_items]
    scene.render.image_settings.file_format = next(item for item in formats if item == "PNG")
    scene.render.filepath = str(OUTPUT / "m1_tank_preview.png")
    saved_versions = bpy.context.preferences.filepaths.save_version
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "m1_tank_scene.blend"))
    bpy.context.preferences.filepaths.save_version = saved_versions
    bpy.ops.render.render(write_still=True)
    print("M1_SCENE_BUILD_COMPLETE", json.dumps({"objects": len(scene.objects), "sources_unchanged": before == after, "engine": scene.render.engine, "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
