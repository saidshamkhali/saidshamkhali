"""Prop builders. Each makes a prop standing on z=0, facing -Y, about 1 unit tall,
under a root empty, and keys its own loop animation.

The animation follows reference/prop_tracks.json: each prop's state in every frame of the
original (mouth open, bell tilt, wing and toast, clock lean, worm loop), measured by
reference/build_reference.py, so every prop moves drawing for drawing with the GIF. A prop
without a track falls back to a regular cycle (LAYOUT["cycles_s"], offset by its phase)."""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

from kit import (LAYOUT, LOOP, REMAKE, SRC_FRAMES, add_shape, bake, box, constant, cycles_per_loop, cylinder, empty, finish,
                 hitch, inflate, keep_world, lathe, mat, saw, slab, smooth_outline, sphere, step_frames, sweep, toon, unrle,
                 wave)

# Cartoon timing, like the figure (jesus.STEPPED): the props are keyed once per source frame
# and hold each pose, as the 10 fps original does. False = keyed on every frame, smooth.
STEPPED = True


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
DRAWING_PX = 1 / 40  # units per GIF pixel for traced drawings (place_prop scales them to the frame anyway)
# how a traced part is inflated: (depth behind the drawing's front, radius, shadow). The ink (the
# whole drawing, its dark line-art) sits just behind the coloured parts and shows between them,
# so it draws the lines: only it gets a (thin) outline, round the whole drawing. The drawings'
# colours are flat, so the shade is barely darker than the light: a deeper one lays a dark
# crescent along one side of every part, which reads as dirt and as a heavier line.
INK = (0.05, 0.03, 0.95)
COLOUR = (0.0, 0.07, 0.92)
# a toaster's crust is the toast's whole patch, between the ink and the toast, so its dark brown
# shows round the toast in the slot as the ink shows round the colours
LAYERS = {"ink": INK, "crust": (0.01, 0.008, 0.92)}
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
    mats = {name: toon(f"{root.name}_{name}", hexc, LAYERS.get(name, COLOUR)[2])
            for name, hexc in spec["palette"].items()}
    drawings = []
    for i, dr in enumerate(spec["drawings"]):
        parts = []
        for name, runs in dr["parts"].items():
            depth, radius, _ = LAYERS.get(name, COLOUR)
            o = inflate(f"{root.name}_d{i}_{name}", coll, mats[name], unrle(runs, w, h), cell, depth=depth, radius=radius,
                        outline=name == "ink")
            if name == "ink":
                o["outline_px"] = INK_OUTLINE_PX
            else:
                # a modifier that moves nothing, after the subdivision: with the Subdivision last in
                # its stack Blender subdivides on the GPU, except on the first render after the file
                # loads, so that frame's rims came out a shade off the rest and a held frame didn't
                # hold. A modifier after it keeps the subdivision on the CPU on every frame. (It
                # displaces by strength * (1 - mid level) = 0; at strength 0 Blender would skip it.)
                hold = o.modifiers.new("Hold", "DISPLACE")
                hold.strength, hold.mid_level = 1.0, 1.0
            o.location.x, o.location.z = -w * cell / 2, -h * cell / 2  # the grid's centre on the root
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
    # flat drawings: build_scene.place_drawing puts the grid back where it was traced, parallel to
    # the image plane, from where it lay in the GIF (its top-left corner and size, in GIF pixels)
    # and the units one GIF pixel covers here
    root["face_camera"] = True
    root["grid_origin_px"] = spec["origin"]
    root["grid_px"] = (w / data["cell"], h / data["cell"])
    root["px_units"] = DRAWING_PX


def traced_or(build):
    """Build the prop from its traced drawings when reference/prop_drawings.json has them,
    otherwise from scratch with `build`."""
    def run(root, coll, phase):
        spec = load_drawings().get("props", {}).get(root.name)
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


WORM_LENGTH = 1.1
WORM_LOOP = (0.45, 0.85)  # share of the body that curls up into the loop, starting out and curled all
                          # the way: the drawings' worm first humps its middle, then arches most of itself
WORM_CURL = 1.85     # radians the body turns at the loop's sides: past upright, so curled all the way
                     # the sides lean out into the drawings' Omega, with a hole under the arch
WORM_LIFT = 0.25     # cartoon cheat: the loop stands a little taller than the body allows
# How long the worm is drawn, end to end, against flat, by curl: measured on all three worms in
# the upscaled frames. Half curled, the ends pull in less than the body's length would make them
# (a steep arch on long flat ends); curled all the way they pull in much less (so the Omega keeps
# its hole). A worm that pulled in as its body bends was a broad low hump half curled.
WORM_LENGTHS = ((0.0, 1.0), (0.35, 0.99), (0.5, 0.935), (0.7, 0.915), (0.9, 0.905), (1.0, 0.78))
WORM_R = 0.09        # one smooth tube, as drawn
# the body is built at these curls and blends between them; closer at the top, where an arch
# turns into the Omega and the drawn length falls off fast (WORM_LENGTHS)
WORM_CURLS = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)
WORM_STRIPE = "#5A5464"  # mid-dark slate: the drawings' worms have no black in them
WORM_STRIPE_W = 0.035    # about a GIF pixel
# where the stripes sit along the body (share of its length) and how far each one leans off
# square to it, in degrees: irregular, like the drawn ones
WORM_STRIPES = [(0.1, 12), (0.2, -8), (0.3, 18), (0.4, 4), (0.5, -14), (0.6, 10), (0.7, -6), (0.8, 16), (0.9, -10)]


