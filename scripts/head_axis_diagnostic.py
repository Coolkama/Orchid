import bpy, math, sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'head-axis-diagnostic'
OUT.mkdir(parents=True, exist_ok=True)
arg = next((x for x in sys.argv if x.startswith('--model=')), None)
model = Path(arg.split('=',1)[1]) if arg else ROOT / 'assets/models/glimmerkin.glb'
if not model.is_absolute(): model = ROOT / model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
meshes = [o for o in scene.objects if o.type == 'MESH']

# Limijoy head/neck chain found by the rig inspection.
# Bone_032 is the terminal/head bone; animate it one local axis at a time.
head = arm.pose.bones['Bone_032']
head.rotation_mode = 'XYZ'

# 3 seconds @ 24fps. Each axis gets a short isolated excursion and returns to neutral.
# X: frames 1-24, Y: 25-48, Z: 49-72.
keys = [
    (1,  (0,0,0)), (7,  (math.radians(22),0,0)), (13, (math.radians(-22),0,0)), (19, (0,0,0)), (24, (0,0,0)),
    (25, (0,0,0)), (31, (0,math.radians(22),0)), (37, (0,math.radians(-22),0)), (43, (0,0,0)), (48, (0,0,0)),
    (49, (0,0,0)), (55, (0,0,math.radians(22))), (61, (0,0,math.radians(-22))), (67, (0,0,0)), (72, (0,0,0)),
]
for f, rot in keys:
    head.rotation_euler = rot
    head.keyframe_insert(data_path='rotation_euler', frame=f)

if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action.name = 'Limijoy_Head_Axis_Diagnostic'
    for fc in arm.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'

scene.frame_start = 1
scene.frame_end = 72
scene.render.fps = 24
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
eng = {x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')

pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
cen = (mn + mx) * 0.5
size = mx - mn
ext = max(size)

if scene.world is None:
    scene.world = bpy.data.worlds.new('AxisWorld')
scene.world.color = (0.035, 0.035, 0.045)

# Near-front three-quarter camera so yaw/pitch/roll differences are obvious.
cam_loc = cen + Vector((ext*0.65, -ext*3.6, size.z*0.12))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = ext * 1.45
cam.rotation_euler = (cen - cam.location).to_track_quat('-Z','Y').to_euler()
scene.camera = cam

for loc,en,rad in [
    (cen+Vector((ext*2,-ext*2,ext*2)), 900, ext*2),
    (cen+Vector((-ext*2,-ext,ext)), 500, ext*2.4),
    (cen+Vector((0,ext*2,ext*1.5)), 550, ext*2),
]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    l=bpy.context.object; l.data.energy=en; l.data.size=rad
    l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()

bpy.ops.mesh.primitive_plane_add(size=ext*6, location=(cen.x,cen.y,mn.z))
g=bpy.context.object
gm=bpy.data.materials.new('AxisGround'); gm.diffuse_color=(0.06,0.06,0.075,1); g.data.materials.append(gm)

for f in range(1,73):
    scene.frame_set(f)
    scene.render.filepath = str(OUT / f'axis_{f:03d}.png')
    bpy.ops.render.render(write_still=True)

print('Rendered 72-frame Limijoy head-axis diagnostic: X then Y then Z.')