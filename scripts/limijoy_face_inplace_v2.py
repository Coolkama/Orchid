"""Experimental refinement of the Limijoy in-place face prototype.

This wrapper deliberately keeps the validated v1 script intact while applying
small source-level refinements before executing it: full central relief
projection and regenerated shading normals.  Once visually approved these
changes can be folded back into the main prototype script.
"""

from __future__ import annotations

from pathlib import Path


SOURCE = Path(__file__).with_name("limijoy_face_inplace_prototype.py")
code = SOURCE.read_text(encoding="utf-8")

replacements = (
    (
        "if radius >= 0.84:\n            fixed_boundary += 1",
        "if radius >= 0.86:\n            fixed_boundary += 1",
    ),
    (
        "boundary_weight = 1.0 - smooth_step(0.58, 0.84, radius)\n        weight = 0.96 * boundary_weight",
        "boundary_weight = 1.0 - smooth_step(0.55, 0.86, radius)\n        weight = boundary_weight",
    ),
    (
        "weight = max(weight, 0.985 * boundary_weight * mouth_focus)",
        "weight = max(weight, boundary_weight * mouth_focus)",
    ),
)

for old, new in replacements:
    if old not in code:
        raise RuntimeError(f"Expected v1 source fragment was not found: {old!r}")
    code = code.replace(old, new, 1)

normal_hook = '''    mesh.update()\n    return {\n        "candidate_vertices": len(candidates),'''
normal_replacement = '''    mesh.update()\n\n    # The GLB carries custom split normals from the original sculpt.  Once the\n    # baked relief has been projected away, rebuild those normals from the\n    # cleaned geometry so old eyes/mouth/cheeks cannot survive as shading ghosts.\n    custom_normals_rebuilt = False\n    if getattr(mesh, "has_custom_normals", False):\n        generated_normals = [vertex.normal.copy() for vertex in mesh.vertices]\n        mesh.normals_split_custom_set_from_vertices(generated_normals)\n        custom_normals_rebuilt = True\n        mesh.update()\n\n    return {\n        "candidate_vertices": len(candidates),'''
if normal_hook not in code:
    raise RuntimeError("Could not find the v1 smoothing return hook")
code = code.replace(normal_hook, normal_replacement, 1)

nose_report = '''        "nose_centre": tuple(float(value) for value in nose_centre) if nose_centre else None,\n    }'''
nose_report_replacement = '''        "nose_centre": tuple(float(value) for value in nose_centre) if nose_centre else None,\n        "custom_normals_rebuilt": custom_normals_rebuilt,\n    }'''
if nose_report not in code:
    raise RuntimeError("Could not find the v1 nose-report hook")
code = code.replace(nose_report, nose_report_replacement, 1)

code = code.replace(
    '"Original facial vertices moved only in depth toward a robust fitted "\n        "surface; wide outer face band fixed; probable physical nose preserved "',
    '"Original facial vertices fully projected in the central region toward a robust fitted "\n        "surface with a feathered wide outer face band; imported sculpt normals rebuilt; probable physical nose preserved "',
    1,
)

namespace = {
    "__name__": "__main__",
    "__file__": str(SOURCE),
    "__package__": None,
}
exec(compile(code, str(SOURCE), "exec"), namespace, namespace)
