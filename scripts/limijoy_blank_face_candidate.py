"""Render texture expressions directly on the new native blank Limijoy face.

Unlike the earlier face-plate experiments, this prototype never cuts, smooths,
or replaces facial geometry.  It detects the cream front-face polygons already
present in the new Meshy model, gives only those polygons a dedicated expression
material/UV layer, and proves the texture remains attached while the real
head/neck rig turns.

The candidate rig is resolved semantically through limijoy_rig_profiles.py so
this experiment also validates that the 28-bone Meshy generation is a usable
second rig profile.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Iterable

import bpy
import numpy as np
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from limijoy_rig_profiles import resolve_rig_profile  # noqa: E402


OUTPUT = ROOT / "output" / "limijoy-blank-face-candidate"
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
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
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
            "matrix": tuple(
                float(value)
                for row in bone.matrix_local
                for value in row
            ),
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

    shader.inputs["Roughness"].default_value = 0.62
    if "Specular IOR Level" in shader.inputs:
        shader.inputs["Specular IOR Level"].default_value = 0.22
    elif "Specular" in shader.inputs:
        shader.inputs["Specular"].default_value = 0.22

    material.diffuse_color = (0.88, 0.83, 0.58, 1.0)
    material.use_backface_culling = False
    return material, texture


def find_base_colour_image(mesh_object: bpy.types.Object) -> bpy.types.Image:
    for material in mesh_object.data.materials:
        if material is None or not material.use_nodes:
            continue
        nodes = material.node_tree.nodes
        principled = next(
            (node for node in nodes if node.type == "BSDF_PRINCIPLED"),
            None,
        )
        if principled is None:
            continue
        base_input = principled.inputs.get("Base Color")
        if base_input is None or not base_input.is_linked:
            continue
        source = base_input.links[0].from_node
        if source.type == "TEX_IMAGE" and source.image is not None:
            return source.image
    raise RuntimeError("Could not find source base-colour image on Mesh_0")


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


def identify_native_face_polygons(
    mesh_object: bpy.types.Object,
    *,
    minimum: Vector,
    maximum: Vector,
) -> list[int]:
    mesh = mesh_object.data
    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        raise RuntimeError("Candidate mesh has no source UV layer")

    image = find_base_colour_image(mesh_object)
    pixels = image_pixels(image)
    size = maximum - minimum
    centre = (minimum + maximum) * 0.5
    selected: list[int] = []
    matrix_world = mesh_object.matrix_world

    for polygon in mesh.polygons:
        point = matrix_world @ polygon.center
        if point.z < minimum.z + size.z * 0.53:
            continue
        if point.y > centre.y - size.y * 0.04:
            continue

        colours = [
            sample_uv_rgb(pixels, tuple(uv_layer.data[loop_index].uv))
            for loop_index in polygon.loop_indices
        ]
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
        raise RuntimeError(
            f"Native face detection found only {len(selected)} polygons"
        )
    if len(selected) > len(mesh.polygons) * 0.18:
        raise RuntimeError(
            f"Native face detection is too broad: {len(selected)} polygons"
        )
    return selected


def assign_expression_material(
    mesh_object: bpy.types.Object,
    face_polygons: list[int],
    material: bpy.types.Material,
) -> dict[str, object]:
    mesh = mesh_object.data
    source_uv = mesh.uv_layers.active
    if source_uv is None:
        raise RuntimeError("Candidate mesh has no source UV layer")

    face_set = set(face_polygons)
    matrix_world = mesh_object.matrix_world
    face_points: list[Vector] = []
    for polygon_index in face_polygons:
        polygon = mesh.polygons[polygon_index]
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            face_points.append(matrix_world @ mesh.vertices[vertex_index].co)

    min_x = min(point.x for point in face_points)
    max_x = max(point.x for point in face_points)
    min_z = min(point.z for point in face_points)
    max_z = max(point.z for point in face_points)
    width = max_x - min_x
    height = max_z - min_z
    if width <= 1.0e-6 or height <= 1.0e-6:
        raise RuntimeError("Detected native face has degenerate bounds")

    face_uv = mesh.uv_layers.get(FACE_UV_NAME)
    if face_uv is None:
        face_uv = mesh.uv_layers.new(name=FACE_UV_NAME)
    for index, source in enumerate(source_uv.data):
        face_uv.data[index].uv = source.uv

    mesh.materials.append(material)
    material_index = len(mesh.materials) - 1
    padding = 0.035
    usable = 1.0 - padding * 2.0
    loop_count = 0

    for polygon in mesh.polygons:
        if polygon.index not in face_set:
            continue
        polygon.material_index = material_index
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            point = matrix_world @ mesh.vertices[vertex_index].co
            u = padding + usable * ((point.x - min_x) / width)
            v = padding + usable * ((point.z - min_z) / height)
            face_uv.data[loop_index].uv = (
                max(0.0, min(1.0, u)),
                max(0.0, min(1.0, v)),
            )
            loop_count += 1

    mesh.uv_layers.active = source_uv
    mesh.update()
    return {
        "face_polygons": len(face_polygons),
        "face_uv_loops": loop_count,
        "face_bounds": {
            "minimum": [float(min_x), float(min_z)],
            "maximum": [float(max_x), float(max_z)],
        },
        "geometry_policy": (
            "Native blank face retained exactly; no facial vertices or polygons "
            "added, removed, smoothed, or repositioned"
        ),
        "uv_policy": (
            "Source UV retained; LimijoyFaceUV added only for polygons detected "
            "as the native cream facial patch"
        ),
    }


class CandidateLookControls:
    """Small semantic look proof using the resolved candidate rig profile."""

    def __init__(self, armature: bpy.types.Object, profile) -> None:
        self.armature = armature
        self.profile = profile
        body = profile.body
        self.torso = armature.pose.bones[body["torso"]]
        self.neck = armature.pose.bones[body["neck"]]
        self.head = armature.pose.bones[body["head"]]
        self.controlled = (self.torso, self.neck, self.head)
        for pose_bone in self.controlled:
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        self.rest = {
            pose_bone.name: pose_bone.matrix_basis.copy()
            for pose_bone in self.controlled
        }

    def reset(self) -> None:
        for pose_bone in self.controlled:
            pose_bone.matrix_basis = self.rest[pose_bone.name].copy()
        bpy.context.view_layer.update()

    def character_axis(self, axis) -> Vector:
        return (
            self.armature.matrix_world.to_quaternion()
            @ Vector(axis).normalized()
        ).normalized()

    def pose_bone_world_rotation(self, pose_bone: bpy.types.PoseBone) -> Quaternion:
        result = (
            self.armature.matrix_world.to_quaternion()
            @ pose_bone.matrix.to_quaternion()
        )
        result.normalize()
        return result

    def apply_yaw(self, pose_bone: bpy.types.PoseBone, degrees: float) -> None:
        delta = Quaternion(
            self.character_axis((0.0, 0.0, 1.0)),
            math.radians(degrees),
        )
        desired_world = delta @ self.pose_bone_world_rotation(pose_bone)
        desired_world.normalize()
        desired_armature = (
            self.armature.matrix_world.to_quaternion().inverted()
            @ desired_world
        )
        desired_matrix = desired_armature.to_matrix().to_4x4()
        desired_matrix.translation = pose_bone.head.copy()
        pose_bone.matrix = desired_matrix
        bpy.context.view_layer.update()

    def turn(self, degrees: float) -> None:
        self.reset()
        torso = max(-6.0, min(6.0, degrees * 0.18))
        neck = max(-12.0, min(12.0, degrees * 0.32))
        head = max(-20.0, min(20.0, degrees - torso - neck))
        self.apply_yaw(self.torso, torso)
        self.apply_yaw(self.neck, neck)
        self.apply_yaw(self.head, head)


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
            minimum.z + size.z * 0.68,
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
        scene.world = bpy.data.worlds.new("LimijoyCandidateWorld")
    scene.world.color = (0.028, 0.027, 0.035)

    camera_location = head_target + Vector((0.0, -extent * 3.0, 0.0))
    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.name = "LimijoyCandidateCamera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size.z * 0.66
    camera.rotation_euler = (
        head_target - camera.location
    ).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    for location, energy, radius in (
        (
            head_target + Vector((extent * 1.4, -extent * 1.8, extent * 1.4)),
            850,
            extent * 1.8,
        ),
        (
            head_target + Vector((-extent * 1.2, -extent * 1.0, extent * 0.7)),
            390,
            extent * 2.2,
        ),
        (
            head_target + Vector((0.0, extent * 1.4, extent * 1.2)),
            470,
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


model_path = argument_path(
    "model",
    ROOT / "assets" / "models" / "glimmerkin-blank-face-candidate.glb",
)
texture_dir = argument_path("textures", TEXTURES)
if not model_path.exists():
    raise FileNotFoundError(
        f"Blank-face candidate GLB is missing: {model_path}. "
        "Upload the new Meshy export to that repository path."
    )
for state in STATES:
    texture_path = texture_dir / f"limijoy-face-{state}.png"
    if not texture_path.exists():
        raise FileNotFoundError(f"Missing generated face texture: {texture_path}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
armature = next((obj for obj in scene.objects if obj.type == "ARMATURE"), None)
if armature is None:
    raise RuntimeError("Candidate GLB contains no armature")
skinned_meshes = [
    obj
    for obj in scene.objects
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
if not skinned_meshes:
    raise RuntimeError("Candidate GLB contains no skinned mesh")
main_mesh = max(skinned_meshes, key=lambda obj: len(obj.data.vertices))

if armature.animation_data and armature.animation_data.action:
    armature.animation_data.action = None
for pose_bone in armature.pose.bones:
    pose_bone.matrix_basis.identity()
bpy.context.view_layer.update()

profile = resolve_rig_profile(armature.data.bones.keys())
if profile.name != "blank-face-candidate-28":
    raise RuntimeError(f"Expected blank-face candidate rig, resolved {profile.name!r}")

source_rig = rig_fingerprint(armature)
source_vertex_count = len(main_mesh.data.vertices)
source_polygon_count = len(main_mesh.data.polygons)
source_group_names = {group.name for group in main_mesh.vertex_groups}
minimum, maximum = world_bounds(skinned_meshes)

configure_render(scene, minimum, maximum)
render(scene, "00-native-blank-face.png")
face_polygons = identify_native_face_polygons(
    main_mesh,
    minimum=minimum,
    maximum=maximum,
)
face_material, face_texture = create_face_material(
    texture_dir / "limijoy-face-neutral.png"
)
face_report = assign_expression_material(main_mesh, face_polygons, face_material)

if len(main_mesh.data.vertices) != source_vertex_count:
    raise RuntimeError("Native face setup changed the candidate vertex count")
if len(main_mesh.data.polygons) != source_polygon_count:
    raise RuntimeError("Native face setup changed the candidate polygon count")

for state in STATES:
    face_texture.image = bpy.data.images.load(
        str(texture_dir / f"limijoy-face-{state}.png"),
        check_existing=True,
    )
    bpy.context.view_layer.update()
    render(scene, f"10-{state}-front.png")

look = CandidateLookControls(armature, profile)
for label, degrees, state in (
    ("right", 28.0, "neutral"),
    ("left", -28.0, "blink"),
):
    look.turn(degrees)
    face_texture.image = bpy.data.images.load(
        str(texture_dir / f"limijoy-face-{state}.png"),
        check_existing=True,
    )
    bpy.context.view_layer.update()
    render(scene, f"20-{state}-head-{label}.png")

look.reset()
face_texture.image = bpy.data.images.load(
    str(texture_dir / "limijoy-face-neutral.png"),
    check_existing=True,
)
bpy.context.view_layer.update()

prototype_path = OUTPUT / "glimmerkin-blank-face-textured.glb"
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
    filepath=str(OUTPUT / "limijoy-blank-face-candidate.blend")
)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(prototype_path))
exported_scene = bpy.context.scene
exported_armature = next(
    obj for obj in exported_scene.objects if obj.type == "ARMATURE"
)
exported_meshes = [
    obj
    for obj in exported_scene.objects
    if obj.type == "MESH"
    and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
exported_main = max(exported_meshes, key=lambda obj: len(obj.data.vertices))
exported_rig = rig_fingerprint(exported_armature)
maximum_rig_delta, rig_problems = compare_rigs(source_rig, exported_rig)
if rig_problems:
    raise RuntimeError("; ".join(rig_problems))
if maximum_rig_delta > 1.0e-4:
    raise RuntimeError(
        f"Candidate rig rest transforms drifted by {maximum_rig_delta:.8f}"
    )

exported_group_names = {group.name for group in exported_main.vertex_groups}
missing_groups = sorted(source_group_names - exported_group_names)
if missing_groups:
    raise RuntimeError(f"Exported candidate lost vertex groups: {missing_groups}")

semantic_bones = {
    "body": dict(profile.body),
    "right_arm": dict(profile.right_arm),
    "left_arm": dict(profile.left_arm),
}
mapped_missing = sorted(
    {
        bone
        for mapping in semantic_bones.values()
        for bone in mapping.values()
        if bone not in source_rig
    }
)
if mapped_missing:
    raise RuntimeError(
        f"Candidate semantic map references missing bones: {mapped_missing}"
    )

report = {
    "source_model": str(model_path.relative_to(ROOT)),
    "prototype_model": str(prototype_path.relative_to(ROOT)),
    "rig_profile": profile.name,
    "source_bones": len(source_rig),
    "exported_bones": len(exported_rig),
    "maximum_rig_rest_delta": maximum_rig_delta,
    "source_vertex_groups": len(source_group_names),
    "exported_vertex_groups": len(exported_group_names),
    "source_vertices": source_vertex_count,
    "source_polygons": source_polygon_count,
    "semantic_bones": semantic_bones,
    "all_semantic_bones_present": not mapped_missing,
    **face_report,
    "states": list(STATES),
}
with (OUTPUT / "candidate-report.json").open("w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
print(json.dumps(report, indent=2))
