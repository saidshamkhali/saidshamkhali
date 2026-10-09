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
    --font PATH        title font (default: remake/fonts/Ultra-Regular.ttf, packed into the .blend)

Everything is placed from remake/reference/layout.json, so props and the figure
land where they were in the original GIF. Shared helpers live in kit.py, the
props in props.py and the figure (model, rig, animation) in jesus.py.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jesus  # noqa: E402
from kit import (FPS, HERE, LAYOUT, LENS, LOOP, PALETTE, REMAKE, RES_X, RES_Y, SOFT,  # noqa: E402
                 SENSOR, SRC_H, SRC_W, add_outlines, empty, finish, flat, new_collection, toon)
from props import BUILDERS, TURN  # noqa: E402

CAM_PITCH = 20.0       # degrees below horizontal
CAM_TARGET = Vector((0.0, 0.0, 1.05))
TYPE_TURN = TURN


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    elif "blender" in os.path.basename(sys.argv[0]).lower():
        argv = []
    else:
        argv = sys.argv[1:]
    opts = {"save": os.path.join(HERE, "homers_web_page_soft.blend" if SOFT else "homers_web_page.blend"), "still": [],
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
    bpy.context.scene.camera = cam
    frame_camera(cam)
    return cam


def frame_camera(cam):
    """Move the camera back until the top of the figure's hair, standing on its feet
    point, lands on the source's head_top row. The raised hand is a stretched cartoon
    cheat, so the body is the more reliable yardstick."""
    from bpy_extras.object_utils import world_to_camera_view
    scene = bpy.context.scene
    pitch = math.radians(CAM_PITCH)
    fx, fy = LAYOUT["figure"]["feet"]
    target_y = LAYOUT["figure"]["head_top"]

    def head_row(dist):
        cam.location = CAM_TARGET + Vector((0, -dist * math.cos(pitch), dist * math.sin(pitch)))
        cam.rotation_euler = (CAM_TARGET - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        top = on_plane(cam, fx, fy, 0.0) + Vector((0, 0, jesus.hair_top()))
        return (1 - world_to_camera_view(scene, cam, top).y) * SRC_H

    lo, hi = 3.0, 60.0  # the head drops down the frame as the camera backs away
    for _ in range(40):
        mid = (lo + hi) / 2
        if head_row(mid) < target_y:
            lo = mid
        else:
            hi = mid
    head_row((lo + hi) / 2)


def screen_ray(cam, px, py):
    """Ray from the camera through a pixel of the source GIF."""
    u = (px / SRC_W - 0.5) * SENSOR
    v = (0.5 - py / SRC_H) * SENSOR * RES_Y / RES_X
    d = cam.matrix_world.to_3x3() @ Vector((u, v, -LENS))
    return cam.matrix_world.translation.copy(), d.normalized()


def on_plane(cam, px, py, z):
    o, d = screen_ray(cam, px, py)
    return o + d * ((z - o.z) / d.z)


def descendants(obj):
    out = []
    for ch in obj.children:
        out.append(ch)
        out += descendants(ch)
    return out


def place_prop(cam, root, box, turn=0.0):
    """Scale and move a prop so its silhouette covers the source box.
    turn: extra yaw in degrees on top of facing the camera. The prop is measured as
    the camera sees it once turned: width along the camera's horizontal, height in Z.
    It's measured at the frame in the root's "fit_frame" (default 1), so a prop whose shape
    changes is sized in a set pose, and without its outline shells, so re-placing an outlined
    prop gives the same result. Parts flagged "no_fit", or hidden on that frame (a mouth swaps
    drawings), are left out of the measurement.
    A root with "fit_axis" = "x" is sized by its width alone; one with "face_camera" (a traced
    drawing) is also tipped back to face the camera square on; "fit_scale" scales the result."""
    scene = bpy.context.scene
    shells = [m for o in descendants(root) if o.type == "MESH" for m in o.modifiers
              if m.name == "Outline" and m.show_viewport]
    for m in shells:
        m.show_viewport = False
    fit = root.get("fit_frame", 1.0)
    scene.frame_set(int(fit), subframe=fit - int(fit))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0))
    right.z = 0
    right.normalize()
    tan_h = (SENSOR / 2) / LENS
    root.location, root.scale = (0, 0, 0), (1, 1, 1)
    pos = on_plane(cam, cx, cy, 0.5)
    s, mid_r = 1.0, 0.0
    for _ in range(4):
        yaw = math.atan2(cam.location.x - pos.x, -(cam.location.y - pos.y))
        root.rotation_euler.z = yaw + (0.0 if root.get("face_camera") else math.radians(turn))
        if root.get("face_camera"):  # a traced drawing: square on to the camera, which looks down on it
            off = cam.location - pos
            root.rotation_euler.x = -math.atan2(off.z, math.hypot(off.x, off.y))
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in descendants(root)
               if o.type == "MESH" and not o.get("no_fit") and not o.hide_render for c in o.bound_box]
        rs = [p.dot(right) for p in pts]
        zs = [p.z for p in pts]
        mid_r = (min(rs) + max(rs)) / 2
        depth = (pos - cam.matrix_world.translation).dot(fwd)
        units_per_px = 2 * depth * tan_h / SRC_W
        sx = (x1 - x0) * units_per_px / (max(rs) - min(rs))
        s = sx if root.get("fit_axis") == "x" else min(sx, (y1 - y0) * units_per_px / (max(zs) - min(zs)))
        pos = on_plane(cam, cx, cy, s * (min(zs) + max(zs)) / 2)
    s *= root.get("fit_scale", 1.0)  # a prop whose bounding box runs wider than what shows
    root.scale = (s, s, s)
    root.location = (pos.x - right.x * mid_r * s, pos.y - right.y * mid_r * s, 0.0)
    for m in shells:
        m.show_viewport = True


