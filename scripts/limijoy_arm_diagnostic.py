import bpy, math, sys, json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-arm-diagnostic'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
# Rig hierarchy shows two mirrored upper-limb branches from the shoulder region.
chains=[['Bone_023','Bone_022','Bone_021','Bone_020','Bone_019','Bone_018','Bone_017','Bone_016'],['Bone_031','Bone_030','Bone_029','Bone_028','Bone_027','Bone_026','Bone_025','Bone_024']]
# Assume the established convention: X=pitch/forward-back, Y=yaw, Z=roll.
# First pass uses X only; enough to identify shoulder/elbow/hand influence without repeating axis diagnostics.
for ch in chains:
 for n in ch: arm.pose.bones[n].rotation_mode='XYZ'
pts=[main.matrix_world@Vector(c) for c in main.bound_box];mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));cen=(mn+mx)*.5;ext=max(mx-mn)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items};s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');s.render.resolution_x=s.render.resolution_y=320;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.035,.035,.045)
cl=cen+Vector((ext*1.25,-ext*3.7,(mx-mn).z*.05));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.35;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,sz in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=sz;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
def reset():
 for ch in chains:
  for n in ch: arm.pose.bones[n].rotation_euler=(0,0,0)
def render(name): s.render.filepath=str(OUT/f'{name}.png');bpy.ops.render.render(write_still=True)
reset();render('00_neutral')
idx=1
# Test the first three major bones and one distal control on each side. Tiny terminal bones are retained in report but not all rendered.
for side,ch in enumerate(chains,1):
 for n in [ch[0],ch[1],ch[2],ch[3]]:
  reset();arm.pose.bones[n].rotation_euler.x=math.radians(18);render(f'{idx:02d}_arm{side}_{n}_X18');idx+=1
(OUT/'report.json').write_text(json.dumps({'chains':chains,'assumed_axes':{'X':'pitch/forward-back','Y':'yaw/left-right','Z':'roll/side-tilt'},'rendered_controls':[chains[0][:4],chains[1][:4]],'purpose':'identify shoulder, elbow, wrist/hand controls before reach and arm swing'},indent=2))