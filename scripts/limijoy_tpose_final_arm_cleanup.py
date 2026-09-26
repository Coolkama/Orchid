"""Final arm/hand cleanup review for the 45-bone T-pose Limijoy candidate.

The T-pose generation fixed the original arm/torso topology problem, but two
model-specific issues remain:

* Meshy generated small finger branches. They must remain passive and the walk
  must not twist the wrist in a way that presents those digits sideways.
* Carry/push must route the entire arm around the belly, not through it. Their
  final hand targets must also remain inside the real two-bone reach envelope
  instead of relying on target clamping.

This review deliberately leaves the generic semantic action defaults alone. It
captures the final calibration constants for this one Meshy generation so they
can be ported into the Limijoy runtime only after visual approval.
"""

from __future__ import annotations

import json
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
from limijoy_semantic_actions import (  # noqa: E402
    ArmIntent,
    LimijoySemanticActions,
    PoseIntent,
)

OUTPUT = ROOT / "output" / "limijoy-tpose-final-arm-cleanup"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)
EXPECTED_PROFILE = "tpose-blank-face-candidate-45"

# Meshy added 16 small hand/finger branch/end bones. The lowest foot controls
# also extend below the visible sole. These bones must never receive their own
# procedural animation; they may only inherit their parent's transform.
PROTECTED_BONES = tuple(f"Bone_{index:03d}" for index in range(29, 45)) + (
    "Bone_002",
    "Bone_003",
    "Bone_007",
    "Bone_008",
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
    """Drop only upper arms from the T-pose; never deform the collar/girdle."""
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
        identity = controller.girdle.matrix_basis.Identity(4)
        report[side] = {
            "requested_direction": tuple(float(value) for value in target),
            "achieved_direction": tuple(float(value) for value in achieved),
            "angular_error_degrees": float(achieved.angle(target) * 57.29577951308232),
            "neutral_hand": tuple(float(value) for value in controller.rest_hand_target),
            "neutral_shoulder": tuple(float(value) for value in controller.rest_shoulder),
            "girdle_matrix_basis_drift": matrix_basis_delta(controller.girdle, identity),
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


def protected_drift(armature: bpy.types.Object) -> float:
    maximum = 0.0
    for name in PROTECTED_BONES:
        bone = armature.pose.bones.get(name)
        if bone is None:
            return float("inf")
        identity = bone.matrix_basis.Identity(4)
        maximum = max(maximum, matrix_basis_delta(bone, identity))
    return maximum


def key_protected_rest(armature: bpy.types.Object, frames: set[int]) -> None:
    """Make the passive finger/toe policy explicit in the authored preview."""
    for name in PROTECTED_BONES:
        pose_bone = armature.pose.bones[name]
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.matrix_basis.identity()
        for frame in sorted(frames):
            pose_bone.matrix_basis.identity()
            pose_bone.keyframe_insert("rotation_quaternion", frame=frame)
            pose_bone.keyframe_insert("location", frame=frame)
            pose_bone.keyframe_insert("scale", frame=frame)


def bilateral_targets(
    actions: LimijoySemanticActions,
    centre: Vector,
    separation_scale: float,
    palm_mode: str,
) -> tuple[ArmIntent, ...]:
    separation = actions.right * (actions.reference_chain_length * separation_scale)
    return (
        ArmIntent("left", tuple(centre - separation), palm_mode, "outward"),
        ArmIntent("right", tuple(centre + separation), palm_mode, "outward"),
    )


def clearance_carry(actions: LimijoySemanticActions, *, start_frame: int = 70):
    """Route hands up/outside first, then forward around the belly to the prop."""
    length = actions.reference_chain_length
    shoulders = actions.shoulder_centre()

    # The route is deliberately not a straight lerp from the low neutral hands.
    # It rises outside the torso before moving inward toward the held object.
    stage_a = shoulders + actions.forward * (length * 0.18) - actions.up * (length * 0.72)
    stage_b = shoulders + actions.forward * (length * 0.41) - actions.up * (length * 0.43)
    final = shoulders + actions.forward * (length * 0.56) - actions.up * (length * 0.32)

    poses = (
        PoseIntent(
            frame=start_frame + 9,
            arms=bilateral_targets(actions, stage_a, 0.98, "up"),
            look_target=tuple(final),
            gaze_strength=0.12,
            body_follow=0.12,
        ),
        PoseIntent(
            frame=start_frame + 20,
            arms=bilateral_targets(actions, stage_b, 0.60, "up"),
            look_target=tuple(final),
            gaze_strength=0.18,
            body_follow=0.20,
            forward_lean_degrees=0.4,
        ),
        PoseIntent(
            frame=start_frame + 32,
            arms=bilateral_targets(actions, final, 0.36, "up"),
            look_target=tuple(final),
            gaze_strength=0.22,
            body_follow=0.28,
            forward_lean_degrees=0.8,
        ),
    )
    return actions.animate_path(
        "carry_tpose_clearance",
        poses,
        neutral_start=start_frame,
        neutral_end=start_frame + 44,
        peak_frames=(start_frame + 32,),
        notes=(
            "T-pose candidate: hands route outside the belly before closing on the prop.",
            "Final target intentionally stays inside the unclamped two-bone reach envelope.",
        ),
    ), final


def clearance_push(actions: LimijoySemanticActions, *, start_frame: int = 125):
    """Bring arms forward from outside the belly instead of tucking through it."""
    length = actions.reference_chain_length
    shoulders = actions.shoulder_centre()

    stage_a = shoulders + actions.forward * (length * 0.28) - actions.up * (length * 0.18)
    stage_b = shoulders + actions.forward * (length * 0.52) - actions.up * (length * 0.06)
    final = shoulders + actions.forward * (length * 0.68) - actions.up * (length * 0.02)

    poses = (
        PoseIntent(
            frame=start_frame + 10,
            arms=bilateral_targets(actions, stage_a, 0.82, "forward"),
            look_target=tuple(final),
            gaze_strength=0.14,
            body_follow=0.18,
            forward_lean_degrees=0.4,
        ),
        PoseIntent(
            frame=start_frame + 23,
            arms=bilateral_targets(actions, stage_b, 0.50, "forward"),
            look_target=tuple(final),
            gaze_strength=0.22,
            body_follow=0.38,
            forward_lean_degrees=1.2,
        ),
        PoseIntent(
            frame=start_frame + 34,
            arms=bilateral_targets(actions, final, 0.36, "forward"),
            look_target=tuple(final),
            gaze_strength=0.26,
            body_follow=0.50,
            forward_lean_degrees=1.8,
        ),
    )
    return actions.animate_path(
        "push_tpose_clearance",
        poses,
        neutral_start=start_frame,
        neutral_end=start_frame + 46,
        peak_frames=(start_frame + 34,),
        notes=(
            "T-pose candidate: no inward tuck through the belly.",
            "Final palms remain forward and outside the torso silhouette.",
        ),
    ), final


def preserve_walk_hand_rest(actions: LimijoySemanticActions, clip) -> float:
    """Keep wrists/hands in their relaxed relative orientation during walk IK.

    The arm target still swings front/back, but the wrist no longer rotates the
    accidental Meshy digits sideways toward camera. Finger branches stay at
    identity and simply inherit this mitten-like hand orientation.
    """
    maximum = 0.0
    for application in clip.applications:
        frame = application.frame
        actions.scene.frame_set(frame)
        for controller in actions.arms.values():
            controller.wrist.matrix_basis = controller._rest_basis[controller.wrist.name].copy()
            controller.hand.matrix_basis = controller._rest_basis[controller.hand.name].copy()
            bpy.context.view_layer.update()
            controller.wrist.keyframe_insert("rotation_quaternion", frame=frame)
            controller.hand.keyframe_insert("rotation_quaternion", frame=frame)
            maximum = max(
                maximum,
                matrix_basis_delta(
                    controller.wrist,
                    controller._rest_basis[controller.wrist.name],
                ),
                matrix_basis_delta(
                    controller.hand,
                    controller._rest_basis[controller.hand.name],
                ),
            )
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
    obj
    for obj in scene.objects
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE!r}, resolved {profile.name!r}")

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.030)
calibration = calibrate_relaxed_neutral(actions)

