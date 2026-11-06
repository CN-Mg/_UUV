"""生成微型潜航器和独立杆装相机资产，单位为米。"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

OUT = Path(__file__).resolve().parents[1] / "assets/models/micro_uuv"


def material(name, color, metallic=0):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = next(node for node in result.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    return result


def finish(name, surface, smooth=False):
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(surface)
    for face in obj.data.polygons:
        face.use_smooth = smooth
    return obj


def cylinder(name, position, radius, length, surface, axis=(1, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=length, location=position)
    obj = finish(name, surface)
    obj.rotation_euler = Vector(axis).to_track_quat("Z", "Y").to_euler()
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    return obj


def box(name, position, dimensions, surface):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
    obj = finish(name, surface)
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new("Rounded edges", "BEVEL")
    bevel.width = min(dimensions) * .18
    bevel.segments = 3
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def export(name, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), use_selection=True)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system = "METRIC"
metal = material("Satin aluminium", (.43, .49, .52), .65)
dark = material("Graphite", (.025, .038, .046), .25)
orange = material("Safety orange", (.9, .23, .03))
glass = material("Lens glass", (.016, .13, .19), .5)
# 尺寸约束来自用户，母线站位和舵面细节按参考图比例拟合。
def lathe(name, stations, surface, segments=96):
    vertices = [(x, r * math.cos(i * math.tau / segments), r * math.sin(i * math.tau / segments))
                for x, r in stations for i in range(segments)]
    faces = [(k*segments+i, k*segments+(i+1)%segments,
              (k+1)*segments+(i+1)%segments, (k+1)*segments+i)
             for k in range(len(stations)-1) for i in range(segments)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(surface)
    for face in mesh.polygons:
        face.use_smooth = True
    return obj


nose = [(.224 + .076*math.sin(i*math.pi/64), .045*math.cos(i*math.pi/64)) for i in range(33)]
lathe("Turned pressure hull and ogive", [(-.278, .012), (-.263, .016), (-.223, .027),
      (-.181, .041), (-.164, .045), (.224, .045), *nose[1:]], metal)
for x in (.221, -.16, -.092):
    cylinder("Circumferential joint", (x, 0, 0), .04505, .0007, dark)
cylinder("Propeller shaft", (-.281, 0, 0), .005, .028, metal)
cylinder("Propeller hub", (-.288, 0, 0), .008, .015, dark)
lathe("Duct outer and inner wall", [(-.300, .023), (-.299, .026), (-.282, .026),
      (-.280, .024), (-.281, .021), (-.299, .021), (-.300, .023)], metal)
for i in range(3):
    angle = i * math.tau / 3
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16,
        location=(-.290, .012 * math.sin(angle), .012 * math.cos(angle)))
    blade = finish("Pitched propeller blade", metal, True)
    blade.scale = (.003, .005, .010)
    blade.rotation_euler = (-angle, .42, 0)
    support = box("Duct support strut", (-.279, .018*math.sin(angle), .018*math.cos(angle)),
                  (.012, .003, .017), metal)
    support.rotation_euler.x = -angle


def fin(name, angle, outline):
    rotation = Matrix.Rotation(-angle, 3, "X")
    vertices = [rotation @ Vector((x, side*.0015, radial))
                for side in (-1, 1) for x, radial in outline]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3), (7, 6, 5, 4),
                                   (0, 4, 5, 1), (1, 5, 6, 2),
                                   (2, 6, 7, 3), (3, 7, 4, 0)])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(metal)
    bevel = obj.modifiers.new("Machined edge", "BEVEL")
    bevel.width = .0009
    bevel.segments = 3


for i in range(4):
    angle = i * math.pi / 2
    fin("Swept stern control surface", angle, [(-.126, .042), (-.148, .071),
        (-.173, .071), (-.180, .040)])
    cylinder("Control surface pivot", (-.155, .042*math.sin(angle), .042*math.cos(angle)),
             .007, .010, dark, (0, math.sin(angle), math.cos(angle)))
# 从 +Z 向两侧量角，顶部留出 120° 扇区容纳完整曲面标签。
for degrees in (-135, -60, 60, 135):
    fin("Bow control surface", math.radians(degrees),
        [(.213, .042), (.205, .070), (.182, .070), (.171, .042)])
# +X 向前。竖直圆柱贴合梯形板的直角边，两者坐在同一安装平台上。
box("Bow flow guide platform", (.117, 0, .045), (.026, .018, .003), metal)
fin("Bow flow guide trapezoid", 0, [(.124, .046), (.124, .059), (.117, .059), (.107, .046)])
cylinder("Bow flow guide upright", (.1255, 0, .054), .004, .016, metal, (0, 0, 1))
for x in (-.023, .003):
    box("Lifting handle foot", (x, 0, .050), (.010, .009, .012), metal)
box("Lifting handle bridge", (-.010, 0, .057), (.036, .008, .006), metal)

# v 沿圆周展开，u 沿艇轴；左右舷略偏下，避免与顶部标记重叠。
radius = .04535
markers = []
tilt = math.radians(22)
positions = [(x, (1, 0, 0), (0, 0, 1)) for x in (.176, .055, -.080)]
positions += [(x, (-side, 0, 0), (0, side*math.cos(tilt), -math.sin(tilt)))
              for side in (1, -1) for x in (.119, -.051)]
signs = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
for tag_id, (x, axial, radial) in enumerate(positions):
    u, normal = Vector(axial), Vector(radial)
    v = normal.cross(u)
    axis_point = Vector((x, 0, 0))
    center = axis_point + radius * normal

    def on_surface(along, arc):
        angle = arc / radius
        return axis_point + along*u + radius*(math.cos(angle)*normal + math.sin(angle)*v)

    half_width = .04375
    steps = 64
    vertices = [on_surface(a*half_width, (2*j/steps-1)*half_width)
                for j in range(steps+1) for a in (-1, 1)]
    faces = [(2*j, 2*j+1, 2*j+3, 2*j+2) for j in range(steps)]
    mesh = bpy.data.meshes.new(f"Conformal tag {tag_id}")
    mesh.from_pydata(vertices, [], faces)
    uv_layer = mesh.uv_layers.new()
    for loop in mesh.loops:
        j, column = divmod(loop.vertex_index, 2)
        uv_layer.data[loop.index].uv = (column, j/steps)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    corners = [on_surface(a*half_width, b*half_width) for a, b in signs]
    tag = bpy.data.objects.new(f"AprilTag36h11 ID {tag_id}", mesh)
    bpy.context.collection.objects.link(tag)
    face = material(f"Backlit tag {tag_id}", (1, 1, 1))
    nodes = face.node_tree.nodes
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(OUT / f"tags/tag36_11_{tag_id:05}.png"))
    texture.image.pack()
    texture.interpolation = "Closest"
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    for socket in ("Base Color", "Emission Color"):
        face.node_tree.links.new(texture.outputs["Color"], shader.inputs[socket])
    shader.inputs["Emission Strength"].default_value = .65
    shader.inputs["Roughness"].default_value = 1
    tag.data.materials.append(face)
    markers.append(dict(id=tag_id, center_m=list(center), u_axis=list(u), v_axis=list(v),
                        outward_normal=list(normal), surface_radius_m=radius, black_square_size_m=.07, board_size_m=.0875,
                        corners_body_m=[list(corner) for corner in corners]))

vehicle = list(bpy.context.scene.objects)
export("micro_uuv", vehicle)
(OUT / "marker_geometry.json").write_text(json.dumps(dict(
    evidence_status="DEMO_UNCALIBRATED", family="tag36h11", length_m=.6, hull_diameter_m=.09,
    body_frame="+X forward, +Y port, +Z up; origin at hull axis reference",
    corner_order="bottom-left, bottom-right, top-right, top-left in texture coordinates",
    markers=markers), indent=2), encoding="utf-8")

# 相机局部 -Z 朝前，杆独立保持世界 +Z 竖直。
box("Weatherproof camera", (0, 0, .059), (.16, .12, .106), dark)
cylinder("Lens bezel", (0, 0, .018), .043, .033, orange, (0, 0, 1))
cylinder("Lens front", (0, 0, .002), .033, .004, glass, (0, 0, 1))
box("Rear mounting bracket", (0, 0, .135), (.07, .07, .06), metal)
camera = [obj for obj in bpy.context.scene.objects if obj not in vehicle]
export("pole_camera", camera)
pole = cylinder("Vertical camera pole", (0, 0, .5), .024, 1, metal, (0, 0, 1))
export("camera_pole", [pole])
# 保留一个独立编辑场景，内含一艇和一套杆装相机。
camera_origin = Vector((-.44, .17, 1.0))
camera_rotation = Vector((.44, -.17, -1.0)).to_track_quat("-Z", "Y")
for obj in camera:
    obj.location = camera_origin + camera_rotation @ obj.location
    obj.rotation_euler = (camera_rotation @ obj.rotation_euler.to_quaternion()).to_euler()
pole_top = camera_origin + camera_rotation @ Vector((0, 0, .145))
pole.location = (pole_top.x, pole_top.y, pole_top.z / 2)
pole.scale.z = pole_top.z
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "micro_uuv_and_camera.blend"))

