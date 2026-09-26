"""Render revised texture-driven expressions on the 45-bone T-pose Limijoy keeper.

The model's native cream face is retained exactly. A second UV set projects only
transparent 2D features onto polygons detected as the cream facial patch. The
review also turns the real head/neck controls left, right, up and down to verify
the face remains attached under animation.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
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
from limijoy_rig_profile_adapter import activate_semantic_rig_profile  # noqa: E402

OUTPUT = ROOT / "output" / "limijoy-tpose-face-review"
RENDERS = OUTPUT / "renders"
TEXTURES = OUTPUT / "textures"
RENDERS.mkdir(parents=True, exist_ok=True)
TEXTURES.mkdir(parents=True, exist_ok=True)

EXPECTED_PROFILE = "tpose-blank-face-candidate-45"
STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")
FACE_UV_NAME = "LimijoyFaceUV"
OVERLAY_NODE_NAME = "LimijoyFaceOverlay"


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


def find_source_material_and_image(mesh_object: bpy.types.Object):
    for material in mesh_object.data.materials:
        if material is None or not material.use_nodes:
            continue
        principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if principled is None:
            continue
        base_input = principled.inputs.get("Base Color")
        if base_input is None or not base_input.is_linked:
            continue
        source = base_input.links[0].from_node
        if source.type == "TEX_IMAGE" and source.image is not None:
            return material, principled, source.image
    raise RuntimeError("Could not find source base-colour image on keeper mesh")


def image_pixels(image: bpy.types.Image) -> np.ndarray:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Source image {image.name!r} has no pixel data")
    values = np.asarray(image.pixels[:], dtype=np.float32)
    return values.reshape((height, width, 4))


def sample_uv_rgb(pixels: np.ndarray, uv: tuple[float, float]) -> np.ndarray:
    height, width, _ = pixels.shape
    u = float(uv[0]) % 1.0
    v = float(uv[1]) % 1.0
    x = max(0, min(width - 1, int(round(u * (width - 1)))))
    y = max(0, min(height - 1, int(round(v * (height - 1)))))
    return pixels[y, x, :3]


def cream_likelihood(rgb: np.ndarray) -> float:
    r, g, b = [float(value) for value in rgb]
    brightness = (r + g + b) / 3.0
    warm_balance = 1.0 - min(1.0, abs(r - g) * 2.5)
    blue_ratio = b / max(0.05, max(r, g))
    return brightness * max(0.0, warm_balance) * min(1.0, blue_ratio * 1.8)


def identify_native_face_polygons(mesh_object, *, minimum, maximum, source_image) -> list[int]:
    mesh = mesh_object.data
    source_uv = mesh.uv_layers.active
    if source_uv is None:
        raise RuntimeError("Keeper mesh has no source UV layer")
    pixels = image_pixels(source_image)
    size = maximum - minimum
    centre = (minimum + maximum) * 0.5
    selected = []
    matrix_world = mesh_object.matrix_world

    for polygon in mesh.polygons:
        point = matrix_world @ polygon.center
        if point.z < minimum.z + size.z * 0.53:
            continue
        if point.y > centre.y - size.y * 0.04:
            continue
        colours = [sample_uv_rgb(pixels, tuple(source_uv.data[loop].uv)) for loop in polygon.loop_indices]
        rgb = np.mean(np.stack(colours), axis=0)
        score = cream_likelihood(rgb)
        r, g, b = [float(value) for value in rgb]
        pale_enough = (
            score >= 0.22
            and r >= 0.20
            and g >= 0.20
            and b >= 0.10
            and b >= min(r, g) * 0.38
        )
        if pale_enough:
            selected.append(polygon.index)

    if len(selected) < 120:
        raise RuntimeError(f"Native face detection found only {len(selected)} polygons")
    if len(selected) > len(mesh.polygons) * 0.18:
        raise RuntimeError(f"Native face detection is too broad: {len(selected)} polygons")
    return selected


def expand_face_uv_polygons(mesh_object, face_polygons: list[int], rings: int = 1) -> list[int]:
    """Expand only the UV-assignment mask around the detected cream patch.

    The colour detector can omit isolated lower-face polygons where the native
    texture contains seams, dirt or dark edge pixels. Once the authored mouth
    was moved down, those omissions appeared as triangular bites in the mouth.
    Expanding the UV mask topologically gives those neighbouring polygons
    coherent face UVs while keeping the original cream selection as the source
    of the projection bounds.
    """
    mesh = mesh_object.data
    selected = set(face_polygons)
    frontier = set(face_polygons)
    vertex_to_polygons: dict[int, set[int]] = {}

    for polygon in mesh.polygons:
        for vertex_index in polygon.vertices:
            vertex_to_polygons.setdefault(vertex_index, set()).add(polygon.index)

    for _ in range(max(0, rings)):
        neighbours: set[int] = set()
        for polygon_index in frontier:
            for vertex_index in mesh.polygons[polygon_index].vertices:
                neighbours.update(vertex_to_polygons.get(vertex_index, ()))
        neighbours.difference_update(selected)
        if not neighbours:
            break
        selected.update(neighbours)
        frontier = neighbours

    return sorted(selected)


def configure_face_uv(
    mesh_object,
    face_polygons: list[int],
    uv_polygons: list[int] | None = None,
) -> dict[str, object]:
    """Project face artwork with preserved proportions and tuned placement.

    X and Z share one world-space extent so the source art keeps its physical
    aspect ratio. The authored features are narrowed to 85.5% of the original
    aspect-corrected width (about another 5% narrower than the previous 90%
    pass) and remain shifted downward without changing their height.

    The projection bounds come only from the reliably detected cream patch.
    UVs may additionally be written to an expanded polygon mask so small holes
    in colour detection cannot clip low facial features.
    """
    mesh = mesh_object.data
    source_uv = mesh.uv_layers.active
    matrix_world = mesh_object.matrix_world
    points = []
    for polygon_index in face_polygons:
        polygon = mesh.polygons[polygon_index]
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            points.append(matrix_world @ mesh.vertices[vertex_index].co)

    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_z = min(point.z for point in points)
    max_z = max(point.z for point in points)
    width = max_x - min_x
    height = max_z - min_z
    if width <= 1.0e-6 or height <= 1.0e-6:
        raise RuntimeError("Detected face bounds are degenerate")

    centre_x = (min_x + max_x) * 0.5
    centre_z = (min_z + max_z) * 0.5
    aspect_extent = max(width, height)
    assigned_polygons = uv_polygons if uv_polygons is not None else face_polygons

    face_uv = mesh.uv_layers.get(FACE_UV_NAME) or mesh.uv_layers.new(name=FACE_UV_NAME)
    for item in face_uv.data:
        item.uv = (0.0, 0.0)

    padding = 0.035
    usable = 1.0 - padding * 2.0
    visible_width_scale = 0.855
    horizontal_sample_scale = 1.0 / visible_width_scale
    downward_sample_offset = 0.080

    loops = 0
    for polygon_index in assigned_polygons:
        polygon = mesh.polygons[polygon_index]
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            point = matrix_world @ mesh.vertices[vertex_index].co
            face_uv.data[loop_index].uv = (
                padding
                + usable
                * (0.5 + ((point.x - centre_x) / aspect_extent) * horizontal_sample_scale),
                padding
                + usable
                * (0.5 + (point.z - centre_z) / aspect_extent + downward_sample_offset),
            )
            loops += 1
    mesh.uv_layers.active = source_uv
    mesh.update()
    return {
        "face_polygons": len(face_polygons),
        "face_uv_polygons": len(assigned_polygons),
        "face_uv_extra_polygons": len(assigned_polygons) - len(face_polygons),
        "face_uv_loops": loops,
        "face_width": float(width),
        "face_height": float(height),
        "face_width_to_height": float(width / height),
        "face_uv_aspect_extent": float(aspect_extent),
        "face_uv_aspect_preserved": True,
        "face_visible_width_scale": visible_width_scale,
        "face_downward_uv_shift": downward_sample_offset,
    }


def install_overlay(material, principled, overlay_path: Path):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    base_input = principled.inputs["Base Color"]
    source_link = base_input.links[0] if base_input.is_linked else None
    source_socket = source_link.from_socket if source_link else None
    source_default = tuple(float(value) for value in base_input.default_value)

    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.name = "LimijoyFaceOverlayUV"
    uv_map.uv_map = FACE_UV_NAME
    overlay = nodes.new("ShaderNodeTexImage")
    overlay.name = OVERLAY_NODE_NAME
    overlay.interpolation = "Linear"
    overlay.extension = "CLIP"
    overlay.image = bpy.data.images.load(str(overlay_path), check_existing=True)
    overlay.image.alpha_mode = "STRAIGHT"
    mix = nodes.new("ShaderNodeMixRGB")
    mix.name = "LimijoyFaceOverlayMix"
    mix.blend_type = "MIX"

    if source_link is not None:
        links.remove(source_link)
        links.new(source_socket, mix.inputs[1])
    else:
        mix.inputs[1].default_value = source_default
    links.new(uv_map.outputs["UV"], overlay.inputs["Vector"])
    links.new(overlay.outputs["Alpha"], mix.inputs[0])
    links.new(overlay.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], base_input)
    return overlay


def configure_render(scene, minimum, maximum):
    size = maximum - minimum
    extent = max(size)
    target = Vector(((minimum.x + maximum.x) * 0.5, (minimum.y + maximum.y) * 0.5, minimum.z + size.z * 0.72))
    engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = 620
    scene.render.resolution_y = 620
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = (0.028, 0.027, 0.035)

    bpy.ops.object.camera_add(location=target + Vector((0.0, -extent * 3.0, 0.0)))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size.z * 0.55
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    for location, energy, radius in (
        (target + Vector((extent * 1.4, -extent * 1.8, extent * 1.3)), 850, extent * 1.8),
        (target + Vector((-extent * 1.2, -extent, extent * 0.7)), 390, extent * 2.2),
        (target + Vector((0.0, extent * 1.4, extent * 1.0)), 470, extent * 1.5),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.size = radius
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    return camera


def render(scene, name: str) -> None:
    scene.render.filepath = str(RENDERS / name)
    bpy.ops.render.render(write_still=True)


def look_target(body, armature, yaw_degrees: float, pitch_degrees: float, distance: float) -> Vector:
    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)
    local = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch)))
    world = armature.matrix_world.to_quaternion() @ local
    return body.look_origin() + world.normalized() * distance


model_path = argument_path("model", ROOT / "assets" / "models" / "glimmerkin-tpose-blank-face-candidate.glb")
texture_dir = argument_path("textures", TEXTURES)
if not model_path.exists():
    raise FileNotFoundError(f"Keeper model missing: {model_path}")
for state in STATES:
    if not (texture_dir / f"limijoy-face-{state}-overlay.png").exists():
        raise FileNotFoundError(f"Missing revised overlay for {state}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
skinned_meshes = [obj for obj in scene.objects if obj.type == "MESH" and any(mod.type == "ARMATURE" for mod in obj.modifiers)]
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = activate_semantic_rig_profile(armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Expected {EXPECTED_PROFILE!r}, resolved {profile.name!r}")

source_vertices = len(main_mesh.data.vertices)
source_polygons = len(main_mesh.data.polygons)
source_bones = len(armature.data.bones)
minimum, maximum = world_bounds(skinned_meshes)
size = maximum - minimum
material, principled, source_image = find_source_material_and_image(main_mesh)
configure_render(scene, minimum, maximum)
render(scene, "00-native-blank.png")

face_polygons = identify_native_face_polygons(main_mesh, minimum=minimum, maximum=maximum, source_image=source_image)
face_uv_polygons = expand_face_uv_polygons(main_mesh, face_polygons, rings=2)
face_report = configure_face_uv(main_mesh, face_polygons, face_uv_polygons)
overlay = install_overlay(material, principled, texture_dir / "limijoy-face-neutral-overlay.png")

if len(main_mesh.data.vertices) != source_vertices or len(main_mesh.data.polygons) != source_polygons:
    raise RuntimeError("Face overlay setup changed keeper geometry")
if len(armature.data.bones) != source_bones:
    raise RuntimeError("Face overlay setup changed keeper rig")

for state in STATES:
    overlay.image = bpy.data.images.load(str(texture_dir / f"limijoy-face-{state}-overlay.png"), check_existing=True)
    overlay.image.alpha_mode = "STRAIGHT"
    bpy.context.view_layer.update()
    render(scene, f"10-{state}-front.png")

body = LimijoyBodySemanticControls(armature)
overlay.image = bpy.data.images.load(str(texture_dir / "limijoy-face-neutral-overlay.png"), check_existing=True)
overlay.image.alpha_mode = "STRAIGHT"
turns = {}
for label, yaw, pitch in (
    ("right", 28.0, 0.0),
    ("left", -28.0, 0.0),
    ("up", 0.0, 18.0),
    ("down", 0.0, -18.0),
):
    result = body.look_at(
        look_target(body, armature, yaw, pitch, max(size) * 2.5),
        strength=1.0,
        body_follow=0.0,
    )
    turns[label] = asdict(result)
    render(scene, f"20-head-{label}.png")
body.reset_pose()

report = {
    "model": str(model_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "bone_count": source_bones,
    "source_vertices": source_vertices,
    "post_overlay_vertices": len(main_mesh.data.vertices),
    "source_polygons": source_polygons,
    "post_overlay_polygons": len(main_mesh.data.polygons),
    "geometry_unchanged": len(main_mesh.data.vertices) == source_vertices and len(main_mesh.data.polygons) == source_polygons,
    "states": list(STATES),
    "head_turns": turns,
    "art_revision": {
        "overlay_visible_width_scale": 0.855,
        "overlay_downward_uv_shift": 0.080,
        "vertical_scale": 1.00,
        "uv_mask_expansion_rings": 2,
        "uv_mask_reason": "prevent lower mouth clipping on cream-patch polygons missed by colour detection",
    },
    "overlay_policy": "RGBA features over native cream material; native face geometry and shading retained",
    **face_report,
}
(OUTPUT / "face-review-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))