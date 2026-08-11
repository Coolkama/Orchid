import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output'/'prototype-tail'; OUTPUT.mkdir(parents=True,exist_ok=True)
arg=next((a for a in sys.argv if a.startswith('--model=')),None)
model=Path(arg.split('=',1)[1]) if arg else ROOT/'assets/models/glimmerkin.glb'
if not model.is_absolute(): model=ROOT/model
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=str(model))
scene=bpy.context.scene; arm=next(o for o in scene.objects if o.type=='ARMATURE'); meshes=[o for o in scene.objects if o.type=='MESH']
roots=[b for b in arm.data.bones if b.parent is None]; pelvis_name=roots[0].children[0].name

# Bounds and rear-tail region. Glimmerkin faces -Y in the imported asset; the real tail occupies +Y,
# low on the torso. We bind only vertices already belonging to that region: no replacement geometry.
pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
mins=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))); maxs=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
centre=(mins+maxs)*.5; size=maxs-mins; extent=max(size)

# Locate candidate tail vertices geometrically, then derive a chain from their distribution.
candidates=[]
for obj in meshes:
    for v in obj.data.vertices:
        w=obj.matrix_world@v.co
        # rear half, below mid-height, excluding the broad central torso near x=0/y=centre
        if w.y > centre.y + size.y*.12 and w.z < mins.z + size.z*.58:
            candidates.append((obj,v,w))
if len(candidates)<20: raise RuntimeError(f'Could not isolate existing tail; only {len(candidates)} candidate vertices')
ys=[w.y for _,_,w in candidates]; y0=min(ys); y1=max(ys)
# centres at quartiles along the real appendage
chain=[]
for t in (0.02,.34,.67,1.0):
    target=y0+(y1-y0)*t; near=sorted(candidates,key=lambda q:abs(q[2].y-target))[:max(12,len(candidates)//30)]
    chain.append(sum((q[2] for q in near),Vector())/len(near))
# ensure chain originates close to body centreline at tail root
chain[0]=Vector((chain[0].x,y0,chain[0].z))

bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
prev=arm.data.edit_bones[pelvis_name]; inv=arm.matrix_world.inverted(); names=[]
for i in range(3):
    b=arm.data.edit_bones.new(f'Orchid_Tail_{i+1:02d}'); b.head=inv@chain[i]; b.tail=inv@chain[i+1]; b.parent=prev; b.use_connect=False; names.append(b.name); prev=b
bpy.ops.object.mode_set(mode='OBJECT')

# Add the new bones to each skinned mesh's Armature modifier and blend weights by distance along Y.
# Existing weights are preserved; only isolated rear-tail vertices receive Orchid tail groups.
weighted=0
for obj in meshes:
    relevant=[(v,w) for oo,v,w in candidates if oo==obj]
    if not relevant: continue
    groups=[obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n) for n in names]
    for v,w in relevant:
        u=max(0,min(.999,(w.y-y0)/max(1e-6,y1-y0))); pos=u*3; idx=min(2,int(pos)); frac=pos-idx
        # remove influence from our new groups before assigning deterministic weights
        for g in groups:
            try:g.remove([v.index])
            except:pass
        groups[idx].add([v.index],1-frac,'REPLACE')
        if idx<2: groups[idx+1].add([v.index],frac,'REPLACE')
        weighted+=1

bpy.context.view_layer.objects.active=arm; bpy.ops.object.mode_set(mode='POSE')
for n in names: arm.pose.bones[n].rotation_mode='XYZ'
for frame,angles in [(1,(0,0,0)),(12,(5,9,13)),(24,(0,0,0)),(36,(-5,-9,-13)),(48,(0,0,0))]:
    for n,d in zip(names,angles):
        p=arm.pose.bones[n]; p.rotation_euler.z=math.radians(d); p.keyframe_insert(data_path='rotation_euler',frame=frame)
bpy.ops.object.mode_set(mode='OBJECT')
if arm.animation_data and arm.animation_data.action:
    arm.animation_data.action.name='Orchid_Real_Tail_Swish'
    for fc in arm.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation='BEZIER'

eng={x.identifier for x in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}; scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in eng else ('BLENDER_EEVEE' if 'BLENDER_EEVEE' in eng else 'BLENDER_WORKBENCH')
scene.render.resolution_x=scene.render.resolution_y=512; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.render.fps=24; scene.frame_start=1; scene.frame_end=48
if scene.world is None: scene.world=bpy.data.worlds.new('TailWorld')
scene.world.color=(.035,.035,.045)
camloc=centre+Vector((extent*2.4,extent*3.5,size.z*.12)); bpy.ops.object.camera_add(location=camloc); cam=bpy.context.object; cam.data.type='ORTHO'; cam.data.ortho_scale=extent*1.55; cam.rotation_euler=(centre-cam.location).to_track_quat('-Z','Y').to_euler(); scene.camera=cam
for loc,en,rad in [(centre+Vector((extent*2,-extent*2,extent*2)),950,extent*2),(centre+Vector((-extent*2,extent,extent)),650,extent*2.5)]:
    bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=en; l.data.size=rad; l.rotation_euler=(centre-l.location).to_track_quat('-Z','Y').to_euler()
for f in (1,12,24,36,48): scene.frame_set(f); scene.render.filepath=str(OUTPUT/f'tail_{f:02d}.png'); bpy.ops.render.render(write_still=True)
scene.frame_set(1); bpy.ops.export_scene.gltf(filepath=str(OUTPUT/'glimmerkin-tail-proof.glb'),export_format='GLB',export_animations=True,export_skins=True,export_materials='EXPORT')
report={'source':str(model.relative_to(ROOT)),'pelvis':pelvis_name,'added_bones':names,'candidate_tail_vertices':len(candidates),'weighted_vertices':weighted,'animation':'Orchid_Real_Tail_Swish','preview_frames':[1,12,24,36,48],'principle':'Orchid identified existing unrigged tail geometry, extended the Meshy Smart Rig, bound that existing geometry to the new bones, and animated it without creating replacement tail geometry.'}
(OUTPUT/'report.json').write_text(json.dumps(report,indent=2)); bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'prototype-tail.blend')); print(json.dumps(report,indent=2))
