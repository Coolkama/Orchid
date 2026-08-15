"""Build and render a non-destructive textured-face prototype for Limijoy.

The current Meshy asset bakes its eyes and recessed mouth into one skinned mesh,
one colour atlas, and one normal map.  This prototype keeps the approved
armature and body skinning, locally restores the face to a smooth neutral
surface, assigns the facial polygons their own material, and projects the
canonical expression textures onto that curved surface.

No remeshing, decimation, or auto-rigging is performed.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Iterable

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from limijoy_body_semantic_controls import LimijoyBodySemanticControls  # noqa: E402


OUTPUT = ROOT / "output" / "limijoy-face-texture-prototype"
RENDERS = OUTPUT / "renders"
TEXTURES = OUTPUT / "textures"
RENDERS.mkdir(parents=True, exist_ok=True)
TEXTURES.mkdir(parents=True, exist_ok=True)

STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    argument = next((value for value in sys.argv if value.startswith(prefix)), None)
    result = Path(argument.split("=", 1)[1]) if argument else default
    return result if result.is_absolute() else ROOT / result


def world_bounds(objects: Iterable[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return minimum, maximum


def rig_fingerprint(armature: bpy.types.Object) -> dict[str, dict[str, object]]:
    result = {}
    for bone in armature.data.bones:
        result[bone.name] = {
            "parent": bone.parent.name if bone.parent else None,
            "head": tuple(float(value) for value in bone.head_local),
            "tail": tuple(float(value) for value in bone.tail_local),
            "matrix": tuple(float(value) for row in bone.matrix_local for value in row),
        }
    return result


def compare_rigs(
    source: dict[str, dict[str, object]],
    exported: dict[str, dict[str, object]],
) -> tuple[float, list[str]]:
    problems = []
    if set(source) != set(exported):
        problems.append(
            f"bone names differ: missing={sorted(set(source) - set(exported))}, "
            f"added={sorted(set(exported) - set(source))}"
        )
    maximum_delta = 0.0
    for name in sorted(set(source) & set(exported)):
        if source[name]["parent"] != exported[name]["parent"]:
            problems.append(
                f"{name} parent changed from {source[name]['parent']} to {exported[name]['parent']}"
            )
        for key in ("head", "tail", "matrix"):
            delta = max(
                abs(float(left) - float(right))
                for left, right in zip(source[name][key], exported[name][key])
            )
            maximum_delta = max(maximum_delta, delta)
    return maximum_delta, problems


def smooth_step(edge0: float, edge1: float, value: float) -> float:
    amount = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return amount * amount * (3.0 - 2.0 * amount)


def ellipse_radius(
    point: Vector,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
) -> float:
    return math.sqrt(
        ((point.x - centre_x) / radius_x) ** 2
        + ((point.z - centre_z) / radius_z) ** 2
    )


def robust_surface_fit(points: list[Vector]) -> np.ndarray:
    if len(points) < 100:
        raise RuntimeError(f"Not enough neutral face samples for surface fitting: {len(points)}")
    values = np.array([(point.x, point.z, point.y) for point in points], dtype=np.float64)
    x_values = values[:, 0]
    z_values = values[:, 1]
    y_values = values[:, 2]
    design = np.column_stack(
        (
            np.ones(len(values)),
            x_values,
            z_values,
            x_values * x_values,
            x_values * z_values,
            z_values * z_values,
        )
    )
    keep = np.ones(len(values), dtype=bool)
    coefficients = np.zeros(6, dtype=np.float64)
    for _ in range(5):
        coefficients = np.linalg.lstsq(design[keep], y_values[keep], rcond=None)[0]
        residuals = y_values - design @ coefficients
        median = float(np.median(residuals[keep]))
        deviation = float(np.median(np.abs(residuals[keep] - median)))
        limit = max(0.002, deviation * 3.5)
        updated = np.abs(residuals - median) <= limit
        if updated.sum() == keep.sum():
            break
        keep = updated
    print(f"Neutral surface fit retained {int(keep.sum())}/{len(points)} samples")
    return coefficients


def surface_forward(coefficients: np.ndarray, point: Vector) -> float:
    x_value = point.x
    z_value = point.z
    return float(
        np.dot(
            coefficients,
            np.array(
                (
                    1.0,
                    x_value,
                    z_value,
                    x_value * x_value,
                    x_value * z_value,
                    z_value * z_value,
                )
            ),
        )
    )


def create_face_material(texture_path: Path) -> tuple[bpy.types.Material, bpy.types.ShaderNodeTexImage]:
    material = bpy.data.materials.new("Limijoy_Face_Animated")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "LimijoyFaceTexture"
    texture.label = "Animated Limijoy face"
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Roughness"].default_value = 0.58
    if "Specular IOR Level" in shader.inputs:
        shader.inputs["Specular IOR Level"].default_value = 0.28
    elif "Specular" in shader.inputs:
        shader.inputs["Specular"].default_value = 0.28
    material.diffuse_color = (0.86, 0.80, 0.56, 1.0)
    return material, texture


def configure_render(scene: bpy.types.Scene, minimum: Vector, maximum: Vector) -> bpy.types.Object:
    size = maximum - minimum
    extent = max(size)
    head_target = Vector(((minimum.x + maximum.x) * 0.5, (minimum.y + maximum.y) * 0.5, minimum.z + size.z * 0.59))

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
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("LimijoyFaceWorld")
    scene.world.color = (0.028, 0.027, 0.035)

    camera_location = head_target + Vector((0.0, -extent * 3.2, extent * 0.015))
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.name = "LimijoyFaceCamera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size.z * 0.62
    camera.rotation_euler = (head_target - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    for location, energy, radius in (
        (head_target + Vector((extent * 1.5, -extent * 1.8, extent * 1.6)), 850, extent * 1.8),
        (head_target + Vector((-extent * 1.4, -extent * 1.2, extent * 0.8)), 420, extent * 2.2),
        (head_target + Vector((0.0, extent * 1.6, extent * 1.4)), 520, extent * 1.5),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.size = radius
        light.rotation_euler = (head_target - light.location).to_track_quat("-Z", "Y").to_euler()
    return camera


def render(scene: bpy.types.Scene, name: str) -> None:
    scene.render.filepath = str(RENDERS / name)
    bpy.ops.render.render(write_still=True)


model_path = argument_path("model", ROOT / "assets" / "models" / "glimmerkin.glb")
texture_dir = argument_path("textures", TEXTURES)
for state in STATES:
    path = texture_dir / f"limijoy-face-{state}.png"
    if not path.exists():
        raise FileNotFoundError(f"Missing generated face texture: {path}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
skinned_meshes = [
    obj
    for obj in scene.objects
    if obj.type == "MESH" and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
if not skinned_meshes:
    raise RuntimeError("The source GLB contains no skinned mesh")
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

source_rig = rig_fingerprint(armature)
source_bone_names = {group.name for group in main_mesh.vertex_groups}
minimum, maximum = world_bounds(skinned_meshes)
size = maximum - minimum
extent = max(size)
centre = (minimum + maximum) * 0.5
configure_render(scene, minimum, maximum)

# Capture the actual baked face before making any change.
render(scene, "00-original-baked-face.png")

face_centre_x = centre.x
face_centre_z = minimum.z + size.z * 0.565
face_radius_x = size.x * 0.255
face_radius_z = size.z * 0.148
front_threshold = centre.y - size.y * 0.245

eye_centre_z = minimum.z + size.z * 0.575
eye_offset_x = size.x * 0.120
eye_radius_x = size.x * 0.072
eye_radius_z = size.z * 0.068
mouth_centre_z = minimum.z + size.z * 0.495
mouth_radius_x = size.x * 0.080
mouth_radius_z = size.z * 0.047

matrix_world = main_mesh.matrix_world.copy()
matrix_world_inverse = matrix_world.inverted()
world_vertices = [matrix_world @ vertex.co for vertex in main_mesh.data.vertices]


def feature_radius(point: Vector) -> float:
    return min(
        ellipse_radius(point, face_centre_x - eye_offset_x, eye_centre_z, eye_radius_x, eye_radius_z),
        ellipse_radius(point, face_centre_x + eye_offset_x, eye_centre_z, eye_radius_x, eye_radius_z),
        ellipse_radius(point, face_centre_x, mouth_centre_z, mouth_radius_x, mouth_radius_z),
    )


neutral_samples = []
for point in world_vertices:
    face_radius = ellipse_radius(point, face_centre_x, face_centre_z, face_radius_x, face_radius_z)
    if face_radius <= 0.92 and point.y < front_threshold and feature_radius(point) >= 1.35:
        neutral_samples.append(point)

coefficients = robust_surface_fit(neutral_samples)
modified_vertices = 0
maximum_displacement = 0.0
for vertex, point in zip(main_mesh.data.vertices, world_vertices):
    if point.y >= front_threshold:
        continue
    face_radius = ellipse_radius(point, face_centre_x, face_centre_z, face_radius_x, face_radius_z)
    if face_radius > 1.02:
        continue
    radius = feature_radius(point)
    weight = 1.0 - smooth_step(0.72, 1.28, radius)
    if weight <= 0.0:
        continue
    target_forward = surface_forward(coefficients, point)
    displacement = (target_forward - point.y) * weight
    if abs(displacement) < 1.0e-7:
        continue
    changed = point.copy()
    changed.y += displacement
    vertex.co = matrix_world_inverse @ changed
    modified_vertices += 1
    maximum_displacement = max(maximum_displacement, abs(displacement))

if modified_vertices < 100:
    raise RuntimeError(f"Face smoothing selected too few vertices: {modified_vertices}")
if maximum_displacement > extent * 0.065:
    raise RuntimeError(
        f"Unsafe face displacement {maximum_displacement:.6f} exceeds {extent * 0.065:.6f}"
    )
main_mesh.data.update()

face_material, face_texture_node = create_face_material(texture_dir / "limijoy-face-neutral.png")
main_mesh.data.materials.append(face_material)
face_material_index = len(main_mesh.data.materials) - 1
uv_layer = main_mesh.data.uv_layers.active or main_mesh.data.uv_layers.new(name="UVMap")
face_polygons = 0
for polygon in main_mesh.data.polygons:
    centre_local = sum(
        (main_mesh.data.vertices[index].co for index in polygon.vertices),
        Vector((0.0, 0.0, 0.0)),
    ) / len(polygon.vertices)
    point = matrix_world @ centre_local
    radius = ellipse_radius(point, face_centre_x, face_centre_z, face_radius_x, face_radius_z)
    if point.y >= front_threshold or radius > 1.0:
        continue
    polygon.material_index = face_material_index
    face_polygons += 1
    for loop_index in polygon.loop_indices:
        vertex = main_mesh.data.vertices[main_mesh.data.loops[loop_index].vertex_index]
        world_point = matrix_world @ vertex.co
        u_value = 0.5 + (world_point.x - face_centre_x) / (2.0 * face_radius_x)
        v_value = 0.5 + (world_point.z - face_centre_z) / (2.0 * face_radius_z)
        uv_layer.data[loop_index].uv = (
            max(0.0, min(1.0, u_value)),
            max(0.0, min(1.0, v_value)),
        )

if face_polygons < 100:
    raise RuntimeError(f"Face material selected too few polygons: {face_polygons}")
main_mesh.data.update()
bpy.context.view_layer.update()

for state in STATES:
    face_texture_node.image = bpy.data.images.load(
        str(texture_dir / f"limijoy-face-{state}.png"),
        check_existing=True,
    )
    bpy.context.view_layer.update()
    render(scene, f"10-{state}-front.png")

controls = LimijoyBodySemanticControls(armature)
look_origin = controls.look_origin()
for label, x_offset, state in (
    ("right", extent * 0.72, "neutral"),
    ("left", -extent * 0.72, "blink"),
):
    controls.look_at(look_origin + Vector((x_offset, -extent * 2.4, 0.0)), strength=0.92)
    face_texture_node.image = bpy.data.images.load(
        str(texture_dir / f"limijoy-face-{state}.png"),
        check_existing=True,
    )
    bpy.context.view_layer.update()
    render(scene, f"20-{state}-head-{label}.png")

controls.reset_pose()
face_texture_node.image = bpy.data.images.load(
    str(texture_dir / "limijoy-face-neutral.png"),
    check_existing=True,
)
bpy.context.view_layer.update()

prototype_path = OUTPUT / "glimmerkin-textured-face-prototype.glb"
bpy.ops.object.select_all(action="DESELECT")
armature.select_set(True)
main_mesh.select_set(True)
bpy.context.view_layer.objects.active = main_mesh
bpy.ops.export_scene.gltf(
    filepath=str(prototype_path),
    export_format="GLB",
    use_selection=True,
    export_animations=False,
    export_cameras=False,
    export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "limijoy-face-texture-prototype.blend"))

source_bounds = {
    "minimum": tuple(float(value) for value in minimum),
    "maximum": tuple(float(value) for value in maximum),
}

# Re-import the exported model and verify the runtime rig contract survived.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(prototype_path))
exported_armature = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
exported_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
exported_skinned = [
    obj
    for obj in exported_meshes
    if any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
exported_rig = rig_fingerprint(exported_armature)
maximum_rig_delta, rig_problems = compare_rigs(source_rig, exported_rig)
if rig_problems:
    raise RuntimeError("; ".join(rig_problems))
if maximum_rig_delta > 1.0e-4:
    raise RuntimeError(f"Exported rig rest transforms drifted by {maximum_rig_delta:.8f}")
exported_group_names = {group.name for mesh in exported_skinned for group in mesh.vertex_groups}
missing_groups = sorted(source_bone_names - exported_group_names)
if missing_groups:
    raise RuntimeError(f"Exported skin lost vertex groups: {missing_groups}")

exported_minimum, exported_maximum = world_bounds(exported_skinned)
report = {
    "source_model": str(model_path.relative_to(ROOT)),
    "prototype_model": str(prototype_path.relative_to(ROOT)),
    "source_bones": len(source_rig),
    "exported_bones": len(exported_rig),
    "maximum_rig_rest_delta": maximum_rig_delta,
    "source_vertex_groups": len(source_bone_names),
    "exported_vertex_groups": len(exported_group_names),
    "modified_face_vertices": modified_vertices,
    "face_material_polygons": face_polygons,
    "maximum_face_displacement": maximum_displacement,
    "source_bounds": source_bounds,
    "exported_bounds": {
        "minimum": tuple(float(value) for value in exported_minimum),
        "maximum": tuple(float(value) for value in exported_maximum),
    },
    "states": list(STATES),
    "body_topology_policy": "No remesh, decimation, or auto-rigging",
}
(OUTPUT / "prototype-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
