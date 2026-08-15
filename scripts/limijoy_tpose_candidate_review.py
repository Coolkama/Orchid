"""Review the 45-bone T-pose Limijoy candidate with existing semantic actions.

The source images deliberately separated the arms from the torso.  This review
therefore concentrates on the exact failure mode of the previous Meshy asset:
wave/carry/push must move the arms without dragging or reforming the belly.

Meshy added small finger branches and lower-foot end joints.  They are treated
as passive skin-followers in this experiment: no semantic action keys or rotates
them independently.  The useful shoulder/elbow/wrist chain remains the same
five-role abstraction used by Limijoy.
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


OUTPUT = ROOT / "output" / "limijoy-tpose-candidate-review"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)

EXPECTED_PROFILE = "tpose-blank-face-candidate-45"
FINGER_BONES = tuple(
    f"Bone_{index:03d}"
    for index in (
        29, 30, 31, 32, 33, 34, 35, 36,
        37, 38, 39, 40, 41, 42, 43, 44,
    )
)
# These terminal lower-foot chains are intentionally not procedural controls.
# The screen-shot review showed some pivots below the visible sole.  Future walk
# calibration should begin one joint higher (Bone_004/Bone_009) and only use
# these if a grounded foot solver proves they are useful.
LOW_FOOT_BONES = ("Bone_002", "Bone_003", "Bone_007", "Bone_008")
PROTECTED_BONES = FINGER_BONES + LOW_FOOT_BONES


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def model_bounds(mesh: bpy.types.Object) -> tuple[Vector, Vector, Vector, float]:
    points = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
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


def keyed_bone_names(armature: bpy.types.Object) -> set[str]:
    animation_data = armature.animation_data
    if animation_data is None or animation_data.action is None:
        return set()
    result: set[str] = set()
    for fcurve in animation_data.action.fcurves:
        data_path = fcurve.data_path
        prefix = 'pose.bones["'
        if not data_path.startswith(prefix):
            continue
        remainder = data_path[len(prefix):]
        name, separator, _ = remainder.partition('"]')
        if separator:
            result.add(name)
    return result


def protected_basis_drift(armature: bpy.types.Object) -> dict[str, float]:
    """Measure independent rotation/translation applied to passive end bones."""
    result = {}
    for name in PROTECTED_BONES:
        pose_bone = armature.pose.bones.get(name)
        if pose_bone is None:
            result[name] = float("inf")
            continue
        matrix = pose_bone.matrix_basis
        identity = matrix.Identity(4)
        result[name] = max(
            abs(float(matrix[row][column]) - float(identity[row][column]))
            for row in range(4)
            for column in range(4)
        )
    return result


def vertex_group_summary(mesh: bpy.types.Object, names: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Document whether Meshy's extra branches actually carry skin influence."""
    result = {}
    for name in names:
        group = mesh.vertex_groups.get(name)
        if group is None:
            result[name] = {"weighted_vertices": 0, "weight_sum": 0.0, "maximum_weight": 0.0}
            continue
        count = 0
        weight_sum = 0.0
        maximum = 0.0
        group_index = group.index
        for vertex in mesh.data.vertices:
            for membership in vertex.groups:
                if membership.group != group_index or membership.weight <= 1.0e-8:
                    continue
                count += 1
                weight_sum += float(membership.weight)
                maximum = max(maximum, float(membership.weight))
                break
        result[name] = {
            "weighted_vertices": count,
            "weight_sum": weight_sum,
            "maximum_weight": maximum,
        }
    return result


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
if not skinned_meshes:
    raise RuntimeError("T-pose candidate contains no skinned mesh")
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE!r}, resolved {profile.name!r}")

missing_protected = [name for name in PROTECTED_BONES if name not in armature.pose.bones]
if missing_protected:
    raise RuntimeError(f"Expected passive finger/foot bones are missing: {missing_protected}")

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.030)
length = actions.reference_chain_length
shoulder_centre = actions.shoulder_centre()

# Reuse the same behaviour-level targets as the previous candidate.  Do not
# compensate for the T-pose here: the point of this pass is to see how much the
# cleaner topology/weights can tolerate without another animation redesign.
carry_centre = (
    shoulder_centre
    + actions.forward * (length * 0.62)
    - actions.up * (length * 0.42)
)
push_centre = (
    shoulder_centre
    + actions.forward * (length * 0.82)
    - actions.up * (length * 0.05)
)

clips = [
    actions.wave(side="right", start_frame=1),
    actions.carry(carry_centre, start_frame=70),
    actions.push(push_centre, start_frame=125),
    actions.walking_arm_swing(
        start_frame=185,
        amplitude=0.18,
        release_at_end=True,
    ),
]
actions.set_smooth_interpolation()

