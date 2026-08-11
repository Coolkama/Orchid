import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "prototype-motion"
OUTPUT.mkdir(parents=True, exist_ok=True)

model_arg = next((a for a in sys.argv if a.startswith("--model=")), None)
model_path = Path(model_arg.split("=", 1)[1]) if model_arg else ROOT / "assets" / "models" / "glimmerkin.glb"
if not model_path.is_absolute():
    model_path = ROOT / model_path
if not model_path.exists():
    raise FileNotFoundError(model_path)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armatures = [o for o in scene.objects if o.type == "ARMATURE"]
meshes = [o for o in scene.objects if o.type == "MESH"]
if len(armatures) != 1 or not meshes:
    raise RuntimeError(f"Expected one armature and at least one mesh; got {len(armatures)} armatures, {len(meshes)} meshes")
arm = armatures[0]

# Discover the Smart Rig structurally. Meshy names the bones anonymously, so Orchid should
# understand branch roles instead of depending on Bone_### values.
roots = [b for b in arm.data.bones if b.parent is None]
if len(roots) != 1:
    raise RuntimeError(f"Expected one root bone, found {len(roots)}")
root = roots[0]
if len(root.children) != 1:
    raise RuntimeError("Unexpected Smart Rig root structure")
pelvis = root.children[0]

pelvis_children = list(pelvis.children)
spine_root = min(pelvis_children, key=lambda b: abs(b.head_local.x))
leg_roots = [b for b in pelvis_children if b != spine_root]

# Follow the centred single-child spine until the shoulder/chest junction.
spine_chain = [spine_root]
while len(spine_chain[-1].children) == 1:
    spine_chain.append(spine_chain[-1].children[0])
chest = spine_chain[-1]
if len(chest.children) < 3:
    raise RuntimeError("Could not identify head/arm junction")

junction_children = list(chest.children)
head_root = min(junction_children, key=lambda b: abs(b.head_local.x))
left_arm_root = min(junction_children, key=lambda b: b.head_local.x)
right_arm_root = max(junction_children, key=lambda b: b.head_local.x)

# Set up a restrained, readable studio preview.
engine_items = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
if "BLENDER_EEVEE_NEXT" in engine_items:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
elif "BLENDER_EEVEE" in engine_items:
    scene.render.engine = "BLENDER_EEVEE"
else:
    scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 48

# Bounds for camera/light placement.
points = []
for obj in meshes:
    points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
centre = (mins + maxs) * 0.5
size = maxs - mins
max_extent = max(size)

world = bpy.data.worlds.new("PrototypeWorld") if scene.world is None else scene.world
scene.world = world
world.color = (0.035, 0.035, 0.045)

bpy.ops.object.camera_add(location=centre + Vector((0, -max_extent * 4.0, size.z * 0.06)))
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = max_extent * 1.35
scene.camera = camera
camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()

for name, loc, energy, radius in [
    ("Key", centre + Vector((max_extent * 2.0, -max_extent * 2.0, max_extent * 2.2)), 950, max_extent * 2.0),
    ("Fill", centre + Vector((-max_extent * 1.8, -max_extent * 1.2, max_extent * 1.0)), 500, max_extent * 2.4),
    ("Rim", centre + Vector((0, max_extent * 1.8, max_extent * 1.6)), 650, max_extent * 1.8),
]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.size = radius
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

bpy.ops.mesh.primitive_plane_add(size=max_extent * 6, location=(centre.x, centre.y, mins.z - max_extent * 0.015))
ground = bpy.context.object
mat = bpy.data.materials.new("PrototypeGround")
mat.diffuse_color = (0.06, 0.06, 0.075, 1)
ground.data.materials.append(mat)

# Multi-bone test: tiny body weight shift, a modest head turn and a small right-arm lift.
# The head stays nearly rigid; there is no broad squash/stretch and no canned humanoid motion.
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="POSE")
pose_torso = arm.pose.bones[spine_root.name]
pose_head = arm.pose.bones[head_root.name]
pose_arm = arm.pose.bones[right_arm_root.name]
for pb in (pose_torso, pose_head, pose_arm):
    pb.rotation_mode = "XYZ"

keyframes = [
    (1,   0.0,  0.0,  0.0),
    (12,  0.8,  3.5,  4.0),
    (24,  0.0,  6.0,  7.0),
    (36, -0.8,  3.0,  3.5),
    (48,  0.0,  0.0,  0.0),
]
for frame, torso_z_deg, head_y_deg, arm_z_deg in keyframes:
    pose_torso.rotation_euler.z = math.radians(torso_z_deg)
    pose_head.rotation_euler.y = math.radians(head_y_deg)
    pose_arm.rotation_euler.z = math.radians(arm_z_deg)
    pose_torso.keyframe_insert(data_path="rotation_euler", frame=frame)
    pose_head.keyframe_insert(data_path="rotation_euler", frame=frame)
    pose_arm.keyframe_insert(data_path="rotation_euler", frame=frame)

bpy.ops.object.mode_set(mode="OBJECT")
action = arm.animation_data.action if arm.animation_data else None
if action:
    action.name = "Orchid_Prototype_Gesture"
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"

# Render a few decisive frames so the result can be reviewed from a phone without a 3D viewer.
preview_frames = [1, 12, 24, 36, 48]
for frame in preview_frames:
    scene.frame_set(frame)
    scene.render.filepath = str(OUTPUT / f"preview_{frame:02d}.png")
    bpy.ops.render.render(write_still=True)

# Export the animated derivative. Source asset remains untouched.
scene.frame_set(1)
export_path = OUTPUT / "glimmerkin-prototype-gesture.glb"
bpy.ops.export_scene.gltf(
    filepath=str(export_path),
    export_format="GLB",
    export_animations=True,
    export_skins=True,
    export_materials="EXPORT",
)

report = {
    "source": str(model_path.relative_to(ROOT)),
    "armature": arm.name,
    "bone_count": len(arm.data.bones),
    "discovered_roles": {
        "root": root.name,
        "pelvis": pelvis.name,
        "spine_root": spine_root.name,
        "chest": chest.name,
        "head_root": head_root.name,
        "left_arm_root": left_arm_root.name,
        "right_arm_root": right_arm_root.name,
        "leg_roots": [b.name for b in leg_roots],
    },
    "animation": "Orchid_Prototype_Gesture",
    "frames": [scene.frame_start, scene.frame_end],
    "fps": scene.render.fps,
    "preview_frames": preview_frames,
    "max_motion_degrees": {"torso": 0.8, "head": 6.0, "right_arm": 7.0},
    "principle": "Restrained multi-bone proof on existing Meshy weights; no production-detail rigging.",
}
(OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "prototype-motion.blend"))
print(json.dumps(report, indent=2))
