"""Render a one-run calibration sheet for Limijoy's semantic arm controls."""

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

from limijoy_arm_semantic_controls import (  # noqa: E402
    ELBOW_MODES,
    PALM_MODES,
    LimijoyArmSemanticControls,
)


OUTPUT = ROOT / "output" / "limijoy-palm-orientation-sheet"
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
    extent = max(maximum - minimum)
    return minimum, maximum, centre, extent


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
        vertices=16,
        radius=radius,
        depth=shaft_length,
        location=start + unit * (shaft_length * 0.5),
        rotation=rotation,
    )
    shaft = bpy.context.object
    shaft.name = f"DBG_{name}_shaft"
    shaft.data.materials.append(arrow_material)

    bpy.ops.mesh.primitive_cone_add(
        vertices=16,
        radius1=radius * 2.2,
        radius2=0.0,
        depth=tip_length,
        location=start + unit * (shaft_length + tip_length * 0.5),
        rotation=rotation,
    )
    tip = bpy.context.object
    tip.name = f"DBG_{name}_tip"
    tip.data.materials.append(arrow_material)


def clear_arrows() -> None:
    for obj in list(bpy.data.objects):
        if obj.name.startswith("DBG_Palm") or obj.name.startswith("DBG_HandForward"):
            bpy.data.objects.remove(obj, do_unlink=True)


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

minimum, maximum, centre, extent = model_bounds(main_mesh)
controller = LimijoyArmSemanticControls(
    armature,
    side="right",
    control_size=extent * 0.045,
)

# Keep the calibration target reachable.  The hand control is the wrist/palm
# anchor at Bone_021's tail, so 90% of the two-bone IK length gives a nearly
# straight horizontal reach without asking the solver to exceed the chain.
reach_target = controller.rest_shoulder + Vector(
    (0.0, -controller.chain_length * 0.90, controller.chain_length * 0.04)
)

bpy.ops.mesh.primitive_plane_add(size=extent * 6.0, location=(centre.x, centre.y, minimum.z))
ground_material = material("Ground", (0.055, 0.055, 0.07, 1.0))
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
scene.render.resolution_x = 512
scene.render.resolution_y = 512
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
        "side": centre + Vector((extent * 4.0, 0.0, extent * 0.06)),
        "three-quarter": centre + Vector((extent * 2.15, -extent * 3.2, extent * 0.35)),
    }
    camera.location = locations[view]
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()


results = []
pose_index = 0
for elbow_mode in ELBOW_MODES:
    for palm_mode in PALM_MODES:
        pose_index += 1
        controller.reset_pose()
        result = controller.reach_to(
            reach_target,
            palm_mode=palm_mode,
            elbow_mode=elbow_mode,
        )
        results.append(asdict(result))

        clear_arrows()
        anchor = Vector(result.achieved_hand_anchor)
        add_arrow(
            "Palm",
            anchor,
            Vector(result.palm_direction),
            extent * 0.16,
            extent * 0.009,
            palm_material,
        )
        add_arrow(
            "HandForward",
            anchor,
            Vector(result.hand_forward),
            extent * 0.13,
            extent * 0.007,
            forward_material,
        )

        stem = f"{pose_index:02d}_elbow-{elbow_mode}_palm-{palm_mode}"
        for view in ("front", "side", "three-quarter"):
            set_camera(view)
            scene.render.filepath = str(STILLS / f"{stem}_{view}.png")
            bpy.ops.render.render(write_still=True)

        print(
            f"{stem}: target_error={result.target_error:.6f}, "
            f"palm_error={result.palm_error_degrees:.4f} degrees"
        )

clear_arrows()
(OUTPUT / "orientation_report.json").write_text(
    json.dumps(
        {
            "model": str(model_path.relative_to(ROOT)),
            "coordinate_convention": {
                "right": "+X",
                "forward": "-Y",
                "up": "+Z",
            },
            "palm_modes": list(PALM_MODES),
            "elbow_modes": list(ELBOW_MODES),
            "palm_reference_local": list(controller.palm_normal_local),
            "hand_forward_local": list(controller.hand_forward_local),
            "reach_target": list(reach_target),
            "poses": results,
        },
        indent=2,
    ),
    encoding="utf-8",
)

(OUTPUT / "README.md").write_text(
    "\n".join(
        (
            "# Limijoy semantic palm-orientation calibration",
            "",
            "Every pose uses the same reachable hand target. Rows use elbow poles "
            "outward, neutral, and inward; columns use palm inward, outward, up, "
            "down, forward, and backward.",
            "",
            "- Magenta arrow: measured palm-normal direction",
            "- Cyan arrow: measured hand/finger-forward direction",
            "- `orientation_report.json`: numeric target and orientation errors",
            "",
            "The controller uses a neutral-pose palm reference plus vector/quaternion "
            "orientation maths. No palm mode is implemented as a Meshy Euler angle.",
        )
    ),
    encoding="utf-8",
)
