import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output'/'prototype-walk'; OUTPUT.mkdir(parents=True,exist_ok=True)
arg=next((a for a in sys.argv if a.startswith('--model=')),None)
model=Path(arg.split('=',1)[1]) if arg else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
if not model.exists(): raise FileNotFoundError(model)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model))
scene=bpy.context.scene; arm=next(o for o in scene.objects if o.type=='ARMATURE'); meshes=[o for o in scene.objects if o.type=='MESH']
roots=[b for b in arm.data.bones if b.parent is None]
if len(roots)!=1 or len(roots[0].children)!=1: raise RuntimeError('Unexpected Smart Rig root')
root=roots[0]; pelvis=root.children[0]; pchildren=list(pelvis.children); spine_root=min(pchildren,key=lambda b:abs(b.head_local.x)); legs=sorted([b for b in pchildren if b!=spine_root],key=lambda b:b.head_local.x)
if len(legs)!=2: raise RuntimeError('Expected two leg roots')
left_leg,right_leg=legs; spine=[spine_root]
while len(spine[-1].children)==1: spine.append(spine[-1].children[0])
chest=spine[-1]; jc=list(chest.children); head=min(jc,key=lambda b:abs(b.head_local.x)); arms=sorted([b for b in jc if b!=head],key=lambda b:b.head_local.x)
left_arm,right_arm=arms[0],arms[-1]
scene.frame_start=1; scene.frame_end=24; scene.render.fps=24
bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode='POSE')
pp=arm.pose.bones[pelvis.name]; pl=arm.pose.bones[left_leg.name]; pr=arm.pose.bones[right_leg.name]; pal=arm.pose.bones[left_arm.name]; par=arm.pose.bones[right_arm.name]; ps=arm.pose.bones[spine_root.name]
for pb in (pp,pl,pr,pal,par,ps): pb.rotation_mode='XYZ'
base=pp.location.copy(); poses=[(1,-7,7,4,-4,0,.7),(7,0,0,0,0,.018,-.3),(13,7,-7,-4,4,0,-.7),(19,0,0,0,0,.018,.3),(24,-7,7,4,-4,0,.7)]
for f,ll,rr,la,ra,bob,sway in poses:
    pl.rotation_euler.x=math.radians(ll); pr.rotation_euler.x=math.radians(rr); pal.rotation_euler.x=math.radians(la); par.rotation_euler.x=math.radians(ra); pp.location=base+Vector((0,0,bob)); ps.rotation_euler.z=math.radians(sway)
    for pb,path in ((pl,'rotation_euler'),(pr,'rotation_euler'),(pal,'rotation_euler'),(par,'rotation_euler'),(pp,'location'),(ps,'rotation_euler')): pb.keyframe_insert(data_path=path,frame=f)
bpy.ops.object.mode_set(mode='OBJECT')
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action.name='Orchid_Prototype_Walk'
    for fc in arm.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation='BEZIER'
pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]; mins=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); maxs=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts))); centre=(mins+maxs)*.5; size=maxs-mins; extent=max(size)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH'); scene.render.resolution_x=scene.render.resolution_y=512; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'
if scene.world is None: scene.world=bpy.data.worlds.new('WalkWorld')
scene.world.color=(.035,.035,.045); camloc=centre+Vector((extent*1.5,-extent*3.6,size.z*.10)); bpy.ops.object.camera_add(location=camloc); cam=bpy.context.object; cam.data.type='ORTHO'; cam.data.ortho_scale=extent*1.45; cam.rotation_euler=(centre-cam.location).to_track_quat('-Z','Y').to_euler(); scene.camera=cam
for loc,en,rad in [(centre+Vector((extent*2,-extent*2,extent*2)),950,extent*2),(centre+Vector((-extent*2,-extent,extent)),550,extent*2.4),(centre+Vector((0,extent*2,extent*1.5)),600,extent*2)]:
    bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=en; l.data.size=rad; l.rotation_euler=(centre-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=extent*6,location=(centre.x,centre.y,mins.z)); ground=bpy.context.object; gm=bpy.data.materials.new('WalkGround'); gm.diffuse_color=(.06,.06,.075,1); ground.data.materials.append(gm)
# Render every animation frame so the artifact can be reviewed as a true 24 fps cycle.
for f in range(scene.frame_start,scene.frame_end+1):
    scene.frame_set(f); scene.render.filepath=str(OUTPUT/f'walk_{f:02d}.png'); bpy.ops.render.render(write_still=True)
scene.frame_set(1); bpy.ops.export_scene.gltf(filepath=str(OUTPUT/'glimmerkin-walk-proof.glb'),export_format='GLB',export_animations=True,export_skins=True,export_materials='EXPORT')
report={'source':str(model.relative_to(ROOT)),'animation':'Orchid_Prototype_Walk','frames':[1,24],'rendered_frames':24,'fps':24,'max_stride_degrees':7,'max_arm_swing_degrees':4,'pelvis_bob':.018,'principle':'Full-frame restrained walk-cycle proof authored directly on the Meshy Smart Rig.'}; (OUTPUT/'report.json').write_text(json.dumps(report,indent=2)); bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'prototype-walk.blend')); print(json.dumps(report,indent=2))
