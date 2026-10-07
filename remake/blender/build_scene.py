"""Build the 3D "Homer's Web Page" scene (style A: toon shading + outlines).

Run with Blender 5.x:
    blender --background --python remake/blender/build_scene.py -- [options]
or with the bpy module (pip install bpy):
    python remake/blender/build_scene.py [options]

Options:
    --save PATH        .blend to write (default: remake/blender/homers_web_page.blend)
    --still N [N ...]  render these frames to remake/render/stills/
    --render           render the whole loop to remake/render/frames/
    --percent P        render resolution percentage (default 100)
    --font PATH        title font (default: first of Cooper Black / Bookman / Georgia Bold found)

Everything is placed from remake/reference/layout.json, so props and the figure
land where they were in the original GIF. Shared helpers live in kit.py, the
props in props.py and the figure (model, rig, animation) in jesus.py.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jesus  # noqa: E402
from kit import (FPS, HERE, LAYOUT, LENS, LOOP, PALETTE, REMAKE, RES_X, RES_Y,  # noqa: E402
                 SENSOR, SRC_H, SRC_W, add_outlines, empty, finish, flat, new_collection, toon)
from props import BUILDERS  # noqa: E402

CAM_PITCH = 20.0       # degrees below horizontal
CAM_TARGET = Vector((0.0, 0.0, 1.05))
FIGURE_HEIGHT = 2.25   # feet to raised hand
TYPE_TURN = {"toaster": -30.0}  # degrees; show toasters three-quarter like the source


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    elif "blender" in os.path.basename(sys.argv[0]).lower():
        argv = []
    else:
        argv = sys.argv[1:]
    opts = {"save": os.path.join(HERE, "homers_web_page.blend"), "still": [],
            "render": False, "percent": 100, "font": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--save":
            opts["save"] = argv[i + 1]; i += 2
        elif a == "--still":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                opts["still"].append(int(argv[i])); i += 1
        elif a == "--render":
            opts["render"] = True; i += 1
        elif a == "--percent":
            opts["percent"] = int(argv[i + 1]); i += 2
        elif a == "--font":
            opts["font"] = argv[i + 1]; i += 2
        else:
            raise SystemExit(f"unknown option {a}")
    return opts


# --------------------------------------------------------------------------- scene

def camera_setup():
    data = bpy.data.cameras.new("Camera")
    data.lens = LENS
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = SENSOR
    data.clip_end = 500
    cam = bpy.data.objects.new("Camera", data)
    bpy.context.scene.collection.objects.link(cam)
    # distance so the figure fills the same share of the frame as in the source
    fx0, fy0, fx1, fy1 = LAYOUT["figure"]["box"]
    share = (fy1 - fy0) / SRC_H
    tan_v = (SENSOR * RES_Y / RES_X / 2) / LENS
    dist = FIGURE_HEIGHT / share / 2 / tan_v
    pitch = math.radians(CAM_PITCH)
    cam.location = CAM_TARGET + Vector((0, -dist * math.cos(pitch), dist * math.sin(pitch)))
    cam.rotation_euler = (CAM_TARGET - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    bpy.context.view_layer.update()
    return cam


def screen_ray(cam, px, py):
    """Ray from the camera through a pixel of the source GIF."""
    u = (px / SRC_W - 0.5) * SENSOR
    v = (0.5 - py / SRC_H) * SENSOR * RES_Y / RES_X
    d = cam.matrix_world.to_3x3() @ Vector((u, v, -LENS))
    return cam.matrix_world.translation.copy(), d.normalized()


def on_plane(cam, px, py, z):
    o, d = screen_ray(cam, px, py)
    return o + d * ((z - o.z) / d.z)


def world_bbox(objs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def descendants(obj):
    out = []
    for ch in obj.children:
        out.append(ch)
        out += descendants(ch)
    return out


def place_prop(cam, root, box, turn=0.0):
    """Scale and move a prop so its silhouette covers the source box.
    turn: extra yaw in degrees on top of facing the camera."""
    bpy.context.scene.frame_set(1)
    lo, hi = world_bbox(descendants(root))
    model_w, model_h = hi.x - lo.x, hi.z - lo.z
    center_x = (lo.x + hi.x) / 2
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    tan_h = (SENSOR / 2) / LENS
    s = 1.0
    pos = on_plane(cam, cx, cy, 0.5)
    for _ in range(4):
        depth = (pos - cam.matrix_world.translation).dot(fwd)
        units_per_px = 2 * depth * tan_h / SRC_W
        s = min((x1 - x0) * units_per_px / model_w, (y1 - y0) * units_per_px / model_h)
        pos = on_plane(cam, cx, cy, s * (lo.z + hi.z) / 2)
    root.scale = (s, s, s)
    yaw = math.atan2(cam.location.x - pos.x, -(cam.location.y - pos.y))
    root.rotation_euler.z = yaw + math.radians(turn)
    offset = Matrix.Rotation(yaw, 3, "Z") @ Vector((center_x * s, 0, 0))
    root.location = (pos.x - offset.x, pos.y - offset.y, 0.0)


def find_font(path):
    candidates = [path] if path else []
    fonts = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
    candidates += [os.path.join(fonts, n) for n in ("COOPBL.TTF", "BOOKOSB.TTF", "georgiab.ttf")]
    candidates += ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]
    for c in candidates:
        if c and os.path.exists(c):
            return bpy.data.fonts.load(c)
    return None


def build_title(cam, coll, font_path):
    t = LAYOUT["title"]
    curve = bpy.data.curves.new("Title", "FONT")
    curve.body = t["text"]
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = 0.01
    curve.offset = 0.022  # embolden: the original title is a heavy display serif
    font = find_font(font_path)
    if font:
        curve.font = font
    obj = bpy.data.objects.new("Title", curve)
    coll.objects.link(obj)
    obj.data.materials.append(flat("TitleInk", "#111111"))
    obj.visible_shadow = False
    # flat card 6 units in front of the camera, sized to the source title box
    d = 6.0
    tan_h = (SENSOR / 2) / LENS
    units_per_px = 2 * d * tan_h / SRC_W
    bpy.context.view_layer.update()
    w = obj.dimensions.x
    x0, y0, x1, y1 = t["box"]
    s = (x1 - x0) * units_per_px / w
    obj.parent = cam
    obj.scale = (s, s, s)
    obj.location = (((x0 + x1) / 2 - SRC_W / 2) * units_per_px,
                    (SRC_H / 2 - (y0 + y1) / 2) * units_per_px, -d)


def world_and_lights():
    world = bpy.data.worlds.new("World")
    if world.node_tree is None and hasattr(world, "use_nodes"):
        world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    if bg is None:
        nt.nodes.clear()
        bg = nt.nodes.new("ShaderNodeBackground")
        out = nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.02, 0.02, 0.02, 1)
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    direction = Vector((0.45, 0.75, -1.0))
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def floor(coll):
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 60, 0))
    obj = bpy.context.active_object
    obj.name = "Floor"
    finish(obj, toon("floor", PALETTE["bg"], shadow=0.84, threshold=0.06, softness=0.04),
           coll, outline=False, smooth=False)


def render_settings(percent):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = percent
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = LOOP
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    ee = scene.eevee
    ee.taa_render_samples = 32
    if hasattr(ee, "use_raytracing"):
        ee.use_raytracing = False


def build(opts):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render_settings(opts["percent"])
    world_and_lights()
    cam = camera_setup()

    set_coll = new_collection("Set")
    props_coll = new_collection("Props")
    fig_coll = new_collection("Figure")
    floor(set_coll)
    build_title(cam, set_coll, opts["font"])

    for p in LAYOUT["props"]:
        coll = new_collection(p["id"], props_coll)
        root = empty(p["id"], coll)
        BUILDERS[p["type"]](root, coll, p["phase"])
        place_prop(cam, root, p["box"], p.get("turn", TYPE_TURN.get(p["type"], 0.0)))

    rig = jesus.build(fig_coll)
    feet = on_plane(cam, *LAYOUT["figure"]["feet"], 0.0)
    rig.location = (feet.x, feet.y, 0.0)
    jesus.animate(rig)

    add_outlines(cam)
    bpy.context.scene.frame_set(1)
    return cam


def main():
    opts = parse_args()
    build(opts)
    os.makedirs(os.path.dirname(os.path.abspath(opts["save"])), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opts["save"]))
    print("saved", opts["save"])

    scene = bpy.context.scene
    if opts["still"]:
        out = os.path.join(REMAKE, "render", "stills")
        os.makedirs(out, exist_ok=True)
        for f in opts["still"]:
            scene.frame_set(f)
            scene.render.filepath = os.path.join(out, f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
            print("rendered", scene.render.filepath)
    if opts["render"]:
        scene.render.filepath = os.path.join(REMAKE, "render", "frames", "frame_")
        bpy.ops.render.render(animation=True)
        print("rendered loop to", os.path.dirname(scene.render.filepath))


if __name__ == "__main__":
    main()
