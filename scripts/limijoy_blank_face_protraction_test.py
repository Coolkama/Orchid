"""Test shoulder protraction for carry/push on the 28-bone Limijoy candidate.

The candidate has a deep, round torso and comparatively short visible arms.
A centre-biased hand target can therefore be mathematically reachable yet still
sit inside the belly.  This proof uses the existing long girdle bones to bring
the shoulders naturally forward before solving the same semantic carry/push
hand intents.  No mesh deformation, scaling, or bone-length changes are used.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


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


OUTPUT = ROOT / "output" / "limijoy-blank-face-protraction"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)

CALIBRATION = {
    "carry_protraction_degrees": 26.0,
    "carry_forward_chain": 0.62,
    "carry_down_chain": 0.52,
    "carry_half_separation_chain": 0.36,
    "push_protraction_degrees": 28.0,
    "push_forward_chain": 0.74,
    "push_down_chain": 0.15,
    "push_half_separation_chain": 0.34,
}


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    value = next((item for item in sys.argv if item.startswith(prefix)), None)
    result = Path(value.split("=", 1)[1]) if value else default
    return result if result.is_absolute() else ROOT / result


def tuple3(value: Vector) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def bounds(mesh: bpy.types.Object):
    points = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    minimum = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    centre = (minimum + maximum) * 0.5
    return minimum, maximum, centre, max(maximum - minimum)


def reset_semantic_pose(actions: LimijoySemanticActions) -> None:
    actions.body.reset_pose()
    for controller in actions.arms.values():
        controller.reset_pose()
    bpy.context.view_layer.update()


def apply_world_yaw_to_girdle(
    actions: LimijoySemanticActions,
    *,
    side: str,
    degrees: float,
) -> None:
    """Swing the shoulder girdle forward around character-space vertical."""

    controller = actions.arms[side]
    girdle = controller.girdle
    girdle.matrix_basis = controller._rest_basis[girdle.name].copy()
    bpy.context.view_layer.update()

    world_up = actions.character_direction((0.0, 0.0, 1.0))
    # Right shoulder swings clockwise from +X toward character forward (-Y);
    # left shoulder swings the opposite way.
    signed_degrees = -degrees if side == "right" else degrees
    delta = Quaternion(world_up, math.radians(signed_degrees))

    armature_rotation = actions.armature.matrix_world.to_quaternion()
    current_world = armature_rotation @ girdle.matrix.to_quaternion()
    desired_world = delta @ current_world
    desired_world.normalize()
    desired_armature = armature_rotation.inverted() @ desired_world
    desired_matrix = desired_armature.to_matrix().to_4x4()
    desired_matrix.translation = girdle.head.copy()
    girdle.matrix = desired_matrix
    bpy.context.view_layer.update()


def protract(actions: LimijoySemanticActions, degrees: float) -> None:
    for side in ("left", "right"):
        apply_world_yaw_to_girdle(actions, side=side, degrees=degrees)


def live_shoulder_centre(actions: LimijoySemanticActions) -> Vector:
    return actions.arms["left"].shoulder_position().lerp(
        actions.arms["right"].shoulder_position(),
        0.5,
    )


def bilateral_targets(
    actions: LimijoySemanticActions,
    *,
    centre: Vector,
    half_separation_chain: float,
    palm_mode: str,
):
    separation = actions.right * (
        actions.reference_chain_length * half_separation_chain
    )
    return (
        ArmIntent("left", tuple3(centre - separation), palm_mode, "outward"),
        ArmIntent("right", tuple3(centre + separation), palm_mode, "outward"),
    )


def make_material(name: str, colour):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = colour
    shader = material.node_tree.nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = colour
        shader.inputs["Roughness"].default_value = 0.36
    return material


def configure_render(scene, minimum, maximum, centre, extent):
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

    bpy.ops.mesh.primitive_plane_add(
        size=extent * 6.0,
        location=(centre.x, centre.y, minimum.z),
    )
    ground = bpy.context.object
    ground.data.materials.append(
        make_material("Ground", (0.055, 0.055, 0.07, 1.0))
    )

    target = centre + Vector((0.0, 0.0, extent * 0.04))
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

    front = target + Vector((0.0, -extent * 3.8, extent * 0.10))
    three_quarter = target + Vector((extent * 2.35, -extent * 3.15, extent * 0.14))
    side = target + Vector((extent * 3.8, 0.0, extent * 0.10))
    return camera, target, (front, three_quarter, side)


def render_views(scene, camera, target, locations, prefix: str):
    names = ("front", "three-quarter", "side")
    for name, location in zip(names, locations):
        camera.location = location
        camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        scene.render.filepath = str(STILLS / f"{prefix}-{name}.png")
        bpy.ops.render.render(write_still=True)


model_path = argument_path(
    "model",
    ROOT / "assets" / "models" / "glimmerkin-blank-face-candidate.glb",
)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
meshes = [
    obj
    for obj in scene.objects
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
main_mesh = max(meshes, key=lambda obj: len(obj.data.vertices))

for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
actions = LimijoySemanticActions(armature, control_size=0.04)
length = actions.reference_chain_length
minimum, maximum, centre, extent = bounds(main_mesh)
camera, camera_target, camera_locations = configure_render(
    scene, minimum, maximum, centre, extent
)

reset_semantic_pose(actions)
render_views(scene, camera, camera_target, camera_locations, "00-neutral")

# Carry: protract first, then solve around the live shoulder positions.
reset_semantic_pose(actions)
protract(actions, CALIBRATION["carry_protraction_degrees"])
carry_shoulder_centre = live_shoulder_centre(actions)
carry_centre = (
    carry_shoulder_centre
    + actions.forward * (length * CALIBRATION["carry_forward_chain"])
    - actions.up * (length * CALIBRATION["carry_down_chain"])
)
carry_result = actions.apply_pose(
    PoseIntent(
        frame=20,
        arms=bilateral_targets(
            actions,
            centre=carry_centre,
            half_separation_chain=CALIBRATION["carry_half_separation_chain"],
            palm_mode="up",
        ),
        look_target=tuple3(carry_centre),
        gaze_strength=0.24,
        body_follow=0.35,
        forward_lean_degrees=1.0,
    )
)
render_views(scene, camera, camera_target, camera_locations, "10-carry-protracted")

# Push: slightly stronger protraction and a higher/forward palm target.
reset_semantic_pose(actions)
protract(actions, CALIBRATION["push_protraction_degrees"])
push_shoulder_centre = live_shoulder_centre(actions)
push_centre = (
    push_shoulder_centre
    + actions.forward * (length * CALIBRATION["push_forward_chain"])
    - actions.up * (length * CALIBRATION["push_down_chain"])
)
push_result = actions.apply_pose(
    PoseIntent(
        frame=40,
        arms=bilateral_targets(
            actions,
            centre=push_centre,
            half_separation_chain=CALIBRATION["push_half_separation_chain"],
            palm_mode="forward",
        ),
        look_target=tuple3(push_centre),
        gaze_strength=0.28,
        body_follow=0.65,
        forward_lean_degrees=2.5,
    )
)
render_views(scene, camera, camera_target, camera_locations, "20-push-protracted")

results = {
    "carry": carry_result,
    "push": push_result,
}
report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "calibration": CALIBRATION,
    "chain_length": length,
    "rest_shoulder_span": (
        actions.reference_shoulders["right"]
        - actions.reference_shoulders["left"]
    ).length,
    "carry_live_shoulder_centre": tuple3(carry_shoulder_centre),
    "carry_target_centre": tuple3(carry_centre),
    "push_live_shoulder_centre": tuple3(push_shoulder_centre),
    "push_target_centre": tuple3(push_centre),
    "results": {
        name: {
            "clamped_targets": sum(arm.target_was_clamped for arm in result.arms),
            "maximum_target_error": max(arm.reach.target_error for arm in result.arms),
            "maximum_palm_error_degrees": max(arm.reach.palm_error_degrees for arm in result.arms),
            "applied_targets": {
                arm.side: arm.applied_target
                for arm in result.arms
            },
        }
        for name, result in results.items()
    },
    "geometry_policy": "No mesh deformation or bone scaling; girdle rotation only",
}
(OUTPUT / "protraction-report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

bpy.ops.wm.save_as_mainfile(
    filepath=str(OUTPUT / "blank-face-protraction-test.blend")
)
print(json.dumps(report, indent=2))
