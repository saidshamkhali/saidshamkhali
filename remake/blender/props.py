"""Prop builders. Each makes a prop standing on z=0, facing -Y, about 1 unit tall,
under a root empty, and keys its own loop animation.

The animation follows reference/prop_tracks.json: each prop's state in every frame of the
original (mouth open, bell tilt, wing and toast, clock lean, worm loop), measured by
reference/build_reference.py, so every prop moves drawing for drawing with the GIF. A prop
without a track falls back to a regular cycle (LAYOUT["cycles_s"], offset by its phase)."""
import json
import math
import os

from kit import (LAYOUT, LOOP, REMAKE, SOFT, SRC_FRAMES, add_shape, bake, blobs, box, constant, cycles_per_loop, cylinder, empty, hitch,
                 inflate, keep_world, lathe, mat, saw, slab, smooth_outline, sphere, step_frames, sweep, toon, torus, unrle,
                 wave)

# Cartoon timing, like the figure (jesus.STEPPED): the props are keyed once per source frame
# and hold each pose, as the 10 fps original does. False = keyed on every frame, smooth, as
# in the soft look.
STEPPED = not SOFT


def animate(obj, path, index, fn):
    bake(obj, path, index, fn, step_frames() if STEPPED else None)


def animate_value(owner, prop, fn):
    """Key a single value (e.g. a shape key's) on the same frames as animate()."""
    for f in step_frames() if STEPPED else range(1, LOOP + 2):
        setattr(owner, prop, fn((f - 1) / LOOP))
        owner.keyframe_insert(prop, frame=f)


TRACKS_FILE = os.path.join(REMAKE, "reference", "prop_tracks.json")


def load_tracks():
    if not os.path.exists(TRACKS_FILE):
        return {}
    with open(TRACKS_FILE, encoding="utf-8") as f:
        return json.load(f)


def track(root, name, fallback):
    """The prop's measured state as a function of t (0..1 over the loop), linear between
    source frames; fallback(t) when there is no measurement for this prop."""
    vals = load_tracks().get(root.name, {}).get(name)
    if not vals:
        return fallback
    n = len(vals)

    def f(t):
        x = (t * n) % n
        k = int(x)
        return vals[k] + (vals[(k + 1) % n] - vals[k]) * (x - k)
    return f

# Extra yaw per prop type, in degrees on top of facing the camera: three-quarter views like the source.
TURN = {"toaster": -56.0, "lips": 0.0}

# Toaster wing in (span, chord): a long flat blade like the source's, rounded tip, the
# trailing edge cut into three shallow feathers.
WING = [(0.0, 0.1), (0.28, 0.125), (0.58, 0.115), (0.8, 0.08), (0.92, 0.025), (0.84, -0.035),
        (0.72, -0.015), (0.64, -0.07), (0.5, -0.035), (0.42, -0.09), (0.28, -0.055), (0.17, -0.1),
        (0.03, -0.07)]
# Slice of bread in (length, height): straight sides, a domed top with bulging shoulders.
BREAD = [(-0.2, 0.0), (0.2, 0.0), (0.205, 0.28), (0.245, 0.34), (0.24, 0.4), (0.17, 0.45),
         (0.0, 0.465), (-0.17, 0.45), (-0.24, 0.4), (-0.245, 0.34), (-0.205, 0.28)]


