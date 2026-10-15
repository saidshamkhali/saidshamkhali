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
from kit import (FPS, HERE, LAYOUT, LENS, LINE, LOOP, OUTLINE_PX, PALETTE, REMAKE, RES_X, RES_Y,  # noqa: E402
                 SENSOR, SRC_H, SRC_W, add_outlines, empty, finish, flat, new_collection, srgb)
from props import BUILDERS, TURN  # noqa: E402

CAM_PITCH = 20.0       # degrees below horizontal
CAM_TARGET = Vector((0.0, 0.0, 1.05))
TYPE_TURN = TURN
FLOOR_Z = -0.03        # the floor plane, under the soles' outline shells


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


DRAWING_FLOOR = 0.02  # a traced drawing's lowest point stands this far above the floor


def place_drawing(cam, root):
    """Put a traced drawing (props.build_traced) back exactly where it was traced. Its grid is
    turned parallel to the image plane, so it projects as an undistorted copy at one scale
    wherever it is in the frame, centred on the ray through the grid's centre (where it lay in
    the GIF), at the depth where one of its GIF pixels covers one pixel of the frame. That
    depth is the one where its lowest drawn point clears the floor: every drawing then lands
    at its traced place and size, the bigger ones (a wing up, a shout) included."""
    from mathutils import Matrix
    ox, oy = root["grid_origin_px"]
    gw, gh = root["grid_px"]
    root.location, root.scale = (0, 0, 0), (1, 1, 1)
    # the grid's -Y towards the camera, its Z along the camera's up
    root.rotation_euler = (cam.matrix_world.to_3x3() @ Matrix.Rotation(-math.pi / 2, 3, "X")).to_euler()
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ Vector(c)).z for o in descendants(root) if o.type == "MESH" for c in o.bound_box)
    eye, ray = screen_ray(cam, ox + gw / 2, oy + gh / 2)
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    # at distance t along the ray the scale is k*t (one GIF pixel covers 2*depth*tan/SRC_W units)
    k = 2 * ray.dot(fwd) * (SENSOR / 2) / LENS / SRC_W / root["px_units"]
    t = (DRAWING_FLOOR - eye.z) / (ray.z + k * low)
    root.scale = (k * t,) * 3
    root.location = eye + ray * t


def place_prop(cam, root, box, turn=0.0):
    """Scale and move a prop so its silhouette covers the source box.
    turn: extra yaw in degrees on top of facing the camera. The prop is measured as
    the camera sees it once turned: width along the camera's horizontal, height in Z.
    It's measured at the frame in the root's "fit_frame" (default 1), so a prop whose shape
    changes is sized in a set pose, and without its outline shells, so re-placing an outlined
    prop gives the same result. Parts flagged "no_fit", or hidden on that frame (a mouth swaps
    drawings), are left out of the measurement.
    A root with "fit_axis" = "x" is sized by its width alone. One with "level" lies along the
    camera's horizontal instead of facing the camera, so it reads level anywhere in the frame
    (a worm off to the side would slant). A traced drawing ("face_camera") isn't fitted to the
    box at all: place_drawing puts it back where it was traced."""
    scene = bpy.context.scene
    shells = [m for o in descendants(root) if o.type == "MESH" for m in o.modifiers
              if m.name == "Outline" and m.show_viewport]
    for m in shells:
        m.show_viewport = False
    if root.get("face_camera"):
        place_drawing(cam, root)
        for m in shells:
            m.show_viewport = True
        return
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
        if root.get("level"):
            root.rotation_euler.z = math.atan2(right.y, right.x)
        else:
            root.rotation_euler.z = math.atan2(cam.location.x - pos.x, -(cam.location.y - pos.y)) + math.radians(turn)
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


