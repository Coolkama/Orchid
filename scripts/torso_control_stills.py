import bpy, math, sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'torso-control-stills'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None)
model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))
s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE')
meshes=[o for o in s.objects if o.type=='MESH']

# Likely Limijoy upper-body chain from the rig inspection.
# Bone_034 sits immediately above the torso branch and is the best neck candidate.
# Bone_015 and Bone_014 are the first two central torso/spine controls beneath it.
candidates=['Bone_034','Bone_015','Bone_014']
for n in candidates:
    arm.pose.bones[n].rotation_mode='XYZ'

pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
mn=Vector((min(q.x for q in pts),min(q.y for q in pts),min(q.z for q in pts)))
mx=Vector((max(q.x for q in pts),max(q.y for q in pts),max(q.z for q in pts)))
cen=(mn+mx)*.5; size=mx-mn; ext=max(size)

eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
s.render.resolution_x=384; s.render.resolution_y=384; s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'
if s.world is None: s.world=bpy.data.worlds.new('TorsoDiagWorld')
s.world.color=(.035,.035,.045)
cl=cen+Vector((0,-ext*3.8,size.z*.08)); bpy.ops.object.camera_add(location=cl)
cam=bpy.context.object; cam.data.type='ORTHO'; cam.data.ortho_scale=ext*1.35; cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler(); s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),850,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.4)]:
    bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=en; l.data.size=rad; l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z)); g=bpy.context.object
mat=bpy.data.materials.new('TorsoDiagGround'); mat.diffuse_color=(.06,.06,.075,1); g.data.materials.append(mat)

def reset():
    for n in candidates: arm.pose.bones[n].rotation_euler=(0,0,0)
    bpy.context.view_layer.update()

def render(name):
    s.render.filepath=str(OUT/name); bpy.ops.render.render(write_still=True)

reset(); render('00_neutral.png')
for n in candidates:
    for axis,idx in [('x',0),('y',1),('z',2)]:
        reset(); r=[0,0,0]; r[idx]=math.radians(16); arm.pose.bones[n].rotation_euler=r; bpy.context.view_layer.update(); render(f'{n}_{axis}_plus16.png')

print('Rendered neutral plus X/Y/Z +16 degree tests for: '+', '.join(candidates))