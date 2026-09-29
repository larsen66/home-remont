"""Build or refresh only the generated apartment geometry in the Blender file."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector, Quaternion, Matrix, geometry


HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / "measurements.json"
BLEND_PATH = HERE / "apartment_draft.blend"
PLAN_PNG = HERE / "plan_2d.png"
VIEW_PNG = HERE / "view_3d.png"
BATH_PLAN_PNG = HERE / "bath_2d.png"
BATH_VIEW_PNG = HERE / "bath_3d.png"
METRICS_PATH = HERE / "model_metrics.json"
ROOT_NAME = "GENERATED - rebuildable architecture"
MANUAL_NAME = "MANUAL - your furniture and edits"
DIMENSIONS_NAME = "РАЗМЕРЫ - скрыть или показать"
DIMENSION_Z = 3.25


def meters(point_cm):
    """The source plan has its Y axis pointing down the page."""
    return Vector((point_cm[0] / 100.0, -point_cm[1] / 100.0))


def polygon_area_m2(points_cm):
    total = sum(
        points_cm[i][0] * points_cm[(i + 1) % len(points_cm)][1]
        - points_cm[(i + 1) % len(points_cm)][0] * points_cm[i][1]
        for i in range(len(points_cm))
    )
    return abs(total) / 20000.0


def remove_generated_collection():
    for name in (ROOT_NAME, DIMENSIONS_NAME):
        old = bpy.data.collections.get(name)
        if old is None:
            continue
        for obj in list(old.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for child in list(old.children):
            bpy.data.collections.remove(child)
        bpy.data.collections.remove(old)


def child_collection(parent, name):
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def material(name, rgba, roughness=0.75):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = roughness
    return mat


def mesh_object(name, vertices, faces, collection, mat, metadata=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    for key, value in (metadata or {}).items():
        obj[key] = value
    return obj


def prism(name, outline_cm, bottom_z, top_z, collection, mat, metadata=None):
    base = [meters(p) for p in outline_cm]
    signed_area = sum(
        base[i].x * base[(i + 1) % len(base)].y
        - base[(i + 1) % len(base)].x * base[i].y
        for i in range(len(base))
    )
    if signed_area < 0:
        base.reverse()
    count = len(base)
    vertices = [(p.x, p.y, bottom_z) for p in base]
    vertices += [(p.x, p.y, top_z) for p in base]
    triangles = geometry.tessellate_polygon([[Vector((p.x, p.y, 0)) for p in base]])
    faces = [tuple(reversed(triangle)) for triangle in triangles]
    faces += [tuple(index + count for index in triangle) for triangle in triangles]
    faces += [
        (i, (i + 1) % count, (i + 1) % count + count, i + count)
        for i in range(count)
    ]
    return mesh_object(name, vertices, faces, collection, mat, metadata)


def segment_box(name, a_cm, b_cm, thickness_m, height_m, collection, mat, metadata=None):
    a = meters(a_cm)
    b = meters(b_cm)
    axis = b - a
    if axis.length < 0.001:
        raise ValueError(f"Zero-length wall: {name}")
    side = Vector((-axis.y, axis.x)).normalized() * thickness_m / 2.0
    corners = [a + side, b + side, b - side, a - side]
    points_cm = [(p.x * 100, -p.y * 100) for p in corners]
    obj = prism(name, points_cm, 0, height_m, collection, mat, metadata)
    obj["schematic_length_cm"] = round(axis.length * 100, 2)
    return obj


def label(name, text, position_cm, size_m, collection, mat, z=0.08):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text
    curve.size = size_m
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    x, y = meters(position_cm)
    obj.location = (x, y, z)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def dimension(entry, collection, mats):
    """Draw a plan dimension in the XY plane so it remains visible in 2D and 3D."""
    a = Vector(entry["a"])
    b = Vector(entry["b"])
    axis = b - a
    if axis.length < 0.001:
        raise ValueError(f"Zero-length dimension: {entry['id']}")
    normal = Vector((-axis.y, axis.x)).normalized()
    offset = normal * entry["offset_cm"]
    start = a + offset
    end = b + offset
    tick = normal * 5
    curve = bpy.data.curves.new(entry["id"], "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.004
    curve.bevel_resolution = 2
    for p, q in ((start, end), (start - tick, start + tick), (end - tick, end + tick)):
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        for item, xy in zip(spline.points, (p, q)):
            world = meters(xy)
            item.co = (world.x, world.y, DIMENSION_Z, 1)
    obj = bpy.data.objects.new(f"DIM / {entry['id']}", curve)
    collection.objects.link(obj)
    obj.show_in_front = True
    obj.data.materials.append(mats[entry["status"]])
    obj["source_status"] = entry["status"]
    obj["schematic_span_cm"] = round(axis.length, 2)
    text_position = (start + end) / 2 - normal * 9
    text_obj = label(
        f"DIM TEXT / {entry['id']}", entry["text"], text_position,
        0.13 if axis.length >= 45 else 0.095, collection, mats[entry["status"]], z=DIMENSION_Z + 0.015,
    )
    text_obj.rotation_euler.z = math.atan2(-(b.y - a.y), b.x - a.x)
    text_obj.show_in_front = True
    text_obj["source_status"] = entry["status"]
    return obj


def wall_text(wall, side, height_m, thickness_m, collection, mat):
    """Place a readable measurement on one face of a measured wall."""
    a = meters(wall["a"])
    b = meters(wall["b"])
    axis = (b - a).normalized()
    right = Vector((axis.x * side, axis.y * side, 0))
    up = Vector((0, 0, 1))
    face = right.cross(up)
    length_cm = round((b - a).length * 100, 2)
    value = f"{length_cm:g}"
    curve = bpy.data.curves.new(f"Wall text / {wall['id']} / {side:+d}", "FONT")
    curve.body = value
    curve.size = min(0.25, (b - a).length / (len(value) * 0.75))
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = 0.001
    obj = bpy.data.objects.new(f"WALL TEXT / {wall['id']} / {side:+d}", curve)
    collection.objects.link(obj)
    obj.location = ((a + b) / 2).to_3d() + face * (thickness_m / 2 + 0.008) + up * (height_m * 0.56)
    obj.rotation_euler = Matrix((right, up, face)).transposed().to_euler()
    obj.data.materials.append(mat)
    obj["measured_length_cm"] = length_cm
    obj["source_wall"] = wall["id"]
    return obj


def camera(name, location, target, orthographic_scale, collection):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = orthographic_scale
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    obj.hide_set(True)
    return obj


def configure_workspaces():
    layout = bpy.data.workspaces.get("Layout") or bpy.data.workspaces.get("3D MODEL")
    modeling = bpy.data.workspaces.get("Modeling") or bpy.data.workspaces.get("2D PLAN")
    if layout:
        layout.name = "3D MODEL"
    if modeling:
        modeling.name = "2D PLAN"

    focus = Vector((3.15, -3.35, 0.8))
    for screen in bpy.data.screens:
        if screen.name not in {"Layout", "Modeling"}:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.region_3d.view_location = focus
            space.region_3d.view_distance = 12.5
            space.shading.type = "MATERIAL"
            if screen.name == "Modeling":
                space.region_3d.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
                space.region_3d.view_perspective = "ORTHO"
                space.region_3d.view_location.z = 0.0
            else:
                direction = Vector((-7.0, 8.0, 8.0))
                space.region_3d.view_rotation = direction.to_track_quat("-Z", "Y")
                space.region_3d.view_perspective = "PERSP"
            space.overlay.show_floor = False
    if layout and bpy.context.window:
        bpy.context.window.workspace = layout


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1500
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.8, 0.85, 0.9)
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.82, 0.87, 0.92, 1)
    background.inputs["Strength"].default_value = 0.45
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if BLEND_PATH.exists():
        bpy.ops.wm.open_mainfile(filepath=str(BLEND_PATH))
    for name in ("Cube", "Camera", "Light"):
        startup_object = bpy.data.objects.get(name)
        if startup_object and all(c.name != MANUAL_NAME for c in startup_object.users_collection):
            bpy.data.objects.remove(startup_object, do_unlink=True)
    bpy.context.preferences.filepaths.save_version = 0
    remove_generated_collection()

    scene = bpy.context.scene
    root = bpy.data.collections.new(ROOT_NAME)
    scene.collection.children.link(root)
    floors = child_collection(root, "01 Floors - schematic outlines")
    measured_walls = child_collection(root, "02 Walls - measured lengths")
    provisional_walls = child_collection(root, "03 Walls - provisional placement")
    openings = child_collection(root, "04 Openings - position to verify")
    balcony = child_collection(root, "05 Balcony - area reference only")
    ceilings = child_collection(root, "06 Ceilings - hidden by default")
    annotations = child_collection(root, "07 Room labels")
    cameras = child_collection(root, "08 Cameras and light")
    dimensions = bpy.data.collections.new(DIMENSIONS_NAME)
    scene.collection.children.link(dimensions)
    plan_dimensions = child_collection(dimensions, "01 ЛИНИИ РАЗМЕРОВ")
    wall_dimensions = child_collection(dimensions, "02 НАДПИСИ НА СТЕНАХ")

    if bpy.data.collections.get(MANUAL_NAME) is None:
        manual = bpy.data.collections.new(MANUAL_NAME)
        scene.collection.children.link(manual)

    mats = {
        "living_kitchen": material("Floor / living and kitchen", (0.67, 0.80, 0.88, 1)),
        "bedroom": material("Floor / bedroom", (0.70, 0.81, 0.69, 1)),
        "bathroom": material("Floor / bathroom", (0.92, 0.79, 0.64, 1)),
        "measured": material("Wall / measured length, schematic position", (0.20, 0.32, 0.43, 1)),
        "provisional": material("Wall / provisional geometry", (0.97, 0.49, 0.17, 1)),
        "opening": material("Opening / verify dimensions", (0.22, 0.69, 0.76, 1)),
        "balcony": material("Balcony / unmeasured outline", (0.93, 0.87, 0.57, 1)),
        "text": material("Labels / dark", (0.08, 0.15, 0.22, 1)),
        "dimension_measured": material("Dimension / measured", (0.08, 0.22, 0.55, 1)),
        "dimension_derived": material("Dimension / derived", (0.05, 0.43, 0.48, 1)),
        "dimension_provisional": material("Dimension / provisional", (0.78, 0.29, 0.07, 1)),
        "wall_text": material("Wall text / measured length", (0.96, 0.96, 0.87, 1)),
        "ceiling": material("Ceiling / provisional", (0.88, 0.89, 0.88, 1)),
    }

    metrics = {
        "status": "DRAFT - not for purchasing materials",
        "rooms": [],
        "closure_checks_cm": {
            "bedroom_niche_depth_measured": 93.5,
            "bedroom_niche_depth_schematic": 505.5 - 426,
            "bedroom_depth_discrepancy": 93.5 - (505.5 - 426),
            "bedroom_end_width_measured_parts": 121.5 + 175.5,
            "bedroom_balcony_width": 296,
            "bedroom_width_discrepancy": 121.5 + 175.5 - 296,
            "bath_step_measured": 23.5,
            "bath_vertical_closing_offset": 231.5 + 23.5 - 254.5,
            "bath_partition_straight_measured": 77.5,
            "bath_horizontal_closing_offset": 181 - 102.5 - 77.5,
        },
    }
    floor_thickness = data["assumptions"]["floor_thickness_cm"] / 100
    for room in data["rooms"]:
        area = polygon_area_m2(room["outline_cm"])
        metrics["rooms"].append({
            "id": room["id"],
            "schematic_floor_area_m2": round(area, 3),
            "developer_plan_area_m2": room["planned_area_m2"],
            "difference_m2": round(area - room["planned_area_m2"], 3),
            "outline_status": room["outline_status"],
        })
        prism(
            f"Floor / {room['id']}", room["outline_cm"], -floor_thickness, 0,
            floors, mats[room["id"]],
            {"room": room["id"], "certainty": "schematic", "schematic_area_m2": round(area, 3)},
        )
        ceiling_height = data["assumptions"][
            "bath_wall_height_cm" if room["id"] == "bathroom" else "wall_height_cm"
        ] / 100
        prism(
            f"Ceiling / {room['id']}", room["outline_cm"], ceiling_height,
            ceiling_height + 0.04, ceilings, mats["ceiling"],
            {"certainty": "height assumed except bathroom"},
        )

    thickness = data["assumptions"]["wall_thickness_cm"] / 100
    for wall in data["walls"]:
        measured = wall["status"] == "measured_length"
        height = data["assumptions"][
            "bath_wall_height_cm" if wall["id"].startswith("BA ") else "wall_height_cm"
        ] / 100
        segment_box(
            wall["id"], wall["a"], wall["b"], wall.get("thickness_cm", thickness * 100) / 100, height,
            measured_walls if measured else provisional_walls,
            mats["measured"] if measured else mats["provisional"],
            {"certainty": wall["status"], "source": wall.get("source", "schematic plan")},
        )
        if measured:
            wall_thickness = wall.get("thickness_cm", thickness * 100) / 100
            for side in (-1, 1):
                wall_text(wall, side, height, wall_thickness, wall_dimensions, mats["wall_text"])

    for entry in data["openings"]:
        segment_box(
            entry["id"], entry["a"], entry["b"], 0.045, 0.018,
            openings, mats["opening"], {"certainty": entry["status"]},
        )

    balcony_outline = [[0, -130], [616, -130], [616, 0], [0, 0]]
    prism(
        "Balcony / placeholder from planned area", balcony_outline, -0.03, -0.015,
        balcony, mats["balcony"],
        {"certainty": "depth and exterior perimeter unmeasured", "developer_plan_area_m2": 8.05},
    )

    label("Living label", "LIVING + KITCHEN\noutline provisional", (180, 290), 0.20, annotations, mats["text"])
    label("Bedroom label", "BEDROOM\noutline provisional", (470, 245), 0.20, annotations, mats["text"])
    bath_label = label("Bathroom label", "BATHROOM\noutline provisional", (562, 611), 0.12, annotations, mats["text"], z=DIMENSION_Z + 0.015)
    bath_label.show_in_front = True
    label("Balcony label", "BALCONY 8.05 m2 on plan\ndepth unmeasured", (308, -65), 0.16, annotations, mats["text"], z=0.015)

    dimension_mats = {
        "measured": mats["dimension_measured"],
        "derived": mats["dimension_derived"],
        "provisional": mats["dimension_provisional"],
    }
    for entry in data["dimensions"]:
        dimension(entry, plan_dimensions, dimension_mats)
    label("Niche measured depth", "NICHE 93.5 cm", (497, 363), 0.12, plan_dimensions, mats["dimension_measured"], z=DIMENSION_Z + 0.015)
    label("Niche schematic return", "OUTLINE 79.5 cm ?", (497, 386), 0.10, plan_dimensions, mats["dimension_provisional"], z=DIMENSION_Z + 0.015)
    label(
        "Kitchen niche / unplaced",
        "KITCHEN NICHE\n218.3 x 30.7 cm; h 267.5 cm\nposition unmeasured",
        (167, 660), 0.12, plan_dimensions, mats["dimension_provisional"], z=DIMENSION_Z + 0.015,
    )
    label("Living height", "HEIGHT 300 cm*", (135, 510), 0.12, plan_dimensions, mats["dimension_provisional"], z=DIMENSION_Z + 0.015)
    label("Bathroom height", "HEIGHT 306 cm", (562, 662), 0.13, plan_dimensions, mats["dimension_measured"], z=DIMENSION_Z + 0.015)
    label(
        "Dimension legend", "cm | BLUE measured | TEAL derived | ORANGE provisional\n* source lengths do not close exactly",
        (310, 827), 0.12, plan_dimensions, mats["text"], z=DIMENSION_Z + 0.015,
    )

    for obj in plan_dimensions.objects:
        obj.show_in_front = True

    plan_camera = camera("CAMERA / 2D PLAN", (3.2, -3.15, 14), (3.2, -3.15, 0), 10.8, cameras)
    view_camera = camera("CAMERA / 3D CUTAWAY", (10, -12, 19), (3.15, -3.45, 1.6), 15.5, cameras)
    bath_plan_camera = camera("CAMERA / BATH 2D", (5.3, -6.48, 10), (5.3, -6.48, 0), 3.9, cameras)
    bath_view_camera = camera("CAMERA / BATH 3D", (7.1, -8.4, 13.5), (5.45, -6.48, 1.6), 5.0, cameras)
    light_data = bpy.data.lights.new("Soft sun", "SUN")
    light_data.energy = 1.1
    light = bpy.data.objects.new("Soft sun", light_data)
    cameras.objects.link(light)
    light.rotation_euler = (math.radians(25), math.radians(-20), math.radians(-30))

    ceilings.hide_viewport = True
    ceilings.hide_render = True
    configure_render()
    configure_workspaces()
    scene.camera = view_camera
    scene.render.filepath = str(VIEW_PNG)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    plan_dimensions.hide_render = True
    bpy.ops.render.render(write_still=True)
    plan_dimensions.hide_render = False
    wall_dimensions.hide_render = True
    scene.camera = plan_camera
    scene.render.filepath = str(PLAN_PNG)
    scene.render.resolution_x = 2200
    scene.render.resolution_y = 2200
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "FLAT"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = False
    scene.display.shading.background_type = "WORLD"
    bpy.ops.render.render(write_still=True)
    wall_dimensions.hide_render = False

    generated_objects = set(root.all_objects)
    dimension_objects = set(dimensions.all_objects)
    original_visibility = {obj: obj.hide_render for obj in scene.objects}
    try:
        for obj in scene.objects:
            if obj.type in {"CAMERA", "LIGHT"}:
                continue
            if obj in generated_objects:
                keep = obj.name == "Floor / bathroom" or obj.name == "Bathroom label" or obj.name == "Bathroom door" or obj.name.startswith("BA ")
            elif obj in dimension_objects:
                keep = obj.name == "Bathroom height" or obj.name.startswith("DIM / Bathroom") or obj.name.startswith("DIM TEXT / Bathroom") or obj.name.startswith("WALL TEXT / BA ")
            else:
                keep = False
            obj.hide_render = not keep

        scene.render.engine = "BLENDER_EEVEE"
        scene.camera = bath_view_camera
        scene.render.filepath = str(BATH_VIEW_PNG)
        scene.render.resolution_x = 1800
        scene.render.resolution_y = 1500
        plan_dimensions.hide_render = True
        bpy.ops.render.render(write_still=True)
        plan_dimensions.hide_render = False
        wall_dimensions.hide_render = True
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.camera = bath_plan_camera
        scene.render.filepath = str(BATH_PLAN_PNG)
        scene.render.resolution_x = 1600
        scene.render.resolution_y = 1600
        bpy.ops.render.render(write_still=True)
    finally:
        for obj, was_hidden in original_visibility.items():
            obj.hide_render = was_hidden
        plan_dimensions.hide_render = False
        wall_dimensions.hide_render = False

    scene.render.engine = "BLENDER_EEVEE"
    scene.camera = view_camera
    scene.render.filepath = str(VIEW_PNG)
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1500
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {BLEND_PATH}")
    print(f"Rendered {PLAN_PNG}, {VIEW_PNG}, {BATH_PLAN_PNG}, and {BATH_VIEW_PNG}")


if __name__ == "__main__":
    main()