# The source title is a heavy, wide display serif. Ultra, emboldened and tracked out, then
# fitted to the source glyph box in width and height separately, matches it.
# How much the letters are thickened all round (the curve's offset, in font units). Ultra cuts slits
# between neighbouring serifs and strokes (the feet of m, the tops of W, beside the crossbars of H
# and e), which the source's fatter letters don't have, and they read as hairline cracks. An offset
# big enough to close them (0.02) also filled the counters: a slit for the e's eye, a dot for the a's
# bowl. So the letters are only thickened a little, to the source's weight of ink (within 5%), and
# the slits are closed on their own (close_slits): a closing of TITLE_CLOSE fills gaps narrower than
# twice that, while the counters, wider, keep their size.
TITLE_BOLD = 0.008
TITLE_CLOSE = 0.015
TITLE_VOXEL = 0.008  # the closing's grid: finer only adds time (0.004 took ~10 s) for the same letters
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
    obj = bpy.data.objects.new("Title", curve)
    coll.objects.link(obj)
    obj.data.materials.append(flat("TitleInk", "#111111"))
    obj.visible_shadow = False
    if TITLE_CLOSE > 0:
        close_slits(obj, obj.data.materials[0])
    fit_title(obj, cam)


def close_slits(obj, material):
    """Fill the slits narrower than 2 * TITLE_CLOSE (font units) and leave the rest of the letters as they
    are: a morphological closing, grown by TITLE_CLOSE and shrunk back by as much, on the letters'
    distance field (a Geometry Nodes modifier, so the title stays a text object). Wider gaps (the
    counters of e, a, g and o) come back at their own size."""
    nt = bpy.data.node_groups.new("TitleClose", "GeometryNodeTree")
    nt.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    nt.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = nt.nodes, nt.links.new
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    sdf = n.new("GeometryNodeMeshToSDFGrid")
    sdf.inputs["Voxel Size"].default_value = TITLE_VOXEL
    sdf.inputs["Band Width"].default_value = math.ceil(TITLE_CLOSE / TITLE_VOXEL) + 3
    grow, shrink = n.new("GeometryNodeSDFGridOffset"), n.new("GeometryNodeSDFGridOffset")
    grow.inputs["Distance"].default_value = TITLE_CLOSE
    shrink.inputs["Distance"].default_value = -TITLE_CLOSE
    mesh = n.new("GeometryNodeGridToMesh")
    mesh.inputs["Threshold"].default_value = 0.0
    setmat = n.new("GeometryNodeSetMaterial")
    setmat.inputs["Material"].default_value = material
    link(gin.outputs["Geometry"], sdf.inputs["Mesh"])
    link(sdf.outputs[0], grow.inputs["Grid"])
    link(grow.outputs[0], shrink.inputs["Grid"])
    link(shrink.outputs[0], mesh.inputs["Grid"])
    link(mesh.outputs["Mesh"], setmat.inputs["Geometry"])
    link(setmat.outputs["Geometry"], gout.inputs["Geometry"])
    obj.modifiers.new("CloseSlits", "NODES").node_group = nt


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
    # the sun only sets the toon band (which side of a shape is in shade). The drawings cast no
    # shadows: its cast shadows left a grey smudge beside every prop, a long smear from his feet and
    # a grainy shade on his legs that changed with every pose
    sun_data.use_shadow = False
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    direction = Vector((0.45, 0.75, -1.0))
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def floor(coll):
    """The page: flat sky blue. It sits a little below his soles (at 0), deeper than any outline
    shell reaches: where it cut through the sandals' shells, only their spikes poked out, a comb
    of light teeth under each sole. Nothing casts a shadow on it, so its height doesn't show."""
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 60, FLOOR_Z))
    obj = bpy.context.active_object
    obj.name = "Floor"
    finish(obj, flat("floor", PALETTE["bg"]), coll, outline=False, smooth=False)


# A soft patch of shade on the floor right under each sandal, like concept A's soft floor shadows:
# it stands him on the page without the sun's long cast shadow. Only he gets one; the props float.
CONTACT_HEX = "#3F84AA"   # the shade's colour at its darkest: a deeper sky blue
CONTACT_ALPHA = 0.65      # how much of it shows at the middle, fading to nothing at the rim
CONTACT_PAD = (1.4, 2.0)  # the patch's size against the sole's, along the foot and across it
CONTACT_SOFT = 0.25       # the fade starts this far out from the middle (fraction of the rim)
CONTACT_Z = -0.02         # above the floor, below the soles' outline shells


