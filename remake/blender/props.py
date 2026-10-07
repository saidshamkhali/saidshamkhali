"""Prop builders. Each makes a prop standing on z=0, facing -Y, about 1 unit tall,
under a root empty, and keys its own loop animation.

The animation follows reference/prop_tracks.json: each prop's state in every frame of the
original (mouth open, bell tilt, wing and toast, clock lean, worm loop), measured by
reference/build_reference.py, so every prop moves drawing for drawing with the GIF. A prop
without a track falls back to a regular cycle (LAYOUT["cycles_s"], offset by its phase)."""
import json
import math
import os

from kit import (LAYOUT, REMAKE, SRC_FRAMES, bake, box, constant, cycles_per_loop, cylinder, empty, hitch,
                 keep_world, lathe, mat, saw, slab, smooth_outline, sphere, step_frames, sweep, wave)

# Cartoon timing, like the figure (jesus.STEPPED): the props are keyed once per source frame
# and hold each pose, as the 10 fps original does. False = keyed on every frame, smooth.
STEPPED = True


def animate(obj, path, index, fn):
    bake(obj, path, index, fn, step_frames() if STEPPED else None)


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


def build_lips(root, coll, phase):
    """A shouting mouth like the source's: fat lips curving round in plan, hinged at the
    back corners so they open like a jaw, with a dark mouth, a row of teeth riding on the
    upper lip and a tongue on the lower. Closed, the lips face the camera; as they open they
    swing round so the shout faces screen-left, as in the source."""
    c = cycles_per_loop(LAYOUT["cycles_s"]["lips"])
    hinge = (0.0, 0.07, 0.39)
    swivel = empty(root.name + "_swivel", coll, parent=root)  # turns the shout towards screen-left
    upper_pivot = empty(root.name + "_upper", coll, loc=hinge, parent=swivel)
    lower_pivot = empty(root.name + "_lower", coll, loc=hinge, parent=swivel)
    half = 0.43

    def arc(z, depth, n=7):  # a U round the front of the mouth, corners at the back
        pts = []
        for i in range(n):
            a = math.pi * i / (n - 1)
            pts.append((-half * math.cos(a), 0.07 - 0.28 * depth * math.sin(a) ** 0.8, z + 0.012 * math.sin(a)))
        return pts

    # lens-shaped: thin at the corners, full in the middle; the upper lip dips in a cupid's bow
    upper = sweep("upper", coll, mat("lips"), arc(0.455, 0.9), [0.01, 0.045, 0.085, 0.068, 0.085, 0.045, 0.01],
                  n=36, ring=18, squash=1.0)
    lower = sweep("lower", coll, mat("lips"), arc(0.315, 0.8), [0.01, 0.05, 0.1, 0.112, 0.1, 0.05, 0.01],
                  n=36, ring=18, squash=1.0)
    # the corners: thick round joints where the lips meet, so an open mouth bends like a C
    corners = [sphere(f"corner{k}", coll, mat("lips"), (x, 0.07, 0.39), r=0.062) for k, x in enumerate((-half, half))]
    teeth = []
    for k in range(6):  # separate teeth hanging from the upper lip
        u = (k + 0.5) / 6
        x = -0.26 + 0.52 * u
        y = -0.165 + 0.08 * (2 * u - 1) ** 2
        teeth.append(box(f"tooth{k}", coll, mat("white", 0.85), (x, y, 0.383), (0.072, 0.04, 0.075),
                         rot=(0, 0, math.atan2(0.16 * (2 * u - 1), 1.0)), bevel=0.014))
    tongue = sphere("tongue", coll, mat("tongue"), (0.03, -0.1, 0.352), scale=(0.19, 0.11, 0.045))
    # the dark back of the mouth, behind the teeth and tongue
    inner = sphere("inner", coll, mat("mouth", 0.8), (0.0, 0.02, 0.39), scale=(0.34, 0.07, 0.03), outline=False)
    for p in [upper] + teeth:
        keep_world(p, upper_pivot)
    for p in (lower, tongue):
        keep_world(p, lower_pivot)
    for p in corners + [inner]:
        keep_world(p, swivel)
    for p in [upper, lower, tongue, inner] + teeth + corners:
        p.name = f"{root.name}_{p.name}"

    def shout(t):  # 0 closed .. 1 open, a quick shout each cycle
        x = saw(t, c, phase)
        return math.sin(math.pi * min(1.0, x / 0.65)) ** 0.6 if x < 0.65 else 0.0
    opening = track(root, "open", shout)
    animate(upper_pivot, "rotation_euler", 0, lambda t: math.radians(-62) * opening(t))
    animate(lower_pivot, "rotation_euler", 0, lambda t: math.radians(52) * opening(t))
    animate(inner, "scale", 2, lambda t: 1.0 + 8.0 * opening(t))
    animate(swivel, "rotation_euler", 2, lambda t: math.radians(-58) * opening(t) ** 0.5)
    for corner in corners:  # pointed corners when closed, round joints when shouting
        corner["outline_ref_scale"] = 1.0
        for i in range(3):
            animate(corner, "scale", i, lambda t: 0.15 + 0.85 * opening(t))


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
    return run


BUILDERS = {
    "toaster": held(build_toaster),
    "alarm_clock": held(build_clock),
    "bell": held(build_bell),
    "lips": held(build_lips),
    "worm": held(build_worm),
}
