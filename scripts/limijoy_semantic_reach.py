import bpy, math, sys, subprocess
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'limijoy-reach'
FR = OUT / 'frames'
FR.mkdir(parents=True, exist_ok=True)

arg = next((x for x in sys.argv if x.startswith('--model=')), None)
model = Path(arg.split('=',1)[1]) if arg else ROOT / 'assets/models/glimmerkin.glb'
if not model.is_absolute(): model = ROOT / model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model))
scene=bpy.context.scene; arm=next(o for o in scene.objects if o.type=='ARMATURE'); main=max([o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
bones={'girdle':'Bone_023','upper':'Bone_022','elbow':'Bone_021','wrist':'Bone_020','hand':'Bone_019','head':'Bone_034'}
for name in bones.values(): arm.pose.bones[name].rotation_mode='XYZ'; arm.pose.bones[name].rotation_euler=(0,0,0)
if arm.animation_data and arm.animation_data.action: arm.animation_data.action=None
bpy.context.view_layer.update()
pts=[main.matrix_world@Vector(c) for c in main.bound_box]; mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); cen=(mn+mx)*.5; ext=max(mx-mn)
elbow=arm.pose.bones[bones['elbow']]; rest_tip=arm.matrix_world@elbow.tail.copy(); shoulder=arm.matrix_world@arm.pose.bones[bones['upper']].head.copy()
target_end=Vector((shoulder.x,shoulder.y-ext*.52,shoulder.z+ext*.02)); pole_pos=Vector((shoulder.x+ext*.48,shoulder.y-ext*.16,shoulder.z-ext*.12))
def add_empty(name,loc):
 bpy.ops.object.empty_add(type='PLAIN_AXES',location=loc); o=bpy.context.object;o.name=name;o.empty_display_size=ext*.06;return o
target=add_empty('ReachTarget',rest_tip);pole=add_empty('ReachPole',pole_pos)
c=elbow.constraints.new('IK');c.name='SemanticReachIK';c.target=target;c.pole_target=pole;c.chain_count=2;c.use_tail=True;c.iterations=64
def kt(f,loc): target.location=loc;target.keyframe_insert('location',frame=f)
def kr(name,f,xyz):
 p=arm.pose.bones[name];p.rotation_euler=tuple(math.radians(v) for v in xyz);p.keyframe_insert('rotation_euler',frame=f)
for f,t in [(1,0),(9,.25),(19,.72),(29,1),(39,1),(49,.30),(59,0)]: kt(f,rest_tip.lerp(target_end,t))
# Palm attitude: the previous pass rolled the distal chain toward palm-up.
# Use the mapped elbow/forearm Y roll in the opposite direction so the palm turns inward toward the body/target.
# Wrist and hand helpers only add small finishing corrections.
for f,v in [(1,0),(9,-8),(19,-24),(29,-38),(39,-38),(49,-10),(59,0)]: kr(bones['elbow'],f,(0,v,0))
for f,v in [(1,0),(9,-3),(19,-8),(29,-12),(39,-12),(49,-4),(59,0)]: kr(bones['wrist'],f,(0,v,0))
for f,v in [(1,0),(19,2),(29,4),(39,4),(49,1),(59,0)]: kr(bones['hand'],f,(0,v,0))
for f,v in [(1,0),(9,-2),(19,-5),(29,-8),(39,-8),(49,-3),(59,0)]: kr(bones['head'],f,(0,v,0))
if target.animation_data and target.animation_data.action:
 for fc in target.animation_data.action.fcurves:
  for kp in fc.keyframe_points: kp.interpolation='BEZIER'
if arm.animation_data and arm.animation_data.action:
 for fc in arm.animation_data.action.fcurves:
  for kp in fc.keyframe_points: kp.interpolation='BEZIER'
scene.frame_start=1;scene.frame_end=59;scene.render.fps=24
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z));gm=bpy.data.materials.new('Ground');gm.diffuse_color=(.055,.055,.07,1);bpy.context.object.data.materials.append(gm)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items};scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');scene.render.resolution_x=scene.render.resolution_y=384;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(FR/'frame_')
if scene.world is None: scene.world=bpy.data.worlds.new('World')
scene.world.color=(.035,.035,.045)
cl=cen+Vector((ext*2.15,-ext*3.2,ext*.35));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.42;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();scene.camera=cam
for loc,en,sz in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=sz;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(OUT/'preview.mp4')],check=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-vf','fps=12,scale=384:-1:flags=lanczos','-loop','0',str(OUT/'preview.gif')],check=True)
