"""Animate a standard semantic reach using the reusable Limijoy arm controller."""

from __future__ import annotations

import json
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

from limijoy_arm_semantic_controls import LimijoyArmSemanticControls  # noqa: E402


OUTPUT = ROOT / "output" / "limijoy-reach"
FRAMES = OUTPUT / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)

model_argument = next((value for value in sys.argv if value.startswith("--model=")), None)
model_path = (
    Path(model_argument.split("=", 1)[1])
    if model_argument
    else ROOT / "assets" / "models" / "glimmerkin.glb"
)
if not model_path.is_absolute():
    model_path = ROOT / model_path

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
main_mesh = max(
    [
        obj
        for obj in scene.objects
        if obj.type == "MESH" and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
    ],
    key=lambda obj: len(obj.data.vertices),
)

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

points = [main_mesh.matrix_world @ Vector(corner) for corner in main_mesh.bound_box]
minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
centre = (minimum + maximum) * 0.5
extent = max(maximum - minimum)

controller = LimijoyArmSemanticControls(
    armature,
    side="right",
    control_size=extent * 0.045,
)

# A reachable target at shoulder height. Limijoy forward is world -Y and the
# hand target represents the wrist/palm anchor at the end of the two-bone IK chain.
target_end = controller.rest_shoulder + Vector(
    (0.0, -controller.chain_length * 0.90, controller.chain_length * 0.04)
)

reach_keys = (
    (1, 0.00),
    (9, 0.25),
    (19, 0.72),
    (29, 1.00),
    (39, 1.00),
    (49, 0.30),
    (59, 0.00),
)
reach_results = []
for frame, amount in reach_keys:
    hand_position = controller.rest_hand_target.lerp(target_end, amount)
    result = controller.reach_to(
        hand_position,
        palm_mode="inward",
        elbow_mode="outward",
        frame=frame,
    )
    reach_results.append({"frame": frame, **asdict(result)})

head = armature.pose.bones["Bone_034"]
head.rotation_mode = "XYZ"
head.matrix_basis.identity()
for frame, degrees in ((1, 0), (9, -2), (19, -5), (29, -8), (39, -8), (49, -3), (59, 0)):
    head.rotation_euler = (0.0, degrees * 0.017453292519943295, 0.0)
    head.keyframe_insert("rotation_euler", frame=frame)

for controlled_object in (controller.hand_target, controller.elbow_pole):
    if controlled_object.animation_data and controlled_object.animation_data.action:
        for curve in controlled_object.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"

if armature.animation_data and armature.animation_data.action:
    for curve in armature.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"

scene.frame_start = 1
scene.frame_end = 59
scene.render.fps = 24

bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
ground_material = bpy.data.materials.new("Ground")
ground_material.diffuse_color = (0.055, 0.055, 0.07, 1.0)
bpy.context.object.data.materials.append(ground_material)

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
scene.render.resolution_x = 384
scene.render.resolution_y = 384
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(FRAMES / "frame_")
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.035, 0.035, 0.045)

camera_location = centre + Vector((extent * 2.15, -extent * 3.2, extent * 0.35))
bpy.ops.object.camera_add(location=camera_location)
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.42
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
        "fps=12,scale=384:-1:flags=lanczos",
        "-loop",
        "0",
        str(OUTPUT / "preview.gif"),
    ),
    check=True,
)

(OUTPUT / "reach_report.json").write_text(
    json.dumps(
        {
            "controller": "LimijoyArmSemanticControls",
            "palm_mode": "inward",
            "elbow_mode": "outward",
            "target_end": list(target_end),
            "keyframes": reach_results,
        },
        indent=2,
    ),
    encoding="utf-8",
)
