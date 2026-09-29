"""Read apartment_photos.blend + local assets; save a separate interior concept and exit."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
PREVIEWS = HERE / "interior-previews"
LAYOUT = json.loads((HERE / "interior_layout.json").read_text())
ROOT_NAME = LAYOUT["collection"]
MATS = {}


def collection(name, parent):
    result = bpy.data.collections.new(name)
    parent.children.link(result)
    return result


def relink(obj, target):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    target.objects.link(obj)
    obj["interior_concept"] = True
    return obj


def material(name, color, roughness=0.55, metallic=0, noise=None):
    mat = bpy.data.materials.new("INT / " + name)
    mat.diffuse_color = (*color, 1)
    nodes = mat.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if noise:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise[0]
        tex.inputs["Detail"].default_value = 2
        coord = nodes.new("ShaderNodeTexCoord")
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = noise[1]
        mat.node_tree.links.new(coord.outputs["Generated"], scale.inputs[0])
        mat.node_tree.links.new(scale.outputs[0], tex.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[v * 0.78 for v in color], 1)
        ramp.color_ramp.elements[1].color = (*[min(v * 1.12, 1) for v in color], 1)
        mat.node_tree.links.new(tex.outputs["Fac"], ramp.inputs[0])
        mat.node_tree.links.new(ramp.outputs[0], shader.inputs["Base Color"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.13
        bump.inputs["Distance"].default_value = 0.001
        mat.node_tree.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        mat.node_tree.links.new(bump.outputs[0], shader.inputs["Normal"])
    return mat


def box(name, location, size, mat, target, bevel=0.004):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = relink(bpy.context.object, target)
    obj.name = "INT / " + name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Soft edges", "BEVEL")
        mod.width = min(bevel, min(size) * 0.42)
        mod.segments = 3
        normal = obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
    return obj


def cylinder(name, location, radius, depth, mat, target, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = relink(bpy.context.object, target)
    obj.name = "INT / " + name
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Soft edges", "BEVEL")
    bevel.width = min(0.004, depth / 4)
    bevel.segments = 3
    for p in obj.data.polygons:
        p.use_smooth = abs(p.normal.z) < 0.9
    return obj


def sphere(name, location, size, mat, target):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=location)
    obj = relink(bpy.context.object, target)
    obj.name = "INT / " + name
    obj.scale = size
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def line(name, points, radius, mat, target):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 3
    poly = data.splines.new("POLY")
    poly.points.add(len(points) - 1)
    for p, co in zip(poly.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new("INT / " + name, data)
    target.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def model(name, path, target, position, dimensions, angle=0, kind=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = set(bpy.data.objects) - before
    meshes = [o for o in imported if o.type == "MESH"]
    bpy.context.view_layer.update()
    rotation = Matrix.Rotation(math.radians(angle), 4, "Z")
    coordinates = [rotation @ o.matrix_world @ Vector(p) for o in meshes for p in o.bound_box]
    low = Vector([min(p[i] for p in coordinates) for i in range(3)])
    high = Vector([max(p[i] for p in coordinates) for i in range(3)])
    center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    scale = Matrix.Diagonal([dimensions[i] / (high[i] - low[i]) for i in range(3)] + [1])
    transform = Matrix.Translation(Vector(position)) @ scale @ Matrix.Translation(-center) @ rotation
    parent = bpy.data.objects.new("INT / " + name, None)
    target.objects.link(parent)
    parent.location = position
    parent.empty_display_size = 0.08
    parent["source_asset"] = str(path.relative_to(HERE))
    parent["concept_dimensions_m"] = dimensions
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        transformed = transform @ world
        relink(obj, target)
        obj.name = "INT / " + name + " / " + obj.name
        obj.parent = parent
        # Explicit inverse avoids using an unevaluated parent matrix in background Blender.
        obj.matrix_parent_inverse = Matrix.Translation(-Vector(position))
        obj.matrix_basis = transformed
        if kind in {"sofa", "chair"}:
            for slot in obj.material_slots:
                original = slot.material.name.lower() if slot.material else ""
                slot.material = MATS["dark"] if any(t in original for t in ["wood", "timber", "leg", "trim", "walnut", "surface"]) else MATS["fabric"]
            for poly in obj.data.polygons:
                poly.use_smooth = True
        if kind == "table":
            # The round steel table is an approximate silhouette match, recoloured charcoal.
            for slot in obj.material_slots:
                slot.material = MATS["dark"]
    for obj in imported - set(meshes):
        bpy.data.objects.remove(obj, do_unlink=True)
    return parent


def make_finishes(root):
    finishes = collection("04 ОТДЕЛКА - пол и стены", root)
    src = bpy.data.objects["Floor / living_kitchen"]
    floor = src.copy()
    floor.data = src.data.copy()
    finishes.objects.link(floor)
    floor.name = "INT / Floor finish - living kitchen"
    floor.location.z += 0.018
    floor.data.materials.clear()
    floor.data.materials.append(MATS["oak"])
    # Thin surface layers preserve every original architectural mesh and its material.
    for name,loc,size in [
        ("Left wall finish",(.066,-3.82,1.49),(.012,7.52,2.98)),
        ("TV wall finish",(2.984,-2.13,1.49),(.012,4.14,2.98)),
        ("Entrance wall finish",(1.69,-7.639,1.49),(3.24,.012,2.98)),
        ("Hall wall upper finish",(4.504,-5.10,1.32),(.012,1.34,2.64)),
        ("Hall wall lower finish",(4.504,-7.23,1.49),(.012,.69,2.98)),
    ]:
        box(name,loc,size,MATS["wall"],finishes,0)
    for x,cy,length in [(.084,-3.82,7.48),(2.969,-2.13,4.1),(4.49,-5.10,1.32),(4.49,-7.23,.66)]:
        box("Painted skirting",(x,cy,.065),(.018,length,.10),MATS["wall"],finishes)
    # Board seams run lengthwise; no image texture or external path is needed.
    for i in range(16):
        x=.08+i*.185
        box("Oak plank seam",(x,-3.82,.019),(.0018,7.48,.001),MATS["seam"],finishes,0)
    for i in range(8):
        x=3.07+i*.185
        box("Oak plank seam kitchen",(x,-6.05,.019),(.0018,3.15,.001),MATS["seam"],finishes,0)
    ceilings = collection("05 ПОТОЛКИ - скрыты в рабочем виде", root)
    src = bpy.data.objects["Ceiling / living_kitchen"]
    obj = src.copy(); obj.data = src.data.copy(); ceilings.objects.link(obj)
    obj.name = "INT / Finished ceiling"
    obj.location.z -= .015
    obj.hide_render = False
    obj.data.materials.clear();obj.data.materials.append(MATS["wall"])
    return finishes, ceilings


def make_living(root):
    zone = collection("01 ЗАЛ", root)
    seats = collection("Диван и столик", zone)
    d = LAYOUT["sofa"]
    model("Диван 230 x 86", ASSETS/"sofa_three_seat/model.glb",seats,d["position"],d["dimensions"],d["rotation_deg"],"sofa")
    d = LAYOUT["coffee_table"]
    model("Круглый столик 62",ASSETS/"coffee_table_round_01/coffee_table_round_01_1k.gltf",seats,d["position"],d["dimensions"],kind="table")
    box("Textured living rug",(1.52,-2.29,.031),(1.70,2.58,.018),MATS["rug"],seats,.025)
    tv = collection("ТВ - тумба, витрина и молдинги",zone)
    box("Floating walnut console",(2.84,-2.10,.46),(.28,2.20,.32),MATS["walnut"],tv,.012)
    for y in [-2.93,-2.38,-1.83,-1.28]:
        box("Console door",(2.688,y,.46),(.022,.535,.29),MATS["walnut"],tv)
    box("TV bezel",(2.936,-2.10,1.46),(.043,1.24,.715),MATS["dark"],tv,.013)
    box("TV screen",(2.91,-2.10,1.46),(.004,1.195,.67),MATS["screen"],tv,.001)
    for y in [-3.12,-1.08]:
        box("Wall moulding vertical",(2.968,y,1.55),(.022,.024,1.77),MATS["wall"],tv,.004)
    for z in [.665,2.435]:
        box("Wall moulding horizontal",(2.968,-2.10,z),(.022,2.06,.024),MATS["wall"],tv,.004)
    # Narrow display cabinet stands clear of the balcony door opening.
    box("Display cabinet back",(2.94,-.66,1.32),(.06,.49,2.57),MATS["walnut"],tv)
    for y in [-.91,-.41]:
        box("Display cabinet side",(2.795,y,1.32),(.35,.023,2.57),MATS["walnut"],tv)
    for z in [.035,.66,1.28,1.90,2.605]:
        box("Display shelf",(2.795,-.66,z),(.35,.50,.024),MATS["walnut"],tv)
    for y in [-.908,-.412]:
        box("Display black frame",(2.607,y,1.32),(.022,.018,2.57),MATS["dark"],tv)
    box("Tinted display glass",(2.606,-.66,1.32),(.008,.46,2.52),MATS["glass"],tv,0)
    cylinder("Console vase",(2.82,-1.30,.72),.07,.22,MATS["dark"],tv)
    sphere("Decor ceramic",(2.79,-2.90,.71),(.07,.075,.10),MATS["fabric"],tv)
    textile = collection("Шторы и текстиль",zone)
    for side,x0 in [("left",.15),("right",2.53)]:
        points=[];verts=[];faces=[]
        for i in range(49):
            x=x0+i*.37/48;y=-.33+.045*math.sin(i/48*math.pi*12)
            verts.extend([(x,y,.04),(x,y,2.61)])
            if i:faces.append((2*i-2,2*i,2*i+1,2*i-1))
        mesh=bpy.data.meshes.new("Curtain folds");mesh.from_pydata(verts,[],faces);mesh.update()
        obj=bpy.data.objects.new("INT / Curtain "+side,mesh);textile.objects.link(obj);mesh.materials.append(MATS["curtain"])
        solid=obj.modifiers.new("Cloth thickness","SOLIDIFY");solid.thickness=.002
        for p in mesh.polygons:p.use_smooth=True
    return zone


def make_kitchen(root):
    zone=collection("02 КУХНЯ",root)
    units=collection("Гарнитур - фасады и столешница",zone)
    # L-run in the niche: 3 modules at 50 cm plus a 60 cm corner.
    for i in range(3):
        y=-5.78-i*.50
        box("Kitchen west carcass",(.375,y,.48),(.60,.49,.76),MATS["walnut"],units)
        for z,h in [(.25,.25),(.54,.29),(.785,.17)]:
            box("Kitchen west drawer",(.685,y,z),(.022,.484,h),MATS["walnut"],units)
        box("Upper west cabinet",(.235,y,2.04),(.32,.494,.94),MATS["cashmere"],units)
        box("Upper west door",(.404,y,2.04),(.02,.483,.925),MATS["cashmere"],units)
    box("Kitchen corner base",(.375,-7.33,.48),(.60,.60,.76),MATS["walnut"],units)
    box("West stone worktop",(.386,-6.58,.90),(.64,2.12,.045),MATS["stone"],units,.004)
    box("West backsplash",(.083,-6.58,1.23),(.02,2.12,.61),MATS["stone"],units,0)
    for i in range(2):
        x=.99+i*.60
        box("South kitchen base",(x,-7.335,.48),(.588,.59,.76),MATS["walnut"],units)
        box("South kitchen door",(x,-7.025,.49),(.58,.022,.72),MATS["walnut"],units)
        box("South upper cabinet",(x,-7.47,2.04),(.592,.32,.94),MATS["cashmere"],units)
        box("South upper door",(x,-7.297,2.04),(.58,.022,.925),MATS["cashmere"],units)
    box("South stone worktop",(1.29,-7.325,.90),(1.22,.64,.045),MATS["stone"],units)
    box("South backsplash",(1.29,-7.627,1.23),(1.23,.022,.61),MATS["stone"],units,0)
    box("Fridge tall housing",(2.225,-7.32,1.31),(.65,.62,2.58),MATS["walnut"],units)
    for z,h in [(.44,.78),(1.61,1.53)]:
        box("Integrated fridge door",(2.225,-6.995,z),(.624,.023,h),MATS["walnut"],units)
    appliance=collection("Техника - мойка, варочная и духовка",zone)
    box("Black induction hob",(.395,-5.83,.929),(.49,.54,.014),MATS["screen"],appliance)
    for x in [.27,.52]:
        for y in [-5.68,-5.98]:cylinder("Hob zone",(x,y,.938),.083,.0015,MATS["metal"],appliance)
    box("Oven face",(.707,-5.80,.49),(.034,.46,.57),MATS["screen"],appliance,.008)
    line("Oven handle",[(.747,-6,.69),(.747,-5.60,.69)],.012,MATS["metal"],appliance)
    # Recess impression: top rim surrounds a dark basin without changing architecture.
    box("Sink rim",(.99,-7.31,.93),(.49,.43,.012),MATS["metal"],appliance,.035)
    box("Sink basin",(.99,-7.31,.938),(.426,.365,.012),MATS["dark"],appliance,.035)
    line("Black mixer tap",[(.99,-7.56,.93),(.99,-7.56,1.24),(.99,-7.48,1.29),(.99,-7.35,1.29),(.99,-7.32,1.20)],.014,MATS["dark"],appliance)
    dining=collection("Обеденный стол и 4 стула",zone)
    d=LAYOUT["dining_table"]
    top=cylinder("Oval walnut dining top",d["position"],1,d["dimensions"][2],MATS["walnut"],dining,96)
    top.scale.x=d["dimensions"][0]/2;top.scale.y=d["dimensions"][1]/2
    for x in [1.55,2.35]:
        for y in [-4.90,-4.40]:cylinder("Dining slim leg",(x,y,.383),.022,.72,MATS["dark"],dining)
    for i,d in enumerate(LAYOUT["chairs"]):
        model("Стул "+str(i+1),ASSETS/"upholstered_dining_chair/model.glb",dining,d["position"],[.46,.485,.89] if abs(d["rotation_deg"])!=90 else [.485,.46,.89],d["rotation_deg"],"chair")
    cylinder("Dining ceramic vase",(1.95,-4.65,.88),.06,.17,MATS["wall"],dining)
    return zone


def make_entry(root):
    zone=collection("03 ПРИХОЖАЯ",root)
    box("Entry wardrobe carcass",(4.245,-5.38,1.32),(.49,.80,2.60),MATS["cashmere"],zone)
    for y in [-5.58,-5.18]:
        box("Entry wardrobe door",(3.989,y,1.32),(.025,.391,2.56),MATS["cashmere"],zone)
        line("Entry black handle",[(3.966,y+(.13 if y<-5.3 else -.13),.90),(3.966,y+(.13 if y<-5.3 else -.13),1.50)],.009,MATS["dark"],zone)
    box("Entry bench base",(4.245,-4.66,.255),(.49,.60,.46),MATS["cashmere"],zone)
    box("Entry upholstered seat",(4.215,-4.66,.515),(.52,.59,.075),MATS["fabric"],zone,.035)
    box("Entry timber niche back",(4.485,-4.66,1.48),(.026,.60,1.88),MATS["walnut"],zone)
    for i in range(12):
        box("Entry niche timber slat",(4.463,-4.94+i*.049,1.47),(.025,.022,1.84),MATS["walnut"],zone)
    box("Entry overhead cabinet",(4.245,-4.66,2.48),(.49,.60,.28),MATS["cashmere"],zone)
    for y in [-4.84,-4.66,-4.48]:
        line("Coat hook",[(4.43,y,1.72),(4.36,y,1.72),(4.36,y,1.77)],.01,MATS["dark"],zone)
    box("Entry mirror frame",(4.486,-7.23,1.54),(.025,.55,1.79),MATS["dark"],zone)
    box("Entry full height mirror",(4.468,-7.23,1.54),(.006,.514,1.75),MATS["mirror"],zone,0)
    box("Entry inset mat",(3.875,-7.17,.031),(.85,.61,.014),MATS["rug"],zone,.01)
    # Bedroom niche side is at x=4.405 (inner face 4.345), not the bathroom axis 4.57.
    # Keep the entire cabinet/bench assembly in front of that tighter face.
    for obj in zone.objects:
        if not any(word in obj.name for word in ["mirror", "inset mat"]):
            obj.location.x -= .17
    return zone


def area_light(name,location,target,power,size,group,color=(1,.91,.80)):
    data=bpy.data.lights.new("INT / "+name,"AREA");data.energy=power;data.shape="DISK";data.size=size;data.color=color
    obj=bpy.data.objects.new("INT / "+name,data);group.objects.link(obj);obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()
    return obj


def make_lights(root):
    group=collection("06 СВЕТ - приборы и освещение",root)
    for x,y in [(1.5,-2),(1.7,-6.3),(3.8,-5.1)]:
        area_light("Ceiling soft light",(x,y,2.62),(x,y,0),160 if x<3 else 100,1.8,group)
    area_light("Window daylight",(1.55,-.13,2.0),(1.55,-4.5,1.0),240,1.7,group,(.84,.90,1))
    line("Dining suspension",[(1.95,-4.65,2.94),(1.95,-4.65,2.21)],.009,MATS["dark"],group)
    line("Dining pendant bar",[(1.49,-4.65,2.18),(2.41,-4.65,2.18)],.012,MATS["dark"],group)
    for i in range(5):
        x=1.51+i*.22;z=2.18+(i%2*2-1)*.10
        sphere("Opal pendant globe",(x,-4.65,z),(.10,.10,.10),MATS["opal"],group)
    area_light("Dining pendant glow",(1.95,-4.65,2.12),(1.95,-4.65,.76),38,.75,group)
    for name,loc,size in [("West undercabinet LED",(.397,-6.3,1.56),(.012,1.5,.012)),("South undercabinet LED",(1.29,-7.28,1.56),(1.19,.012,.012))]:
        box(name,loc,size,MATS["opal"],group,0)
    return group


def camera(name,location,target,lens,group,ortho=None):
    data=bpy.data.cameras.new(name);data.lens=lens;data.clip_start=.03
    if ortho:data.type="ORTHO";data.ortho_scale=ortho
    obj=bpy.data.objects.new(name,data);group.objects.link(obj);obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()
    return obj


def architecture_fingerprint(objects):
    report={}
    for o in objects:
        if o.type=="MESH":
            raw=str(([(round(v.co.x,6),round(v.co.y,6),round(v.co.z,6)) for v in o.data.vertices],list(o.matrix_world),[m.name for m in o.data.materials]))
            report[o.name]=hashlib.sha256(raw.encode()).hexdigest()
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,default=HERE/"apartment_photos.blend")
    parser.add_argument("--output",type=Path,default=HERE/"apartment_interior.blend")
    parser.add_argument("--render",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if args.input.resolve()==args.output.resolve():raise ValueError("Use a separate output file to preserve the input")
    bpy.ops.wm.open_mainfile(filepath=str(args.input.resolve()))
    original_objects=list(bpy.data.objects)
    before=architecture_fingerprint(original_objects)
    if bpy.data.collections.get(ROOT_NAME):raise ValueError("Input already has interior; rebuild from the architecture source")
    root=collection(ROOT_NAME,bpy.context.scene.collection)
    root["instructions"]="Глаз: скрыть весь интерьер в рабочем виде. Камера: скрыть на рендере. Подколлекции: комнаты и отделка."
    root["reference_index"]="//../docs/interior-references/README.md"
    MATS.update({
        "wall":material("Warm ivory plaster",(.79,.75,.68),.85),
        "cashmere":material("Grey cashmere",(.55,.51,.45),.64),
        "walnut":material("Brown walnut",(.085,.037,.016),.43,noise=(5,(9,9,.28))),
        "oak":material("Warm oak floor",(.38,.25,.135),.58,noise=(5,(18,.35,1))),
        "seam":material("Fine oak joints",(.18,.12,.07),.7),
        "fabric":material("Cream boucle",(.77,.72,.62),.95,noise=(150,(1,1,1))),
        "rug":material("Natural woven rug",(.56,.50,.40),1,noise=(180,(1,1,1))),
        "curtain":material("Taupe linen",(.37,.30,.23),.93,noise=(80,(2,2,.2))),
        "stone":material("Light stone",(.75,.72,.65),.40,noise=(4,(.7,1,2))),
        "dark":material("Charcoal metal",(.018,.02,.021),.35,.35),
        "metal":material("Brushed metal",(.18,.19,.20),.3,.8),
        "screen":material("Black glass",(.006,.009,.012),.24,0),
        "glass":material("Smoked glass",(.055,.044,.03),.14,.05),
        "mirror":material("Mirror",(.78,.80,.81),.035,1),
        "opal":material("Opal warm diffuser",(.92,.85,.71),.35),
    })
    glass=MATS["glass"].node_tree.nodes.get("Principled BSDF");glass.inputs["Transmission Weight"].default_value=.65
    MATS["screen"].node_tree.nodes.get("Principled BSDF").inputs["Specular IOR Level"].default_value=.12
    opal=MATS["opal"].node_tree.nodes.get("Principled BSDF");opal.inputs["Emission Color"].default_value=(1,.80,.54,1);opal.inputs["Emission Strength"].default_value=.6
    finishes,ceilings=make_finishes(root)
    make_living(root);make_kitchen(root);make_entry(root);make_lights(root)
    # Views and cameras are separate from the hideable furniture collection.
    views=collection("ВИДЫ ИНТЕРЬЕРА",bpy.context.scene.collection)
    cams={
        "living":camera("INTERIOR / ЗАЛ",(1.35,-4.03,1.60),(1.9,-1.5,1.27),23,views),
        "kitchen":camera("INTERIOR / КУХНЯ",(3.20,-5.12,1.65),(1.25,-6.95,1.25),21,views),
        "entry":camera("INTERIOR / ПРИХОЖАЯ",(1.70,-5.15,1.50),(4.10,-5.05,1.35),22,views),
        "dining":camera("INTERIOR / ОБЕДЕННАЯ ЗОНА",(2.85,-6.45,1.65),(1.70,-3.6,1.1),24,views),
        "overview":camera("INTERIOR / ОБЩИЙ ВИД",(10,-13,16),(3.1,-3.7,.5),35,views,11.8),
        "plan":camera("INTERIOR / ПЛАН",(3.1,-3.3,16),(3.1,-3.3,0),35,views,12.3),
    }
    # Hide drafting overlays by default; all remain available as existing collections.
    for name in ["РАЗМЕРЫ - скрыть или показать","07 Room labels","04 Openings - position to verify"]:
        col=bpy.data.collections.get(name)
        col.hide_render=True
        layer=bpy.context.view_layer.layer_collection
        def find(node):
            if node.collection==col:return node
            for child in node.children:
                result=find(child)
                if result:return result
        found=find(layer)
        if found:found.hide_viewport=True
    scene=bpy.context.scene
    scene.render.engine="BLENDER_EEVEE"
    scene.eevee.shadow_pool_size="1024"
    scene.render.resolution_x=1500;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.32
    scene.view_settings.view_transform="AgX"
    scene.view_settings.exposure=-.4
    scene.camera=cams["overview"]
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=="OUTLINER":
                area.spaces.active.show_restrict_column_hide=True
                area.spaces.active.show_restrict_column_render=True
            elif area.type=="VIEW_3D":
                space=area.spaces.active;space.overlay.show_overlays=False
                space.shading.type="MATERIAL"
                space.region_3d.view_location=(3.1,-3.7,.7)
                space.region_3d.view_rotation=(Vector((3.1,-3.7,.7))-Vector((10,-13,16))).to_track_quat("-Z","Y")
                space.region_3d.view_distance=12
                if screen.name=="Modeling":
                    space.region_3d.view_rotation=Quaternion((1,0,0,0))
                    space.region_3d.view_perspective="ORTHO"
                    space.region_3d.view_location=(3.1,-3.3,0)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active=None
    def layer_for(collection,node=None):
        node=node or bpy.context.view_layer.layer_collection
        if node.collection==collection:return node
        for child in node.children:
            found=layer_for(collection,child)
            if found:return found
    layer_for(ceilings).hide_viewport=True
    ceilings.hide_render=True
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    after=architecture_fingerprint(original_objects)
    report={"original_meshes_unchanged":before==after,"original_mesh_count":len(before),"interior_objects":len(root.all_objects),"interior_collections":[c.name for c in root.children],"source":str(args.input.name),"output":str(args.output.name),"assets":["sofa_three_seat","upholstered_dining_chair","coffee_table_round_01"],"packed_images":len([i for i in bpy.data.images if i.packed_file]),"concept_only":True}
    assert before==after,"Architecture changed"
    (HERE/"interior_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    if args.render:
        PREVIEWS.mkdir(exist_ok=True)
        for key in ["living","kitchen","entry","dining","overview","plan"]:
            ceilings.hide_render=key in {"overview","plan"}
            scene.camera=cams[key];scene.render.filepath=str(PREVIEWS/(key+".png"))
            bpy.ops.render.render(write_still=True)
        root.hide_render=True
        scene.camera=cams["overview"];scene.render.filepath=str(PREVIEWS/"interior-hidden.png")
        bpy.ops.render.render(write_still=True)
        root.hide_render=False;ceilings.hide_render=True
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
