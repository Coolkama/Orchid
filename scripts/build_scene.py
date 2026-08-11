from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)

print("Blender version:", bpy.app.version_string)

# Start from a completely empty scene.
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene

# Ubuntu runners may provide different Blender generations. Prefer modern Eevee
# when available, but fall back to the older engine identifier used by Blender 3.x/4.0.
engine_items = {
    item.identifier
    for item in scene.bl_rna.properties["render"].fixed_type.properties["engine"].enum_items
}
if "BLENDER_EEVEE_NEXT" in engine_items:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
elif "BLENDER_EEVEE" in engine_items:
    scene.render.engine = "BLENDER_EEVEE"
else:
    scene.render.engine = "BLENDER_WORKBENCH"

print("Render engine:", scene.render.engine)
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUTPUT / "preview.png")

# Factory settings with use_empty=True may leave the scene without a World.
world = bpy.data.worlds.new("OrchidWorld") if scene.world is None else scene.world
scene.world = world
world.color = (0.035, 0.035, 0.045)

# Ground.
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
plane = bpy.context.object
mat_ground = bpy.data.materials.new("Ground")
mat_ground.diffuse_color = (0.09, 0.11, 0.13, 1.0)
plane.data.materials.append(mat_ground)

# A simple rounded subject so the first test exercises geometry, material,
# lighting, rendering and GLB export rather than merely opening Blender.
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=(0, 0, 1.15))
subject = bpy.context.object
subject.name = "OrchidTestSubject"
subject.scale = (1.05, 0.85, 1.15)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

mat_subject = bpy.data.materials.new("Subject")
mat_subject.diffuse_color = (0.42, 0.68, 0.46, 1.0)
mat_subject.roughness = 0.72
subject.data.materials.append(mat_subject)

# Small top element to make orientation obvious in later renders.
bpy.ops.mesh.primitive_cone_add(
    vertices=32,
    radius1=0.22,
    radius2=0.04,
    depth=0.75,
    location=(0, 0, 2.35),
)
top = bpy.context.object
top.name = "TopMarker"
top.rotation_euler[1] = 0.18
mat_top = bpy.data.materials.new("Top")
mat_top.diffuse_color = (0.22, 0.48, 0.24, 1.0)
top.data.materials.append(mat_top)

# Camera.
bpy.ops.object.camera_add(location=(4.8, -6.8, 4.0))
camera = bpy.context.object
scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = 5.0


def look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


look_at(camera, Vector((0, 0, 1.2)))

# Soft key and fill lights.
bpy.ops.object.light_add(type="AREA", location=(3.5, -3.0, 6.0))
key = bpy.context.object
key.data.energy = 850
key.data.shape = "DISK"
key.data.size = 4.0
look_at(key, Vector((0, 0, 1.0)))

bpy.ops.object.light_add(type="AREA", location=(-3.0, 1.5, 3.5))
fill = bpy.context.object
fill.data.energy = 400
fill.data.size = 3.0
look_at(fill, Vector((0, 0, 1.0)))

# Save a blend file too; useful if a future desktop inspection is ever wanted.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "scene.blend"))

# Render the proof image.
bpy.ops.render.render(write_still=True)

# Export a portable runtime asset. glTF ships with standard Blender builds, but
# report the available operators first so CI failures are immediately diagnosable.
if not hasattr(bpy.ops.export_scene, "gltf"):
    raise RuntimeError("This Blender package does not provide the glTF exporter")

bpy.ops.export_scene.gltf(
    filepath=str(OUTPUT / "scene.glb"),
    export_format="GLB",
    use_selection=False,
)

print(f"Generated artifacts in {OUTPUT}")
