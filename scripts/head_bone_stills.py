import bpy, math, sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'head-bone-stills'
OUT.mkdir(parents=True,exist_ok=True)
arg=next((x for x in sys.argv if x.startswith('--model=')),None)
model=Path(arg.split('=',1)[1]) if arg else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE')
meshes=[o for o in s.objects if o.type=='MESH']

# Frame camera from model bounds
pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
cen=(mn+mx)*.5; size=mx-mn; ext=max(size)
if s.world is None: s.world=bpy.data.worlds.new('World')
s.world.color=(0.035,0.035,0.045)
cam_loc=cen+Vector((ext*1.45,-ext*3.6,size.z*.12))
bpy.ops.object.camera_add(location=cam_loc)
cam=bpy.context.object; cam.data.type='ORTHO'; cam.data.ortho_scale=ext*1.45
cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler(); s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),500,ext*2.3)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    l=bpy.context.object; l.data.energy=en; l.data.size=rad; l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
s.render.resolution_x=s.render.resolution_y=512; s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'

bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode='POSE')
for pb in arm.pose.bones: pb.rotation_mode='XYZ'

def reset():
    for pb in arm.pose.bones:
        pb.rotation_euler=(0,0,0); pb.location=(0,0,0); pb.scale=(1,1,1)

def render(name):
    s.render.filepath=str(OUT/name)
    bpy.ops.render.render(write_still=True)

# Neutral + clear X/Y/Z rotations for the two more plausible whole-head controls.
reset(); render('00_neutral.png')
for bone in ['Bone_033','Bone_034']:
    if bone not in arm.pose.bones: continue
    pb=arm.pose.bones[bone]
    for axis,label in [(0,'x'),(1,'y'),(2,'z')]:
        reset(); pb=arm.pose.bones[bone]; vals=[0,0,0]; vals[axis]=math.radians(22); pb.rotation_euler=vals
        render(f'{bone}_{label}_plus22.png')

bpy.ops.object.mode_set(mode='OBJECT')
print('Rendered quick diagnostic stills for Bone_033 and Bone_034')