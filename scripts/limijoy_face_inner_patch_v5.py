"""Polish the successful V3 retained-border face without cutting more geometry.

V4 proved that deleting the remaining side fragments can open holes at oblique
head angles.  This pass therefore starts from V3's conservative 90% central
cut and keeps all of its border geometry.  Only the few retained lower-side
facial fragments are reassigned to a plain cream material so they blend into
the surviving face border instead of showing their old green atlas colour.
"""

from __future__ import annotations

from pathlib import Path


SOURCE = Path(__file__).with_name("limijoy_face_texture_prototype.py")
code = SOURCE.read_text(encoding="utf-8")

replacements = (
    (
        "if point.y < front_threshold and radius <= 0.95:",
        "if point.y < front_threshold and radius <= 0.90:",
    ),
    (
        "face_radius_x = size.x * 0.285\nface_radius_z = size.z * 0.145",
        "face_radius_x = size.x * 0.260\nface_radius_z = size.z * 0.132",
    ),
    (
        "boundary_forward=centre.y - size.y * 0.442,\n    depth=size.y * 0.100,",
        "boundary_forward=centre.y - size.y * 0.390,\n    depth=size.y * 0.060,",
    ),
)
for old, new in replacements:
    if old not in code:
        raise RuntimeError(f"Expected source fragment was not found: {old!r}")
    code = code.replace(old, new, 1)

# Recolour, rather than delete, the two small retained cheek/edge zones that
# V3 left visible.  A flat material deliberately has no Meshy atlas normal map.
hook = "face_plate_vertex_count = len(face_plate.data.vertices)"
injection = r'''# Neutralise retained side fragments without changing their geometry.
face_border_material = bpy.data.materials.new("Limijoy_Face_Border_Clean")
face_border_material.use_nodes = True
border_shader = face_border_material.node_tree.nodes.get("Principled BSDF")
if border_shader is not None:
    border_shader.inputs["Base Color"].default_value = (0.86, 0.80, 0.56, 1.0)
    border_shader.inputs["Roughness"].default_value = 0.58
    if "Specular IOR Level" in border_shader.inputs:
        border_shader.inputs["Specular IOR Level"].default_value = 0.28
    elif "Specular" in border_shader.inputs:
        border_shader.inputs["Specular"].default_value = 0.28
main_mesh.data.materials.append(face_border_material)
border_material_index = len(main_mesh.data.materials) - 1
border_matrix_world = main_mesh.matrix_world.copy()
retained_edge_polygons_recoloured = 0
for polygon in main_mesh.data.polygons:
    point = border_matrix_world @ polygon.center
    radius = ellipse_radius(
        point,
        face_centre_x,
        face_centre_z,
        removal_radius_x,
        removal_radius_z,
    )
    nx = (point.x - face_centre_x) / removal_radius_x
    nz = (point.z - face_centre_z) / removal_radius_z
    cheek_edge = (
        0.88 <= radius <= 1.02
        and abs(nx) >= 0.58
        and -0.62 <= nz <= 0.08
    )
    if point.y < centre.y - size.y * 0.185 and cheek_edge:
        polygon.material_index = border_material_index
        polygon.use_smooth = True
        retained_edge_polygons_recoloured += 1
main_mesh.data.update()
print(f"Neutralised {retained_edge_polygons_recoloured} retained cheek-edge polygons")

face_plate_vertex_count = len(face_plate.data.vertices)'''
if hook not in code:
    raise RuntimeError("Could not locate face-plate count hook")
code = code.replace(hook, injection, 1)

# Include the cosmetic operation in the validation report.
report_hook = '"modified_source_vertices": 0,'
if report_hook not in code:
    raise RuntimeError("Could not locate prototype report hook")
code = code.replace(
    report_hook,
    report_hook + '\n    "retained_edge_polygons_recoloured": retained_edge_polygons_recoloured,',
    1,
)

code = code.replace(
    '"Smooth skinned ellipsoidal cap replaces fragmented baked facial pieces"',
    '"Recessed smooth skinned inner patch; original cream heart-like face border retained; residual lower-side fragments neutralised to plain cream without further deletion"',
    1,
)
code = code.replace(
    '"Body and rig untouched; only covered facial triangles removed; no remesh, decimation, or auto-rigging"',
    '"Body and rig untouched; conservative central facial cut only; retained border geometry preserved; no remesh, decimation, or auto-rigging"',
    1,
)

namespace = {
    "__name__": "__main__",
    "__file__": str(SOURCE),
    "__package__": None,
}
exec(compile(code, str(SOURCE), "exec"), namespace, namespace)
