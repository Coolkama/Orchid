"""Build and validate the Limijoy runtime keeper from the approved Orchid face review.

This deliberately reuses the exact face detection/projection implemented by
``limijoy_tpose_face_review.py``.  The production GLB keeps the original keeper
mesh and 45-bone armature untouched, and adds one very thin skinned face shell.
The shell owns a transparent material whose base-colour texture can be swapped
at runtime for neutral/blink/happy/curious/sad/determined.

Why a shell instead of exporting the Blender MixRGB review material?
The review material uses a second UV set to composite transparent features over
an existing glTF material.  That arbitrary Blender node graph is not a portable
glTF contract.  A dedicated skinned overlay primitive *is*: it has one UV set,
one ordinary glTF alpha-blended material, and follows the same armature.
"""

from __future__ import annotations

import json
import math
import runpy
import sys
from dataclasses import asdict
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "limijoy-runtime-assets"
RUNTIME_MODEL = OUTPUT / "glimmerkin.glb"
RUNTIME_FACES = OUTPUT / "faces"
RENDERS = OUTPUT / "renders"
OUTPUT.mkdir(parents=True, exist_ok=True)
RUNTIME_FACES.mkdir(parents=True, exist_ok=True)
RENDERS.mkdir(parents=True, exist_ok=True)

STATES = ("neutral", "blink", "happy", "curious", "sad", "determined")
FACE_SHELL_NAME = "LimijoyFaceOverlay"
FACE_MATERIAL_NAME = "LimijoyFaceOverlayMaterial"
EXPECTED_PROFILE = "tpose-blank-face-candidate-45"
EXPECTED_BONES = 45


def argument_path(name: str, default: Path) -> Path:
    prefix = f"--{name}="
    value = next((item for item in sys.argv if item.startswith(prefix)), None)
    result = Path(value.split("=", 1)[1]) if value else default
    return result if result.is_absolute() else ROOT / result


