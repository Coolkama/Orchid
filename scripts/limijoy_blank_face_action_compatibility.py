"""Exercise Limijoy semantic actions on the 28-bone blank-face candidate.

The first compatibility pass proved the semantic IK itself works, but also
showed an important proportion difference: this Meshy generation has a wider
shoulder span relative to its arm length.  The legacy carry/push paths therefore
asked the hands to converge too far towards the centre and hit the reach clamp.

This pass keeps the behaviour meanings unchanged while applying candidate-only
spatial calibration: wider bilateral hand spacing and slightly closer/lower
interaction points.  Wave and walking-arm-swing continue to use the existing
shared action definitions unchanged.
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


OUTPUT = ROOT / "output" / "limijoy-blank-face-actions"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)

CANDIDATE_CALIBRATION = {
    "carry_forward_chain": 0.48,
    "carry_down_chain": 0.58,
    "carry_half_separation_chain": 0.42,
    "push_forward_chain": 0.72,
    "push_down_chain": 0.18,
    "push_tuck_forward_chain": 0.36,
    "push_tuck_down_chain": 0.12,
    "push_half_separation_chain": 0.38,
}


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def vector_tuple(value: Vector) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


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


def candidate_carry(
    actions: LimijoySemanticActions,
    *,
    start_frame: int,
):
    """Carry with spacing derived from this candidate's wider shoulders."""

    length = actions.reference_chain_length
    centre = (
        actions.shoulder_centre()
        + actions.forward * (length * CANDIDATE_CALIBRATION["carry_forward_chain"])
        - actions.up * (length * CANDIDATE_CALIBRATION["carry_down_chain"])
    )
    separation = actions.right * (
        length * CANDIDATE_CALIBRATION["carry_half_separation_chain"]
    )
    targets = {
        "left": centre - separation,
        "right": centre + separation,
    }

    def bilateral(amount: float):
        return tuple(
            ArmIntent(
                side,
                vector_tuple(actions.reference_hands[side].lerp(targets[side], amount)),
                "up",
                "outward",
            )
            for side in ("left", "right")
        )

    poses = (
        PoseIntent(
            frame=start_frame + 9,
            arms=bilateral(0.45),
            look_target=vector_tuple(centre),
            gaze_strength=0.16,
            body_follow=0.20,
        ),
        PoseIntent(
            frame=start_frame + 22,
            arms=bilateral(1.0),
            look_target=vector_tuple(centre),
            gaze_strength=0.24,
            body_follow=0.35,
            forward_lean_degrees=1.0,
        ),
        PoseIntent(
            frame=start_frame + 32,
            arms=bilateral(1.0),
            look_target=vector_tuple(centre),
            gaze_strength=0.24,
            body_follow=0.35,
            forward_lean_degrees=1.0,
        ),
    )
    clip = actions.animate_path(
        "carry_candidate_calibrated",
        poses,
        neutral_start=start_frame,
        neutral_end=start_frame + 44,
        peak_frames=(start_frame + 32,),
        notes=(
            "Same carry intent as legacy profile; candidate-only wider hand spacing.",
        ),
    )
    return clip, centre


def candidate_push(
    actions: LimijoySemanticActions,
    *,
    start_frame: int,
):
    """Push with a reachable wide stance for the candidate's shorter arm span."""

    length = actions.reference_chain_length
    shoulder_centre = actions.shoulder_centre()
    push_centre = (
        shoulder_centre
        + actions.forward * (length * CANDIDATE_CALIBRATION["push_forward_chain"])
        - actions.up * (length * CANDIDATE_CALIBRATION["push_down_chain"])
    )
    tuck_centre = (
        shoulder_centre
        + actions.forward * (length * CANDIDATE_CALIBRATION["push_tuck_forward_chain"])
        - actions.up * (length * CANDIDATE_CALIBRATION["push_tuck_down_chain"])
    )
    separation = actions.right * (
        length * CANDIDATE_CALIBRATION["push_half_separation_chain"]
    )

    def bilateral(centre_point: Vector):
        return (
            ArmIntent(
                "left",
                vector_tuple(centre_point - separation),
                "forward",
                "outward",
            ),
            ArmIntent(
                "right",
                vector_tuple(centre_point + separation),
                "forward",
                "outward",
            ),
        )

    poses = (
        PoseIntent(
            frame=start_frame + 10,
            arms=bilateral(tuck_centre),
            look_target=vector_tuple(push_centre),
            gaze_strength=0.18,
            body_follow=0.45,
            forward_lean_degrees=0.8,
        ),
        PoseIntent(
            frame=start_frame + 24,
            arms=bilateral(push_centre),
            look_target=vector_tuple(push_centre),
            gaze_strength=0.28,
            body_follow=0.65,
            forward_lean_degrees=2.5,
        ),
        PoseIntent(
            frame=start_frame + 34,
            arms=bilateral(push_centre),
            look_target=vector_tuple(push_centre),
            gaze_strength=0.28,
            body_follow=0.65,
            forward_lean_degrees=2.5,
        ),
    )
    clip = actions.animate_path(
        "push_candidate_calibrated",
        poses,
        neutral_start=start_frame,
        neutral_end=start_frame + 46,
        peak_frames=(start_frame + 34,),
        notes=(
            "Same push intent as legacy profile; candidate-only wider, reachable palms.",
        ),
    )
    return clip, push_centre


