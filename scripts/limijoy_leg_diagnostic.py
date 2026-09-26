import bpy, math, sys, json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-leg-diagnostic'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); skinned=[o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)]; main=max(skinned,key=lambda o:len(o.data.vertices))
# Rig inspection established these two five-bone branches as Limijoy's legs.
chains=[['Bone_006','Bone_005','Bone_004','Bone_003','Bone_002'],['Bone_011','Bone_010','Bone_009','Bone_008','Bone_007']]
# Render neutral plus a modest local-X pose for every leg bone. This identifies hip/knee/ankle/foot influence cheaply.
pts=[main.matrix_world@Vector(c) for c in main.bound_box]; mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); cen=(mn+mx)*.5; size=mx-mn; ext=max(size)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH'); s.render.resolution_x=s.render.resolution_y=320;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('LegWorld')
s.world.color=(.035,.035,.045); cl=cen+Vector((ext*1.45,-ext*3.6,size.z*.08)); bpy.ops.object.camera_add(location=cl); cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.4;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),850,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=rad;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z));g=bpy.context.object;gm=bpy.data.materials.new('Ground');gm.diffuse_color=(.06,.06,.075,1);g.data.materials.append(gm)
def reset():
 for ch in chains:
  for n in ch:
   pb=arm.pose.bones[n];pb.rotation_mode='XYZ';pb.rotation_euler=(0,0,0)
def render(name):s.render.filepath=str(OUT/f'{name}.png');bpy.ops.render.render(write_still=True)
reset();render('00_neutral')
idx=1
for side,ch in enumerate(chains,1):
 for n in ch:
  reset();arm.pose.bones[n].rotation_euler.x=math.radians(18);render(f'{idx:02d}_leg{side}_{n}_X18');idx+=1
(OUT/'report.json').write_text(json.dumps({'chains':chains,'test':'neutral plus +18deg local X per bone','purpose':'identify hip/knee/ankle/foot controls before Limijoy walk'},indent=2))