def restore_native_base_colour(material, principled) -> None:
    """Undo the temporary MixRGB overlay installed by the review script."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    mix = nodes.get("LimijoyFaceOverlayMix")
    if mix is None:
        raise RuntimeError("Approved review overlay mix was not installed")

    base_input = principled.inputs["Base Color"]
    original_socket = mix.inputs[1].links[0].from_socket if mix.inputs[1].is_linked else None
    original_default = tuple(float(value) for value in mix.inputs[1].default_value)
    for link in list(base_input.links):
        links.remove(link)
    if original_socket is not None:
        links.new(original_socket, base_input)
    else:
        base_input.default_value = original_default

    for name in ("LimijoyFaceOverlay", "LimijoyFaceOverlayMix", "LimijoyFaceOverlayUV"):
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)


def make_face_shell(main_mesh, face_polygon_indices, face_uv_name: str, neutral_path: Path, model_extent: float):
    """Duplicate only approved face polygons while retaining vertex weights/modifier."""
    shell = main_mesh.copy()
    shell.data = main_mesh.data.copy()
    shell.name = FACE_SHELL_NAME
    shell.data.name = f"{FACE_SHELL_NAME}Mesh"
    main_mesh.users_collection[0].objects.link(shell)

    keep = set(face_polygon_indices)
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bm.faces.ensure_lookup_table()
    remove_faces = [face for face in bm.faces if face.index not in keep]
    bmesh.ops.delete(bm, geom=remove_faces, context="FACES")
    loose_vertices = [vertex for vertex in bm.verts if not vertex.link_faces]
    if loose_vertices:
        bmesh.ops.delete(bm, geom=loose_vertices, context="VERTS")
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.update()

    # The copied object retains the original vertex groups and Armature modifier,
    # therefore this shell deforms with exactly the same 45-bone skin as the face.
    offset = max(model_extent, 1.0e-4) * 0.00045
    for vertex in shell.data.vertices:
        vertex.co += vertex.normal * offset
    shell.data.update()

    face_uv = shell.data.uv_layers.get(face_uv_name)
    if face_uv is None:
        raise RuntimeError(f"Copied shell is missing {face_uv_name!r}")
    for uv_layer in list(shell.data.uv_layers):
        if uv_layer != face_uv:
            shell.data.uv_layers.remove(uv_layer)
    face_uv.name = "UVMap"
    shell.data.uv_layers.active = face_uv

    material = bpy.data.materials.new(FACE_MATERIAL_NAME)
    material.use_nodes = True
    if hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
        except Exception:
            pass
    material.use_backface_culling = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    principled.inputs["Roughness"].default_value = 0.58

    image = bpy.data.images.load(str(neutral_path), check_existing=True)
    image.alpha_mode = "STRAIGHT"
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "LimijoyFaceTexture"
    texture.image = image
    # glTF has CLAMP_TO_EDGE rather than Blender's transparent CLIP mode.  The
    # authored PNG has a transparent perimeter, so clamping still yields clear
    # pixels for the small UV overshoot around the expanded mouth mask.
    texture.extension = "EXTEND"
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.name = "LimijoyFaceTextureUV"
    uv_map.uv_map = "UVMap"
    links.new(uv_map.outputs["UV"], texture.inputs["Vector"])
    links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])

    shell.data.materials.clear()
    shell.data.materials.append(material)
    for polygon in shell.data.polygons:
        polygon.material_index = 0

    return shell, material, texture


def export_runtime_model(armature, skinned_meshes, shell) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [armature, *skinned_meshes, shell]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.gltf(
        filepath=str(RUNTIME_MODEL),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_animations=True,
        export_skins=True,
        export_yup=True,
    )
    if not RUNTIME_MODEL.exists() or RUNTIME_MODEL.stat().st_size == 0:
        raise RuntimeError("Runtime GLB export produced no model")


def render(scene, path: Path) -> None:
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def find_runtime_face_material():
    return next(
        (material for material in bpy.data.materials if material.name.startswith(FACE_MATERIAL_NAME)),
        None,
    )


def find_runtime_face_texture(material):
    if material is None or not material.use_nodes:
        return None
    return next(
        (
            node
            for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image is not None
        ),
        None,
    )


model_path = argument_path("model", ROOT / "assets" / "models" / "glimmerkin-tpose-blank-face-candidate.glb")
texture_dir = argument_path("textures", ROOT / "output" / "limijoy-tpose-face-review" / "textures")
for state in STATES:
    source = texture_dir / f"limijoy-face-{state}-overlay.png"
    if not source.exists():
        raise FileNotFoundError(f"Missing approved face texture: {source}")
    (RUNTIME_FACES / source.name).write_bytes(source.read_bytes())

# Execute the approved review script first.  It leaves the exact selected face
# mask and LimijoyFaceUV projection in the Blender scene, so the runtime export
# cannot silently drift from the pictures that were approved.
review = runpy.run_path(str(SCRIPT_DIR / "limijoy_tpose_face_review.py"), run_name="__limijoy_face_review__")
main_mesh = review["main_mesh"]
armature = review["armature"]
skinned_meshes = review["skinned_meshes"]
face_uv_polygons = review["face_uv_polygons"]
face_uv_name = review["FACE_UV_NAME"]
material = review["material"]
principled = review["principled"]
model_size = review["size"]

restore_native_base_colour(material, principled)
shell, shell_material, shell_texture = make_face_shell(
    main_mesh,
    face_uv_polygons,
    face_uv_name,
    RUNTIME_FACES / "limijoy-face-neutral-overlay.png",
    max(model_size),
)
source_geometry = {
    "vertices": len(main_mesh.data.vertices),
    "polygons": len(main_mesh.data.polygons),
    "bones": len(armature.data.bones),
}
export_runtime_model(armature, skinned_meshes, shell)

# Re-import the exported GLB and validate the *portable* artifact rather than
# trusting Blender's pre-export scene.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(RUNTIME_MODEL))
scene = bpy.context.scene
runtime_armature = next(obj for obj in scene.objects if obj.type == "ARMATURE")
runtime_skinned_meshes = [
    obj
    for obj in scene.objects
    if obj.type == "MESH" and any(modifier.type == "ARMATURE" for modifier in obj.modifiers)
]
runtime_shell = next((obj for obj in runtime_skinned_meshes if obj.name.startswith(FACE_SHELL_NAME)), None)
if runtime_shell is None:
    raise RuntimeError("Exported GLB lost the skinned Limijoy face shell")
if len(runtime_armature.data.bones) != EXPECTED_BONES:
    raise RuntimeError(f"Runtime model has {len(runtime_armature.data.bones)} bones, expected {EXPECTED_BONES}")

# Re-resolve semantic rig profile after round-trip export.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from limijoy_body_semantic_controls import LimijoyBodySemanticControls  # noqa: E402
from limijoy_rig_profile_adapter import activate_semantic_rig_profile  # noqa: E402

profile = activate_semantic_rig_profile(runtime_armature)
if profile.name != EXPECTED_PROFILE:
    raise RuntimeError(f"Runtime GLB resolved {profile.name!r}, expected {EXPECTED_PROFILE!r}")

minimum, maximum = review["world_bounds"](runtime_skinned_meshes)
runtime_size = maximum - minimum
review["configure_render"](scene, minimum, maximum)
runtime_material = find_runtime_face_material()
runtime_texture = find_runtime_face_texture(runtime_material)
if runtime_texture is None:
    raise RuntimeError("Exported face material has no ordinary image texture")

# Render every runtime texture through the exported/re-imported shell.
for state in STATES:
    image = bpy.data.images.load(
        str(RUNTIME_FACES / f"limijoy-face-{state}-overlay.png"),
        check_existing=True,
    )
    image.alpha_mode = "STRAIGHT"
    runtime_texture.image = image
    bpy.context.view_layer.update()
    render(scene, RENDERS / f"10-{state}-front.png")

# And prove that the exported shell follows real semantic head/neck motion.
body = LimijoyBodySemanticControls(runtime_armature)
runtime_texture.image = bpy.data.images.load(
    str(RUNTIME_FACES / "limijoy-face-neutral-overlay.png"), check_existing=True
)
turns = {}
for label, yaw, pitch in (("right", 28.0, 0.0), ("left", -28.0, 0.0), ("up", 0.0, 18.0), ("down", 0.0, -18.0)):
    yaw_radians = math.radians(yaw)
    pitch_radians = math.radians(pitch)
    local = Vector(
        (
            math.sin(yaw_radians) * math.cos(pitch_radians),
            -math.cos(yaw_radians) * math.cos(pitch_radians),
            math.sin(pitch_radians),
        )
    )
    world = runtime_armature.matrix_world.to_quaternion() @ local
    target = body.look_origin() + world.normalized() * max(runtime_size) * 2.5
    result = body.look_at(target, strength=1.0, body_follow=0.0)
    turns[label] = asdict(result)
    render(scene, RENDERS / f"20-head-{label}.png")
body.reset_pose()

report = {
    "source_model": str(model_path.relative_to(ROOT)),
    "runtime_model": str(RUNTIME_MODEL.relative_to(ROOT)),
    "runtime_model_bytes": RUNTIME_MODEL.stat().st_size,
    "rig_profile": profile.name,
    "bone_count": len(runtime_armature.data.bones),
    "source_keeper_geometry": source_geometry,
    "runtime_face_shell": {
        "object": runtime_shell.name,
        "vertices": len(runtime_shell.data.vertices),
        "polygons": len(runtime_shell.data.polygons),
        "skinned": any(modifier.type == "ARMATURE" for modifier in runtime_shell.modifiers),
        "material": runtime_material.name if runtime_material else None,
    },
    "states": list(STATES),
    "head_turns": turns,
    "face_contract": {
        "method": "skinned transparent face shell",
        "material_name": FACE_MATERIAL_NAME,
        "runtime_texture_pattern": "faces/limijoy-face-<state>-overlay.png",
        "source_projection": "exact LimijoyFaceUV mask from approved tpose face review",
        "visible_width_scale": 0.855,
        "downward_uv_shift": 0.080,
    },
}
(OUTPUT / "runtime-assets-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