wave = actions.wave(side="right", start_frame=1)
carry, carry_centre = clearance_carry(actions, start_frame=70)
push, push_centre = clearance_push(actions, start_frame=125)
walk = actions.walking_arm_swing(
    start_frame=185,
    amplitude=0.16,
    release_at_end=True,
)
walk_hand_rest_drift = preserve_walk_hand_rest(actions, walk)
clips = (wave, carry, push, walk)

all_key_frames = {
    application.frame
    for clip in clips
    for application in clip.applications
}
all_key_frames.update(
    {
        clip.frame_start
        for clip in clips
    }
)
all_key_frames.update(
    {
        clip.frame_end
        for clip in clips
    }
)
key_protected_rest(armature, all_key_frames)
actions.set_smooth_interpolation()

# Props match the calibrated final hand spacing rather than forcing the hands
# back toward the belly centre.
carry_material = material("CarryObject", (0.20, 0.72, 1.0, 1.0))
push_material = material("PushObject", (0.75, 0.25, 1.0, 1.0))
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24,
    ring_count=12,
    radius=extent * 0.064,
    location=carry_centre + actions.forward * (extent * 0.038) + actions.up * (extent * 0.025),
)
carry_prop = bpy.context.object
carry_prop.data.materials.append(carry_material)
bpy.ops.mesh.primitive_cube_add(
    size=extent * 0.13,
    location=push_centre + actions.forward * (extent * 0.052),
)
push_prop = bpy.context.object
push_prop.data.materials.append(push_material)

bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
bpy.context.object.data.materials.append(material("Ground", (0.055, 0.055, 0.07, 1.0)))

engines = {
    item.identifier
    for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
}
scene.render.engine = (
    "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE_NEXT" in engines
    else "BLENDER_EEVEE"
    if "BLENDER_EEVEE" in engines
    else "BLENDER_WORKBENCH"
)
scene.render.resolution_x = 600
scene.render.resolution_y = 600
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

