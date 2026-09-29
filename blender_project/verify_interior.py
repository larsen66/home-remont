"""Reopen the saved concept, verify bounds and the one-click collection isolation, then exit."""
import json
from pathlib import Path

import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent


def bounds(objects):
    coords=[o.matrix_world @ Vector(p) for o in objects if o.type=="MESH" for p in o.bound_box]
    return [[min(p[i] for p in coords) for i in range(3)], [max(p[i] for p in coords) for i in range(3)]]


def layer_for(col,node):
    if node.collection==col:return node
    for child in node.children:
        match=layer_for(col,child)
        if match:return match


def main():
    bpy.ops.wm.open_mainfile(filepath=str(HERE/"apartment_interior.blend"))
    bpy.context.view_layer.update()
    root=bpy.data.collections["ИНТЕРЬЕР - скрыть всё"]
    members=set(root.all_objects)
    meshes=[o for o in members if o.type=="MESH"]
    layer=layer_for(root,bpy.context.view_layer.layer_collection)
    original=[o for o in bpy.context.scene.objects if o not in members]
    original_visibility={o.name:o.visible_get() for o in original}
    visible_before={o.name:o.visible_get() for o in meshes}
    layer.hide_viewport=True
    bpy.context.view_layer.update()
    assert not any(o.visible_get() for o in meshes),"Interior object leaked outside the hidden parent"
    assert original_visibility=={o.name:o.visible_get() for o in original},"Architecture visibility was affected"
    layer.hide_viewport=False
    bpy.context.view_layer.update()
    assert visible_before=={o.name:o.visible_get() for o in meshes},"Interior visibility did not restore"
    asset_bounds={}
    for obj in members:
        if not obj.get("source_asset"):continue
        low,high=bounds(obj.children)
        actual=[high[i]-low[i] for i in range(3)]
        expected=list(obj["concept_dimensions_m"])
        assert all(abs(a-e)<.0001 for a,e in zip(actual,expected)),(obj.name,actual,expected)
        center=[(low[0]+high[0])/2,(low[1]+high[1])/2,low[2]]
        assert all(abs(a-e)<.0001 for a,e in zip(center,obj.location)),(obj.name,center,list(obj.location))
        asset_bounds[obj.name]={"min":low,"max":high,"dimensions_m":actual}
    walls=[o for o in original if o.type=="MESH" and any(c.name.startswith(("02 Walls","03 Walls","НИШИ","БАЛКИ")) for c in o.users_collection)]
    # Test imported furniture and the solid cabinet volumes against the original walls.
    solids=[]
    for name,data in asset_bounds.items():solids.append((name,[data["min"],data["max"]]))
    for obj in meshes:
        if any(word in obj.name for word in ["carcass","corner base","South kitchen base","Fridge tall housing","Entry bench base","Display cabinet side"]):
            solids.append((obj.name,bounds([obj])))
    collisions=[]
    for name,(a,b) in solids:
        for wall in walls:
            c,d=bounds([wall])
            overlap=[min(b[i],d[i])-max(a[i],c[i]) for i in range(3)]
            if min(overlap)>.003:collisions.append({"furniture":name,"wall":wall.name,"overlap_m":overlap})
    assert not collisions,collisions
    missing=[im.filepath for im in bpy.data.images if im.source=="FILE" and im.filepath and not im.packed_file and not Path(bpy.path.abspath(im.filepath)).exists()]
    assert not missing,missing
    report=json.loads((HERE/"interior_verification.json").read_text())
    report.update({"reopened_successfully":True,"one_click_viewport_hide_restores":True,"architecture_visibility_unchanged_on_toggle":True,"asset_bounds_m":asset_bounds,"wall_collision_candidates_checked":len(solids),"wall_aabb_collisions":collisions,"missing_external_images":missing,"collision_scope":"Imported furniture and main cabinet volumes vs original walls/niches/beams; excludes dynamic door/chair motion and small decorative parts"})
    (HERE/"interior_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":main()
