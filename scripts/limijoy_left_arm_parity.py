"""Render bilateral parity checks for Limijoy's semantic arm controller."""

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

from limijoy_arm_semantic_controls import (  # noqa: E402
    ELBOW_MODES,
    PALM_MODES,
    LimijoyArmSemanticControls,
)


OUTPUT = ROOT / "output" / "limijoy-left-arm-parity"
STILLS = OUTPUT / "stills"
STILLS.mkdir(parents=True, exist_ok=True)


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def bounds(mesh: bpy.types.Object) -> tuple[Vector, Vector, Vector, float]:
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
    shader.inputs["Roughness"].default_value = 0.35
    if "Emission" in shader.inputs:
        shader.inputs["Emission"].default_value = colour
    if "Emission Color" in shader.inputs:
        shader.inputs["Emission Color"].default_value = colour
    if "Emission Strength" in shader.inputs:
        shader.inputs["Emission Strength"].default_value = 0.35
    return result


def add_arrow(
    name: str,
    start: Vector,
    direction: Vector,
    length: float,
    radius: float,
    arrow_material: bpy.types.Material,
) -> None:
    unit = direction.normalized()
    shaft_length = length * 0.72
    tip_length = length - shaft_length
    rotation = unit.to_track_quat("Z", "Y").to_euler()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12,
        radius=radius,
        depth=shaft_length,
        location=start + unit * (shaft_length * 0.5),
        rotation=rotation,
    )
    bpy.context.object.name = f"DBG_{name}_shaft"
    bpy.context.object.data.materials.append(arrow_material)
    bpy.ops.mesh.primitive_cone_add(
        vertices=12,
        radius1=radius * 2.2,
        radius2=0.0,
        depth=tip_length,
        location=start + unit * (shaft_length + tip_length * 0.5),
        rotation=rotation,
    )
    bpy.context.object.name = f"DBG_{name}_tip"
    bpy.context.object.data.materials.append(arrow_material)


def clear_arrows() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith("DBG_"):
            bpy.data.objects.remove(obj, do_unlink=True)


def mirrored(vector: Vector) -> Vector:
    """Mirror a character-local vector across Limijoy's centre plane."""

    return Vector((-vector.x, vector.y, vector.z))


def angular_error_degrees(first: Vector, second: Vector) -> float:
    dot = max(-1.0, min(1.0, first.normalized().dot(second.normalized())))
    return math.degrees(math.acos(dot))


model_path = argument_path("model", ROOT / "assets" / "models" / "glimmerkin.glb")
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

minimum, maximum, centre, extent = bounds(main_mesh)
controllers = {
    side: LimijoyArmSemanticControls(
        armature,
        side=side,
        control_size=extent * 0.045,
    )
    for side in ("right", "left")
}
average_length = sum(control.chain_length for control in controllers.values()) / 2.0
character_rotation = armature.matrix_world.to_quaternion()
forward = (character_rotation @ Vector((0.0, -1.0, 0.0))).normalized()
up = (character_rotation @ Vector((0.0, 0.0, 1.0))).normalized()
targets = {
    side: control.rest_shoulder + forward * (average_length * 0.88) + up * (average_length * 0.04)
    for side, control in controllers.items()
}

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
scene.render.resolution_x = 448
scene.render.resolution_y = 448
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.025, 0.025, 0.035)

bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = extent * 1.42
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

palm_material = material("PalmDirection", (1.0, 0.08, 0.45, 1.0))
forward_material = material("HandForward", (0.0, 0.85, 1.0, 1.0))


def set_camera(view: str) -> None:
    locations = {
        "front": centre + Vector((0.0, -extent * 4.0, extent * 0.06)),
        "three-quarter": centre + Vector((extent * 2.15, -extent * 3.2, extent * 0.35)),
    }
    camera.location = locations[view]
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()