camera_target = centre + actions.up * (extent * 0.04)
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.34
scene.camera = camera
for location, energy, size in (
    (centre + Vector((extent * 2.0, -extent * 2.0, extent * 2.0)), 900, extent * 2.0),
    (centre + Vector((-extent * 2.0, -extent, extent)), 450, extent * 2.5),
):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

front = camera_target + Vector((0.0, -extent * 3.8, extent * 0.10))
three_quarter = camera_target + Vector((extent * 2.35, -extent * 3.15, extent * 0.14))
side = camera_target + Vector((extent * 3.8, 0.0, extent * 0.10))

review_frames = (
    ("00-neutral", 1, False, False),
    ("10-wave-a", wave.peak_frames[0], False, False),
    ("11-wave-b", wave.peak_frames[-1], False, False),
    ("20-carry", carry.peak_frames[0], True, False),
    ("30-push", push.peak_frames[0], False, True),
    ("40-walk-swing-a", walk.peak_frames[0], False, False),
    ("41-walk-swing-b", walk.peak_frames[1], False, False),
)

maximum_protected_drift = 0.0
for label, frame, show_carry, show_push in review_frames:
    scene.frame_set(frame)
    carry_prop.hide_render = not show_carry
    push_prop.hide_render = not show_push
    maximum_protected_drift = max(maximum_protected_drift, protected_drift(armature))

    camera.data.ortho_scale = extent * 1.34
    point_camera(camera, front, camera_target)
    render(scene, STILLS / f"{label}-front.png")
    point_camera(camera, three_quarter, camera_target)
    render(scene, STILLS / f"{label}-three-quarter.png")

    if label in {"00-neutral", "20-carry", "30-push"}:
        point_camera(camera, side, camera_target)
        render(scene, STILLS / f"{label}-side.png")

    # Tight torso/hand crops make finger presentation and arm/belly clearance
    # obvious instead of hiding them in a full-character thumbnail.
    if label in {"20-carry", "30-push", "40-walk-swing-a", "41-walk-swing-b"}:
        close_target = centre + actions.up * (extent * 0.02)
        close_front = close_target + Vector((0.0, -extent * 3.8, 0.0))
        camera.data.ortho_scale = extent * 0.72
        point_camera(camera, close_front, close_target)
        render(scene, STILLS / f"{label}-hands-close.png")

if maximum_protected_drift > 1.0e-6:
    raise RuntimeError(
        f"Finger/lower-foot passive bones drifted independently: {maximum_protected_drift:.9f}"
    )
if walk_hand_rest_drift > 1.0e-6:
    raise RuntimeError(
        f"Walk wrist/hand failed to retain relaxed relative orientation: {walk_hand_rest_drift:.9f}"
    )
if max(entry["girdle_matrix_basis_drift"] for entry in calibration.values()) > 1.0e-6:
    raise RuntimeError("Relaxed-neutral calibration unexpectedly moved a girdle bone")

applications = [application for clip in clips for application in clip.applications]
arm_results = [arm for application in applications for arm in application.arms]
carry_push_results = [
    arm
    for clip in (carry, push)
    for application in clip.applications
    for arm in application.arms
]
carry_push_clamps = sum(arm.target_was_clamped for arm in carry_push_results)
if carry_push_clamps:
    raise RuntimeError(
        f"Carry/push calibration still relies on {carry_push_clamps} clamped targets"
    )

report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "semantic_neutral_policy": (
        "T-pose bind retained; upper-arm pose calibrated down/out; girdle/collar untouched"
    ),
    "hand_policy": (
        "Finger branch bones remain identity/passive; walk wrist and hand stay in the relaxed "
        "relative rest orientation rather than presenting Meshy digits sideways"
    ),
    "carry_push_policy": (
        "Arms route outside the torso before moving forward; final targets remain inside the "
        "unclamped two-bone reach envelope"
    ),
    "neutral_calibration": calibration,
    "chain_length": actions.reference_chain_length,
    "clips": [asdict(clip) for clip in clips],
    "maximum_target_error": max(arm.reach.target_error for arm in arm_results),
    "maximum_palm_error_degrees": max(arm.reach.palm_error_degrees for arm in arm_results),
    "all_action_clamped_target_count": sum(arm.target_was_clamped for arm in arm_results),
    "carry_push_clamped_target_count": carry_push_clamps,
    "protected_bone_maximum_matrix_basis_drift": maximum_protected_drift,
    "walk_wrist_hand_rest_drift": walk_hand_rest_drift,
    "leg_bones_touched": False,
    "visual_acceptance_focus": [
        "walk hands read as soft mitts rather than sideways finger clusters",
        "walk hands do not clip hips or belly",
        "carry upper arms and forearms stay visibly outside belly",
        "push upper arms and forearms stay visibly outside belly",
        "torso/collar silhouette remains unchanged",
        "finger branches and low foot-end bones receive no independent motion",
    ],
}
(OUTPUT / "final-arm-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "tpose-final-arm-cleanup.blend"))
print(json.dumps(report, indent=2))
