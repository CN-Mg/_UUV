"""Run with Blender --background --python tools/build_uuv.py."""
import bpy, math, json
from pathlib import Path
from mathutils import Vector, Matrix
OUT=Path(r'D:\_UUV\assets\models'); OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene; scene.unit_settings.system='METRIC'
def mat(name,color,metal=0):
 m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
 p=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
 if p is None:
  p=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled'); out=m.node_tree.nodes.new('ShaderNodeOutputMaterial');m.node_tree.links.new(p.outputs[0],out.inputs['Surface'])
 p.inputs['Base Color'].default_value=(*color,1); p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=.32
 return m
silver=mat('Brushed titanium',(.47,.57,.62),.78); dark=mat('Graphite',(.025,.04,.05),.35); orange=mat('Safety orange',(.95,.19,.025)); white=mat('White',(.92,.95,.96))
parts=[]
def finish(o,name,m):
 o.name=name; o.data.materials.append(m); parts.append(o)
 return o
def uv(name,loc,scale,m):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,location=loc); o=bpy.context.object; o.scale=scale
 for p in o.data.polygons:p.use_smooth=True
 return finish(o,name,m)
def cyl(name,loc,r,depth,m,axis=(1,0,0)):
 bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=depth,location=loc); o=bpy.context.object; o.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler()
 for p in o.data.polygons:p.use_smooth=True
 return finish(o,name,m)
def box(name,loc,scale,m,bevel=.015):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel: mod=o.modifiers.new('Soft edges','BEVEL');mod.width=bevel;mod.segments=3; o.modifiers.new('Normals','WEIGHTED_NORMAL')
 return finish(o,name,m)
# Body frame: +X nose, +Y port, +Z up, origin at main hull midpoint.
cyl('Hull',(0,0,0),.18,1.75,silver)
uv('Rounded sensor nose',(.875,0,0),(.36,.18,.18),dark)
uv('Tail taper',(-.99,0,0),(.36,.17,.17),silver)
for x in (-.84,.83):cyl('Hull seam',(x,0,0),.183,.018,dark)
for x in (.65,.69):cyl('Visibility band',(x,0,0),.184,.025,orange)
cyl('Tail motor',(-1.29,0,0),.09,.22,dark)
cyl('Propeller hub',(-1.49,0,0),.045,.18,silver)
for a in range(4):
 angle=a*math.pi/2
 o=box('Cruciform tail fin',(-1.14,.22*math.sin(angle),.22*math.cos(angle)),(.32,.025,.30),dark)
 o.rotation_euler.x=-angle
for a in range(3):
 angle=a*2*math.pi/3
 o=uv('Propeller blade',(-1.48,.095*math.sin(angle),.095*math.cos(angle)),(.024,.053,.12),dark);o.rotation_euler.x=-angle;o.rotation_euler.y=.25
# Open safety duct around propeller, torus axis X.
bpy.ops.mesh.primitive_torus_add(major_radius=.205,minor_radius=.018,major_segments=64,minor_segments=12,location=(-1.48,0,0),rotation=(0,math.pi/2,0)); finish(bpy.context.object,'Propeller guard',dark)
for x in (-.35,.35):box('Handle foot',(x,0,.21),(.045,.045,.09),silver)
box('Lifting handle',(0,0,.265),(.75,.045,.04),silver)
cyl('Navigation mast',(-.63,0,.27),.038,.23,dark,axis=(0,0,1));cyl('Mast cap',(-.63,0,.395),.052,.025,orange,axis=(0,0,1))
uv('Forward camera window',(1.21,0,0),(.032,.064,.064),mat('Optical glass',(.012,.07,.09),.6))
def text(name,body,loc,size,m,basis):
 c=bpy.data.curves.new(name,'FONT');c.body=body;c.size=size;c.align_x='CENTER';c.align_y='CENTER';c.extrude=.0004
 o=bpy.data.objects.new(name,c);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=Matrix(basis).transposed().to_euler();o.data.materials.append(m);parts.append(o)
