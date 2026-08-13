import bpy, math, sys, subprocess
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'limijoy-reach'
FR = OUT / 'frames'
FR.mkdir(parents=True, exist_ok=True)

arg = next((x for x in sys.argv if x.startswith('--model=')), None)
model = Path(arg.split('=',1)[1]) if arg else ROOT / 'assets/models/glimmerkin.glb'
if not model.is_absolute():
    model = ROOT / model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
main = max(
    [o for o in scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)],
    key=lambda o: len(o.data.vertices)
)

bones = {
    'girdle': 'Bone_023',
    'upper': 'Bone_022',
    'elbow': 'Bone_021',
    'wrist': 'Bone_020',
    'hand': 'Bone_019',
    'head': 'Bone_034',
}
for name in bones.values():
    arm.pose.bones[name].rotation_mode = 'XYZ'
    arm.pose.bones[name].rotation_euler = (0,0,0)
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action = None
bpy.context.view_layer.update()

pts = [main.matrix_world @ Vector(c) for c in main.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
cen = (mn + mx) * 0.5
ext = max(mx - mn)

# The rig map showed that raw local Euler angles are poor semantic controls.
# For gross reach placement, drive the 2-bone upper-arm/elbow chain toward a world-space target instead.
elbow = arm.pose.bones[bones['elbow']]
rest_tip = arm.matrix_world @ elbow.tail.copy()
shoulder = arm.matrix_world @ arm.pose.bones[bones['upper']].head.copy()

# Limijoy forward is world -Y. Aim roughly straight ahead at shoulder/chest height.
target_end = Vector((shoulder.x, shoulder.y - ext * 0.52, shoulder.z + ext * 0.02))
# Keep the elbow outside the torso on Limijoy's right.
pole_pos = Vector((shoulder.x + ext * 0.48, shoulder.y - ext * 0.16, shoulder.z - ext * 0.12))

def add_empty(name, location):
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=location)
    obj = bpy.context.object
    obj.name = name
    obj.empty_display_size = ext * 0.06
    return obj

target = add_empty('ReachTarget', rest_tip)
pole = add_empty('ReachPole', pole_pos)

constraint = elbow.constraints.new('IK')
constraint.name = 'SemanticReachIK'
constraint.target = target
constraint.pole_target = pole
constraint.chain_count = 2
constraint.use_tail = True
constraint.iterations = 64

def key_target(frame, location):
    target.location = location
    target.keyframe_insert('location', frame=frame)

def key_rot(bone_name, frame, xyz_degrees):
    pb = arm.pose.bones[bone_name]
    pb.rotation_euler = tuple(math.radians(v) for v in xyz_degrees)
    pb.keyframe_insert('rotation_euler', frame=frame)

key_target(1, rest_tip)
key_target(9, rest_tip.lerp(target_end, 0.25))
key_target(19, rest_tip.lerp(target_end, 0.72))
key_target(29, target_end)
key_target(39, target_end)
key_target(49, rest_tip.lerp(target_end, 0.30))
key_target(59, rest_tip)

# Distal finishing only after gross placement. These are intentionally modest.
for f, v in [(1,0),(9,4),(19,12),(29,20),(39,20),(49,6),(59,0)]:
    key_rot(bones['wrist'], f, (0, v, 0))
for f, v in [(1,0),(19,-4),(29,-7),(39,-7),(49,-2),(59,0)]:
    key_rot(bones['hand'], f, (0, v, 0))
for f, v in [(1,0),(9,-2),(19,-5),(29,-8),(39,-8),(49,-3),(59,0)]:
    key_rot(bones['head'], f, (0, v, 0))

if target.animation_data and target.animation_data.action:
    for fc in target.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
if arm.animation_data and arm.animation_data.action:
    for fc in arm.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'

scene.frame_start = 1
scene.frame_end = 59
scene.render.fps = 24

bpy.ops.mesh.primitive_plane_add(size=ext*6, location=(cen.x, cen.y, mn.z))
ground_mat = bpy.data.materials.new('Ground')
ground_mat.diffuse_color = (.055,.055,.07,1)
bpy.context.object.data.materials.append(ground_mat)

engines = {x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in engines else 'BLENDER_WORKBENCH')
scene.render.resolution_x = scene.render.resolution_y = 384
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(FR / 'frame_')
if scene.world is None:
    scene.world = bpy.data.worlds.new('World')
scene.world.color = (.035,.035,.045)

camera_loc = cen + Vector((ext*2.15, -ext*3.2, ext*.35))
bpy.ops.object.camera_add(location=camera_loc)
cam = bpy.context.object
cam.data.type = 'ORTHO'
cam.data.ortho_scale = ext * 1.42
cam.rotation_euler = (cen - cam.location).to_track_quat('-Z','Y').to_euler()
scene.camera = cam
for loc, energy, size in [
    (cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),
    (cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)
]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (cen-light.location).to_track_quat('-Z','Y').to_euler()

bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(OUT/'preview.mp4')], check=True)
subprocess.run(['ffmpeg','-y','-framerate','24','-i',str(FR/'frame_%04d.png'),'-vf','fps=12,scale=384:-1:flags=lanczos','-loop','0',str(OUT/'preview.gif')], check=True)