results = []
pose_index = 0
inverse_character_rotation = character_rotation.inverted()
for elbow_mode in ELBOW_MODES:
    for palm_mode in PALM_MODES:
        pose_index += 1
        for control in controllers.values():
            control.reset_pose()
        right_result = controllers["right"].reach_to(
            targets["right"],
            palm_mode=palm_mode,
            elbow_mode=elbow_mode,
        )
        left_result = controllers["left"].reach_to(
            targets["left"],
            palm_mode=palm_mode,
            elbow_mode=elbow_mode,
        )

        right_displacement = inverse_character_rotation @ (
            Vector(right_result.achieved_hand_anchor) - controllers["right"].shoulder_position()
        )
        left_displacement = inverse_character_rotation @ (
            Vector(left_result.achieved_hand_anchor) - controllers["left"].shoulder_position()
        )
        right_palm = inverse_character_rotation @ Vector(right_result.palm_direction)
        left_palm = inverse_character_rotation @ Vector(left_result.palm_direction)
        displacement_parity_error = (right_displacement - mirrored(left_displacement)).length
        palm_parity_error = angular_error_degrees(right_palm, mirrored(left_palm))

        results.append(
            {
                "elbow_mode": elbow_mode,
                "palm_mode": palm_mode,
                "right": asdict(right_result),
                "left": asdict(left_result),
                "mirrored_hand_displacement_error": displacement_parity_error,
                "mirrored_palm_error_degrees": palm_parity_error,
            }
        )

        clear_arrows()
        for side, result in (("Right", right_result), ("Left", left_result)):
            anchor = Vector(result.achieved_hand_anchor)
            add_arrow(
                f"{side}_Palm",
                anchor,
                Vector(result.palm_direction),
                extent * 0.14,
                extent * 0.007,
                palm_material,
            )
            add_arrow(
                f"{side}_Forward",
                anchor,
                Vector(result.hand_forward),
                extent * 0.11,
                extent * 0.0055,
                forward_material,
            )

        stem = f"{pose_index:02d}_elbow-{elbow_mode}_palm-{palm_mode}"
        for view in ("front", "three-quarter"):
            set_camera(view)
            scene.render.filepath = str(STILLS / f"{stem}_{view}.png")
            bpy.ops.render.render(write_still=True)

        print(
            f"{stem}: right={right_result.target_error:.6f}, "
            f"left={left_result.target_error:.6f}, "
            f"hand_parity={displacement_parity_error:.6f}, "
            f"palm_parity={palm_parity_error:.4f} degrees"
        )

clear_arrows()
report = {
    "model": str(model_path.relative_to(ROOT)),
    "purpose": "Rendered calibration of the mirrored left arm against the accepted right arm",
    "coordinate_convention": {"right": "+X", "forward": "-Y", "up": "+Z"},
    "right_palm_reference_local": list(controllers["right"].palm_normal_local),
    "left_palm_reference_local": list(controllers["left"].palm_normal_local),
    "right_chain_length": controllers["right"].chain_length,
    "left_chain_length": controllers["left"].chain_length,
    "poses": results,
    "maximum_target_error": max(
        max(pose["right"]["target_error"], pose["left"]["target_error"])
        for pose in results
    ),
    "maximum_mirrored_hand_displacement_error": max(
        pose["mirrored_hand_displacement_error"] for pose in results
    ),
    "maximum_mirrored_palm_error_degrees": max(
        pose["mirrored_palm_error_degrees"] for pose in results
    ),
}
(OUTPUT / "parity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(OUTPUT / "README.md").write_text(
    "\n".join(
        (
            "# Limijoy bilateral semantic-arm parity",
            "",
            "Each still uses mirrored left/right hand targets and the same semantic palm and elbow modes.",
            "",
            "- Magenta arrows: measured palm normals",
            "- Cyan arrows: measured hand/finger-forward axes",
            "- `parity_report.json`: target, orientation, and mirrored displacement errors",
        )
    ),
    encoding="utf-8",
)
