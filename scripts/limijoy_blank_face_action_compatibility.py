"""Exercise the accepted Limijoy semantic actions on the 28-bone candidate.

This is a compatibility proof, not a new animation design pass.  The same
behaviour-facing wave/carry/push/walk-arm intents used by the legacy Glimmerkin
are applied after resolving the candidate through the rig-profile adapter.
Front and three-quarter peak stills make proportion, hand/belly clearance, and
head/body follow-through easy to review before anything moves into Limijoy.
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


OUTPUT = ROOT / "output" / "limijoy-blank-face-actions"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)


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
shoulder_centre = actions.shoulder_centre()

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

# Props are only visible for the actions they explain.
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
    "chain_length": length,
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
