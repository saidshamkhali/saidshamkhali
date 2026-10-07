"""Prop builders. Each makes a prop standing on z=0, facing -Y, about 1 unit tall,
under a root empty, and keys its own loop animation."""
import math

from kit import (LAYOUT, bake, bake_value, box, cycles_per_loop, cylinder, empty, keep_world,
                 lathe, mat, saw, sphere, tube, wave)

def build_toaster(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["toaster"])
    hover = empty(root.name + "_hover", coll, parent=root)
    parts = []
    parts.append(box("body", coll, mat("metal"), (0, 0, 0.42), (1.0, 0.6, 0.72), bevel=0.12))
    parts.append(box("slot", coll, mat("slot"), (0.02, 0, 0.785), (0.62, 0.14, 0.02), outline=False))
    parts.append(box("lever_slot", coll, mat("slot"), (-0.34, -0.305, 0.44), (0.08, 0.02, 0.36), outline=False))
    toast = box("toast", coll, mat("toast"), (0.02, 0, 0.78), (0.56, 0.1, 0.42), bevel=0.06)
    wing_pivot = empty(root.name + "_wing", coll, loc=(0.44, -0.05, 0.55))
    wing = sphere("wing", coll, mat("white", 0.8), (0.72, -0.05, 0.57), scale=(0.32, 0.06, 0.12),
                  rot=(0, math.radians(-12), 0))
    for p in parts + [toast]:
        keep_world(p, hover)
    keep_world(wing_pivot, hover)
    keep_world(wing, wing_pivot)
    for p in parts + [toast, wing]:
        p.name = f"{root.name}_{p.name}"
    hover.location.z = 0.18
    bake(hover, "location", 2, lambda t: 0.18 + 0.05 * wave(t, c, phase))
    toast_z = toast.location.z
    bake(toast, "location", 2, lambda t: toast_z + 0.16 * max(0.0, wave(t, c, phase + 0.1)))
    bake(wing_pivot, "rotation_euler", 1, lambda t: math.radians(28) * wave(t, c * 2, phase))


def build_clock(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["alarm_clock"])
    rattle = empty(root.name + "_rattle", coll, parent=root)
    parts = [
        cylinder("body", coll, mat("clock"), (0, 0, 0.5), 0.42, 0.26, rot=(math.pi / 2, 0, 0)),
        cylinder("face", coll, mat("clockface", 0.85), (0, -0.13, 0.5), 0.35, 0.03, rot=(math.pi / 2, 0, 0)),
        # hands start at the centre (0, 0.5): hour points to 12, minute to 7
        box("hour", coll, mat("black"), (0, -0.155, 0.59), (0.04, 0.01, 0.2), outline=False),
        box("minute", coll, mat("black"), (-0.065, -0.155, 0.388), (0.032, 0.01, 0.27),
            rot=(0, math.radians(30), 0), outline=False),
        cylinder("pin", coll, mat("black"), (0, -0.16, 0.5), 0.03, 0.02, rot=(math.pi / 2, 0, 0), outline=False),
        box("hammer", coll, mat("clock"), (0, 0, 0.97), (0.05, 0.05, 0.14)),
        sphere("bell_l", coll, mat("gold"), (-0.27, 0, 0.92), scale=(0.17, 0.17, 0.11), rot=(0, math.radians(-35), 0)),
        sphere("bell_r", coll, mat("gold"), (0.27, 0, 0.92), scale=(0.17, 0.17, 0.11), rot=(0, math.radians(35), 0)),
        cylinder("leg_l", coll, mat("clock"), (-0.25, 0, 0.08), 0.05, 0.16, rot=(0, math.radians(-25), 0)),
        cylinder("leg_r", coll, mat("clock"), (0.25, 0, 0.08), 0.05, 0.16, rot=(0, math.radians(25), 0)),
    ]
    for p in parts:
        keep_world(p, rattle)
        p.name = f"{root.name}_{p.name}"

    def env(t):  # rattle for the first half of each cycle
        return 1.0 if saw(t, c, phase) < 0.5 else 0.0
    bake(rattle, "rotation_euler", 1, lambda t: math.radians(8) * env(t) * wave(t, c * 6, phase))
    bake(rattle, "location", 2, lambda t: 0.04 * env(t) * abs(wave(t, c * 6, phase)))