def build_toaster(root, coll, phase):
    """A rounded chrome toaster, long side along Y with the lever on the front end, two
    slices peeking out of the slots, and a flat wing beating up and down. Turned three-quarter
    (TYPE_TURN) like the source, so the wing reaches out to the right; as in the source, the far
    wing isn't shown."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["toaster"])
    hover = empty(root.name + "_hover", coll, parent=root)
    parts = [
        box("body", coll, mat("metal"), (0, 0, 0.4), (0.54, 0.95, 0.66), bevel=0.13),
        box("lever_slot", coll, mat("slot"), (0, -0.476, 0.4), (0.11, 0.02, 0.4), bevel=0.02, outline=False),
        box("lever", coll, mat("black"), (0, -0.5, 0.53), (0.15, 0.07, 0.06), bevel=0.02),
    ]
    for x in (-0.1, 0.1):
        parts.append(box("slot", coll, mat("slot"), (x, 0, 0.726), (0.075, 0.6, 0.02), outline=False))
    toasts = [slab("toast", coll, mat("toast", 0.8), smooth_outline(BREAD, 40), 0.055, plane="YZ",
                   offset=x, bevel=0.012) for x in (-0.1, 0.1)]
    for t_ in toasts:
        t_.location.z = 0.3
    wings = []
    for side in (1,):
        # the wing is drawn flat in the picture plane, pointing right, whichever way the toaster
        # turns: its pivot undoes the toaster's turn, and it flaps about the line of sight
        pivot = empty(f"{root.name}_wing", coll, loc=(0.26 * side, 0.28, 0.5))
        pivot.rotation_euler.z = math.radians(-TURN["toaster"])
        outline = [(s * side, -h) for s, h in smooth_outline(WING, 64)][::-1]  # feathers trail
        outline = [(a * 0.64, b * 1.5) for a, b in outline]  # the source's wing is short and broad
        w = slab("wing", coll, mat("white", 0.8), outline, 0.03, plane="XZ", offset=0.0, bevel=0.01)
        w.location = (0.24 * side, 0.28, 0.5)
        w.rotation_euler.x = math.radians(-14)  # broadside to the camera, top tipped back a little
        w.rotation_euler.z = math.radians(-TURN["toaster"])
        wings.append((pivot, w, side))
    for p in parts + toasts:
        keep_world(p, hover)
    for pivot, w, _ in wings:
        keep_world(pivot, hover)
        keep_world(w, pivot)
    for p in parts + toasts + [w for _, w, _ in wings]:
        p.name = f"{root.name}_{p.name}"
    wing = track(root, "wing", lambda t: 0.5 + 0.5 * wave(t, c * 2, phase))      # 0 down .. 1 up
    toast = track(root, "toast", lambda t: max(0.0, wave(t, c, phase + 0.1)))    # 0 in .. 1 popped up
    hover.location.z = 0.18
    animate(hover, "location", 2, lambda t: 0.18 - 0.04 * (wing(t) - 0.5))  # the body dips as the wing beats up
    for t_ in toasts:
        z0 = t_.location.z
        animate(t_, "location", 2, lambda t, z0=z0: z0 + 0.1 * toast(t))
    for pivot, _, side in wings:  # tip up = -Y rotation on the right
        animate(pivot, "rotation_euler", 1, lambda t, side=side: side * math.radians(-6 - 36 * (2 * wing(t) - 1)))


def build_clock(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["alarm_clock"])
    rattle = empty(root.name + "_rattle", coll, parent=root)
    parts = [
        # a thin grey case round a big pale face, like the source
        cylinder("body", coll, mat("metal"), (0, 0, 0.5), 0.42, 0.22, rot=(math.pi / 2, 0, 0)),
        cylinder("face", coll, mat("clockface", 0.85), (0, -0.11, 0.5), 0.385, 0.02, rot=(math.pi / 2, 0, 0)),
        cylinder("pin", coll, mat("black"), (0, -0.133, 0.5), 0.032, 0.02, rot=(math.pi / 2, 0, 0), outline=False),
        box("hammer", coll, mat("clock"), (0, 0, 0.97), (0.05, 0.05, 0.14)),
        sphere("chime_l", coll, mat("gold"), (-0.28, 0, 0.9), scale=(0.125, 0.125, 0.08), rot=(0, math.radians(-38), 0)),
        sphere("chime_r", coll, mat("gold"), (0.28, 0, 0.9), scale=(0.125, 0.125, 0.08), rot=(0, math.radians(38), 0)),
        cylinder("leg_l", coll, mat("clock"), (-0.25, 0, 0.08), 0.05, 0.16, rot=(0, math.radians(-25), 0)),
        cylinder("leg_r", coll, mat("clock"), (0.25, 0, 0.08), 0.05, 0.16, rot=(0, math.radians(25), 0)),
    ]
    if SOFT:  # close up, a real clock: a ring of hour marks, the quarters bolder, and a glass dome
        for k in range(12):
            a = math.radians(30 * k)
            big = k % 3 == 0
            r = 0.315 if big else 0.325
            parts.append(box(f"mark{k}", coll, mat("black"), (r * math.sin(a), -0.123, 0.5 + r * math.cos(a)),
                             (0.024 if big else 0.014, 0.008, 0.07 if big else 0.045), rot=(0, a, 0), outline=False))
        parts.append(torus("bezel", coll, mat("metal"), (0, -0.115, 0.5), 0.395, 0.026,
                           rot=(math.pi / 2, 0, 0), outline=False))
    # long hands from the centre (0, 0.5): hour points to 12, minute to 7; they rattle too
    centre = (0, -0.128, 0.5)
    hands = []
    for name, size, angle in (("hour", (0.045, 0.01, 0.26), 0), ("minute", (0.035, 0.01, 0.34), 210)):
        pivot = empty(f"{root.name}_{name}_pivot", coll, loc=centre)
        hand = box(name, coll, mat("black"), (0, centre[1], centre[2] + size[2] / 2 - 0.01), size, outline=False)
        keep_world(hand, pivot)
        pivot.rotation_euler.y = math.radians(angle)
        hands.append((pivot, angle))
        parts.append(hand)
    for p in parts:
        if p.parent is None:
            keep_world(p, rattle)
        p.name = f"{root.name}_{p.name}"
    for pivot, _ in hands:
        keep_world(pivot, rattle)

    def shake(t):  # -1 / +1: a fast shimmy, or a flip on every held frame when stepped
        if STEPPED:
            return 1.0 if round(t * SRC_FRAMES) % 2 else -1.0
        return wave(t, c * 6, phase)

    def env(t):  # rattle for the first half of each cycle
        return 1.0 if saw(t, c, phase) < 0.5 else 0.0
    lean = track(root, "lean", lambda t: env(t) * shake(t))  # -1 top to the left .. 1 to the right
    animate(rattle, "rotation_euler", 1, lambda t: math.radians(12) * lean(t))
    animate(rattle, "location", 2, lambda t: 0.05 * abs(lean(t)))
    for (pivot, angle), swing in zip(hands, (-14, 22)):  # the hands jolt against the case
        animate(pivot, "rotation_euler", 1, lambda t, a=angle, w=swing: math.radians(a + w * lean(t)))


def build_bell(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["bell"])
    # it rocks about its middle, so the handle tips one way as the body swings the other, as drawn
    pivot = empty(root.name + "_swing", coll, loc=(0, 0, 0.6), parent=root)
    # a narrow hand bell: hollow body (the profile runs up the inside, round the flared
    # lip, then down the outside) under a big turned wooden handle, as in the source
    body = lathe("bell", coll, mat("gold"),
                 [(0.0, 0.42), (0.1, 0.41), (0.15, 0.3), (0.2, 0.12), (0.27, 0.03),
                  (0.3, 0.0), (0.325, 0.018), (0.315, 0.05), (0.25, 0.1), (0.2, 0.22),
                  (0.18, 0.36), (0.16, 0.45), (0.11, 0.51), (0.05, 0.535), (0.0, 0.54)], loc=(0, 0, 0.12))
    clapper = sphere("clapper", coll, mat("clock"), (0, 0, 0.16), r=0.06)
    handle = lathe("handle", coll, mat("black"),
                   [(0.0, 0.5), (0.07, 0.5), (0.05, 0.56), (0.045, 0.66), (0.06, 0.74), (0.105, 0.82),
                    (0.125, 0.9), (0.115, 0.98), (0.075, 1.03), (0.0, 1.045)], loc=(0, 0, 0.12))
    for p in (body, clapper, handle):
        keep_world(p, pivot)
        p.name = f"{root.name}_{p.name}"
    tilt = track(root, "tilt", lambda t: wave(t, c, phase))  # -1 body to the left .. 1 to the right
    animate(pivot, "rotation_euler", 1, lambda t: math.radians(-26) * tilt(t))


# The open mouth, as the source draws it: side-on, facing screen-left, one thick lip line
# bent into a C (upper lip, the corner at the back, lower lip) round a dark mouth. Centre
# line in (x, z) from the upper lip's tip round to the lower lip's, half open and wide open.
MOUTH_HALF = [(-0.4, 0.52), (-0.15, 0.555), (0.12, 0.56), (0.3, 0.53), (0.38, 0.44), (0.36, 0.34),
              (0.24, 0.27), (0.0, 0.25), (-0.24, 0.27)]
MOUTH_WIDE = [(-0.3, 0.66), (-0.09, 0.71), (0.1, 0.72), (0.25, 0.66), (0.3, 0.5), (0.28, 0.3),
              (0.18, 0.14), (0.0, 0.1), (-0.16, 0.15)]
MOUTH_R = [0.055, 0.07, 0.072, 0.065, 0.05, 0.05, 0.065, 0.072, 0.058]


DRAWINGS_FILE = os.path.join(REMAKE, "reference", "prop_drawings.json")
DRAWING_PX = 1 / 40  # units per GIF pixel for traced drawings (place_prop scales the prop to its box anyway)
# how a traced part is inflated: (depth behind the drawing's front, radius, shadow). The ink (the
# whole drawing, its dark line-art) sits just behind the coloured parts and shows between them,
# so it draws the lines: only it gets a (thin) outline, round the whole drawing.
INK = (0.05, 0.03, 0.8)
COLOUR = (0.0, 0.07, 0.72)
INK_OUTLINE_PX = 0.8


def load_drawings():
    if not os.path.exists(DRAWINGS_FILE):
        return {}
    with open(DRAWINGS_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_traced(root, coll, data, spec):
    """The prop's own drawings off the GIF (reference/prop_drawings.json), each coloured part
    inflated into a soft 3D shape in the GIF's own colour, and on every frame only the drawing
    the GIF shows. The drawings keep their places in the frame, so the prop moves between them
    as drawn: the bells swing, the wings beat, the clocks jolt, drawing for drawing."""
    cell = DRAWING_PX / data["cell"]
    w, h = spec["size"]
    mats = {name: toon(f"{root.name}_{name}", hexc, (INK if name == "ink" else COLOUR)[2])
            for name, hexc in spec["palette"].items()}
    drawings = []
    for i, dr in enumerate(spec["drawings"]):
        parts = []
        for name, runs in dr["parts"].items():
            depth, radius, _ = INK if name == "ink" else COLOUR
            o = inflate(f"{root.name}_d{i}_{name}", coll, mats[name], unrle(runs, w, h), cell, depth=depth, radius=radius,
                        outline=name == "ink")
            if name == "ink":
                o["outline_px"] = INK_OUTLINE_PX
            o.location.x = -w * cell / 2
            keep_world(o, root)
            parts.append(o)
        drawings.append(parts)
    shown = spec["frame_drawing"]

    def drawing(t):
        return shown[round(t * SRC_FRAMES) % SRC_FRAMES]
    for i, parts in enumerate(drawings):
        for o in parts:
            animate_value(o, "hide_render", lambda t, i=i: drawing(t) != i)
            animate_value(o, "hide_viewport", lambda t, i=i: drawing(t) != i)
    root["face_camera"] = True  # flat drawings: face the camera square on, its tilt included
    root["fit_axis"] = "x"      # the traced width is the drawing's own; heights include the line-art


def traced_or(build):
    """Build the prop from its traced drawings when reference/prop_drawings.json has them,
    otherwise from scratch with `build`."""
    def run(root, coll, phase):
        spec = None if SOFT else load_drawings().get("props", {}).get(root.name)  # the soft look models them
        if spec:
            build_traced(root, coll, load_drawings(), spec)
        else:
            build(root, coll, phase)
    run.__doc__ = build.__doc__
    return run


def build_lips(root, coll, phase):
    """A shouting mouth, two drawings like the source's: closed, fat lips facing the camera;
    open, the mouth seen side-on facing screen-left, a C of lip round a dark mouth, with a row
    of teeth under the upper lip and a tongue on the lower one when it's wide open."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["lips"])
    half = 0.43

    def arc(z, depth, n=7):  # a U round the front of the mouth, corners at the back
        pts = []
        for i in range(n):
            a = math.pi * i / (n - 1)
            pts.append((-half * math.cos(a), 0.07 - 0.28 * depth * math.sin(a) ** 0.8, z + 0.012 * math.sin(a)))
        return pts

    # closed: lens-shaped lips, thin at the corners, full in the middle; a cupid's bow on top
    front = [sweep(name, coll, mat("lips"), arc(z, depth), radii, n=36, ring=18)
             for name, z, depth, radii in (("upper", 0.455, 0.9, [0.01, 0.045, 0.085, 0.068, 0.085, 0.045, 0.01]),
                                           ("lower", 0.315, 0.8, [0.01, 0.05, 0.1, 0.112, 0.1, 0.05, 0.01]))]

    # open: the C of lip and the dark mouth inside it, each with a "wide" shape key
    def c_line(pts):
        return [(x, 0.0, z) for x, z in pts]

    lip = sweep("side_lip", coll, mat("lips"), c_line(MOUTH_HALF), MOUTH_R, n=40, ring=18, squash=0.7, up=(0, -1, 0))
    add_shape(lip, sweep("side_lip", coll, mat("lips"), c_line(MOUTH_WIDE), MOUTH_R, n=40, ring=18, squash=0.7,
                         up=(0, -1, 0)), "wide")
    inside = slab("mouth", coll, mat("mouth", 0.8), smooth_outline(MOUTH_HALF, 48), 0.02, offset=0.045, outline=False)
    add_shape(inside, slab("mouth", coll, mat("mouth", 0.8), smooth_outline(MOUTH_WIDE, 48), 0.02, offset=0.045,
                           outline=False), "wide")
    teeth = []  # a row of square teeth hanging from the upper lip
    for k, (x, dz) in enumerate(((-0.17, 0.0), (-0.06, 0.006), (0.05, 0.006), (0.16, -0.01))):
        teeth.append(box(f"tooth{k}", coll, mat("white", 0.85), (x, 0.012, 0.715 + dz), (0.1, 0.03, 0.11), bevel=0.018))
    tongue = sphere("tongue", coll, mat("tongue"), (0.02, 0.02, 0.12), scale=(0.21, 0.03, 0.1))
    side = [lip, inside, tongue] + teeth
    for p in front + side:
        keep_world(p, root)
        p.name = f"{root.name}_{p.name}"

    def shout(t):  # 0 closed .. 1 open, a quick shout each cycle
        x = saw(t, c, phase)
        return math.sin(math.pi * min(1.0, x / 0.65)) ** 0.6 if x < 0.65 else 0.0
    opening = track(root, "open", shout)

    # the track: 0 closed, 0.35 half open, 0.55..1 shouting (teeth showing), by how wide
    def wide(t):
        return min(1.0, max(0.0, (opening(t) - 0.35) / 0.65))

    def is_open(t):
        return opening(t) > 0.15

    def shouting(t):
        return 1.0 if opening(t) >= 0.5 else 0.0

    for p in front:
        animate_value(p, "hide_render", lambda t: is_open(t))
        animate_value(p, "hide_viewport", lambda t: is_open(t))
    for p in side:
        animate_value(p, "hide_render", lambda t: not is_open(t))
        animate_value(p, "hide_viewport", lambda t: not is_open(t))
    for p in (lip, inside):
        animate_value(p.data.shape_keys.key_blocks["wide"], "value", wide)
    def upper(t):  # height of the upper lip's centre line, and of the lower one's
        return 0.557 + (0.715 - 0.557) * wide(t)

    def lower(t):
        return 0.26 + (0.12 - 0.26) * wide(t)

    for tooth in teeth:  # hanging under the upper lip when he shouts, tucked inside it otherwise
        dz = tooth.location.z - 0.715
        animate(tooth, "location", 2, lambda t, dz=dz: upper(t) + dz - 0.075 * shouting(t))
    animate(tongue, "location", 2, lambda t: lower(t) + 0.07 * shouting(t))  # on the lower lip
    animate(tongue, "scale", 2, lambda t: 0.4 + 0.6 * shouting(t))