def contact_material():
    """Shade colour over whatever is under it, fading out with the distance from the middle (the
    UV map holds where each point sits on the unit disc). Blended, so where the patches of the
    two feet overlap they darken together instead of one cutting the other off."""
    mat = bpy.data.materials.new("ContactShadow")
    if mat.node_tree is None and hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n, link = nt.nodes, nt.links.new
    uv = n.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    length = n.new("ShaderNodeVectorMath")
    length.operation = "LENGTH"
    fade = n.new("ShaderNodeMapRange")
    fade.interpolation_type = "SMOOTHSTEP"
    fade.inputs["From Min"].default_value = CONTACT_SOFT
    fade.inputs["From Max"].default_value = 1.0
    fade.inputs["To Min"].default_value = CONTACT_ALPHA
    fade.inputs["To Max"].default_value = 0.0
    clear = n.new("ShaderNodeBsdfTransparent")
    shade = n.new("ShaderNodeEmission")
    shade.inputs["Color"].default_value = srgb(CONTACT_HEX) + (1,)
    mix = n.new("ShaderNodeMixShader")
    out = n.new("ShaderNodeOutputMaterial")
    link(uv.outputs["UV"], length.inputs[0])
    link(length.outputs["Value"], fade.inputs["Value"])
    link(fade.outputs["Result"], mix.inputs["Fac"])
    link(clear.outputs["BSDF"], mix.inputs[1])
    link(shade.outputs["Emission"], mix.inputs[2])
    link(mix.outputs["Shader"], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = srgb(CONTACT_HEX) + (CONTACT_ALPHA,)
    return mat


def contact_shadow(rig, coll):
    """A soft elliptical patch under each sandal, sized and turned to the sole as built (its rest
    pose, in the rig's space) and skinned to the foot bone, so it follows the foot every frame."""
    mat = contact_material()
    for side in ("L", "R"):
        sandal = bpy.data.objects.get(f"J_sandal_{side}")
        if sandal is None:
            continue
        pts = [(v.co.x, v.co.y) for v in sandal.data.vertices]
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        syy = sum((p[1] - my) ** 2 for p in pts)
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy)  # the sole's long axis, along the foot
        u = Vector((math.cos(ang), math.sin(ang), 0))
        v = Vector((-u.y, u.x, 0))
        pu = [p[0] * u.x + p[1] * u.y for p in pts]
        pv = [p[0] * v.x + p[1] * v.y for p in pts]
        cu, cv = (min(pu) + max(pu)) / 2, (min(pv) + max(pv)) / 2
        a, b = (max(pu) - min(pu)) / 2 * CONTACT_PAD[0], (max(pv) - min(pv)) / 2 * CONTACT_PAD[1]
        centre = u * cu + v * cv
        segs, rings = 48, 8
        verts, uvs = [(centre.x, centre.y, CONTACT_Z)], [(0.0, 0.0)]
        for i in range(1, rings + 1):
            r = i / rings
            for s in range(segs):
                t = 2 * math.pi * s / segs
                p = centre + u * (a * r * math.cos(t)) + v * (b * r * math.sin(t))
                verts.append((p.x, p.y, CONTACT_Z))
                uvs.append((r * math.cos(t), r * math.sin(t)))
        faces = [(0, 1 + s, 1 + (s + 1) % segs) for s in range(segs)]
        for i in range(rings - 1):
            o0, o1 = 1 + i * segs, 1 + (i + 1) * segs
            faces += [(o0 + s, o1 + s, o1 + (s + 1) % segs, o0 + (s + 1) % segs) for s in range(segs)]
        mesh = bpy.data.meshes.new(f"J_contact_{side}")
        mesh.from_pydata(verts, [], faces)
        layer = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            layer.data[loop.index].uv = uvs[loop.vertex_index]
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(f"J_contact_{side}", mesh)
        coll.objects.link(obj)
        obj.visible_shadow = False
        obj["helper"] = True  # not part of his figure: the fitter leaves it out
        jesus.skin(obj, rig, lambda co, side=side: {f"foot.{side}": 1.0}, subsurf=0)