def worm_curve(a, samples):
    """Centre line of the worm, with the middle curled into a loop by a (0 flat .. 1 tall
    loop), stretched end to end to the length the drawings give that curl (WORM_LENGTHS).
    Returns (x, z, slope) at each arc length in samples."""
    loop = (WORM_LOOP[0] + (WORM_LOOP[1] - WORM_LOOP[0]) * a) * WORM_LENGTH
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
    # end to end, the round ends included
    length = next(l0 + (l1 - l0) * (a - a0) / (a1 - a0)
                  for (a0, l0), (a1, l1) in zip(WORM_LENGTHS, WORM_LENGTHS[1:]) if a <= a1)
    stretch = ((WORM_LENGTH + 2 * WORM_R) * length - 2 * WORM_R) / (max(xs) - min(xs))
    lift = 1 + WORM_LIFT * a
    out = []
    for s in samples:
        k = min(steps, round(s / ds))
        th = ths[min(steps, max(1, k))]
        out.append(((xs[k] - mid) * stretch, zs[k] * lift, math.atan2(lift * math.sin(th), stretch * math.cos(th))))
    return out


def worm_stripes(name, coll, material, centre):
    """The stripes round a worm whose centre line runs through `centre` (points evenly spaced
    along it): short tubes just proud of the body, each leaning a little off square to it."""
    bm = bmesh.new()
    n, ring = len(centre) - 1, 16
    for u, lean in WORM_STRIPES:
        k = min(n - 1, int(u * n))
        c = centre[k].lerp(centre[k + 1], u * n - k)
        axis = Matrix.Rotation(math.radians(lean), 3, "Y") @ (centre[k + 1] - centre[k]).normalized()
        side = Vector((0, 1, 0))
        up = axis.cross(side).normalized()
        ends = [[bm.verts.new(c + axis * d + (side * math.cos(2 * math.pi * j / ring) + up * math.sin(2 * math.pi * j / ring))
                              * WORM_R * 1.04) for j in range(ring)] for d in (-WORM_STRIPE_W / 2, WORM_STRIPE_W / 2)]
        for j in range(ring):
            bm.faces.new((ends[0][j], ends[0][(j + 1) % ring], ends[1][(j + 1) % ring], ends[1][j]))
        bm.faces.new(ends[0])
        bm.faces.new(ends[1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return finish(obj, material, coll, outline=False)


def build_worm(root, coll, phase):
    """Inchworm, as in the source: it stays put while the middle of its body curls up into a
    tall arch and flattens out again, about once a second. One smooth tube with round ends,
    ringed by slate stripes; both are built at each of WORM_CURLS and blend between them (shape
    keys), following the curl measured off the GIF."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["worm"])
    samples = [WORM_LENGTH * i / 32 for i in range(33)]

    def centre(a):
        return [Vector((x, 0.0, z + WORM_R)) for x, z, _ in worm_curve(a, samples)]

    def body(a):  # up: the rings face the camera, so they don't twist as the body bends
        return sweep(f"{root.name}_body", coll, mat("worm"), centre(a), [WORM_R], n=64, ring=16, up=(0, -1, 0))

    stripe_mat = toon(f"{root.name}_stripe", WORM_STRIPE, 0.85)
    parts = [body(0.0), worm_stripes(f"{root.name}_stripes", coll, stripe_mat, centre(0.0))]
    for k, a in enumerate(WORM_CURLS[1:], 1):
        add_shape(parts[0], body(a), f"curl{k}")
        add_shape(parts[1], worm_stripes(f"{root.name}_stripes", coll, stripe_mat, centre(a)), f"curl{k}")
    parts[0]["outline_even"] = False  # an even outline spikes where the arch bends the tube tight
    for p in parts:
        keep_world(p, root)

    def loop(t):  # flat for a moment, then up into the loop and back down
        x = saw(t, c, phase)
        return (0.5 - 0.5 * math.cos(2 * math.pi * x)) ** 1.3
    curl = track(root, "curl", loop)

    def weight(c, k):  # the k-th built curl's share of a body curled c: 1 at its curl, 0 at its neighbours'
        lo, a = WORM_CURLS[k - 1], WORM_CURLS[k]
        if c <= a:
            return max(0.0, (c - lo) / (a - lo))
        return max(0.0, (WORM_CURLS[k + 1] - c) / (WORM_CURLS[k + 1] - a)) if k + 1 < len(WORM_CURLS) else 1.0
    for p in parts:  # each built curl weighs in as the curl passes it, so the body blends from one to the next
        for k in range(1, len(WORM_CURLS)):
            animate_value(p.data.shape_keys.key_blocks[f"curl{k}"], "value", lambda t, k=k: weight(curl(t), k))
    root["fit_axis"] = "x"  # a flat worm's box is a few pixels tall: size it by its length
    root["level"] = True    # along the camera's horizontal: turned to face the camera, one off to the side slants
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
    "lips": held(traced_or(build_lips)),
    "worm": held(traced_or(build_worm)),
}
