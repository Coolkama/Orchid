import bpy, math, sys, json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-arm-diagnostic'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
right_chain=['Bone_023','Bone_022','Bone_021','Bone_020','Bone_019','Bone_018','Bone_017','Bone_016']
left_chain=['Bone_031','Bone_030','Bone_029','Bone_028','Bone_027','Bone_026','Bone_025','Bone_024']
for n in right_chain+left_chain: arm.pose.bones[n].rotation_mode='XYZ'
pts=[main.matrix_world@Vector(c) for c in main.bound_box]; mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); cen=(mn+mx)*.5; ext=max(mx-mn)
wire=bpy.data.materials.new('DiagnosticWire'); wire.diffuse_color=(0.18,0.8,0.25,0.28); wire.use_nodes=True
bs=wire.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(0.18,0.8,0.25,1); bs.inputs['Alpha'].default_value=.28; bs.inputs['Roughness'].default_value=.7
if hasattr(wire,'blend_method'): wire.blend_method='BLEND'
for ob in [o for o in s.objects if o.type=='MESH']:
 ob.data.materials.clear(); ob.data.materials.append(wire); ob.show_wire=True; ob.show_all_edges=True
def make_bone_overlay():
 for o in list(bpy.data.objects):
  if o.name.startswith('DBG_BONE_'): bpy.data.objects.remove(o,do_unlink=True)
 mat=bpy.data.materials.get('BoneOverlay') or bpy.data.materials.new('BoneOverlay'); mat.diffuse_color=(1,.25,.08,1)
 for n in right_chain:
  p=arm.pose.bones[n]; a=arm.matrix_world@p.head; b=arm.matrix_world@p.tail; d=b-a; L=d.length
  if L<1e-5: continue
  bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=ext*.009,depth=L,location=(a+b)*.5);o=bpy.context.object;o.name='DBG_BONE_'+n;o.rotation_euler=d.to_track_quat('Z','Y').to_euler();o.data.materials.append(mat)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=10,ring_count=6,radius=ext*.015,location=a);q=bpy.context.object;q.name='DBG_BONE_joint_'+n;q.data.materials.append(mat)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
s.render.resolution_x=s.render.resolution_y=512;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.025,.025,.03)
bpy.ops.object.light_add(type='AREA',location=cen+Vector((ext*2,-ext*2,ext*2)));bpy.context.object.data.energy=900;bpy.context.object.data.size=ext*3
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.45;s.camera=cam
def reset():
 for n in right_chain+left_chain: arm.pose.bones[n].rotation_euler=(0,0,0)
def set_camera(view):
 loc={'front':cen+Vector((0,-ext*4,0)),'side':cen+Vector((ext*4,0,0))}[view];cam.location=loc;cam.rotation_euler=(cen-loc).to_track_quat('-Z','Y').to_euler()
def render(name,view):
 make_bone_overlay();set_camera(view);s.render.filepath=str(OUT/f'{name}_{view}.png');bpy.ops.render.render(write_still=True)
# Shoulder-joint-only test. Bone_023 is the right shoulder/girdle root identified from the prior arm map.
# Nothing else rotates. Render neutral plus one isolated +90-degree rotation on X, Y and Z, from true front and true side.
shoulder='Bone_023'; axis_index={'X':0,'Y':1,'Z':2}; report={'bone':shoulder,'tests':{}}
reset(); bpy.context.view_layer.update(); p=arm.pose.bones[shoulder]
report['neutral']={'head':list(p.head),'tail':list(p.tail)}
for view in ['front','side']: render('shoulder_neutral',view)
for axis,idx in axis_index.items():
 reset(); arm.pose.bones[shoulder].rotation_euler[idx]=math.radians(90); bpy.context.view_layer.update(); p=arm.pose.bones[shoulder]
 report['tests'][axis]={'degrees':90,'head':list(p.head),'tail':list(p.tail),'direction':list((p.tail-p.head).normalized())}
 for view in ['front','side']: render(f'shoulder_{axis}_+090',view)
(OUT/'axis_report.json').write_text(json.dumps({'purpose':'Bone_023 shoulder-joint-only wireframe diagnostic: neutral and isolated +90 degree X/Y/Z rotations, front and side views; no other bone rotations','result':report},indent=2))