model_path = argument_path(
    "model",
    ROOT / "assets" / "models" / "glimmerkin-blank-face-candidate.glb",
)
if not model_path.exists():
    raise FileNotFoundError(f"Candidate GLB missing: {model_path}")

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
    raise RuntimeError("Candidate contains no skinned mesh")
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != "blank-face-candidate-28":
    raise RuntimeError(f"Expected candidate profile, resolved {profile.name!r}")

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.035)
length = actions.reference_chain_length

wave_clip = actions.wave(side="right", start_frame=1)
carry_clip, carry_centre = candidate_carry(actions, start_frame=70)
push_clip, push_centre = candidate_push(actions, start_frame=125)
walk_clip = actions.walking_arm_swing(
    start_frame=185,
    amplitude=0.18,
    release_at_end=True,
)
clips = [wave_clip, carry_clip, push_clip, walk_clip]
actions.set_smooth_interpolation()

# Small intent markers show where an object would be without hiding the hands.
carry_material = material("CarryTarget", (0.20, 0.72, 1.0, 1.0))
push_material = material("PushTarget", (0.75, 0.25, 1.0, 1.0))

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=20,
    ring_count=10,
    radius=extent * 0.024,
    location=carry_centre,
)
carry_prop = bpy.context.object
carry_prop.name = "TARGET_CarryCentre"
carry_prop.data.materials.append(carry_material)

bpy.ops.mesh.primitive_cube_add(
    size=extent * 0.050,
    location=push_centre,
)
push_prop = bpy.context.object
push_prop.name = "TARGET_PushCentre"
push_prop.data.materials.append(push_material)

# Ground and lighting match Orchid's established animation review style.
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
scene.render.resolution_x = 520
scene.render.resolution_y = 520
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

camera_target = centre + actions.up * (extent * 0.04)
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.name = "CandidateActionCamera"
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.38
scene.camera = camera

for location, energy, size in (
    (
        centre + Vector((extent * 2.0, -extent * 2.0, extent * 2.0)),
        900,
        extent * 2.0,
    ),
    (
        centre + Vector((-extent * 2.0, -extent, extent)),
        450,
        extent * 2.5,
    ),
):
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.size = size
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

front_location = camera_target + Vector((0.0, -extent * 3.8, extent * 0.10))
three_quarter_location = camera_target + Vector(
    (extent * 2.35, -extent * 3.15, extent * 0.14)
)


def set_prop_visibility(*, carry: bool, push: bool) -> None:
    carry_prop.hide_render = not carry
    push_prop.hide_render = not push


# The old review accidentally compared the two identical outward wave peaks.
# Use one inward and one outward authored pose so the actual wave arc is visible.
wave_in_frame = wave_clip.applications[1].frame
wave_out_frame = wave_clip.applications[2].frame
review_frames = (
    ("00-neutral", 1, False, False),
    ("10-wave-in", wave_in_frame, False, False),
    ("11-wave-out", wave_out_frame, False, False),
    ("20-carry", carry_clip.peak_frames[0], True, False),
    ("30-push", push_clip.peak_frames[0], False, True),
    ("40-walk-swing-a", walk_clip.peak_frames[0], False, False),
    ("41-walk-swing-b", walk_clip.peak_frames[1], False, False),
)

for label, frame, show_carry, show_push in review_frames:
    scene.frame_set(frame)
    set_prop_visibility(carry=show_carry, push=show_push)

    point_camera(camera, front_location, camera_target)
    render(scene, STILLS / f"{label}-front.png")

    point_camera(camera, three_quarter_location, camera_target)
    render(scene, STILLS / f"{label}-three-quarter.png")

applications = [application for clip in clips for application in clip.applications]
arm_results = [arm for application in applications for arm in application.arms]
report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": len(armature.data.bones),
    "shared_actions_unchanged": ["wave", "walkingArmSwing"],
    "candidate_calibrated_actions": ["carry", "push"],
    "candidate_calibration": CANDIDATE_CALIBRATION,
    "semantic_bones": {
        "body": dict(profile.body),
        "right_arm": dict(profile.right_arm),
        "left_arm": dict(profile.left_arm),
    },
    "chain_length": length,
    "shoulder_span": (
        actions.reference_shoulders["right"]
        - actions.reference_shoulders["left"]
    ).length,
    "clips": [asdict(clip) for clip in clips],
    "maximum_target_error": max(
        arm.reach.target_error
        for arm in arm_results
    ),
    "maximum_palm_error_degrees": max(
        arm.reach.palm_error_degrees
        for arm in arm_results
    ),
    "clamped_target_count": sum(
        arm.target_was_clamped
        for arm in arm_results
    ),
    "clamped_by_clip": {
        clip.name: sum(
            arm.target_was_clamped
            for application in clip.applications
            for arm in application.arms
        )
        for clip in clips
    },
    "leg_bones_touched": False,
    "review_frames": [
        {"label": label, "frame": frame}
        for label, frame, _, _ in review_frames
    ],
}
(OUTPUT / "compatibility-report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

bpy.ops.wm.save_as_mainfile(
    filepath=str(OUTPUT / "blank-face-action-compatibility.blend")
)
print(json.dumps(report, indent=2))
