import bpy, json, sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'rig-inspection'
OUT.mkdir(parents=True, exist_ok=True)
arg = next((x for x in sys.argv if x.startswith('--model=')), None)
model = Path(arg.split('=',1)[1]) if arg else ROOT / 'assets/models/glimmerkin.glb'
if not model.is_absolute(): model = ROOT / model

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(model))

armatures = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']

def v3(v): return [round(float(v.x),6), round(float(v.y),6), round(float(v.z),6)]

def bone_record(b):
    m = b.matrix_local.to_3x3()
    return {
        'name': b.name,
        'parent': b.parent.name if b.parent else None,
        'children': [c.name for c in b.children],
        'head_local': v3(b.head_local),
        'tail_local': v3(b.tail_local),
        'length': round(float(b.length),6),
        'local_axis_x_world_basis': v3(m @ Vector((1,0,0))),
        'local_axis_y_world_basis': v3(m @ Vector((0,1,0))),
        'local_axis_z_world_basis': v3(m @ Vector((0,0,1))),
        'use_deform': bool(b.use_deform),
    }

report = {
    'source': str(model.relative_to(ROOT)),
    'object_count': len(bpy.context.scene.objects),
    'armature_count': len(armatures),
    'mesh_count': len(meshes),
    'meshes': [],
    'armatures': [],
    'actions': [],
}

for m in meshes:
    mods = [mod.object.name for mod in m.modifiers if mod.type == 'ARMATURE' and mod.object]
    report['meshes'].append({
        'name': m.name,
        'vertex_count': len(m.data.vertices),
        'polygon_count': len(m.data.polygons),
        'armature_modifiers': mods,
        'vertex_group_count': len(m.vertex_groups),
        'vertex_groups': [g.name for g in m.vertex_groups],
        'material_count': len(m.data.materials),
    })

for a in armatures:
    roots = [b.name for b in a.data.bones if b.parent is None]
    report['armatures'].append({
        'name': a.name,
        'bone_count': len(a.data.bones),
        'root_bones': roots,
        'bones': [bone_record(b) for b in a.data.bones],
    })

for act in bpy.data.actions:
    report['actions'].append({
        'name': act.name,
        'frame_range': [round(float(act.frame_range[0]),3), round(float(act.frame_range[1]),3)],
        'fcurve_count': len(act.fcurves),
    })

(OUT/'rig-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

lines=[]
lines.append(f"Source: {report['source']}")
lines.append(f"Armatures: {len(armatures)} | Meshes: {len(meshes)} | Actions: {len(report['actions'])}")
for a in report['armatures']:
    lines.append(f"\nARMATURE {a['name']} ({a['bone_count']} bones), roots={a['root_bones']}")
    byname={b['name']:b for b in a['bones']}
    def walk(name, depth=0):
        b=byname[name]
        lines.append('  '*depth + f"- {name} len={b['length']} head={b['head_local']} tail={b['tail_local']} deform={b['use_deform']}")
        lines.append('  '*(depth+1) + f"axes X={b['local_axis_x_world_basis']} Y={b['local_axis_y_world_basis']} Z={b['local_axis_z_world_basis']}")
        for c in b['children']: walk(c, depth+1)
    for r in a['root_bones']: walk(r)
for m in report['meshes']:
    lines.append(f"\nMESH {m['name']}: verts={m['vertex_count']} polys={m['polygon_count']} groups={m['vertex_group_count']} armature={m['armature_modifiers']}")
if report['actions']:
    lines.append('\nACTIONS')
    for a in report['actions']: lines.append(f"- {a['name']} frames={a['frame_range']} fcurves={a['fcurve_count']}")
else:
    lines.append('\nACTIONS: none')
(OUT/'rig-report.txt').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(lines))