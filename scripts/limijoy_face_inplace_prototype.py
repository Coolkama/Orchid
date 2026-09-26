"""Build and render an in-place textured-face prototype for Limijoy.

This iteration keeps the original Meshy facial topology and face outline.  It
removes baked facial relief by moving only front-face vertices in depth toward
a robustly fitted smooth reference surface, while leaving a wide boundary band
fixed.  The original UV map, vertex groups, armature, and non-facial geometry
are preserved.  A second UV layer and material are added only to drive the
texture-based expression states.

A small central forward protrusion is preserved when one is detected in the
expected nose region.  Nose preservation is best-effort: it must not prevent
the baked mouth/eye/brow relief from being cleaned away.
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
FACE_UV_NAME = "LimijoyFaceUV"
FACE_MATERIAL_NAME = "Limijoy_Face_Animated"


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
                f"{name} parent changed from {source[name]['parent']} "
                f"to {exported[name]['parent']}"
            )
        for key in ("head", "tail", "matrix"):
            delta = max(
                abs(float(left) - float(right))
                for left, right in zip(source[name][key], exported[name][key])
            )
            maximum_delta = max(maximum_delta, delta)
    return maximum_delta, problems


def smooth_step(edge0: float, edge1: float, value: float) -> float:
    if math.isclose(edge0, edge1):
        return 0.0 if value < edge0 else 1.0
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
    """Fit y=f(x,z), rejecting baked facial relief as outliers."""
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
    for _ in range(7):
        coefficients = np.linalg.lstsq(design[keep], y_values[keep], rcond=None)[0]
        residuals = y_values - design @ coefficients
        median = float(np.median(residuals[keep]))
        deviation = float(np.median(np.abs(residuals[keep] - median)))
        limit = max(0.0015, deviation * 3.0)
        updated = np.abs(residuals - median) <= limit
        if updated.sum() < 100:
            break
        if np.array_equal(updated, keep):
            keep = updated
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


def uv_snapshot(uv_layer: bpy.types.MeshUVLoopLayer | None) -> list[tuple[float, float]]:
    if uv_layer is None:
        return []
    return [(float(item.uv.x), float(item.uv.y)) for item in uv_layer.data]


def max_uv_delta(
    before: list[tuple[float, float]],
    after: list[tuple[float, float]],
) -> float:
    if len(before) != len(after):
        return float("inf")
    if not before:
        return 0.0
    return max(
        max(abs(left[0] - right[0]), abs(left[1] - right[1]))
        for left, right in zip(before, after)
    )


def create_face_material(
    texture_path: Path,
) -> tuple[bpy.types.Material, bpy.types.ShaderNodeTexImage]:
    material = bpy.data.materials.new(FACE_MATERIAL_NAME)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.uv_map = FACE_UV_NAME
    texture.name = "LimijoyFaceTexture"
    texture.label = "Animated Limijoy face"
    texture.interpolation = "Linear"
    texture.extension = "CLIP"
    texture.image = bpy.data.images.load(str(texture_path), check_existing=True)

    links.new(uv_map.outputs["UV"], texture.inputs["Vector"])
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


def find_nose_preservation(
    points: dict[int, Vector],
    fitted_forward: dict[int, float],
    *,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
    depth_scale: float,
) -> tuple[bool, Vector | None, set[int]]:
    """Detect and retain a real central protrusion if one exists.

    The source render may contain no physical nose at all.  We therefore only
    preserve geometry when a narrow central region above the mouth has a clear
    forward protrusion relative to the fitted neutral face.
    """
    samples: list[tuple[int, float, float, float]] = []
    for index, point in points.items():
        nx = (point.x - centre_x) / radius_x
        nz = (point.z - centre_z) / radius_z
        if abs(nx) > 0.18 or not -0.06 <= nz <= 0.30:
            continue
        protrusion = fitted_forward[index] - point.y
        samples.append((index, protrusion, nx, nz))

    if not samples:
        return False, None, set()

    threshold = max(depth_scale * 0.012, 0.0025)
    best = max(samples, key=lambda item: item[1])
    if best[1] < threshold:
        print(
            "No confident physical nose detected; central relief will be smoothed "
            f"(best protrusion {best[1]:.6f}, threshold {threshold:.6f})"
        )
        return False, None, set()

    best_index, best_protrusion, _, _ = best
    centre = points[best_index]
    preserved: set[int] = set()
    for index, protrusion, nx, nz in samples:
        dx = (points[index].x - centre.x) / (radius_x * 0.16)
        dz = (points[index].z - centre.z) / (radius_z * 0.18)
        distance_sq = dx * dx + dz * dz
        if distance_sq <= 1.0 and protrusion > threshold * 0.30:
            preserved.add(index)

    print(
        f"Preserving probable nose: {len(preserved)} vertices, "
        f"peak protrusion {best_protrusion:.6f}"
    )
    return True, centre, preserved


def smooth_face_in_place(
    mesh_object: bpy.types.Object,
    *,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
    front_threshold: float,
) -> dict[str, object]:
    """Move only facial vertices in depth; preserve outline/topology/weights/UVs."""
    mesh = mesh_object.data
    matrix_world = mesh_object.matrix_world.copy()
    matrix_inverse = matrix_world.inverted()

    world_points = {
        vertex.index: matrix_world @ vertex.co
        for vertex in mesh.vertices
    }
    candidates = {
        index: point
        for index, point in world_points.items()
        if point.y < front_threshold
        and ellipse_radius(point, centre_x, centre_z, radius_x, radius_z) <= 0.95
    }
    if len(candidates) < 500:
        raise RuntimeError(f"Facial smoothing selected too few vertices: {len(candidates)}")

    fit_samples = [
        point
        for point in candidates.values()
        if 0.58
        <= ellipse_radius(point, centre_x, centre_z, radius_x, radius_z)
        <= 0.90
    ]
    if len(fit_samples) < 100:
        fit_samples = list(candidates.values())
    coefficients = robust_surface_fit(fit_samples)
    fitted_forward = {
        index: surface_forward(coefficients, point)
        for index, point in candidates.items()
    }

    model_depth = max(point.y for point in world_points.values()) - min(
        point.y for point in world_points.values()
    )
    nose_detected, nose_centre, nose_vertices = find_nose_preservation(
        candidates,
        fitted_forward,
        centre_x=centre_x,
        centre_z=centre_z,
        radius_x=radius_x,
        radius_z=radius_z,
        depth_scale=model_depth,
    )

    modified = 0
    fixed_boundary = 0
    maximum_movement = 0.0
    movement_sum = 0.0

    for index, point in candidates.items():
        radius = ellipse_radius(point, centre_x, centre_z, radius_x, radius_z)
        if radius >= 0.84:
            fixed_boundary += 1
            continue

        boundary_weight = 1.0 - smooth_step(0.58, 0.84, radius)
        weight = 0.96 * boundary_weight

        nx = (point.x - centre_x) / radius_x
        nz = (point.z - centre_z) / radius_z
        mouth_focus = (
            (1.0 - smooth_step(0.20, 0.48, abs(nx)))
            * (1.0 - smooth_step(-0.42, -0.04, nz))
        )
        weight = max(weight, 0.985 * boundary_weight * mouth_focus)

        if nose_detected and nose_centre is not None:
            dx = (point.x - nose_centre.x) / (radius_x * 0.18)
            dz = (point.z - nose_centre.z) / (radius_z * 0.20)
            nose_distance = math.sqrt(dx * dx + dz * dz)
            nose_keep = 1.0 - smooth_step(0.65, 1.20, nose_distance)
            if index in nose_vertices:
                nose_keep = max(nose_keep, 0.92)
            weight *= 1.0 - 0.92 * nose_keep

        if weight <= 1.0e-6:
            continue

        target = point.copy()
        target.y = fitted_forward[index]
        new_world = point.lerp(target, weight)
        movement = (new_world - point).length
        if movement <= 1.0e-7:
            continue

        mesh.vertices[index].co = matrix_inverse @ new_world
        modified += 1
        maximum_movement = max(maximum_movement, movement)
        movement_sum += movement

    mesh.update()
    return {
        "candidate_vertices": len(candidates),
        "modified_facial_vertices": modified,
        "fixed_boundary_vertices": fixed_boundary,
        "modified_nonfacial_vertices": 0,
        "maximum_vertex_movement": maximum_movement,
        "mean_modified_vertex_movement": movement_sum / modified if modified else 0.0,
        "nose_preservation_attempted": True,
        "nose_detected": nose_detected,
        "nose_preserved_vertices": len(nose_vertices),
        "nose_centre": tuple(float(value) for value in nose_centre) if nose_centre else None,
    }


def apply_face_material_and_uv(
    mesh_object: bpy.types.Object,
    *,
    material: bpy.types.Material,
    centre_x: float,
    centre_z: float,
    radius_x: float,
    radius_z: float,
    front_threshold: float,
) -> dict[str, int]:
    """Add a face-only UV set/material without changing the source UV set."""
    mesh = mesh_object.data
    matrix_world = mesh_object.matrix_world.copy()

    original_uv = mesh.uv_layers.active
    face_uv = mesh.uv_layers.get(FACE_UV_NAME)
    if face_uv is None:
        face_uv = mesh.uv_layers.new(name=FACE_UV_NAME)

    if original_uv is not None and original_uv != face_uv:
        for index, item in enumerate(original_uv.data):
            face_uv.data[index].uv = item.uv

    mesh.materials.append(material)
    material_index = len(mesh.materials) - 1

    face_polygons = 0
    face_loops = 0
    for polygon in mesh.polygons:
        centre = matrix_world @ polygon.center
        radius = ellipse_radius(centre, centre_x, centre_z, radius_x, radius_z)
        if centre.y >= front_threshold or radius > 0.88:
            continue

        polygon.material_index = material_index
        face_polygons += 1
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            point = matrix_world @ mesh.vertices[vertex_index].co
            u = 0.5 + 0.49 * ((point.x - centre_x) / radius_x)
            v = 0.5 + 0.49 * ((point.z - centre_z) / radius_z)
            face_uv.data[loop_index].uv = (
                max(0.0, min(1.0, u)),
                max(0.0, min(1.0, v)),
            )
            face_loops += 1

    if face_polygons < 100:
        raise RuntimeError(f"Face material selected too few polygons: {face_polygons}")
    mesh.uv_layers.active = original_uv if original_uv is not None else face_uv
    mesh.update()
    return {
        "face_material_polygons": face_polygons,
        "face_uv_loops": face_loops,
    }


def configure_render(
    scene: bpy.types.Scene,
    minimum: Vector,
    maximum: Vector,
) -> bpy.types.Object:
    size = maximum - minimum
    extent = max(size)
    head_target = Vector(
        (
            (minimum.x + maximum.x) * 0.5,
            (minimum.y + maximum.y) * 0.5,
            minimum.z + size.z * 0.59,
        )
    )

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
    camera.rotation_euler = (
        head_target - camera.location
    ).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    for location, energy, radius in (
        (
            head_target + Vector((extent * 1.5, -extent * 1.8, extent * 1.6)),
            850,
            extent * 1.8,
        ),
        (
            head_target + Vector((-extent * 1.4, -extent * 1.2, extent * 0.8)),
            420,
            extent * 2.2,
        ),
        (
            head_target + Vector((0.0, extent * 1.6, extent * 1.4)),
            520,
            extent * 1.5,
        ),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.size = radius
        light.rotation_euler = (
            head_target - light.location
        ).to_track_quat("-Z", "Y").to_euler()
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
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
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
source_group_names = {group.name for group in main_mesh.vertex_groups}
source_vertex_count = len(main_mesh.data.vertices)
source_polygon_count = len(main_mesh.data.polygons)
source_uv_layer = main_mesh.data.uv_layers.active
source_uv_name = source_uv_layer.name if source_uv_layer else None
source_uv = uv_snapshot(source_uv_layer)

minimum, maximum = world_bounds(skinned_meshes)
size = maximum - minimum
extent = max(size)
centre = (minimum + maximum) * 0.5
configure_render(scene, minimum, maximum)

render(scene, "00-original-baked-face.png")

face_centre_x = centre.x
face_centre_z = minimum.z + size.z * 0.565
face_radius_x = size.x * 0.265
face_radius_z = size.z * 0.135
front_threshold = centre.y - size.y * 0.185

smoothing_report = smooth_face_in_place(
    main_mesh,
    centre_x=face_centre_x,
    centre_z=face_centre_z,
    radius_x=face_radius_x,
    radius_z=face_radius_z,
    front_threshold=front_threshold,
)

if len(main_mesh.data.vertices) != source_vertex_count:
    raise RuntimeError("In-place smoothing unexpectedly changed the source vertex count")
if len(main_mesh.data.polygons) != source_polygon_count:
    raise RuntimeError("In-place smoothing unexpectedly changed the source polygon count")
source_uv_after_geometry = uv_snapshot(
    main_mesh.data.uv_layers.get(source_uv_name) if source_uv_name else None
)
geometry_uv_delta = max_uv_delta(source_uv, source_uv_after_geometry)
if geometry_uv_delta > 1.0e-9:
    raise RuntimeError(f"In-place smoothing changed source UVs by {geometry_uv_delta:.12f}")

face_material, face_texture_node = create_face_material(
    texture_dir / "limijoy-face-neutral.png"
)
face_material_report = apply_face_material_and_uv(
    main_mesh,
    material=face_material,
    centre_x=face_centre_x,
    centre_z=face_centre_z,
    radius_x=face_radius_x,
    radius_z=face_radius_z,
    front_threshold=front_threshold,
)

source_uv_after_material = uv_snapshot(
    main_mesh.data.uv_layers.get(source_uv_name) if source_uv_name else None
)
material_uv_delta = max_uv_delta(source_uv, source_uv_after_material)
if material_uv_delta > 1.0e-9:
    raise RuntimeError(f"Face material setup changed source UVs by {material_uv_delta:.12f}")

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
    controls.look_at(
        look_origin + Vector((x_offset, -extent * 2.4, 0.0)),
        strength=0.92,
    )
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
bpy.ops.wm.save_as_mainfile(
    filepath=str(OUTPUT / "limijoy-face-texture-prototype.blend")
)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(prototype_path))
exported_scene = bpy.context.scene
exported_armature = next(
    obj for obj in exported_scene.objects if obj.type == "ARMATURE"
)
exported_meshes = [obj for obj in exported_scene.objects if obj.type == "MESH"]
exported_skinned = [
    obj
    for obj in exported_meshes
    if any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
if not exported_skinned:
    raise RuntimeError("Exported GLB contains no skinned mesh")
exported_main = max(exported_skinned, key=lambda obj: len(obj.data.vertices))
exported_rig = rig_fingerprint(exported_armature)
maximum_rig_delta, rig_problems = compare_rigs(source_rig, exported_rig)
if rig_problems:
    raise RuntimeError("; ".join(rig_problems))
if maximum_rig_delta > 1.0e-4:
    raise RuntimeError(
        f"Exported rig rest transforms drifted by {maximum_rig_delta:.8f}"
    )

exported_group_names = {group.name for group in exported_main.vertex_groups}
missing_groups = sorted(source_group_names - exported_group_names)
if missing_groups:
    raise RuntimeError(f"Exported skin lost vertex groups: {missing_groups}")

exported_minimum, exported_maximum = world_bounds(exported_skinned)
report = {
    "source_model": str(model_path.relative_to(ROOT)),
    "prototype_model": str(prototype_path.relative_to(ROOT)),
    "source_bones": len(source_rig),
    "exported_bones": len(exported_rig),
    "maximum_rig_rest_delta": maximum_rig_delta,
    "source_vertex_groups": len(source_group_names),
    "exported_vertex_groups": len(exported_group_names),
    "source_vertices": source_vertex_count,
    "source_polygons": source_polygon_count,
    "post_smoothing_vertices": source_vertex_count,
    "post_smoothing_polygons": source_polygon_count,
    "exported_roundtrip_vertices": len(exported_main.data.vertices),
    "exported_roundtrip_polygons": len(exported_main.data.polygons),
    **smoothing_report,
    **face_material_report,
    "source_uv_name": source_uv_name,
    "source_uv_max_delta": max(geometry_uv_delta, material_uv_delta),
    "added_face_uv_name": FACE_UV_NAME,
    "uv_policy": (
        "Original UV map preserved byte-for-byte within float tolerance; "
        "separate face UV layer added for expression textures"
    ),
    "body_topology_policy": (
        "Original mesh topology retained; no polygons removed or added and no "
        "remesh, decimation, or auto-rigging"
    ),
    "face_surface_policy": (
        "Original facial vertices moved only in depth toward a robust fitted "
        "surface; wide outer face band fixed; probable physical nose preserved "
        "when confidently detected"
    ),
    "states": list(STATES),
    "source_bounds": {
        "minimum": tuple(float(value) for value in minimum),
        "maximum": tuple(float(value) for value in maximum),
    },
    "exported_bounds": {
        "minimum": tuple(float(value) for value in exported_minimum),
        "maximum": tuple(float(value) for value in exported_maximum),
    },
}

with (OUTPUT / "prototype-report.json").open("w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)

print(json.dumps(report, indent=2))
