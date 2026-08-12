import bpy, math, sys, subprocess
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-first-step'; FR=OUT/'frames'; FR.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
L={'hip':'Bone_006','thigh':'Bone_005','knee':'Bone_004','ankle':'Bone_003','toe':'Bone_002'};R={'hip':'Bone_011','thigh':'Bone_010','knee':'Bone_009','ankle':'Bone_008','toe':'Bone_007'}
for n in list(L.values())+list(R.values()): arm.pose.bones[n].rotation_mode='XYZ'
# Corrected cycle: retain the successful hip/knee rhythm, reverse fore/aft sense,
# and use ankle + terminal toe bones by gait phase rather than holding toes up.
def pose(f, lhip,lth,lknee,lank,ltoe, rhip,rth,rknee,rank,rtoe, bodyz=0):
 vals=[(L['hip'],lhip),(L['thigh'],lth),(L['knee'],lknee),(L['ankle'],lank),(L['toe'],ltoe),(R['hip'],rhip),(R['thigh'],rth),(R['knee'],rknee),(R['ankle'],rank),(R['toe'],rtoe)]
 for n,d in vals:
  p=arm.pose.bones[n];p.rotation_euler.x=math.radians(d);p.keyframe_insert('rotation_euler',frame=f)
 arm.location.z=bodyz;arm.keyframe_insert('location',frame=f)
# contact: leading foot nearly level; trailing foot begins toe-off
# passing: swing foot clears with knee flex, ankle/toe relaxed rather than permanently dorsiflexed
pose(1,  -8,-10, 2, 2, 0,   8,10,18,-3,-7, 0)
pose(9,   2,  4, 4, 0, 0,  -4,-7,25, 2, 3, 0.018)
pose(17,  8, 10,18,-3,-7,  -8,-10,2, 2, 0, 0)
pose(25, -4, -7,25, 2, 3,   2, 4, 4, 0, 0, 0.018)
pose(33, -8,-10, 2, 2, 0,   8,10,18,-3,-7, 0)
for fc in arm.animation_data.action.fcurves:
 for kp in fc.keyframe_points: kp.interpolation='BEZIER'
s.frame_start=1;s.frame_end=32;s.render.fps=24
pts=[main.matrix_world@Vector(c) for c in main.bound_box];mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));cen=(mn+mx)*.5;ext=max(mx-mn)
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z));gm=bpy.data.materials.new('Ground');gm.diffuse_color=(.055,.055,.07,1);bpy.context.object.data.materials.append(gm)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items};s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.filepath=str(FR/'frame_')
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.035,.035,.045)
cl=cen+Vector((ext*1.35,-ext*3.8,(mx-mn).z*.05));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.35;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,sz in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=sz;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(OUT/'preview.mp4')],check=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-vf','fps=12,scale=384:-1:flags=lanczos','-loop','0',str(OUT/'preview.gif')],check=True)
