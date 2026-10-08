"""Prop builders. Each makes a prop standing on z=0, facing -Y, about 1 unit tall,
under a root empty, and keys its own loop animation.

The animation follows reference/prop_tracks.json: each prop's state in every frame of the
original (mouth open, bell tilt, wing and toast, clock lean, worm loop), measured by
reference/build_reference.py, so every prop moves drawing for drawing with the GIF. A prop
without a track falls back to a regular cycle (LAYOUT["cycles_s"], offset by its phase)."""
import json
import math
import os

from kit import (LAYOUT, LOOP, REMAKE, SRC_FRAMES, add_shape, bake, box, constant, cycles_per_loop, cylinder, empty, hitch,
                 keep_world, lathe, mat, saw, slab, smooth_outline, sphere, step_frames, sweep, wave)

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
TURN = {"toaster": -56.0, "lips": -8.0}

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
    tight loop and flattens out again, about once a second. A row of overlapping ring
    segments (their outlines draw the rings), each one tilted along the body."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["worm"])
    n = 13
    spacing = WORM_LENGTH / (n - 1)
    segs = []
    for i in range(n):
        u = i / (n - 1)
        r = 0.052 + 0.014 * math.sin(math.pi * min(1.0, u * 1.15)) ** 0.6 + (0.01 if i == n - 1 else 0.0)
        sx = max(0.7, 1.3 * spacing / (2 * r))  # fat rings that overlap, even stretched
        seg = sphere(f"{root.name}_seg{i}", coll, mat("worm"), (-WORM_LENGTH / 2 + WORM_LENGTH * u, 0, r),
                     scale=(sx if i < n - 1 else 1.1, 1.0, 1.0), r=r)
        keep_world(seg, root)
        segs.append((seg, u, r))

    def loop(t):  # flat for a moment, then up into the loop and back down
        x = saw(t, c, phase)
        return (0.5 - 0.5 * math.cos(2 * math.pi * x)) ** 1.3
    curl = track(root, "curl", loop)

    cache = {}

    def pose(t):
        if t not in cache:
            cache[t] = worm_curve(curl(t), [u * WORM_LENGTH for _, u, _ in segs])
        return cache[t]

    for i, (seg, _, r) in enumerate(segs):
        animate(seg, "location", 0, lambda t, i=i: pose(t)[i][0])
        animate(seg, "location", 2, lambda t, i=i, r=r: pose(t)[i][1] + r)
        animate(seg, "rotation_euler", 1, lambda t, i=i: -pose(t)[i][2])
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
    "toaster": held(build_toaster),
    "alarm_clock": held(build_clock),
    "bell": held(build_bell),
    "lips": held(build_lips),
    "worm": held(build_worm),
}