# The drawings line each hanging sleeve all the way down where it lies on the robe (the back views,
# the waves, the turns), and the outline shells can't draw every line they have. A Grease Pencil
# Line Art object draws the rest, in passes:
# - where a sleeve sinks a little into the robe (their intersection), its shell is buried: a slate line
#   down the sleeve. Only there: the robe's other intersections (under the hair, the V-neck and the
#   collar) doubled lines the shells already draw, and a hand's left slate scraps round it.
# - where a hand sinks into the robe, its shell is buried too: a line in the skin's brown, as the rest
#   of the hand has.
# - edge marks, in slate: the hem across his legs (jesus.flat_hem: its cap is edge-on, so its shell
#   draws nothing there) and each cuff's end, where the hand comes out (jesus.build_arms: the hand
#   covers the shell there).
# Not where the two tubes of a sleeve meet at the elbow, nor where the legs cross the hem. False skips
# it (it about doubles the render time of a frame).
INNER_LINES = True
SLEEVES = ("J_sleeve_", "J_cuff_")
HANDS = ("J_hand_",)
MARKED = ("J_robe", "J_cuff_")  # the parts with edge marks
BELOW_HEM = ("J_leg_", "J_foot_", "J_sandal_")
# Line Art tags an intersection with the masks of the collections of the two parts it lies between,
# and a pass in match mode keeps only the lines tagged exactly with its own: robe and sleeve (1+2),
# robe and hand (1+4). One bit per group of parts, each in a collection of its own inside the figure's
MASK_BITS = {"robe": 0, "sleeves": 1, "hands": 2}
# strokes shorter than this (pixels at RES_X) are dropped: the ticks, dashes and hooks a sleeve leaves
# where it starts and ends against the robe (the shoulder, the curl near a hand)
MIN_STROKE_PX = 6.0


def mask_collection(fig_coll, group, prefixes):
    """A collection inside the figure's holding these parts too (they stay in the figure's collection),
    with its own intersection mask bit: Line Art reads the masks from collections, not objects."""
    c = new_collection(f"Lines {group}", fig_coll)
    c.lineart_use_intersection_mask = True
    c.lineart_intersection_mask[MASK_BITS[group]] = True
    for o in list(fig_coll.objects):
        if o.name.startswith(prefixes):
            c.objects.link(o)
    return c


def marks_off_shells(obj):
    """The outline shell (kit.add_outline, a Solidify) copies the edge marks onto its own copy of each
    edge, a second line 2 px out from the first. Clear them on the shell's faces (those with the
    outline material) after it, so only the part's own edges are drawn."""
    shell = obj.modifiers.get("Outline")
    if shell is None:
        return
    name = f"ShellMarks{shell.material_offset}"  # one group per shell material slot
    nt = bpy.data.node_groups.get(name)
    if nt is None:
        nt = bpy.data.node_groups.new(name, "GeometryNodeTree")
        nt.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        nt.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        n, link = nt.nodes, nt.links.new
        gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
        on_shell = n.new("FunctionNodeCompare")  # the edge's faces have the shell's material
        on_shell.data_type, on_shell.operation = "FLOAT", "GREATER_THAN"
        link(n.new("GeometryNodeInputMaterialIndex").outputs[0], on_shell.inputs["A"])
        on_shell.inputs["B"].default_value = shell.material_offset - 0.5
        clear = n.new("GeometryNodeStoreNamedAttribute")
        clear.data_type, clear.domain = "BOOLEAN", "EDGE"
        clear.inputs["Name"].default_value = "freestyle_edge"
        clear.inputs["Value"].default_value = False
        link(gin.outputs["Geometry"], clear.inputs["Geometry"])
        link(on_shell.outputs["Result"], clear.inputs["Selection"])
        link(clear.outputs["Geometry"], gout.inputs["Geometry"])
    obj.modifiers.new("ShellMarks", "NODES").node_group = nt


def drop_short_strokes(obj, length):
    """Delete the strokes shorter than `length` (world units) from the Line Art's output."""
    nt = bpy.data.node_groups.new("ShortStrokes", "GeometryNodeTree")
    nt.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    nt.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = nt.nodes, nt.links.new
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    short = n.new("FunctionNodeCompare")
    short.data_type, short.operation = "FLOAT", "LESS_THAN"
    link(n.new("GeometryNodeSplineLength").outputs["Length"], short.inputs["A"])
    short.inputs["B"].default_value = length
    delete = n.new("GeometryNodeDeleteGeometry")
    delete.domain = "CURVE"
    link(gin.outputs["Geometry"], delete.inputs["Geometry"])
    link(short.outputs["Result"], delete.inputs["Selection"])
    link(delete.outputs["Geometry"], gout.inputs["Geometry"])
    mod = obj.modifiers.new("ShortStrokes", "NODES")
    mod.node_group = nt
    mod.show_viewport = False


