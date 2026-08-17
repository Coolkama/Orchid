"""Review world-stable walk hands for the 45-bone T-pose Limijoy candidate.

The previous final-arm pass proved carry/push can stay outside the belly with
zero target clamps.  Its remaining visual failure is walking: preserving the
wrist/hand LOCAL rest basis still lets the swinging arm rotate Meshy's accidental
finger geometry toward camera.  This focused review keeps the hand and wrist at
their relaxed NEUTRAL WORLD orientation while the upper arm swings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from limijoy_rig_profile_adapter import activate_semantic_rig_profile  # noqa: E402
from limijoy_semantic_actions import LimijoySemanticActions  # noqa: E402

OUTPUT = ROOT / "output" / "limijoy-tpose-walk-world-hands"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)
EXPECTED_PROFILE = "tpose-blank-face-candidate-45"
PROTECTED_BONES = tuple(f"Bone_{index:03d}" for index in range(29, 45)) + (
    "Bone_002", "Bone_003", "Bone_007", "Bone_008",
)


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def bounds(mesh: bpy.types.Object):
    points = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    minimum = Vector(tuple(min(point[a] for point in points) for a in range(3)))
    maximum = Vector(tuple(max(point[a] for point in points) for a in range(3)))
    centre = (minimum + maximum) * 0.5
    return minimum, maximum, centre, max(maximum - minimum)


def material(name: str, colour):
    result = bpy.data.materials.new(name)
    result.diffuse_color = colour
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = colour
        shader.inputs["Roughness"].default_value = 0.34
    return result


def calibrate_relaxed_neutral(actions: LimijoySemanticActions):
    for controller in actions.arms.values():
        controller.ik.influence = 0.0
        bpy.context.view_layer.update()
        current = (
            controller._bone_tail_world(controller.upper)
            - controller._bone_head_world(controller.upper)
        ).normalized()
        target = (
            actions.right * (controller.side_sign * 0.20)
            - actions.up * 0.98
        ).normalized()
        delta = current.rotation_difference(target)
        desired_world = delta @ controller._pose_bone_world_rotation(controller.upper)
        desired_world.normalize()
        desired_armature = (
            controller.armature.matrix_world.to_quaternion().inverted()
            @ desired_world
        )
        matrix = desired_armature.to_matrix().to_4x4()
        matrix.translation = controller.upper.head.copy()
        controller.upper.matrix = matrix
        bpy.context.view_layer.update()

        controlled = (
            controller.girdle,
            controller.upper,
            controller.elbow,
            controller.wrist,
            controller.hand,
        )
        controller._rest_basis = {
            bone.name: bone.matrix_basis.copy()
            for bone in controlled
        }
        controller.rest_hand_target = controller._bone_tail_world(controller.elbow)
        controller.rest_shoulder = controller._bone_head_world(controller.upper)
        controller.hand_target.location = controller.rest_hand_target
        controller.elbow_pole.location = controller.rest_shoulder
        controller.palm_target.location = controller.rest_hand_target

    actions.reference_shoulders = {
        side: controller.rest_shoulder.copy()
        for side, controller in actions.arms.items()
    }
    actions.reference_hands = {
        side: controller.rest_hand_target.copy()
        for side, controller in actions.arms.items()
    }


def set_world_rotation(controller, pose_bone, world_rotation) -> None:
    desired_armature = (
        controller.armature.matrix_world.to_quaternion().inverted()
        @ world_rotation
    )
    matrix = desired_armature.to_matrix().to_4x4()
    matrix.translation = pose_bone.head.copy()
    pose_bone.matrix = matrix


def rotation_error_degrees(left, right) -> float:
    delta = left.rotation_difference(right)
    return float(delta.angle * 57.29577951308232)


def passive_bone_drift(armature: bpy.types.Object) -> float:
    maximum = 0.0
    for name in PROTECTED_BONES:
        bone = armature.pose.bones[name]
        identity = bone.matrix_basis.Identity(4)
        maximum = max(
            maximum,
            max(
                abs(float(bone.matrix_basis[r][c]) - float(identity[r][c]))
                for r in range(4)
                for c in range(4)
            ),
        )
    return maximum


def render(scene: bpy.types.Scene, camera, location: Vector, target: Vector, path: Path):
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(path)
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)


model_path = argument_path(
    "model",
    ROOT / "assets" / "models" / "glimmerkin-tpose-blank-face-candidate.glb",
)
if not model_path.exists():
    raise FileNotFoundError(model_path)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
mesh = max(
    (
        obj for obj in scene.objects
        if obj.type == "MESH"
        and any(mod.type == "ARMATURE" for mod in obj.modifiers)
    ),
    key=lambda obj: len(obj.data.vertices),
)
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE}, resolved {profile.name}")

minimum, maximum, centre, extent = bounds(mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.030)
calibrate_relaxed_neutral(actions)

# Capture the neutral WORLD rotations before any walk IK is authored.  These are
# the orientations that make the hand silhouette read like the original soft paw.
neutral_world = {
    side: {
        "wrist": controller._pose_bone_world_rotation(controller.wrist).copy(),
        "hand": controller._pose_bone_world_rotation(controller.hand).copy(),
    }
    for side, controller in actions.arms.items()
}

walk = actions.walking_arm_swing(
    start_frame=1,
    amplitude=0.16,
    release_at_end=True,
)

maximum_world_error = 0.0
for application in walk.applications:
    scene.frame_set(application.frame)
    for side, controller in actions.arms.items():
        set_world_rotation(controller, controller.wrist, neutral_world[side]["wrist"])
        bpy.context.view_layer.update()
        set_world_rotation(controller, controller.hand, neutral_world[side]["hand"])
        bpy.context.view_layer.update()
        controller.wrist.keyframe_insert("rotation_quaternion", frame=application.frame)
        controller.hand.keyframe_insert("rotation_quaternion", frame=application.frame)
        maximum_world_error = max(
            maximum_world_error,
            rotation_error_degrees(
                controller._pose_bone_world_rotation(controller.wrist),
                neutral_world[side]["wrist"],
            ),
            rotation_error_degrees(
                controller._pose_bone_world_rotation(controller.hand),
                neutral_world[side]["hand"],
            ),
        )

# Finger branches and low foot ends remain identity/passive at every authored key.
for name in PROTECTED_BONES:
    bone = armature.pose.bones[name]
    bone.rotation_mode = "QUATERNION"
    for application in walk.applications:
        bone.matrix_basis.identity()
        bone.keyframe_insert("rotation_quaternion", frame=application.frame)
        bone.keyframe_insert("location", frame=application.frame)
        bone.keyframe_insert("scale", frame=application.frame)

actions.set_smooth_interpolation()

bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
bpy.context.object.data.materials.append(material("Ground", (0.055, 0.055, 0.07, 1.0)))
engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
scene.render.engine = (
    "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines
    else "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines
    else "BLENDER_WORKBENCH"
)
scene.render.resolution_x = 700
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

for location, energy, size in (
    (centre + Vector((extent * 2.0, -extent * 2.0, extent * 2.0)), 900, extent * 2.0),
    (centre + Vector((-extent * 2.0, -extent, extent)), 450, extent * 2.5),
):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (centre - location).to_track_quat("-Z", "Y").to_euler()

bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
scene.camera = camera
camera_target = centre + actions.up * (extent * 0.04)
front = camera_target + Vector((0.0, -extent * 3.8, extent * 0.10))
three_quarter = camera_target + Vector((extent * 2.35, -extent * 3.15, extent * 0.14))

# Include neutral plus both swing extremes, with full and tight hand views.
frames = (
    ("00-neutral", walk.frame_start),
    ("10-walk-a", walk.peak_frames[0]),
    ("11-walk-b", walk.peak_frames[1]),
)
for label, frame in frames:
    scene.frame_set(frame)
    camera.data.ortho_scale = extent * 1.34
    render(scene, camera, front, camera_target, STILLS / f"{label}-front.png")
    render(scene, camera, three_quarter, camera_target, STILLS / f"{label}-three-quarter.png")

    close_target = centre + actions.up * (extent * 0.00)
    close_front = close_target + Vector((0.0, -extent * 3.8, 0.0))
    camera.data.ortho_scale = extent * 0.58
    render(scene, camera, close_front, close_target, STILLS / f"{label}-hands-close.png")

maximum_passive_drift = 0.0
for _, frame in frames:
    scene.frame_set(frame)
    maximum_passive_drift = max(maximum_passive_drift, passive_bone_drift(armature))

if maximum_world_error > 0.05:
    raise RuntimeError(f"Walk hand world-orientation error {maximum_world_error:.6f} degrees")
if maximum_passive_drift > 1.0e-6:
    raise RuntimeError(f"Finger/toe-end drift {maximum_passive_drift:.9f}")

report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "walk_policy": (
        "Upper arms swing normally; wrist and hand retain relaxed neutral WORLD rotation so "
        "Meshy's accidental fingers do not rotate toward camera"
    ),
    "maximum_wrist_hand_world_orientation_error_degrees": maximum_world_error,
    "protected_bone_maximum_matrix_basis_drift": maximum_passive_drift,
    "walk_peak_frames": list(walk.peak_frames),
    "visual_acceptance_focus": [
        "both walk extremes read as soft hanging paws",
        "no sideways finger cluster is presented to camera",
        "hands remain clear of belly and hips",
    ],
}
(OUTPUT / "walk-world-hand-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "walk-world-hands.blend"))
print(json.dumps(report, indent=2))
