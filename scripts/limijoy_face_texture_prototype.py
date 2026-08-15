"""Build and render a non-destructive textured-face prototype for Limijoy.

The current Meshy asset bakes its eyes and recessed mouth into one highly
fragmented skinned mesh, one colour atlas, and one normal map.  This prototype
keeps that approved body completely untouched and adds one smooth curved face
cap, skinned to the existing head bone, for the canonical expression textures.

No remeshing, decimation, or auto-rigging is performed.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Iterable

import bmesh
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
    material.use_backface_culling = False
    return material, texture


def create_face_plate(
    *,
    armature: bpy.types.Object,
    material: bpy.types.Material,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
    boundary_forward: float,
    depth: float,
    radial_steps: int = 28,
    angular_steps: int = 96,
) -> bpy.types.Object:
    """Create one smooth, head-skinned oval over the fragmented Meshy face.

    The source facial detail consists of thousands of disconnected pieces.
    Reusing that surface exposes those fragments as creases when the baked
    normal map is removed.  A conforming ellipsoidal cap is therefore safer:
    it covers the old recesses without changing a single source vertex.
    """

    vertices = [(centre_x, boundary_forward - depth, centre_z)]
    texture_coordinates = [(0.5, 0.5)]
    for ring in range(1, radial_steps + 1):
        radius = ring / radial_steps
        forward = boundary_forward - depth * math.sqrt(max(0.0, 1.0 - radius * radius))
        for segment in range(angular_steps):
            angle = math.tau * segment / angular_steps
            cosine = math.cos(angle)
            sine = math.sin(angle)
            vertices.append(
                (
                    centre_x + radius_x * radius * cosine,
                    forward,
                    centre_z + radius_z * radius * sine,
                )
            )
            texture_coordinates.append(
                (
                    0.5 + 0.49 * radius * cosine,
                    0.5 + 0.49 * radius * sine,
                )
            )

    def ring_vertex(ring: int, segment: int) -> int:
        return 1 + (ring - 1) * angular_steps + segment % angular_steps

    faces = []
    for segment in range(angular_steps):
        faces.append((0, ring_vertex(1, segment), ring_vertex(1, segment + 1)))
    for ring in range(2, radial_steps + 1):
        for segment in range(angular_steps):
            faces.append(
                (
                    ring_vertex(ring - 1, segment),
                    ring_vertex(ring, segment),
                    ring_vertex(ring, segment + 1),
                    ring_vertex(ring - 1, segment + 1),
                )
            )

    mesh_data = bpy.data.meshes.new("LimijoyFacePlateMesh")
    mesh_data.from_pydata(vertices, [], faces)
    mesh_data.materials.append(material)
    uv_layer = mesh_data.uv_layers.new(name="LimijoyFaceUV")
    for polygon in mesh_data.polygons:
        polygon.use_smooth = True
        polygon.material_index = 0
        for loop_index in polygon.loop_indices:
            uv_layer.data[loop_index].uv = texture_coordinates[
                mesh_data.loops[loop_index].vertex_index
            ]
    mesh_data.update()

    face_plate = bpy.data.objects.new("LimijoyAnimatedFace", mesh_data)
    bpy.context.collection.objects.link(face_plate)
    face_plate.parent = armature
    face_plate.matrix_parent_inverse = armature.matrix_world.inverted()
    vertex_group = face_plate.vertex_groups.new(name="Bone_033")
    vertex_group.add(range(len(vertices)), 1.0, "REPLACE")
    modifier = face_plate.modifiers.new(name="LimijoyHeadSkin", type="ARMATURE")
    modifier.object = armature
    return face_plate


def remove_baked_face_fragments(
    mesh_object: bpy.types.Object,
    *,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
    front_threshold: float,
) -> int:
    """Remove only the old front-face triangles that the new cap replaces."""

    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    mesh_object.select_set(True)
    bpy.context.view_layer.objects.active = mesh_object
    matrix_world = mesh_object.matrix_world.copy()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    edit_mesh = bmesh.from_edit_mesh(mesh_object.data)
    edit_mesh.faces.ensure_lookup_table()
    selected = 0
    for face in edit_mesh.faces:
        point = matrix_world @ face.calc_center_median()
        radius = ellipse_radius(point, centre_x, centre_z, radius_x, radius_z)
        # Keep a generous untouched border under the cap.  Polygon-centre
        # selection otherwise produces a saw-tooth hole exactly at the visible
        # cap edge because the source triangles extend beyond their centroids.
        if point.y < front_threshold and radius <= 0.90:
            face.select_set(True)
            selected += 1
    if selected < 100:
        raise RuntimeError(f"Baked-face removal selected too few polygons: {selected}")
    bmesh.update_edit_mesh(mesh_object.data, loop_triangles=False, destructive=False)
    bpy.ops.mesh.delete(type="FACE")
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh_object.data.update()
    return selected


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
face_radius_x = size.x * 0.238
face_radius_z = size.z * 0.137
baked_face_polygons_removed = remove_baked_face_fragments(
    main_mesh,
    centre_x=face_centre_x,
    centre_z=face_centre_z,
    radius_x=face_radius_x,
    radius_z=face_radius_z,
    front_threshold=centre.y - size.y * 0.185,
)
face_material, face_texture_node = create_face_material(texture_dir / "limijoy-face-neutral.png")
face_plate = create_face_plate(
    armature=armature,
    material=face_material,
    centre_x=face_centre_x,
    centre_z=face_centre_z,
    radius_x=face_radius_x,
    radius_z=face_radius_z,
    boundary_forward=centre.y - size.y * 0.335,
    depth=size.y * 0.172,
)
face_plate_vertex_count = len(face_plate.data.vertices)
face_plate_polygon_count = len(face_plate.data.polygons)
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
face_plate.select_set(True)
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
    "modified_source_vertices": 0,
    "removed_baked_face_polygons": baked_face_polygons_removed,
    "face_plate_vertices": face_plate_vertex_count,
    "face_plate_polygons": face_plate_polygon_count,
    "face_plate_head_group": "Bone_033",
    "source_bounds": source_bounds,
    "exported_bounds": {
        "minimum": tuple(float(value) for value in exported_minimum),
        "maximum": tuple(float(value) for value in exported_maximum),
    },
    "states": list(STATES),
    "body_topology_policy": "Body and rig untouched; only covered facial triangles removed; no remesh, decimation, or auto-rigging",
    "face_surface_policy": "Smooth skinned ellipsoidal cap replaces fragmented baked facial pieces",
}
(OUTPUT / "prototype-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
