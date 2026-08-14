"""Render the reusable Limijoy semantic action layer as one reviewable reel."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from limijoy_semantic_actions import (  # noqa: E402
    WALK_POLICY,
    LimijoySemanticActions,
)


OUTPUT = ROOT / "output" / "limijoy-semantic-actions"
FRAMES = OUTPUT / "frames"
PEAK_STILLS = OUTPUT / "peak-stills"
FRAMES.mkdir(parents=True, exist_ok=True)
PEAK_STILLS.mkdir(parents=True, exist_ok=True)


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
    shader.inputs["Base Color"].default_value = colour
    shader.inputs["Roughness"].default_value = 0.32
    return result


def animate_prop_visibility(
    prop: bpy.types.Object,
    *,
    first_frame: int,
    last_frame: int,
) -> None:
    visible_scale = prop.scale.copy()
    for frame, scale in (
        (max(1, first_frame - 1), Vector((0.0, 0.0, 0.0))),
        (first_frame, visible_scale),
        (last_frame, visible_scale),
        (last_frame + 1, Vector((0.0, 0.0, 0.0))),
    ):
        prop.scale = scale
        prop.keyframe_insert("scale", frame=frame)
    action = prop.animation_data.action if prop.animation_data else None
    if action:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"


model_path = argument_path("model", ROOT / "assets" / "models" / "glimmerkin.glb")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
skinned_meshes = [
    obj
    for obj in scene.objects
    if obj.type == "MESH" and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

minimum, maximum, centre, extent = model_bounds(main_mesh)
actions = LimijoySemanticActions(armature, control_size=extent * 0.042)
length = actions.reference_chain_length
shoulder_centre = actions.shoulder_centre()

# Off-centre targets make automatic side choice, head turn, and torso follow easy
# to judge.  Props only visualise intent; they are not part of the controller.
reach_target = (
    shoulder_centre
    + actions.forward * (length * 0.82)
    + actions.right * (length * 0.27)
    + actions.up * (length * 0.08)
)
point_target = (
    shoulder_centre
    + actions.forward * (length * 0.86)
    - actions.right * (length * 0.30)
    + actions.up * (length * 0.14)
)
carry_centre = (
    shoulder_centre
    + actions.forward * (length * 0.47)
    - actions.up * (length * 0.24)
)
push_centre = (
    shoulder_centre
    + actions.forward * (length * 0.82)
    - actions.up * (length * 0.05)
)

clips = [
    actions.reach_for(reach_target, side="auto", start_frame=1),
    actions.point(point_target, side="auto", start_frame=57),
    actions.wave(side="right", start_frame=105),
    actions.carry(carry_centre, start_frame=171),
    actions.push(push_centre, start_frame=223),
    actions.walking_arm_swing(start_frame=277, release_at_end=True),
]
actions.set_smooth_interpolation()

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action.name = "Limijoy_Semantic_Action_Showcase"

# Small scene props make reach/point/carry/push intent readable at a glance.
prop_material = material("InteractionTarget", (1.0, 0.30, 0.08, 1.0))
carry_material = material("CarryObject", (0.20, 0.72, 1.0, 1.0))
push_material = material("PushObject", (0.75, 0.25, 1.0, 1.0))

bpy.ops.mesh.primitive_ico_sphere_add(
    subdivisions=2,
    radius=extent * 0.035,
    location=reach_target,
)
reach_prop = bpy.context.object
reach_prop.name = "PROP_ReachTarget"
reach_prop.data.materials.append(prop_material)
animate_prop_visibility(reach_prop, first_frame=1, last_frame=49)

bpy.ops.mesh.primitive_ico_sphere_add(
    subdivisions=2,
    radius=extent * 0.027,
    location=point_target,
)
point_prop = bpy.context.object
point_prop.name = "PROP_PointTarget"
point_prop.data.materials.append(prop_material)
animate_prop_visibility(point_prop, first_frame=57, last_frame=97)

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24,
    ring_count=12,
    radius=extent * 0.060,
    location=carry_centre + actions.up * (extent * 0.028),
)
carry_prop = bpy.context.object
carry_prop.name = "PROP_CarryObject"
carry_prop.data.materials.append(carry_material)
animate_prop_visibility(carry_prop, first_frame=171, last_frame=215)

bpy.ops.mesh.primitive_cube_add(
    size=extent * 0.13,
    location=push_centre + actions.forward * (extent * 0.055),
)
push_prop = bpy.context.object
push_prop.name = "PROP_PushObject"
push_prop.data.materials.append(push_material)
animate_prop_visibility(push_prop, first_frame=223, last_frame=269)

# Render setup deliberately matches the earlier accepted arm previews.
bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
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
scene.render.resolution_x = 360
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(FRAMES / "frame_")
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = max(clip.frame_end for clip in clips)
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

camera_location = centre + Vector((extent * 1.55, -extent * 3.75, extent * 0.26))
bpy.ops.object.camera_add(location=camera_location)
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.52
camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
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

bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "semantic-action-showcase.blend"))
bpy.ops.render.render(animation=True)

subprocess.run(
    (
        "ffmpeg",
        "-y",
        "-framerate",
        "24",
        "-i",
        str(FRAMES / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(OUTPUT / "preview.mp4"),
    ),
    check=True,
)
subprocess.run(
    (
        "ffmpeg",
        "-y",
        "-framerate",
        "24",
        "-i",
        str(FRAMES / "frame_%04d.png"),
        "-vf",
        "fps=10,scale=360:-1:flags=lanczos",
        "-loop",
        "0",
        str(OUTPUT / "preview.gif"),
    ),
    check=True,
)

for index, clip in enumerate(clips, start=1):
    peak_frame = clip.peak_frames[0]
    source = FRAMES / f"frame_{peak_frame:04d}.png"
    destination = PEAK_STILLS / f"{index:02d}_{clip.name}.png"
    shutil.copy2(source, destination)

applications = [application for clip in clips for application in clip.applications]
arm_results = [arm for application in applications for arm in application.arms]
report = {
    "model": str(model_path.relative_to(ROOT)),
    "controller": "LimijoySemanticActions",
    "public_intents": ["reachFor", "point", "wave", "carry", "push", "walkingArmSwing"],
    "coordinate_convention": {"right": "+X", "forward": "-Y", "up": "+Z"},
    "clips": [asdict(clip) for clip in clips],
    "timeline": {
        clip.name: {
            "frame_start": clip.frame_start,
            "frame_end": clip.frame_end,
            "peak_frames": list(clip.peak_frames),
        }
        for clip in clips
    },
    "walk_policy": WALK_POLICY,
    "maximum_target_error": max(arm.reach.target_error for arm in arm_results),
    "maximum_palm_error_degrees": max(
        arm.reach.palm_error_degrees for arm in arm_results
    ),
    "clamped_target_count": sum(arm.target_was_clamped for arm in arm_results),
    "baked_walk_source_edited": False,
}
(OUTPUT / "action_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(OUTPUT / "README.md").write_text(
    "\n".join(
        (
            "# Limijoy semantic action showcase",
            "",
            "The reel demonstrates target-space reach, point, wave, carry, push, and an optional arm-only walking overlay.",
            "Head and torso follow the interaction target within conservative semantic limits.",
            "",
            "The existing baked walk remains the default locomotion source; no leg controls are touched here.",
            "`action_report.json` records every requested target, applied target, IK error, palm error, gaze distribution, and clip frame range.",
        )
    ),
    encoding="utf-8",
)
