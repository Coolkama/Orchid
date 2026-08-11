import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'prototype-alive'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); meshes=[o for o in s.objects if o.type=='MESH']
# Limijoy Smart Rig mapping established by still diagnostics:
# Bone_033 = primary whole-head control candidate; local X=pitch, Y=yaw, Z=roll.
head=arm.pose.bones['Bone_033']; head.rotation_mode='XYZ'
# 3 seconds / 72 frames: neutral -> look right -> curious tilt -> straighten -> forward.
# Positive Y turned Limijoy left in the diagnostic, so right is negative Y.
# Positive Z tilted Limijoy right, so use a modest positive Z while looking right.
keys=[
 (1,0,0),(10,0,0),
 (25,-22,0),(34,-22,0),
 (44,-22,10),(52,-22,10),
 (59,-22,0),(72,0,0)]
for f,yaw,roll in keys:
    head.rotation_euler=(0,math.radians(yaw),math.radians(roll))
    head.keyframe_insert(data_path='rotation_euler',frame=f)
s.frame_start=1;s.frame_end=72;s.render.fps=24
if arm.animation_data and arm.animation_data.action:
 arm.animation_data.action.name='Limijoy_LookRight_CuriousTilt'
 for fc in arm.animation_data.action.fcurves:
  for k in fc.keyframe_points:k.interpolation='BEZIER'
pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box];mn=Vector((min(q.x for q in pts),min(q.y for q in pts),min(q.z for q in pts)));mx=Vector((max(q.x for q in pts),max(q.y for q in pts),max(q.z for q in pts)));cen=(mn+mx)*.5;size=mx-mn;ext=max(size)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items};s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('AliveWorld')
s.world.color=(.035,.035,.045);cl=cen+Vector((0,-ext*3.8,size.z*.08));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.35;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),850,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=rad;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z));g=bpy.context.object;gm=bpy.data.materials.new('AliveGround');gm.diffuse_color=(.06,.06,.075,1);g.data.materials.append(gm)
for f in range(1,73):s.frame_set(f);s.render.filepath=str(OUT/f'alive_{f:03d}.png');bpy.ops.render.render(write_still=True)
r={'source':str(model.relative_to(ROOT)),'animation':'Limijoy_LookRight_CuriousTilt','duration_seconds':3,'fps':24,'head_bone':'Bone_033','mapping':{'pitch':'X','yaw':'Y','roll':'Z'},'story':['neutral','turn to Limijoy right','hold','curious right tilt','straighten while still looking','return forward']};(OUT/'report.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))