def find_font(path):
    """The title font: Ultra (Apache 2.0, in remake/fonts) is packed into the .blend so
    the file renders the same anywhere. Fallbacks are only used if it's missing."""
    candidates = [path] if path else []
    candidates.append(os.path.join(REMAKE, "fonts", "Ultra-Regular.ttf"))
    fonts = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
    candidates.append(os.path.join(fonts, "georgiab.ttf"))
    for c in candidates:
        if c and os.path.exists(c):
            font = bpy.data.fonts.load(c, check_existing=True)
            if os.path.basename(c).startswith("Ultra"):
                font.pack()
            return font
    return None


# The source title is a heavy, wide display serif. Ultra, a touch emboldened and tracked
# out, then fitted to the source glyph box in width and height separately, matches it.
TITLE_BOLD = 0.012
TITLE_TRACKING = 1.12
TITLE_WORD_SPACE = 1.2


def glyph_bounds(obj):
    """(x0, y0, x1, y1) of the evaluated glyph geometry in local space. A text object's
    bound_box covers the font's whole line height, not just the letters."""
    bpy.context.view_layer.update()
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    xs, ys = [v.co.x for v in me.vertices], [v.co.y for v in me.vertices]
    ev.to_mesh_clear()
    return min(xs), min(ys), max(xs), max(ys)


def fit_title(obj, cam):
    """Scale and move the title (parented to the camera, 6 units out) onto the source box."""
    d = 6.0
    units_per_px = 2 * d * (SENSOR / 2) / LENS / SRC_W
    obj.parent = cam
    obj.scale = (1, 1, 1)
    lx, ly, hx, hy = glyph_bounds(obj)
    x0, y0, x1, y1 = LAYOUT["title"]["box"]
    sx = (x1 - x0) * units_per_px / (hx - lx)
    sy = (y1 - y0) * units_per_px / (hy - ly)
    obj.scale = (sx, sy, sx)
    obj.location = (((x0 + x1) / 2 - SRC_W / 2) * units_per_px - sx * (lx + hx) / 2,
                    (SRC_H / 2 - (y0 + y1) / 2) * units_per_px - sy * (ly + hy) / 2, -d)


def build_title(cam, coll, font_path):
    curve = bpy.data.curves.new("Title", "FONT")
    curve.body = LAYOUT["title"]["text"]
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = 0.01
    curve.offset = TITLE_BOLD
    curve.space_character = TITLE_TRACKING
    curve.space_word = TITLE_WORD_SPACE
    font = find_font(font_path)
    if font:
        curve.font = font
    if SOFT:  # a solid, bevelled title that catches the studio light
        curve.extrude = 0.06
        curve.bevel_depth = 0.012
        curve.bevel_resolution = 3
    obj = bpy.data.objects.new("Title", curve)
    coll.objects.link(obj)
    obj.data.materials.append(flat("TitleInk", "#111111"))
    obj.visible_shadow = False
    fit_title(obj, cam)


def soft_lights(cam):
    """The soft look's studio: a big warm key from the upper left, a cool fill from the right,
    a rim from behind, under a pale blue sky."""
    target = on_plane(cam, *LAYOUT["figure"]["feet"], 0.0) + Vector((0.0, 0.0, 0.9))  # his middle
    for name, energy, size, colour, where in (
            ("Key", 4800.0, 9.0, (1.0, 0.95, 0.88), Vector((-9.0, -11.0, 13.0))),
            ("Fill", 1500.0, 12.0, (1.0, 0.96, 0.9), Vector((12.0, -9.0, 6.0))),  # warm: yellow in cool shade turns green
            ("Rim", 2500.0, 6.0, (1.0, 0.98, 0.95), Vector((3.0, 14.0, 10.0)))):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = colour
        light = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(light)
        light.location = target + where
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()


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
    bg.inputs["Color"].default_value = (0.55, 0.72, 0.9, 1) if SOFT else (0.02, 0.02, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.15 if SOFT else 1.0
    bpy.context.scene.world = world
    if SOFT:
        return  # lit by soft_lights once the camera is placed

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


def use_gpu():
    """Render Cycles on the GPU when there is one (OptiX, else CUDA); the CPU otherwise."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == kind]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == kind
            bpy.context.scene.cycles.device = "GPU"
            return kind
    bpy.context.scene.cycles.device = "CPU"
    return "CPU"


def soft_render_settings():
    """Cycles with soft studio light, denoised, and a touch of motion blur. The Standard view
    keeps the Simpsons' saturated yellow and sky blue (AgX greys them)."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    use_gpu()
    cy = scene.cycles
    cy.samples = 128
    cy.use_denoising = True
    cy.max_bounces = 8
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.35


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
    if SOFT:
        soft_render_settings()


def build(opts):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render_settings(opts["percent"])
    world_and_lights()
    cam = camera_setup()
    if SOFT:
        soft_lights(cam)

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
    tweaks_json = os.path.join(HERE, "tweaks.json")  # hand edits exported from the .blend
    if os.path.exists(tweaks_json) and not os.environ.get("REMAKE_NO_TWEAKS"):  # set by tweaks.py export
        from tweaks import apply_tweaks
        apply_tweaks(tweaks_json)
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