text('Port identification','UUV-001',(.22,.181,.02),.087,dark,((1,0,0),(0,0,1),(0,-1,0)))
# Text normal above points starboard; use explicit outward port basis.
bpy.data.objects['Port identification'].rotation_euler=Matrix((( -1,0,0),(0,0,1),(0,1,0))).transposed().to_euler()
text('Starboard identification','UUV-001',(.22,-.182,.02),.087,dark,((1,0,0),(0,0,1),(0,-1,0)))
markers=[]
for i,(center,u,v,n) in enumerate([
 ((-.27,-.188,0),(1,0,0),(0,0,1),(0,-1,0)),
 ((-.27,.188,0),(-1,0,0),(0,0,1),(0,1,0)),
 ((.48,0,.188),(1,0,0),(0,1,0),(0,0,1)),
 ((.48,0,-.188),(1,0,0),(0,-1,0),(0,0,-1))]):
 # 160 mm board, 120 mm black code; 20 mm quiet margin.
 center=Vector(center);u=Vector(u);v=Vector(v);n=Vector(n)
 vertices=[center+u*x*.08+v*y*.08 for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
 mesh=bpy.data.meshes.new(f'Marker_{i}');mesh.from_pydata(vertices,[],[(0,1,2,3)]);mesh.uv_layers.new()
 for loop,coord in zip(mesh.uv_layers.active.data,[(0,0),(1,0),(1,1),(0,1)]):loop.uv=coord
 o=bpy.data.objects.new(f'ArUco_4x4_50_ID_{i:03}',mesh);scene.collection.objects.link(o);parts.append(o)
 m=mat(f'ArUco {i}',(1,1,1));tex=m.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(OUT/'textures'/f'aruco_4x4_50_{i:03}.png'));tex.interpolation='Closest';m.node_tree.links.new(tex.outputs['Color'],next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color']);o.data.materials.append(m)
 markers.append(dict(id=i,center_m=list(center),u_axis=list(u),v_axis=list(v),outward_normal=list(n),black_square_size_m=.12,board_size_m=.16,corners_body_m=[list(p) for p in vertices],corner_order='bottom-left,bottom-right,top-right,top-left in texture coordinates'))
root=bpy.data.objects.new('UUV_001_BODY_FRAME',None);scene.collection.objects.link(root)
for o in parts:o.parent=root
root['asset_id']='UUV-001';root['units']='meter';root['forward_axis']='+X'
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'uuv_001.glb'),export_format='GLB',use_selection=True)
(OUT/'uuv_001_metadata.json').write_text(json.dumps(dict(asset_id='UUV-001',status='concept geometry, dimensions assumed; no dynamics calibration',units='m',body_frame={'x':'forward','y':'port','z':'up','origin':'main cylinder midpoint'},hull_diameter_m=.36,nominal_length_m=2.80,marker_dictionary='DICT_4X4_50',markers=markers),indent=2))
# Studio scene is excluded from GLB above.
floor=box('Studio floor',(0,0,-.44),(200,200,.05),mat('Studio',(.022,.04,.055)))
world=scene.world;world.use_nodes=True;bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs[0].default_value=(.13,.18,.23,1);bg.inputs[1].default_value=.5
def aim(o,point):o.rotation_euler=(Vector(point)-o.location).to_track_quat('-Z','Y').to_euler()
for loc,power,size in [((1,-3,5),1700,5),((-3,1,3),2000,4),((2,4,2),1400,3)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;aim(o,(0,0,0))
bpy.ops.object.camera_add(location=(3.1,-4.5,2.45));scene.camera=bpy.context.object;aim(scene.camera,(-.15,0,0));scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=3.65
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'uuv_001_preview.png');bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'uuv_001.blend'));bpy.ops.render.render(write_still=True)
print('UUV_ASSET_BUILD_COMPLETE')
