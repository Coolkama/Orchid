import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'prototype-alive'
OUT.mkdir(parents=True,exist_ok=True)
arg=next((x for x in sys.argv if x.startswith('--model=')),None)
model=Path(arg.split('=',1)[1]) if arg else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE')
meshes=[o for o in s.objects if o.type=='MESH']

# Limijoy mapping established by our diagnostics.
# X=pitch, Y=yaw, Z=roll for head/neck/torso controls.
head=arm.pose.bones['Bone_033']
neck=arm.pose.bones['Bone_034']
torso=arm.pose.bones['Bone_015']
for b in (head,neck,torso): b.rotation_mode='XYZ'

# 2.5 s performance: Limijoy starts looking slightly away, notices the camera,
# the neck and torso follow with a small delay, then comes a curious head tilt.
# Positive Y turns Limijoy left; positive Z tilts Limijoy right.
# frame: head(yaw,roll,pitch), neck(yaw,roll,pitch), torso(yaw,roll,pitch)
poses=[
 (1,  (16,0,0), (6,0,0), (3,0,0)),
 (10, (16,0,0), (6,0,0), (3,0,0)),
 (20, (0,0,0),  (6,0,0), (3,0,0)),       # eyes/head notice us first
 (26, (0,0,0),  (0,0,0), (3,0,0)),       # neck follows
 (32, (0,0,0),  (0,0,0), (0,0,2)),       # torso squares up + tiny interest lean
 (40, (0,10,0), (0,2,0), (0,0,2)),       # curious tilt, mostly in head
 (48, (0,10,0), (0,2,0), (0,0,2)),
 (55, (0,0,0),  (0,0,0), (0,0,1)),
 (60, (0,0,0),  (0,0,0), (0,0,0)),
]

def apply(bone, vals, frame):
    yaw,roll,pitch=vals
    bone.rotation_euler=(math.radians(pitch),math.radians(yaw),math.radians(roll))
    bone.keyframe_insert(data_path='rotation_euler',frame=frame)

for f,h,n,t in poses:
    apply(head,h,f); apply(neck,n,f); apply(torso,t,f)

s.frame_start=1;s.frame_end=60;s.render.fps=24
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action.name='Limijoy_NoticeCamera_Curious'
    for fc in arm.animation_data.action.fcurves:
        for k in fc.keyframe_points:k.interpolation='BEZIER'

# Ground from the primary skinned mesh only. The previous preview used every mesh's
# bounding box, so an unrelated helper/icosphere could place the floor below the feet.
skinned=[o for o in meshes if any(m.type=='ARMATURE' and m.object==arm for m in o.modifiers)]
primary=max(skinned or meshes,key=lambda o:len(o.data.vertices))
world_verts=[primary.matrix_world @ v.co for v in primary.data.vertices]
foot_z=min(v.z for v in world_verts)
mn=Vector((min(v.x for v in world_verts),min(v.y for v in world_verts),min(v.z for v in world_verts)))
mx=Vector((max(v.x for v in world_verts),max(v.y for v in world_verts),max(v.z for v in world_verts)))
cen=(mn+mx)*.5; size=mx-mn; ext=max(size)

eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100
s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('AliveWorld')
s.world.color=(.035,.035,.045)

# Straight-on camera so the turn toward us and facial tilt read clearly.
cl=cen+Vector((0,-ext*3.8,size.z*.06))
bpy.ops.object.camera_add(location=cl)
cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.34
cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),850,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.4)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    l=bpy.context.object;l.data.energy=en;l.data.size=rad
    l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()

bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,foot_z))
g=bpy.context.object
gm=bpy.data.materials.new('AliveGround');gm.diffuse_color=(.06,.06,.075,1);g.data.materials.append(gm)

for f in range(1,61):
    s.frame_set(f);s.render.filepath=str(OUT/f'alive_{f:03d}.png');bpy.ops.render.render(write_still=True)

report={
 'source':str(model.relative_to(ROOT)),
 'animation':'Limijoy_NoticeCamera_Curious','duration_seconds':2.5,'fps':24,
 'controls':{'head':'Bone_033','neck':'Bone_034','torso':'Bone_015'},
 'mapping':{'pitch':'X','yaw':'Y','roll':'Z'},
 'ground_source_mesh':primary.name,'ground_z':foot_z,
 'story':['starts looking slightly away','head notices camera','neck follows','torso follows subtly','curious tilt toward camera','relaxes']
}
(OUT/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))