# Props clarify carry/push intent without participating in the rig calculation.
carry_material = material("CarryObject", (0.20, 0.72, 1.0, 1.0))
push_material = material("PushObject", (0.75, 0.25, 1.0, 1.0))

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24,
    ring_count=12,
    radius=extent * 0.055,
    location=(
        carry_centre
        + actions.forward * (extent * 0.040)
        + actions.up * (extent * 0.035)
    ),
)
carry_prop = bpy.context.object
carry_prop.name = "PROP_CarryObject"
carry_prop.data.materials.append(carry_material)

bpy.ops.mesh.primitive_cube_add(
    size=extent * 0.13,
    location=push_centre + actions.forward * (extent * 0.055),
)
push_prop = bpy.context.object
push_prop.name = "PROP_PushObject"
push_prop.data.materials.append(push_material)

bpy.ops.mesh.primitive_plane_add(
    size=extent * 6.0,
    location=(centre.x, centre.y, minimum.z),
)
ground = bpy.context.object
ground.name = "PreviewGround"
ground.data.materials.append(material("Ground", (0.055, 0.055, 0.07, 1.0)))

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
camera.name = "TposeCandidateReviewCamera"
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

front_location = camera_target + Vector((0.0, -extent * 3.8, extent * 0.10))
three_quarter_location = camera_target + Vector((extent * 2.35, -extent * 3.15, extent * 0.14))
side_location = camera_target + Vector((extent * 3.8, 0.0, extent * 0.10))


def set_prop_visibility(*, carry: bool, push: bool) -> None:
    carry_prop.hide_render = not carry
    push_prop.hide_render = not push


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
    set_prop_visibility(carry=show_carry, push=show_push)

    drift = protected_basis_drift(armature)
    maximum_protected_drift = max(maximum_protected_drift, max(drift.values()))

    point_camera(camera, front_location, camera_target)
    render(scene, STILLS / f"{label}-front.png")

    point_camera(camera, three_quarter_location, camera_target)
    render(scene, STILLS / f"{label}-three-quarter.png")

    # Side views are particularly useful for detecting a torso wall being pulled
    # forward by an arm, the structural failure seen in the A-pose generation.
    if label in {"00-neutral", "20-carry", "30-push"}:
        point_camera(camera, side_location, camera_target)
        render(scene, STILLS / f"{label}-side.png")

applications = [application for clip in clips for application in clip.applications]
arm_results = [arm for application in applications for arm in application.arms]
keyed = keyed_bone_names(armature)
protected_keyed = sorted(set(PROTECTED_BONES) & keyed)
if protected_keyed:
    raise RuntimeError(f"Passive finger/foot bones were keyed unexpectedly: {protected_keyed}")
if maximum_protected_drift > 1.0e-6:
    raise RuntimeError(
        "Passive finger/foot bones received independent transforms: "
        f"maximum matrix-basis drift {maximum_protected_drift:.9f}"
    )

finger_groups = vertex_group_summary(main_mesh, FINGER_BONES)
foot_groups = vertex_group_summary(main_mesh, LOW_FOOT_BONES)
report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "semantic_actions_reused_without_behaviour_changes": [
        "wave",
        "carry",
        "push",
        "walkingArmSwing",
    ],
    "semantic_bones": {
        "body": dict(profile.body),
        "right_arm": dict(profile.right_arm),
        "left_arm": dict(profile.left_arm),
    },
    "passive_finger_policy": {
        "bones": list(FINGER_BONES),
        "independently_keyed": False,
        "maximum_matrix_basis_drift": maximum_protected_drift,
        "skin_groups": finger_groups,
        "note": "Finger branches inherit hand motion only; Limijoy does not articulate them.",
    },
    "lower_foot_policy": {
        "passive_bones": list(LOW_FOOT_BONES),
        "future_control_pivots": ["Bone_004", "Bone_009"],
        "independently_keyed": False,
        "skin_groups": foot_groups,
        "note": "Below-sole/end pivots stay neutral; procedural foot animation remains disabled.",
    },
    "chain_length": length,
    "clips": [asdict(clip) for clip in clips],
    "maximum_target_error": max(arm.reach.target_error for arm in arm_results),
    "maximum_palm_error_degrees": max(arm.reach.palm_error_degrees for arm in arm_results),
    "clamped_target_count": sum(arm.target_was_clamped for arm in arm_results),
    "leg_bones_touched": False,
    "review_frames": [
        {"label": label, "frame": frame}
        for label, frame, _, _ in review_frames
    ],
    "visual_acceptance_focus": [
        "armpit gap remains clean during arm motion",
        "belly sidewall does not follow the arm",
        "carry hands clear the belly",
        "push hands clear the belly",
        "finger geometry remains passive and visually unobtrusive",
    ],
}
(OUTPUT / "review-report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

bpy.ops.wm.save_as_mainfile(
    filepath=str(OUTPUT / "tpose-candidate-review.blend")
)
print(json.dumps(report, indent=2))
