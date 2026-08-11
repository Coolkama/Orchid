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

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armatures = [o for o in scene.objects if o.type == "ARMATURE"]
meshes = [o for o in scene.objects if o.type == "MESH"]
if len(armatures) != 1 or not meshes:
    raise RuntimeError(f"Expected one armature and at least one mesh; got {len(armatures)} armatures, {len(meshes)} meshes")
arm = armatures[0]

# Work from the generated hierarchy rather than assuming Meshy's anonymous bone numbers.
bones = list(arm.data.bones)
roots = [b for b in bones if b.parent is None]
leaves = [b for b in bones if not b.children]

# Find a conservative torso candidate: a deform bone near the model centre with multiple descendants.
def descendants(b):
    out = []
    stack = list(b.children)
    while stack:
        x = stack.pop()
        out.append(x)
        stack.extend(x.children)
    return out

centre_z = sum((o.dimensions.z for o in meshes), 0.0) / max(1, len(meshes)) * 0.5
candidates = sorted(
    [b for b in bones if b.use_deform],
    key=lambda b: (-len(descendants(b)), abs(b.head_local.x), abs(b.head_local.y), abs(b.head_local.z - centre_z)),
)
if not candidates:
    raise RuntimeError("No deform bones found")
torso = candidates[0]

# The proof deliberately uses only existing weights. This avoids damaging the production mesh while
# demonstrating that Orchid can author restrained motion on top of a Meshy Smart Rig.
scene.frame_start = 1
scene.frame_end = 48
scene.render.fps = 24
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="POSE")
pb = arm.pose.bones[torso.name]
pb.rotation_mode = "XYZ"

# Gentle breathing/weight shift: 2 seconds, loopable, intentionally tiny angles.
keys = [
    (1, 0.0, 0.0),
    (12, math.radians(1.2), math.radians(-0.8)),
    (24, 0.0, 0.0),
    (36, math.radians(-1.0), math.radians(0.8)),
    (48, 0.0, 0.0),
]
for frame, rx, rz in keys:
    pb.rotation_euler.x = rx
    pb.rotation_euler.z = rz
    pb.keyframe_insert(data_path="rotation_euler", frame=frame)

bpy.ops.object.mode_set(mode="OBJECT")
if arm.animation_data and arm.animation_data.action:
    action = arm.animation_data.action
    action.name = "Orchid_Prototype_Idle"
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"

# Export an animated GLB. The original source remains untouched in the repository.
export_path = OUTPUT / "glimmerkin-prototype-idle.glb"
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
    "bone_count": len(bones),
    "root_bones": [b.name for b in roots],
    "leaf_bones": [b.name for b in leaves],
    "prototype_driver_bone": torso.name,
    "animation": "Orchid_Prototype_Idle",
    "frames": [scene.frame_start, scene.frame_end],
    "fps": scene.render.fps,
    "principle": "Minimal proof using existing Meshy weights; no production-detail rigging.",
}
(OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "prototype-motion.blend"))
print(json.dumps(report, indent=2))
