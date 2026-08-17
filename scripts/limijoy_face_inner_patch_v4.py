"""Final cosmetic cleanup candidate for Limijoy's recessed textured face.

V3 proved the retained-border approach works.  This pass keeps its successful
centre and heart-like outer cream face contour, but removes a few remaining
Meshy fragments in the lower/cheek transition zones and brings the recessed
patch edge slightly closer to the surviving border.  The centre expression
surface, rig, body and hood are otherwise unchanged.
"""

from __future__ import annotations

from pathlib import Path


SOURCE = Path(__file__).with_name("limijoy_face_texture_prototype.py")
code = SOURCE.read_text(encoding="utf-8")

# Replace the broad old 95% cut with a conservative 90% centre cut plus two
# targeted clean-up zones.  This preserves the top/side heart-shaped border,
# while removing the partial cheek leaves and ragged lower fragments visible
# in V3.
old_condition = """        if point.y < front_threshold and radius <= 0.95:\n            face.select_set(True)\n            selected += 1"""
new_condition = """        nx = (point.x - centre_x) / radius_x\n        nz = (point.z - centre_z) / radius_z\n        lower_cleanup = nz < -0.16 and radius <= 0.94\n        cheek_cleanup = abs(nx) > 0.58 and -0.62 < nz < 0.10 and radius <= 0.97\n        if point.y < front_threshold and (radius <= 0.90 or lower_cleanup or cheek_cleanup):\n            face.select_set(True)\n            selected += 1"""
if old_condition not in code:
    raise RuntimeError("Could not locate the original baked-face selection condition")
code = code.replace(old_condition, new_condition, 1)

replacements = (
    (
        "face_radius_x = size.x * 0.285\nface_radius_z = size.z * 0.145",
        "face_radius_x = size.x * 0.260\nface_radius_z = size.z * 0.132",
    ),
    (
        "boundary_forward=centre.y - size.y * 0.442,\n    depth=size.y * 0.100,",
        "boundary_forward=centre.y - size.y * 0.400,\n    depth=size.y * 0.055,",
    ),
)
for old, new in replacements:
    if old not in code:
        raise RuntimeError(f"Expected source fragment was not found: {old!r}")
    code = code.replace(old, new, 1)

code = code.replace(
    '"Smooth skinned ellipsoidal cap replaces fragmented baked facial pieces"',
    '"Recessed smooth skinned inner patch with targeted lower/cheek cleanup; original cream heart-like outer face border retained"',
    1,
)
code = code.replace(
    '"Body and rig untouched; only covered facial triangles removed; no remesh, decimation, or auto-rigging"',
    '"Body and rig untouched; fragmented central/lower-cheek facial triangles removed only; original cream outer face border retained; no remesh, decimation, or auto-rigging"',
    1,
)

namespace = {
    "__name__": "__main__",
    "__file__": str(SOURCE),
    "__package__": None,
}
exec(compile(code, str(SOURCE), "exec"), namespace, namespace)
