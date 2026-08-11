import bpy
import json
import math
import os
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "inspection"
OUTPUT.mkdir(parents=True, exist_ok=True)

model_arg = next((a for a in sys.argv if a.startswith("--model=")), None)
model_path = Path(model_arg.split("=", 1)[1]) if model_arg else ROOT / "assets" / "models" / "glimmerkin.glb"
if not model_path.is_absolute():
    model_path = ROOT / model_path
if not model_path.exists():
    raise FileNotFoundError(f"Model not found: {model_path}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene

# Renderer compatibility across Blender versions.
engine_items = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
if "BLENDER_EEVEE_NEXT" in engine_items:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
elif "BLENDER_EEVEE" in engine_items:
    scene.render.engine = "BLENDER_EEVEE"
else:
    scene.render.engine = "BLENDER_WORKBENCH"

scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False

world = bpy.data.worlds.new("InspectionWorld") if scene.world is None else scene.world
scene.world = world
world.color = (0.035, 0.035, 0.045)

mesh_objects = [o for o in scene.objects if o.type == "MESH"]
armatures = [o for o in scene.objects if o.type == "ARMATURE"]
if not mesh_objects:
    raise RuntimeError("Imported GLB contains no mesh objects")

# World-space bounds.
points = []
for obj in mesh_objects:
    points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
centre = (mins + maxs) * 0.5
size = maxs - mins
max_extent = max(size.x, size.y, size.z)

# Camera.
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.name = "InspectionCamera"
camera.data.type = "ORTHO"
camera.data.ortho_scale = max_extent * 1.35
scene.camera = camera

def point_camera(position):
    camera.location = position
    direction = centre - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

# Simple studio lighting.
for name, loc, energy, size_l in [
    ("Key", centre + Vector((max_extent * 2.2, -max_extent * 2.2, max_extent * 2.4)), 1000, max_extent * 2.0),
    ("Fill", centre + Vector((-max_extent * 2.0, -max_extent * 1.0, max_extent * 1.2)), 650, max_extent * 2.5),
    ("Rim", centre + Vector((0, max_extent * 2.2, max_extent * 1.8)), 800, max_extent * 1.8),
]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size_l
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

# Neutral ground plane slightly below the model.
bpy.ops.mesh.primitive_plane_add(size=max_extent * 6, location=(centre.x, centre.y, mins.z - max_extent * 0.015))
ground = bpy.context.object
ground.name = "InspectionGround"
mat = bpy.data.materials.new("GroundMaterial")
mat.diffuse_color = (0.06, 0.06, 0.075, 1)
ground.data.materials.append(mat)

views = {
    "front": Vector((0, -1, 0)),
    "three_quarter": Vector((1, -1, 0)),
    "left": Vector((-1, 0, 0)),
    "right": Vector((1, 0, 0)),
    "back": Vector((0, 1, 0)),
}
for name, axis in views.items():
    axis.normalize()
    point_camera(centre + axis * max_extent * 4.0 + Vector((0, 0, size.z * 0.04)))
    scene.render.filepath = str(OUTPUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)

mesh_report = []
total_vertices = 0
total_edges = 0
total_polygons = 0
for obj in mesh_objects:
    mesh = obj.data
    verts = len(mesh.vertices)
    edges = len(mesh.edges)
    polys = len(mesh.polygons)
    total_vertices += verts
    total_edges += edges
    total_polygons += polys
    tris = sum(max(1, len(p.vertices) - 2) for p in mesh.polygons)
    mesh_report.append({
        "name": obj.name,
        "vertices": verts,
        "edges": edges,
        "polygons": polys,
        "triangles_estimated": tris,
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "vertex_groups": [g.name for g in obj.vertex_groups],
        "armature_modifiers": [m.object.name for m in obj.modifiers if m.type == "ARMATURE" and m.object],
    })

armature_report = []
for arm_obj in armatures:
    bones = []
    for bone in arm_obj.data.bones:
        bones.append({
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "children": [c.name for c in bone.children],
            "use_deform": bone.use_deform,
            "head_local": list(bone.head_local),
            "tail_local": list(bone.tail_local),
        })
    armature_report.append({"name": arm_obj.name, "bone_count": len(bones), "bones": bones})

report = {
    "source": str(model_path.relative_to(ROOT) if model_path.is_relative_to(ROOT) else model_path),
    "blender_version": bpy.app.version_string,
    "bounds": {"min": list(mins), "max": list(maxs), "size": list(size), "centre": list(centre)},
    "summary": {
        "mesh_objects": len(mesh_objects),
        "armatures": len(armatures),
        "vertices": total_vertices,
        "edges": total_edges,
        "polygons": total_polygons,
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "actions": len(bpy.data.actions),
    },
    "meshes": mesh_report,
    "armatures": armature_report,
    "actions": [a.name for a in bpy.data.actions],
    "materials": [m.name for m in bpy.data.materials],
    "images": [{"name": i.name, "size": list(i.size)} for i in bpy.data.images],
}

with open(OUTPUT / "report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "inspection.blend"))
print(json.dumps(report["summary"], indent=2))