def build_bell(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["bell"])
    pivot = empty(root.name + "_swing", coll, loc=(0, 0, 1.12), parent=root)
    body = lathe("bell", coll, mat("gold"),
                 [(0.0, 0.0), (0.40, 0.0), (0.41, 0.05), (0.34, 0.14), (0.25, 0.32),
                  (0.21, 0.5), (0.15, 0.6), (0.06, 0.64), (0.0, 0.645)], loc=(0, 0, 0.12))
    handle = lathe("handle", coll, mat("black"),
                   [(0.0, 0.6), (0.06, 0.6), (0.045, 0.7), (0.05, 0.8), (0.09, 0.87),
                    (0.085, 0.95), (0.05, 0.99), (0.0, 1.0)], loc=(0, 0, 0.12))
    for p in (body, handle):
        keep_world(p, pivot)
        p.name = f"{root.name}_{p.name}"
    bake(pivot, "rotation_euler", 1, lambda t: math.radians(22) * wave(t, c, phase))


def build_lips(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["lips"])

    def taper(u):
        return math.sin(math.pi * u) ** 0.6

    def bow(u):  # cupid's bow dip in the middle of the upper lip
        return math.exp(-((u - 0.5) / 0.09) ** 2)

    def lip(sign, ry, rz, gape):
        def shape(u):
            z = 0.38 + sign * (0.08 * taper(u) + gape * math.sin(math.pi * u) ** 0.8)
            k = 1 - 0.3 * bow(u) if sign > 0 else 1.0
            return -0.5 + u, z, ry * taper(u), rz * taper(u) * k
        return shape

    upper = tube("upper", coll, mat("lips"), [lip(1, 0.17, 0.085, 0.0), lip(1, 0.17, 0.085, 0.2)])
    lower = tube("lower", coll, mat("lips"), [lip(-1, 0.18, 0.1, 0.0), lip(-1, 0.18, 0.1, 0.22)])
    inner = sphere("inner", coll, mat("mouth", 0.8), (0, 0.05, 0.38), scale=(0.46, 0.1, 0.04), outline=False)
    teeth = box("teeth", coll, mat("white", 0.85), (0, -0.04, 0.41), (0.42, 0.06, 0.07), bevel=0.02, outline=False)
    tongue = sphere("tongue", coll, mat("tongue"), (0, 0.0, 0.33), scale=(0.22, 0.1, 0.06), outline=False)
    for p in (upper, lower, inner, teeth, tongue):
        keep_world(p, root)
        p.name = f"{root.name}_{p.name}"

    def opening(t):  # 0 closed .. 1 open, a quick shout each cycle
        x = saw(t, c, phase)
        return math.sin(math.pi * min(1.0, x / 0.6)) ** 0.7 if x < 0.6 else 0.0
    for obj in (upper, lower):
        bake_value(obj.data.shape_keys.key_blocks["key1"], "value", opening)
    bake(inner, "scale", 2, lambda t: 1.0 + 5.0 * opening(t))
    bake(teeth, "location", 2, lambda t: 0.41 + 0.15 * opening(t))
    bake(tongue, "location", 2, lambda t: 0.33 - 0.15 * opening(t))
    bake(teeth, "scale", 0, lambda t: 0.1 + 0.9 * opening(t))
    bake(tongue, "scale", 0, lambda t: 0.1 + 0.9 * opening(t))


def build_worm(root, coll, phase):
    c = cycles_per_loop(LAYOUT["cycles_s"]["worm"])
    n = 9
    for i in range(n):
        u = i / (n - 1)
        r = 0.09 + 0.05 * math.sin(math.pi * u) + (0.03 if i == n - 1 else 0.0)
        seg = sphere(f"{root.name}_seg{i}", coll, mat("worm"), (-0.55 + 1.1 * u, 0, r), r=r)
        keep_world(seg, root)
        base_x = seg.location.x

        def hump(t, u=u, r=r):  # inchworm hump travelling head-ward
            h = math.sin(math.pi * u) * max(0.0, wave(t, c, phase - u * 0.5))
            return r + 0.22 * h

        def creep(t, base_x=base_x, u=u):
            return base_x * (1.0 - 0.12 * max(0.0, wave(t, c, phase - u * 0.5)))
        bake(seg, "location", 2, hump)
        bake(seg, "location", 0, creep)


BUILDERS = {
    "toaster": build_toaster,
    "alarm_clock": build_clock,
    "bell": build_bell,
    "lips": build_lips,
    "worm": build_worm,
}
