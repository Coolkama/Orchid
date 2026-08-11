import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "prototype-tail"
OUTPUT.mkdir(parents=True, exist_ok=True)

model_arg = next((a for a in sys.argv if a.startswith("--model=")), None)
model_path = Path(model_arg.split("=", 1)[1]) if model_arg else ROOT / "assets" / "models" / "glimmerkin.glb"
if not model_path.is_absolute(): model_path = ROOT / model_path
if not model_path.exists(): raise FileNotFoundError(model_path)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model_path))
scene = bpy.context.scene
arms = [o for o in scene.objects if o.type == "ARMATURE"]
meshes = [o for o in scene.objects if o.type == "MESH"]
if len(arms) != 1 or not meshes: raise RuntimeError("Expected one armature and mesh")
arm = arms[0]

# Find pelvis structurally, as in the motion proof.
roots = [b for b in arm.data.bones if b.parent is None]
if len(roots) != 1 or len(roots[0].children) != 1: raise RuntimeError("Unexpected Smart Rig root")
pelvis_name = roots[0].children[0].name

# Character bounds establish scale and the rear direction. The existing preview camera looks along +Y,
# so the tail extends from the body's +Y/rear side. This proof adds a visible appendage rather than
# attempting production skin surgery on the source mesh.
points = [obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]
mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
centre = (mins + maxs) * .5
size = maxs - mins
extent = max(size)
base = Vector((centre.x, maxs.y - size.y * .08, mins.z + size.z * .34))

# Extend the imported armature with a three-bone tail chain parented to the discovered pelvis.
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
pelvis = arm.data.edit_bones[pelvis_name]
segments = []
prev = pelvis
world_to_arm = arm.matrix_world.inverted()
world_pts = [
    base,
    base + Vector((0, size.y * .20, size.z * .03)),
    base + Vector((0, size.y * .38, size.z * .09)),
    base + Vector((0, size.y * .54, size.z * .17)),
]
arm_pts = [world_to_arm @ p for p in world_pts]
for i in range(3):
    b = arm.data.edit_bones.new(f"Orchid_Tail_{i+1:02d}")
    b.head, b.tail, b.parent = arm_pts[i], arm_pts[i+1], prev
    b.use_connect = False
    segments.append(b.name)
    prev = b
bpy.ops.object.mode_set(mode="OBJECT")

# Make a lightweight visible tail around the bones. Each tapered segment is rigidly parented to its
# corresponding bone, which is sufficient to prove custom rig extension and animation without
# altering Glimmerkin's original weights.
def add_segment(name, a, b, radius):
    mid = (a + b) * .5
    vec = b - a
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (radius, radius, vec.length * .56)
    obj.rotation_euler = vec.to_track_quat("Z", "Y").to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = name.replace("TailMesh", "Orchid_Tail")
    # compensate bone-parent transform while preserving the intended world placement
    obj.matrix_parent_inverse = (arm.matrix_world @ arm.pose.bones[obj.parent_bone].matrix).inverted()
    return obj

tail_mat = bpy.data.materials.new("OrchidTailMaterial")
tail_mat.diffuse_color = (0.16, 0.48, 0.62, 1)
for i in range(3):
    o = add_segment(f"TailMesh_{i+1:02d}", world_pts[i], world_pts[i+1], extent * (.075 - i*.014))
    o.data.materials.append(tail_mat)

# Animate only the new bones: a gentle side-to-side swish, deliberately restrained.
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="POSE")
for n in segments: arm.pose.bones[n].rotation_mode = "XYZ"
for frame, angles in [(1,(0,0,0)), (12,(8,12,16)), (24,(0,0,0)), (36,(-8,-12,-16)), (48,(0,0,0))]:
    for n, deg in zip(segments, angles):
        pb = arm.pose.bones[n]
        pb.rotation_euler.z = math.radians(deg)
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)
bpy.ops.object.mode_set(mode="OBJECT")
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action.name = "Orchid_Tail_Swish"
    for fc in arm.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation = "BEZIER"

# Studio setup: render a rear three-quarter view so the added appendage is unmistakable.
engine_ids = {x.identifier for x in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engine_ids else ("BLENDER_EEVEE" if "BLENDER_EEVEE" in engine_ids else "BLENDER_WORKBENCH")
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = 24; scene.frame_start = 1; scene.frame_end = 48
world = bpy.data.worlds.new("TailWorld") if scene.world is None else scene.world
scene.world = world; world.color = (.035,.035,.045)
cam_loc = centre + Vector((extent*2.5, extent*3.4, size.z*.15))
bpy.ops.object.camera_add(location=cam_loc)
cam=bpy.context.object; cam.data.type="ORTHO"; cam.data.ortho_scale=extent*1.55
cam.rotation_euler=(centre-cam.location).to_track_quat("-Z","Y").to_euler(); scene.camera=cam
for loc, energy, radius in [(centre+Vector((extent*2,-extent*2,extent*2)),950,extent*2),(centre+Vector((-extent*2,extent,extent)),650,extent*2.5)]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    l=bpy.context.object; l.data.energy=energy; l.data.size=radius; l.rotation_euler=(centre-l.location).to_track_quat("-Z","Y").to_euler()

for frame in [1,12,24,36,48]:
    scene.frame_set(frame); scene.render.filepath=str(OUTPUT/f"tail_{frame:02d}.png"); bpy.ops.render.render(write_still=True)

scene.frame_set(1)
export_path=OUTPUT/"glimmerkin-tail-proof.glb"
bpy.ops.export_scene.gltf(filepath=str(export_path), export_format="GLB", export_animations=True, export_skins=True, export_materials="EXPORT")
report={"source":str(model_path.relative_to(ROOT)),"pelvis":pelvis_name,"added_bones":segments,"animation":"Orchid_Tail_Swish","frames":[1,48],"preview_frames":[1,12,24,36,48],"principle":"Orchid extended an imported Meshy Smart Rig with a custom animated three-bone appendage without modifying the source asset."}
(OUTPUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/"prototype-tail.blend"))
print(json.dumps(report,indent=2))