def line_pass(obj, name, layer, hex_color, fig_coll, radius, groups, edge_marks=False, cache=False):
    """One Line Art pass onto its own layer, in its own colour: the intersections between exactly these
    groups of parts (MASK_BITS), and the edge marks if asked."""
    gp = obj.data
    gp.layers.new(layer).frames.new(bpy.context.scene.frame_start)
    ink = bpy.data.materials.new(f"InnerInk_{layer}")
    bpy.data.materials.create_gpencil_data(ink)
    ink.grease_pencil.color = srgb(hex_color) + (1.0,)
    gp.materials.append(ink)
    m = obj.modifiers.new(name, "LINEART")
    m.source_type = "COLLECTION"
    m.source_collection = fig_coll
    m.target_layer = layer
    m.target_material = ink
    for kind in ("contour", "loose", "crease", "material"):
        setattr(m, f"use_{kind}", False)
    m.use_intersection = True
    m.use_edge_mark = edge_marks
    for g in groups:
        m.use_intersection_mask[MASK_BITS[g]] = True
    m.use_intersection_match = True
    m.radius = radius
    m.use_cache = cache  # the second pass reuses the first one's lines instead of computing them again
    # render only: the fitter and every frame change in the UI would otherwise recompute it
    m.show_viewport = False
    return m


def inner_lines(cam, rig, fig_coll, coll):
    """A Grease Pencil Line Art object drawing the figure's inner lines (see INNER_LINES), in the
    outline's weight. Everything else only hides lines behind it."""
    for o in fig_coll.all_objects:
        if o.type != "MESH":
            continue
        if o.hide_render or o.get("helper") or o.name.startswith(BELOW_HEM):
            # the legs cross the robe near the hem in the turns, a broken dashed line; and below
            # the hem they can't hide a sleeve. Not hiding anything, they let the hem's line cross them
            o.lineart.usage = "EXCLUDE"
        elif o.name == "J_robe":
            o.lineart.usage = "FORCE_INTERSECTION"  # meets the sleeves, which draw no lines of their own
        elif o.name.startswith(SLEEVES):
            o.lineart.usage = "NO_INTERSECTION"  # so not where the two tubes meet at the elbow
        else:
            o.lineart.usage = "OCCLUSION_ONLY"
        if o.name.startswith(MARKED):
            marks_off_shells(o)
    mask_collection(fig_coll, "robe", ("J_robe",))
    mask_collection(fig_coll, "sleeves", SLEEVES)
    mask_collection(fig_coll, "hands", HANDS)
    gp = bpy.data.grease_pencils.new("InnerLines")
    obj = bpy.data.objects.new("InnerLines", gp)
    coll.objects.link(obj)
    # Line Art already hides each line behind the parts in front of it, so draw its lines over the
    # render: where a knee pokes through the robe in the turns, the render's own depth test cut the
    # hem's line short behind it
    obj.show_in_front = True
    # the outline's weight at his distance from the camera, in world units. Measured on the renders, a
    # Line Art stroke comes out as wide as its radius
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    depth = (rig.matrix_world.translation + Vector((0, 0, 1.0)) - cam.matrix_world.translation).dot(fwd)
    world_px = 2 * depth * (SENSOR / 2 / LENS) / RES_X
    line_pass(obj, "LineArt", "Lines", LINE["robe"], fig_coll, OUTLINE_PX * world_px, ("robe", "sleeves"),
              edge_marks=True)
    line_pass(obj, "LineArtHands", "Hands", LINE["skin"], fig_coll, OUTLINE_PX * world_px, ("robe", "hands"),
              cache=True)
    drop_short_strokes(obj, MIN_STROKE_PX * world_px)


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
    # flat fills and no long gradients that could band: dithering would only sprinkle +-1 noise over
    # every colour, which makes the GIF and WebP bigger
    scene.render.dither_intensity = 0.0
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
    contact_shadow(rig, fig_coll)
    feet = on_plane(cam, *LAYOUT["figure"]["feet"], 0.0)
    rig.location = (feet.x, feet.y, 0.0)
    jesus.animate(rig)

    add_outlines(cam)
    bpy.context.scene.frame_set(1)
    if INNER_LINES:
        inner_lines(cam, rig, fig_coll, set_coll)
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
