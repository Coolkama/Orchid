"""Prototype a recessed inner face patch while retaining Limijoy's original face border.

The Meshy face is a fragmented triangle soup, so an in-place smoothing pass
cannot remove all baked brows/cheeks/mouth pieces.  This experiment starts from
the already validated textured-face prototype script but changes the cut and
cap geometry: only the messy inner 90% of the facial ellipse is removed; the
original cream outer face border remains visible and defines Limijoy's organic
heart-like contour.  A smaller, shallower animated surface overlaps underneath
that retained border so its own oval edge is never intended to be visible.
"""

from __future__ import annotations

from pathlib import Path


SOURCE = Path(__file__).with_name("limijoy_face_texture_prototype.py")
code = SOURCE.read_text(encoding="utf-8")

replacements = (
    # Keep the original cream border instead of cutting all the way to the hood.
    (
        "if point.y < front_threshold and radius <= 0.95:",
        "if point.y < front_threshold and radius <= 0.90:",
    ),
    # The patch now terminates beneath the retained cream border rather than
    # beneath the green hood opening.
    (
        "face_radius_x = size.x * 0.285\nface_radius_z = size.z * 0.145",
        "face_radius_x = size.x * 0.260\nface_radius_z = size.z * 0.132",
    ),
    # Recess the patch edge under the surviving face shell and use only a
    # shallow convexity through the centre.  This should eliminate the exposed
    # cream oval/rim seen in the first cap prototype.
    (
        "boundary_forward=centre.y - size.y * 0.442,\n    depth=size.y * 0.100,",
        "boundary_forward=centre.y - size.y * 0.390,\n    depth=size.y * 0.060,",
    ),
)

for old, new in replacements:
    if old not in code:
        raise RuntimeError(f"Expected source fragment was not found: {old!r}")
    code = code.replace(old, new, 1)

code = code.replace(
    '"Smooth skinned ellipsoidal cap replaces fragmented baked facial pieces"',
    '"Recessed smooth skinned inner patch replaces only the fragmented central facial pieces; original cream outer face border retained"',
    1,
)
code = code.replace(
    '"Body and rig untouched; only covered facial triangles removed; no remesh, decimation, or auto-rigging"',
    '"Body and rig untouched; only fragmented inner facial triangles removed; original cream face border retained; no remesh, decimation, or auto-rigging"',
    1,
)

namespace = {
    "__name__": "__main__",
    "__file__": str(SOURCE),
    "__package__": None,
}
exec(compile(code, str(SOURCE), "exec"), namespace, namespace)
