import bpy, math, sys, subprocess
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-reach'; FR=OUT/'frames'; FR.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
A={'girdle':'Bone_023','upper':'Bone_022','elbow':'Bone_021','wrist_helper':'Bone_020','hand_helper':'Bone_019','head':'Bone_034'}
for n in A.values(): arm.pose.bones[n].rotation_mode='XYZ'
def set_rot(role, xyz):
 p=arm.pose.bones[A[role]]; p.rotation_euler=tuple(math.radians(v) for v in xyz)
def key(frame, upper=(0,0,0), elbow=(0,0,0), wrist=(0,0,0), hand=(0,0,0), girdle=(0,0,0), head=(0,0,0)):
 set_rot('girdle',girdle); set_rot('upper',upper); set_rot('elbow',elbow); set_rot('wrist_helper',wrist); set_rot('hand_helper',hand); set_rot('head',head)
 for role in A: arm.pose.bones[A[role]].keyframe_insert('rotation_euler',frame=frame)
# Forward direction is now established: Bone_022 negative X moves the upper arm forward.
# The previous pass proved that large Bone_021 negative X over-flexes the elbow and curls the hand back toward the torso.
# This pass holds the upper arm at the proven forward value and compares three elbow endpoint variants:
# +10 degrees, 0 degrees, and -10 degrees X. Y stays at zero throughout to avoid axial roll.
# The sequence deliberately pauses on each variant so the straightest reach can be identified visually.
key(1)
key(9,  upper=(-24,0,-1), elbow=(0,0,0), head=(0,-4,0))
key(17, upper=(-48,0,-3), elbow=(10,0,0), head=(0,-10,0))
key(25, upper=(-48,0,-3), elbow=(10,0,0), head=(0,-10,0))
key(33, upper=(-48,0,-3), elbow=(0,0,0), head=(0,-10,0))
key(41, upper=(-48,0,-3), elbow=(0,0,0), head=(0,-10,0))
key(49, upper=(-48,0,-3), elbow=(-10,0,0), head=(0,-10,0))
key(57, upper=(-48,0,-3), elbow=(-10,0,0), head=(0,-10,0))
key(65, upper=(-24,0,-1), elbow=(0,0,0), head=(0,-4,0))
key(73)
for fc in arm.animation_data.action.fcurves:
 for kp in fc.keyframe_points: kp.interpolation='BEZIER'
s.frame_start=1;s.frame_end=73;s.render.fps=24
pts=[main.matrix_world@Vector(c) for c in main.bound_box]; mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); cen=(mn+mx)*.5; ext=max(mx-mn)
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z)); gm=bpy.data.materials.new('Ground');gm.diffuse_color=(.055,.055,.07,1);bpy.context.object.data.materials.append(gm)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.filepath=str(FR/'frame_')
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.035,.035,.045)
cl=cen+Vector((ext*2.15,-ext*3.2,ext*.35));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.42;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,sz in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=sz;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(OUT/'preview.mp4')],check=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-vf','fps=12,scale=384:-1:flags=lanczos','-loop','0',str(OUT/'preview.gif')],check=True)
