import bpy, math, sys, json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-arm-diagnostic'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
root='Bone_023'
# Discover the complete descendant tree automatically so this includes every joint/bone below the right shoulder,
# including any hand/finger branches present in this particular Meshy rig. Do not rely on an assumed linear chain.
def descendants(name):
 out=[]
 def walk(b):
  for c in b.children:
   out.append(c.name); walk(c)
 walk(arm.data.bones[name]); return out
mapped=[root]+descendants(root)
for n in mapped: arm.pose.bones[n].rotation_mode='XYZ'
pts=[main.matrix_world@Vector(c) for c in main.bound_box]; mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); cen=(mn+mx)*.5; ext=max(mx-mn)
wire=bpy.data.materials.new('DiagnosticWire'); wire.diffuse_color=(0.18,0.8,0.25,0.28); wire.use_nodes=True
bs=wire.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(0.18,0.8,0.25,1); bs.inputs['Alpha'].default_value=.28; bs.inputs['Roughness'].default_value=.7
if hasattr(wire,'blend_method'): wire.blend_method='BLEND'
for ob in [o for o in s.objects if o.type=='MESH']:
 ob.data.materials.clear(); ob.data.materials.append(wire); ob.show_wire=True; ob.show_all_edges=True
bone_mat=bpy.data.materials.new('BoneOverlay'); bone_mat.diffuse_color=(1,.25,.08,1)
test_mat=bpy.data.materials.new('TestBoneOverlay'); test_mat.diffuse_color=(1,1,.05,1)
def make_bone_overlay(test_name=None):
 for o in list(bpy.data.objects):
  if o.name.startswith('DBG_BONE_'): bpy.data.objects.remove(o,do_unlink=True)
 for n in mapped:
  p=arm.pose.bones[n]; a=arm.matrix_world@p.head; b=arm.matrix_world@p.tail; d=b-a; L=d.length
  if L<1e-5: continue
  mat=test_mat if n==test_name else bone_mat
  bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=ext*(.012 if n==test_name else .007),depth=L,location=(a+b)*.5)
  o=bpy.context.object;o.name='DBG_BONE_'+n;o.rotation_euler=d.to_track_quat('Z','Y').to_euler();o.data.materials.append(mat)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=10,ring_count=6,radius=ext*(.018 if n==test_name else .011),location=a)
  q=bpy.context.object;q.name='DBG_BONE_joint_'+n;q.data.materials.append(mat)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.025,.025,.03)
bpy.ops.object.light_add(type='AREA',location=cen+Vector((ext*2,-ext*2,ext*2)));bpy.context.object.data.energy=900;bpy.context.object.data.size=ext*3
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.45;s.camera=cam
def reset():
 for n in mapped: arm.pose.bones[n].rotation_euler=(0,0,0)
def set_camera(view):
 loc={'front':cen+Vector((0,-ext*4,0)),'side':cen+Vector((ext*4,0,0))}[view];cam.location=loc;cam.rotation_euler=(cen-loc).to_track_quat('-Z','Y').to_euler()
def render(name,view,test_name=None):
 make_bone_overlay(test_name);set_camera(view);s.render.filepath=str(OUT/f'{name}_{view}.png');bpy.ops.render.render(write_still=True)
def state(n):
 p=arm.pose.bones[n]; d=(p.tail-p.head)
 return {'head':list(p.head),'tail':list(p.tail),'direction':list(d.normalized()) if d.length else [0,0,0]}
# Common neutral reference.
reset();bpy.context.view_layer.update()
for view in ['front','side']: render('ALL_neutral',view)
axis_index={'X':0,'Y':1,'Z':2}; report={'root':root,'mapped_bones':mapped,'hierarchy':{},'bones':{}}
for n in mapped:
 b=arm.data.bones[n]
 report['hierarchy'][n]={'parent':b.parent.name if b.parent else None,'children':[c.name for c in b.children]}
 report['bones'][n]={'neutral':state(n),'tests':{}}
 for axis,idx in axis_index.items():
  report['bones'][n]['tests'][axis]={}
  for deg in [90,180]:
   reset();arm.pose.bones[n].rotation_euler[idx]=math.radians(deg);bpy.context.view_layer.update()
   # Record the tested bone and every descendant endpoint after this isolated rotation so downstream effect is explicit.
   affected=[n]+descendants(n)
   report['bones'][n]['tests'][axis][str(deg)]={'tested':state(n),'affected':{x:state(x) for x in affected}}
   for view in ['front','side']: render(f'{n}_{axis}_+{deg:03d}',view,n)
# Generate a compact machine-readable and human-readable inventory alongside the renders.
(OUT/'axis_report.json').write_text(json.dumps({'purpose':'Complete right-arm descendant cardinal map. Each bone isolated at +90/+180 on local X/Y/Z; front+side wireframe; all other rotations zero.','result':report},indent=2))
lines=['# Limijoy right-arm diagnostic inventory','',f'Root: `{root}`',f'Bones discovered: **{len(mapped)}**','', '## Hierarchy']
for n in mapped:
 h=report['hierarchy'][n]; lines.append(f'- `{n}` — parent `{h["parent"]}`; children: '+(', '.join(f'`{c}`' for c in h['children']) if h['children'] else 'none'))
lines += ['', '## Test matrix', 'Every listed bone is rendered independently at **+90°** and **+180°** on **X, Y, Z**, from **front and side**. No other arm rotation is applied. The tested bone is highlighted in yellow; the remaining descendant rig is orange.', '', 'Visual interpretation should be added to the project rig documentation only after the rendered set has been reviewed.']
(OUT/'README.md').write_text('\n'.join(lines))
