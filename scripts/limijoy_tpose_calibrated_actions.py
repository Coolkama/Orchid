"""Calibrate the 45-bone T-pose Limijoy rig into a relaxed semantic neutral.

Meshy correctly keeps the arms separate from the torso, but the imported bind pose
is a true T-pose. Limijoy behaviour expects a relaxed neutral pose. This review
rotates only the upper-arm controls into a gentle down/out neutral while leaving
the shoulder-girdle/collar controls untouched, records that pose as the semantic
rest state, then reuses the existing wave/carry/push and walking-arm-swing actions
unchanged.
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
from limijoy_semantic_actions import LimijoySemanticActions  # noqa: E402

OUTPUT = ROOT / "output" / "limijoy-tpose-calibrated-actions"
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


def calibrate_relaxed_neutral(actions: LimijoySemanticActions) -> dict[str, object]:
    """Turn only the upper arms down; preserve the girdle/collar and bind rig."""
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

        # IMPORTANT: the girdle bones influence collar/torso vertices in this
        # Meshy generation. Rotating them pinches the chest. Apply the neutral
        # drop at the upper arm itself so the torso remains structurally still.
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
            "requested_direction": tuple(float(v) for v in target),
            "achieved_direction": tuple(float(v) for v in achieved),
            "angular_error_degrees": float(achieved.angle(target) * 57.29577951308232),
            "neutral_hand": tuple(float(v) for v in controller.rest_hand_target),
            "neutral_shoulder": tuple(float(v) for v in controller.rest_shoulder),
            "girdle_matrix_basis_drift": max(
                abs(float(controller.girdle.matrix_basis[r][c]) - float(controller.girdle.matrix_basis.Identity(4)[r][c]))
                for r in range(4)
                for c in range(4)
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


def protected_drift(armature: bpy.types.Object) -> float:
    maximum = 0.0
    for name in PROTECTED_BONES:
        bone = armature.pose.bones.get(name)
        if bone is None:
            return float("inf")
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
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE!r}, resolved {profile.name!r}")

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.030)
calibration = calibrate_relaxed_neutral(actions)
length = actions.reference_chain_length
shoulder_centre = actions.shoulder_centre()

carry_centre = shoulder_centre + actions.forward * (length * 0.62) - actions.up * (length * 0.42)
push_centre = shoulder_centre + actions.forward * (length * 0.82) - actions.up * (length * 0.05)

clips = [
    actions.wave(side="right", start_frame=1),
    actions.carry(carry_centre, start_frame=70),
    actions.push(push_centre, start_frame=125),
    actions.walking_arm_swing(start_frame=185, amplitude=0.18, release_at_end=True),
]
actions.set_smooth_interpolation()

carry_material = material("CarryObject", (0.20, 0.72, 1.0, 1.0))
push_material = material("PushObject", (0.75, 0.25, 1.0, 1.0))
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24,
    ring_count=12,
    radius=extent * 0.055,
    location=carry_centre + actions.forward * (extent * 0.040) + actions.up * (extent * 0.035),
)
carry_prop = bpy.context.object
carry_prop.data.materials.append(carry_material)
bpy.ops.mesh.primitive_cube_add(
    size=extent * 0.13,
    location=push_centre + actions.forward * (extent * 0.055),
)
push_prop = bpy.context.object
push_prop.data.materials.append(push_material)

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
    ("10-wave-a", clips[0].peak_frames[0], False, False),
    ("11-wave-b", clips[0].peak_frames[-1], False, False),
    ("20-carry", clips[1].peak_frames[0], True, False),
    ("30-push", clips[2].peak_frames[0], False, True),
    ("40-walk-swing-a", clips[3].peak_frames[0], False, False),
    ("41-walk-swing-b", clips[3].peak_frames[1], False, False),
)

maximum_protected_drift = 0.0
for label, frame, show_carry, show_push in review_frames:
    scene.frame_set(frame)
    carry_prop.hide_render = not show_carry
    push_prop.hide_render = not show_push
    maximum_protected_drift = max(maximum_protected_drift, protected_drift(armature))
    point_camera(camera, front, camera_target)
    render(scene, STILLS / f"{label}-front.png")
    point_camera(camera, three_quarter, camera_target)
    render(scene, STILLS / f"{label}-three-quarter.png")
    if label in {"00-neutral", "20-carry", "30-push"}:
        point_camera(camera, side, camera_target)
        render(scene, STILLS / f"{label}-side.png")

if maximum_protected_drift > 1.0e-6:
    raise RuntimeError(
        f"Finger/lower-foot passive bones drifted independently: {maximum_protected_drift:.9f}"
    )

if max(entry["girdle_matrix_basis_drift"] for entry in calibration.values()) > 1.0e-6:
    raise RuntimeError("Relaxed-neutral calibration unexpectedly moved a girdle bone")

applications = [application for clip in clips for application in clip.applications]
arm_results = [arm for application in applications for arm in application.arms]
report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "semantic_neutral_policy": "T-pose bind retained; upper-arm pose calibrated down/out; girdle/collar untouched",
    "neutral_calibration": calibration,
    "chain_length": length,
    "clips": [asdict(clip) for clip in clips],
    "maximum_target_error": max(arm.reach.target_error for arm in arm_results),
    "maximum_palm_error_degrees": max(arm.reach.palm_error_degrees for arm in arm_results),
    "clamped_target_count": sum(arm.target_was_clamped for arm in arm_results),
    "protected_bone_maximum_matrix_basis_drift": maximum_protected_drift,
    "leg_bones_touched": False,
    "visual_acceptance_focus": [
        "relaxed neutral arms without collar/chest pinch",
        "wave rises above shoulder rather than remaining in T-pose",
        "belly side silhouette stays stable during carry/push",
        "hands clear the belly",
        "finger branches inherit only",
    ],
}
(OUTPUT / "calibrated-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "tpose-calibrated-actions.blend"))
print(json.dumps(report, indent=2))