# The soft look's mouth: fleshy lips round a deep mouth, after the five drawings the original
# flips between. Side-on it's a C facing screen-left (-X): the upper lip juts out past the
# lower one, an overbite, and both are thick, thinning only at the back corner. Centre line
# of the lip band from the upper lip's front, over the top, round the back corner and along
# the bottom to the lower lip's front, half open and shouting.
SOFT_MOUTH_HALF = [(-0.46, 0.6), (-0.2, 0.64), (0.08, 0.64), (0.28, 0.6), (0.4, 0.45), (0.37, 0.3),
                   (0.22, 0.2), (0.0, 0.17), (-0.22, 0.2)]
SOFT_MOUTH_WIDE = [(-0.4, 0.8), (-0.14, 0.86), (0.1, 0.86), (0.28, 0.79), (0.38, 0.5), (0.34, 0.2),
                   (0.2, 0.04), (0.0, 0.0), (-0.18, 0.04)]
SOFT_MOUTH_R = [0.095, 0.12, 0.115, 0.095, 0.065, 0.075, 0.105, 0.12, 0.1]
SOFT_TEETH_X = (-0.33, -0.21, -0.09, 0.03, 0.14)


def closed_lips_soft(coll, half=0.45, z_mid=0.38, nx=48, ring=36):
    """Closed lips seen from the front, one almond body: pointed corners, the upper lip lower
    and dipped in the middle (the cupid's bow), the lower one fuller, and a crease where they
    press together."""
    import bmesh
    import bpy
    from kit import finish
    bm = bmesh.new()
    rings = []
    for i in range(nx + 1):
        u = -0.97 + 1.94 * i / nx                      # across the mouth, corner to corner
        x = u * half
        w = max(0.0, 1 - u * u)
        top = 0.16 * w ** 0.7 * (1 - 0.2 * math.exp(-(u / 0.13) ** 2))  # the bow dips in the middle
        bot = 0.21 * w ** 0.6
        depth = 0.13 * w ** 0.5 + 0.006
        yc = 0.06 - 0.12 * w                            # the middle comes forward, the corners go back
        pts = []
        for j in range(ring):
            a = 2 * math.pi * j / ring
            s, c = math.sin(a), math.cos(a)
            h = top if s >= 0 else bot
            d = depth * (1 - 0.3 * math.exp(-(s / 0.16) ** 2) * max(0.0, c))  # the crease, in front
            pts.append(bm.verts.new((x, yc - d * c, z_mid + h * s)))
        rings.append(pts)
    for a, b in zip(rings, rings[1:]):
        for j in range(ring):
            bm.faces.new((a[j], a[(j + 1) % ring], b[(j + 1) % ring], b[j]))
    for pts, end in ((rings[0], -1), (rings[-1], 1)):  # close each corner on a point
        tip = bm.verts.new((end * half, 0.06, z_mid))
        for j in range(ring):
            f = (pts[j], pts[(j + 1) % ring], tip)
            bm.faces.new(f if end > 0 else f[::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("lips_closed")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("lips_closed", mesh)
    return finish(obj, mat("lips"), coll)


def build_mouth_soft(root, coll, phase):
    """The soft look's shouting mouth, modelled after the original's drawings: closed, fat
    lips seen from the front, a cupid's bow on the upper one; open, the mouth side-on facing
    screen-left: thick lips round a deep, dark mouth, a row of upper teeth along the upper lip
    and a big tongue rising from the lower one as he shouts."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["lips"])
    half = 0.45

    # closed: one almond of lip, and a dark line along the crease where they press together
    front = [closed_lips_soft(coll, half)]
    seam = [(x, 0.06 - 0.12 * max(0.0, 1 - (x / half) ** 2) - (0.13 * max(0.0, 1 - (x / half) ** 2) ** 0.5 + 0.006) * 0.72,
             0.38) for x in (-0.42, -0.3, -0.15, 0.0, 0.15, 0.3, 0.42)]
    front.append(sweep("seam", coll, mat("mouth", 0.8), seam, [0.003, 0.009, 0.012, 0.012, 0.012, 0.009, 0.003],
                       n=40, ring=10))

    # open: the lip band and the mouth inside it, each with a "wide" shape key
    def c_line(pts):
        return [(x, 0.0, z) for x, z in pts]

    lip = sweep("side_lip", coll, mat("lips"), c_line(SOFT_MOUTH_HALF), SOFT_MOUTH_R, n=48, ring=22, squash=0.85,
                up=(0, -1, 0))
    add_shape(lip, sweep("side_lip", coll, mat("lips"), c_line(SOFT_MOUTH_WIDE), SOFT_MOUTH_R, n=48, ring=22,
                         squash=0.85, up=(0, -1, 0)), "wide")
    inside = slab("mouth", coll, mat("mouth", 0.8), smooth_outline(SOFT_MOUTH_HALF, 64), 0.05, offset=0.07,
                  outline=False)
    add_shape(inside, slab("mouth", coll, mat("mouth", 0.8), smooth_outline(SOFT_MOUTH_WIDE, 64), 0.05,
                           offset=0.07, outline=False), "wide")
    # a row of upper teeth, each a little wider than its spacing so the row reads as one band
    # with notches along its edge
    teeth = [box(f"tooth{k}", coll, mat("white", 0.85), (x, -0.01, 0.0), (0.128, 0.075, 0.13), bevel=0.038)
             for k, x in enumerate(SOFT_TEETH_X)]
    # a fat tongue lying in the bottom of the mouth, its tip curling up at the front: the red
    # curl the drawings show under the teeth
    tongue = sweep("tongue", coll, mat("tongue"), [(0.22, 0.04, -0.02), (0.08, 0.02, 0.0), (-0.06, 0.0, 0.05),
                                                    (-0.17, 0.0, 0.14)],
                   [0.1, 0.14, 0.135, 0.095], n=28, ring=20, squash=0.85, up=(0, -1, 0))
    side = [lip, inside, tongue] + teeth
    # the prop is sized by its closed drawing; drawn side-on, the open mouth is narrower than
    # the closed lips (32 x 36 GIF px against 42 wide), so the open parts hang off an empty
    # that scales them down about their middle
    opened = empty(f"{root.name}_open", coll, loc=(-0.05, 0.0, 0.43), parent=root)
    for p in front:
        keep_world(p, root)
    for p in side:
        keep_world(p, opened)
    for p in front + side:
        p.name = f"{root.name}_{p.name}"
    opened.scale = (0.69, 0.8, 0.73)
    # face the camera square on, like the drawings, and size by width: seen from above, the open
    # mouth's height is foreshortened, which made a mouth sized on an open frame come out small
    root["face_camera"] = True
    root["fit_axis"] = "x"
    root["fit_scale"] = 1.08  # the lips' bounding box runs wider than the lips: measured on the renders

    def shout(t):  # 0 closed .. 1 open, a quick shout each cycle
        x = saw(t, c, phase)
        return math.sin(math.pi * min(1.0, x / 0.65)) ** 0.6 if x < 0.65 else 0.0
    opening = track(root, "open", shout)
    drawn = load_tracks().get(root.name, {}).get("open")

    def opening_held(t):
        """The opening as drawn, held for each of the original's frames: the switch between the
        closed and the open mouth keeps the original's beat (a closed drawing lasts a tenth of a
        second) instead of flashing for a single frame at 30 fps."""
        return drawn[int(t * len(drawn) + 1e-6) % len(drawn)] if drawn else shout(t)

    # the track: 0 closed, 0.35 half open, 0.55..1 shouting (teeth showing), by how wide
    def wide(t):
        return min(1.0, max(0.0, (opening(t) - 0.35) / 0.65))

    def is_open(t):
        return opening_held(t) > 0.15

    def line(t, x, upper):
        """Height of the lip band's centre line at x, and its radius there, for this frame."""
        w = wide(t)
        idx = (0, 1, 2, 3) if upper else (8, 7, 6, 5)
        pts = [(SOFT_MOUTH_HALF[i][0] + (SOFT_MOUTH_WIDE[i][0] - SOFT_MOUTH_HALF[i][0]) * w,
                SOFT_MOUTH_HALF[i][1] + (SOFT_MOUTH_WIDE[i][1] - SOFT_MOUTH_HALF[i][1]) * w, SOFT_MOUTH_R[i]) for i in idx]
        for (x0, z0, r0), (x1, z1, r1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                f = (x - x0) / (x1 - x0)
                return z0 + (z1 - z0) * f, r0 + (r1 - r0) * f
        x0, z0, r0 = pts[0] if x < pts[0][0] else pts[-1]
        return z0, r0

    def teeth_show(t):  # the teeth come down from under the upper lip as the mouth opens
        return min(1.0, max(0.0, (opening(t) - 0.42) / 0.2))

    def tongue_show(t):  # the tongue rises as he shouts
        return min(1.0, max(0.0, (opening(t) - 0.5) / 0.35))

    for p in front:
        animate_value(p, "hide_render", lambda t: is_open(t))
        animate_value(p, "hide_viewport", lambda t: is_open(t))
    for p in side:
        animate_value(p, "hide_render", lambda t: not is_open(t))
        animate_value(p, "hide_viewport", lambda t: not is_open(t))
    for p in (lip, inside):
        animate_value(p.data.shape_keys.key_blocks["wide"], "value", wide)
    for tooth, x in zip(teeth, SOFT_TEETH_X):
        def tooth_z(t, x=x):
            z, r = line(t, x, True)
            return z - r * 0.45 - 0.06 * teeth_show(t)
        animate(tooth, "location", 2, tooth_z)
        animate(tooth, "scale", 2, lambda t: 0.35 + 0.65 * teeth_show(t))

    def tongue_z(t):
        z, r = line(t, 0.0, False)
        return z + r * 0.5 + 0.09 * tongue_show(t)
    animate(tongue, "location", 2, tongue_z)
    for axis in range(3):  # none while the mouth is only half open, as drawn
        animate(tongue, "scale", axis, lambda t: max(0.001, tongue_show(t)))


WORM_LENGTH = 1.1
WORM_LOOP = 0.7      # share of the body that curls up into the loop
WORM_CURL = 1.5      # radians the body turns at the loop's sides: an arch with a small hole under it
WORM_SPREAD = 0.2    # cartoon cheat: at the top of the loop the ends pull in less than they should


def worm_curve(a, samples):
    """Centre line of the worm, its body length kept, with the middle curled into a loop by
    a (0 flat .. 1 tall loop). Returns (x, z, slope) at each arc length in samples."""
    loop = WORM_LOOP * WORM_LENGTH
    start = (WORM_LENGTH - loop) / 2
    steps = 400
    ds = WORM_LENGTH / steps
    xs, zs, ths = [0.0], [0.0], [0.0]
    for k in range(steps):
        s = (k + 0.5) * ds
        th = 0.0
        if start < s < start + loop:  # the slope rises, turns over the top and comes back down
            th = a * WORM_CURL * math.sin(2 * math.pi * (s - start) / loop)
        xs.append(xs[-1] + math.cos(th) * ds)
        zs.append(zs[-1] + math.sin(th) * ds)
        ths.append(th)
    mid = xs[steps // 2]
    stretch = 1 + WORM_SPREAD * a
    out = []
    for s in samples:
        k = min(steps, round(s / ds))
        th = ths[min(steps, max(1, k))]
        out.append(((xs[k] - mid) * stretch, zs[k], math.atan2(math.sin(th), stretch * math.cos(th))))
    return out


def build_worm(root, coll, phase):
    """Inchworm, as in the source: it stays put while the middle of its body curls up into a
    tight loop and flattens out again, about once a second. A row of fat overlapping ring
    segments, each one tilted along the body, with a dark band between each two (the stripes)."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["worm"])
    n = 13
    spacing = WORM_LENGTH / (n - 1)
    segs = []
    for i in range(n):
        u = i / (n - 1)
        r = 0.1 + 0.02 * math.sin(math.pi * min(1.0, u * 1.15)) ** 0.6 + (0.015 if i == n - 1 else 0.0)  # chunky, as drawn
        sx = max(0.7, 1.3 * spacing / (2 * r))  # fat rings that overlap, even stretched
        seg = sphere(f"{root.name}_seg{i}", coll, mat("worm"), (-WORM_LENGTH / 2 + WORM_LENGTH * u, 0, r),
                     scale=(sx if i < n - 1 else 1.1, 1.0, 1.0), r=r)
        keep_world(seg, root)
        segs.append((seg, u, r))
    bands = []
    for i in range(n - 1):  # thin dark discs between the segments, across the body
        u = (i + 0.5) / (n - 1)
        r = (segs[i][2] + segs[i + 1][2]) / 2 * 1.04
        band = cylinder(f"{root.name}_band{i}", coll, mat("black"), (-WORM_LENGTH / 2 + WORM_LENGTH * u, 0, r), r, 0.03,
                        rot=(0, math.pi / 2, 0), outline=False)
        keep_world(band, root)
        bands.append((band, u, r))
    if SOFT:  # close up, a face: two little eyes on the head end, looking out at us
        head, _, hr = segs[-1]
        hx = WORM_LENGTH / 2
        for k, dx in enumerate((-0.02, 0.06)):
            eye = sphere(f"{root.name}_eye{k}", coll, mat("white", 0.93), (hx + dx, -0.085, hr + 0.075), r=0.042)
            pupil = sphere(f"{root.name}_pupil{k}", coll, mat("black"), (hx + dx + 0.008, -0.12, hr + 0.07), r=0.02)
            keep_world(eye, head)
            keep_world(pupil, head)

    def loop(t):  # flat for a moment, then up into the loop and back down
        x = saw(t, c, phase)
        return (0.5 - 0.5 * math.cos(2 * math.pi * x)) ** 1.3
    curl = track(root, "curl", loop)

    cache = {}

    def pose(t):
        if t not in cache:
            cache[t] = worm_curve(curl(t), [u * WORM_LENGTH for _, u, _ in segs + bands])
        return cache[t]

    for i, (part, _, r) in enumerate(segs + bands):
        turn = math.pi / 2 if i >= len(segs) else 0.0  # the bands' discs stand across the body
        animate(part, "location", 0, lambda t, i=i: pose(t)[i][0])
        animate(part, "location", 2, lambda t, i=i, r=r: pose(t)[i][1] + r)
        animate(part, "rotation_euler", 1, lambda t, i=i, turn=turn: turn - pose(t)[i][2])
    root["fit_axis"] = "x"  # a flat worm's box is a few pixels tall: size it by its length
    if not load_tracks().get(root.name):  # untracked: size it in its box when flat, whatever its phase
        root["fit_frame"] = 1 + ((-phase) % 1.0) / c * (len(step_frames()) - 1)


def held(build):
    """Run a builder, then hold every key it made (when STEPPED)."""
    def run(root, coll, phase):
        build(root, coll, phase)
        if STEPPED:
            for obj in coll.objects:
                constant(obj)
                hitch(obj)
                keys = obj.data.shape_keys if obj.type == "MESH" else None
                if keys is not None and keys.animation_data:
                    constant(keys)
                    hitch(keys)
    return run


BUILDERS = {
    "toaster": held(traced_or(build_toaster)),
    "alarm_clock": held(traced_or(build_clock)),
    "bell": held(traced_or(build_bell)),
    "lips": held(build_mouth_soft if SOFT else traced_or(build_lips)),
    "worm": held(traced_or(build_worm)),
}
