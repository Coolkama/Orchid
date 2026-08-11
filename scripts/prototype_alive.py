import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'/'prototype-alive'; OUT.mkdir(parents=True,exist_ok=True)
a=next((x for x in sys.argv if x.startswith('--model=')),None); model=Path(a.split('=',1)[1]) if a else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model)); s=bpy.context.scene
arm=next(o for o in s.objects if o.type=='ARMATURE'); meshes=[o for o in s.objects if o.type=='MESH']; root=next(b for b in arm.data.bones if b.parent is None); pelvis=root.children[0]
pc=list(pelvis.children); spine=min(pc,key=lambda b:abs(b.head_local.x)); chain=[spine]
while len(chain[-1].children)==1: chain.append(chain[-1].children[0])
chest=chain[-1]; cc=list(chest.children); head=min(cc,key=lambda b:abs(b.head_local.x)); arms=sorted([b for b in cc if b!=head],key=lambda b:b.head_local.x)
tails=[b.name for b in arm.data.bones if b.name.startswith('Orchid_Tail_')]
bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode='POSE')
p={n:arm.pose.bones[n] for n in [pelvis.name,spine.name,head.name,arms[0].name,arms[-1].name]+tails}
for x in p.values(): x.rotation_mode='XYZ'
base=p[pelvis.name].location.copy()
# Five-second performance. Head yaw and roll are deliberately separated so the action reads as
# LOOK RIGHT first, then CURIOUS TILT, rather than one ambiguous diagonal lean.
# frame,bob,body_sway,head_yaw,head_tilt,left_arm,right_arm,tail
keys=[
(1,0,0,0,0,0,0,0),(24,0,0,0,0,0,0,0),
(38,0,1,18,0,0,0,2),(50,.006,2,24,0,1,-1,3),
(62,.010,3,24,10,3,-2,5),(74,.012,3,24,14,5,-3,6),
(84,.010,2,24,8,3,-2,4),(94,.006,1,14,0,1,-1,2),
(108,0,0,0,0,0,0,0),(120,0,0,0,0,0,0,0)]
for f,bob,sway,yaw,tilt,la,ra,tail in keys:
    p[pelvis.name].location=base+Vector((0,0,bob)); p[spine.name].rotation_euler.z=math.radians(sway)
    # For this imported Smart Rig, local X gives the visually readable left/right yaw while local Z is tilt.
    p[head.name].rotation_euler.x=math.radians(yaw); p[head.name].rotation_euler.z=math.radians(tilt)
    p[arms[0].name].rotation_euler.x=math.radians(la); p[arms[-1].name].rotation_euler.x=math.radians(ra)
    for i,n in enumerate(tails): p[n].rotation_euler.z=math.radians(tail*(i+1)/max(1,len(tails)))
    for n,x in p.items(): x.keyframe_insert(data_path='location' if n==pelvis.name else 'rotation_euler',frame=f)
bpy.ops.object.mode_set(mode='OBJECT'); s.frame_start=1; s.frame_end=120; s.render.fps=24
if arm.animation_data and arm.animation_data.action:
 arm.animation_data.action.name='Orchid_Alive_LookAndTilt'
 for fc in arm.animation_data.action.fcurves:
  for k in fc.keyframe_points:k.interpolation='BEZIER'
pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]; mn=Vector((min(q.x for q in pts),min(q.y for q in pts),min(q.z for q in pts))); mx=Vector((max(q.x for q in pts),max(q.y for q in pts),max(q.z for q in pts))); cen=(mn+mx)*.5; size=mx-mn; ext=max(size)
eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; s.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH'); s.render.resolution_x=s.render.resolution_y=512; s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'
if s.world is None:s.world=bpy.data.worlds.new('AliveWorld')
s.world.color=(.035,.035,.045); cl=cen+Vector((ext*1.5,-ext*3.6,size.z*.10)); bpy.ops.object.camera_add(location=cl); cam=bpy.context.object; cam.data.type='ORTHO'; cam.data.ortho_scale=ext*1.45; cam.rotation_euler=(cen-cam.location).to_track_quat('-Z','Y').to_euler(); s.camera=cam
for loc,en,rad in [(cen+Vector((ext*2,-ext*2,ext*2)),950,ext*2),(cen+Vector((-ext*2,-ext,ext)),550,ext*2.4),(cen+Vector((0,ext*2,ext*1.5)),600,ext*2)]:
 bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object;l.data.energy=en;l.data.size=rad;l.rotation_euler=(cen-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=ext*6,location=(cen.x,cen.y,mn.z)); g=bpy.context.object; gm=bpy.data.materials.new('AliveGround');gm.diffuse_color=(.06,.06,.075,1);g.data.materials.append(gm)
for f in range(1,121):s.frame_set(f);s.render.filepath=str(OUT/f'alive_{f:03d}.png');bpy.ops.render.render(write_still=True)
s.frame_set(1);bpy.ops.export_scene.gltf(filepath=str(OUT/'glimmerkin-alive-proof.glb'),export_format='GLB',export_animations=True,export_skins=True,export_materials='EXPORT')
r={'source':str(model.relative_to(ROOT)),'animation':'Orchid_Alive_LookAndTilt','duration_seconds':5,'fps':24,'rendered_frames':120,'head_yaw_max_degrees':24,'head_tilt_max_degrees':14,'tail_bones_used':tails,'story':['settled idle','clear look right','curious head tilt while looking','relax to neutral']};(OUT/'report.json').write_text(json.dumps(r,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'prototype-alive.blend'));print(json.dumps(r,indent=2))