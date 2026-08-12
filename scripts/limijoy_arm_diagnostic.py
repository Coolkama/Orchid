import bpy, math, sys, json
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'limijoy-arm-diagnostic'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); main=max([o for o in s.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)],key=lambda o:len(o.data.vertices))
chains={
 'right':['Bone_023','Bone_022','Bone_021','Bone_020','Bone_019','Bone_018','Bone_017','Bone_016'],
 'left':['Bone_031','Bone_030','Bone_029','Bone_028','Bone_027','Bone_026','Bone_025','Bone_024']
}
for ch in chains.values():
 for n in ch: arm.pose.bones[n].rotation_mode='XYZ'
pts=[main.matrix_world@Vector(c) for c in main.bound_box];mn=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));mx=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));cen=(mn+mx)*.5;ext=max(mx-mn)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items};s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH');s.render.resolution_x=s.render.resolution_y=384;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('World');s.world.color=(.035,.035,.045)
cl=cen+Vector((ext*2.15,-ext*3.2,ext*.35));bpy.ops.object.camera_add(location=cl);cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=ext*1.42;cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
for loc,en,sz in [(cen+Vector((ext*2,-ext*2,ext*2)),900,ext*2),(cen+Vector((-ext*2,-ext,ext)),450,ext*2.5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=en;l.data.size=sz;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
def reset():
 for ch in chains.values():
  for n in ch: arm.pose.bones[n].rotation_euler=(0,0,0)
def render(name):
 s.render.filepath=str(OUT/f'{name}.png');bpy.ops.render.render(write_still=True)
axis_index={'X':0,'Y':1,'Z':2}; reports={}
# Finish the untested distal right-side chain, then validate the mirrored left-side chain bone-for-bone.
tests={
 'right':['Bone_018','Bone_017','Bone_016'],
 'left':['Bone_031','Bone_030','Bone_029','Bone_028','Bone_027','Bone_026','Bone_025','Bone_024']
}
for side,bones in tests.items():
 for bone in bones:
  p=arm.pose.bones[bone]; b=p.bone
  reports[bone]={
   'side':side,
   'parent':b.parent.name if b.parent else None,
   'head_local':list(b.head_local),'tail_local':list(b.tail_local),
   'rest_direction':list((b.tail_local-b.head_local).normalized()),
   'matrix_local':[list(r) for r in b.matrix_local],
   'parent_matrix_local':[list(r) for r in b.parent.matrix_local] if b.parent else None,
   'tests':{'X':[0,20,40],'Y':[0,20,40],'Z':[0,20,40]}
  }
  for axis,idx in axis_index.items():
   for label,deg in [('start',0),('mid',20),('end',40)]:
    reset();arm.pose.bones[bone].rotation_euler[idx]=math.radians(deg);render(f'{side}_{bone}_{axis}_{label}_{deg:02d}')
report={
 'known_right_reference':{
  'Bone_023':'shoulder-girdle/root candidate; heavy rotation visibly drops shoulder',
  'Bone_022':{'X':'raises arm outward/upward','Y':'long-axis roll','Z':'fore-aft depth swing; negative is forward candidate'},
  'Bone_021':'visible distal-arm articulation; X strongest elbow/bend candidate',
  'Bone_020':'little/no visible deformation at +40 in prior diagnostic',
  'Bone_019':'little/no visible deformation at +40 in prior diagnostic'
 },
 'new_tests':reports,
 'purpose':'complete empirical arm-chain mapping on right side and verify mirrored left-side behaviour using isolated X/Y/Z start-mid-end stills'
}
(OUT/'axis_report.json').write_text(json.dumps(report,indent=2))
