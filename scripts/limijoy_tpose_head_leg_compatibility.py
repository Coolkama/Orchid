"""Confirm head and leg compatibility on the current 45-bone T-pose Limijoy.

This is deliberately a compatibility review, not a new locomotion system.  The
current candidate is first calibrated into the same relaxed upper-arm neutral
used by the accepted arm pass.  We then exercise the existing useful leg joints
and the semantic head-look controller on that exact rig generation.

Acceptance goals:
* both hip/knee chains visibly deform their own leg;
* opposite-leg controls remain untouched;
* protected lower-foot/finger branches receive no independent motion;
* semantic look left/right/up/down moves neck/head on the 45-bone profile;
* torso remains neutral because this review requests zero body follow.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from limijoy_rig_profile_adapter import activate_semantic_rig_profile  # noqa: E402
from limijoy_semantic_actions import LimijoySemanticActions  # noqa: E402

OUTPUT = ROOT / "output" / "limijoy-tpose-head-leg-compatibility"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)
EXPECTED_PROFILE = "tpose-blank-face-candidate-45"

LEFT_LEG = ("Bone_006", "Bone_005", "Bone_004")
RIGHT_LEG = ("Bone_011", "Bone_010", "Bone_009")
PROTECTED_BONES = tuple(f"Bone_{index:03d}" for index in range(29, 45)) + (
    "Bone_002", "Bone_003", "Bone_007", "Bone_008",
)


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def model_bounds(mesh: bpy.types.Object) -> tuple[Vector, Vector, Vector, float]:
    points = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    minimum = Vector(tuple(min(point[a] for point in points) for a in range(3)))
    maximum = Vector(tuple(max(point[a] for point in points) for a in range(3)))
    centre = (minimum + maximum) * 0.5
    return minimum, maximum, centre, max(maximum - minimum)


def material(name: str, colour: tuple[float, float, float, float]) -> bpy.types.Material:
    result = bpy.data.materials.new(name)
    result.diffuse_color = colour
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = colour
        shader.inputs["Roughness"].default_value = 0.34
    return result


def render(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def point_camera(camera: bpy.types.Object, location: Vector, target: Vector) -> None:
    camera.location = location
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()


def matrix_basis_delta(pose_bone: bpy.types.PoseBone, reference) -> float:
    return max(
        abs(float(pose_bone.matrix_basis[row][column]) - float(reference[row][column]))
        for row in range(4)
        for column in range(4)
    )


def calibrate_relaxed_neutral(actions: LimijoySemanticActions) -> dict[str, object]:
    """Match the accepted arm pass: drop upper arms, never the collar/girdle."""
    report = {}
    for side, controller in actions.arms.items():
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
        desired_matrix = desired_armature.to_matrix().to_4x4()
        desired_matrix.translation = controller.upper.head.copy()
        controller.upper.matrix = desired_matrix
        bpy.context.view_layer.update()

        controlled = (
            controller.girdle,
            controller.upper,
            controller.elbow,
            controller.wrist,
            controller.hand,
        )
        controller._rest_basis = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in controlled
        }
        controller.rest_hand_target = controller._bone_tail_world(controller.elbow)
        controller.rest_shoulder = controller._bone_head_world(controller.upper)
        controller.hand_target.location = controller.rest_hand_target
        controller.elbow_pole.location = controller.rest_shoulder
        controller.palm_target.location = controller.rest_hand_target
        achieved = (
            controller._bone_tail_world(controller.upper)
            - controller._bone_head_world(controller.upper)
        ).normalized()
        report[side] = {
            "angular_error_degrees": float(achieved.angle(target) * 57.29577951308232),
            "girdle_drift": matrix_basis_delta(
                controller.girdle,
                controller.girdle.matrix_basis.Identity(4),
            ),
        }

    actions.reference_shoulders = {
        side: controller.rest_shoulder.copy()
        for side, controller in actions.arms.items()
    }
    actions.reference_hands = {
        side: controller.rest_hand_target.copy()
        for side, controller in actions.arms.items()
    }
    return report


def bone_point_world(armature: bpy.types.Object, bone_name: str, *, tail: bool = True) -> Vector:
    bone = armature.pose.bones[bone_name]
    return armature.matrix_world @ (bone.tail if tail else bone.head)


def rotate_local_x(armature: bpy.types.Object, bone_name: str, degrees: float) -> None:
    bone = armature.pose.bones[bone_name]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (math.radians(degrees), 0.0, 0.0)
    bpy.context.view_layer.update()


def protected_drift(armature: bpy.types.Object) -> float:
    identity = None
    maximum = 0.0
    for name in PROTECTED_BONES:
        bone = armature.pose.bones.get(name)
        if bone is None:
            return float("inf")
        if identity is None:
            identity = bone.matrix_basis.Identity(4)
        maximum = max(maximum, matrix_basis_delta(bone, identity))
    return maximum


model_path = argument_path(
    "model",
    ROOT / "assets" / "models" / "glimmerkin-tpose-blank-face-candidate.glb",
)
if not model_path.exists():
    raise FileNotFoundError(f"T-pose candidate GLB missing: {model_path}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
skinned_meshes = [
    obj for obj in scene.objects
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE!r}, resolved {profile.name!r}")

required = set(LEFT_LEG + RIGHT_LEG + PROTECTED_BONES)
required.update(profile.body.values())
missing = sorted(required - set(armature.pose.bones.keys()))
if missing:
    raise RuntimeError(f"Compatibility review bones missing: {missing}")

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.030)
arm_calibration = calibrate_relaxed_neutral(actions)

# Capture the exact relaxed baseline. Every diagnostic pose starts here so the
# arm solution cannot leak into head/leg conclusions and poses cannot accumulate.
baseline = {
    bone.name: bone.matrix_basis.copy()
    for bone in armature.pose.bones
}


def restore_baseline() -> None:
    for name, matrix in baseline.items():
        armature.pose.bones[name].matrix_basis = matrix.copy()
    bpy.context.view_layer.update()


# Preview environment.
bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
bpy.context.object.data.materials.append(material("Ground", (0.055, 0.055, 0.07, 1.0)))
engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
scene.render.engine = (
    "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines
    else "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines
    else "BLENDER_WORKBENCH"
)
scene.render.resolution_x = 560
scene.render.resolution_y = 560
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

camera_target = centre + Vector((0.0, 0.0, extent * 0.03))
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.34
scene.camera = camera
front = camera_target + Vector((0.0, -extent * 3.8, extent * 0.08))
three_quarter = camera_target + Vector((extent * 2.30, -extent * 3.15, extent * 0.12))
side = camera_target + Vector((extent * 3.8, 0.0, extent * 0.08))
for location, energy, size in (
    (centre + Vector((extent * 2.0, -extent * 2.0, extent * 2.0)), 900, extent * 2.0),
    (centre + Vector((-extent * 2.0, -extent, extent)), 450, extent * 2.5),
):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()


def render_front(label: str) -> None:
    point_camera(camera, front, camera_target)
    render(scene, STILLS / f"{label}-front.png")


def render_side(label: str) -> None:
    point_camera(camera, side, camera_target)
    render(scene, STILLS / f"{label}-side.png")


def render_three_quarter(label: str) -> None:
    point_camera(camera, three_quarter, camera_target)
    render(scene, STILLS / f"{label}-three-quarter.png")


restore_baseline()
render_front("00-neutral")
render_three_quarter("00-neutral")

# Leg articulation. Bone_006/011 are the upper leg controls and Bone_005/010
# are the next useful flex joints. The lower terminal branches stay protected.
leg_report = {}
for label, joint, probe, opposite in (
    ("10-left-hip", "Bone_006", "Bone_004", RIGHT_LEG),
    ("11-left-knee", "Bone_005", "Bone_004", RIGHT_LEG),
    ("20-right-hip", "Bone_011", "Bone_009", LEFT_LEG),
    ("21-right-knee", "Bone_010", "Bone_009", LEFT_LEG),
):
    restore_baseline()
    before = bone_point_world(armature, probe)
    rotate_local_x(armature, joint, 18.0)
    after = bone_point_world(armature, probe)
    displacement = float((after - before).length)
    opposite_drift = max(
        matrix_basis_delta(armature.pose.bones[name], baseline[name])
        for name in opposite
    )
    leg_report[label] = {
        "joint": joint,
        "probe": probe,
        "probe_displacement": displacement,
        "probe_displacement_fraction_of_extent": displacement / extent,
        "opposite_leg_matrix_basis_drift": opposite_drift,
    }
    render_front(label)
    render_side(label)

# Semantic head look on the resolved 45-bone profile. Zero body follow isolates
# the neck/head and explicitly proves that the torso stays neutral.
head_origin = actions.body.look_origin()
character_rotation = armature.matrix_world.to_quaternion()
forward = (character_rotation @ Vector((0.0, -1.0, 0.0))).normalized()
right = (character_rotation @ Vector((1.0, 0.0, 0.0))).normalized()
up = (character_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
head_targets = {
    "30-head-left": head_origin + forward * (extent * 2.0) - right * (extent * 0.90),
    "31-head-right": head_origin + forward * (extent * 2.0) + right * (extent * 0.90),
    "32-head-up": head_origin + forward * (extent * 2.0) + up * (extent * 0.65),
    "33-head-down": head_origin + forward * (extent * 2.0) - up * (extent * 0.65),
}
head_report = {}
for label, target in head_targets.items():
    restore_baseline()
    result = actions.body.look_at(target, strength=1.0, body_follow=0.0)
    head_drift = matrix_basis_delta(actions.body.head, baseline[actions.body.head.name])
    neck_drift = matrix_basis_delta(actions.body.neck, baseline[actions.body.neck.name])
    torso_drift = matrix_basis_delta(actions.body.torso, baseline[actions.body.torso.name])
    head_report[label] = {
        **asdict(result),
        "head_matrix_basis_drift": head_drift,
        "neck_matrix_basis_drift": neck_drift,
        "torso_matrix_basis_drift": torso_drift,
    }
    render_front(label)
    render_three_quarter(label)

# Strict compatibility checks.
minimum_leg_motion = extent * 0.010
if any(item["probe_displacement"] < minimum_leg_motion for item in leg_report.values()):
    raise RuntimeError(
        f"A useful leg joint failed to move its chain by at least {minimum_leg_motion:.6f}"
    )
if any(item["opposite_leg_matrix_basis_drift"] > 1.0e-6 for item in leg_report.values()):
    raise RuntimeError("Leg articulation leaked independent motion into the opposite leg")
if max(entry["girdle_drift"] for entry in arm_calibration.values()) > 1.0e-6:
    raise RuntimeError("Relaxed arm calibration moved a girdle/collar bone")
if protected_drift(armature) > 1.0e-6:
    raise RuntimeError("Protected finger/lower-foot bones received independent motion")
if any(entry["head_matrix_basis_drift"] < 1.0e-5 for entry in head_report.values()):
    raise RuntimeError("A semantic look target failed to move the head")
if any(entry["neck_matrix_basis_drift"] < 1.0e-5 for entry in head_report.values()):
    raise RuntimeError("A semantic look target failed to move the neck")
if any(entry["torso_matrix_basis_drift"] > 1.0e-6 for entry in head_report.values()):
    raise RuntimeError("Head-only review unexpectedly moved the torso")

report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "arm_neutral": arm_calibration,
    "leg_controls": {
        "left": LEFT_LEG,
        "right": RIGHT_LEG,
        "policy": "upper leg/knee useful; terminal lower-foot branches remain passive",
    },
    "leg_results": leg_report,
    "head_bones": dict(profile.body),
    "head_results": head_report,
    "protected_bone_maximum_matrix_basis_drift": protected_drift(armature),
    "acceptance": {
        "both_leg_chains_move": True,
        "opposite_leg_stays_independent": True,
        "head_turns_left_right_up_down": True,
        "torso_stays_neutral_for_head_only_look": True,
        "protected_end_bones_stay_passive": True,
    },
}
(OUTPUT / "compatibility-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "tpose-head-leg-compatibility.blend"))
print(json.dumps(report, indent=2))
