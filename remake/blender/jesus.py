"""The figure: Simpsons-style Jesus, modelled from code, skinned to an armature.

Feet at z=0, facing -Y, +X is his left. Proportions are measured from the
source frames: head ~26% of the height, robe to mid-calf, shoulders ~0.5 wide.

build(coll) returns the armature object; animate(rig) keys the turn and the
poses from reference/layout.json.
"""
import math

import bpy
from mathutils import Euler, Vector

from kit import LAYOUT, blobs, cap, hold, loft, mat, merge, remake_frame, shell, step_frames, sweep, torus, zsec

RIG = "Jesus_Rig"

# bone: (head, tail, parent)
BONES = {
    "root": ((0, 0, 0), (0, 0, 0.3), None),
    "hips": ((0, 0, 0.9), (0, 0, 1.2), "root"),
    "chest": ((0, 0, 1.2), (0, 0, 1.5), "hips"),
    "head": ((0, 0, 1.52), (0, 0, 1.95), "chest"),
}
LEG_X = 0.11
KNEE_Z = 0.52
ANKLE_Z = 0.09
for _s, _x in (("L", 1), ("R", -1)):
    BONES[f"upper_arm.{_s}"] = ((0.235 * _x, 0, 1.43), (0.27 * _x, 0, 1.08), "chest")
    BONES[f"forearm.{_s}"] = ((0.27 * _x, 0, 1.08), (0.29 * _x, 0, 0.79), f"upper_arm.{_s}")
    BONES[f"hand.{_s}"] = ((0.29 * _x, 0, 0.79), (0.30 * _x, 0, 0.6), f"forearm.{_s}")
    # legs: knees bend (a hint of bend in the rest pose tells the IK which way), feet stay
    # planted on foot bones that hang off the root, knees aim at poles in front
    BONES[f"thigh.{_s}"] = ((LEG_X * _x, 0, 0.88), (LEG_X * _x, -0.015, KNEE_Z), "hips")
    BONES[f"shin.{_s}"] = ((LEG_X * _x, -0.015, KNEE_Z), (LEG_X * _x, 0, ANKLE_Z), f"thigh.{_s}")
    BONES[f"foot.{_s}"] = ((LEG_X * _x, 0, ANKLE_Z), (LEG_X * _x, -0.16, 0.03), "root")
    BONES[f"knee.{_s}"] = ((LEG_X * _x, -0.7, KNEE_Z), (LEG_X * _x, -0.7, KNEE_Z + 0.1), "root")
CONTROLS = {"knee.L", "knee.R"}  # helpers that don't deform


# --------------------------------------------------------------------------- rig + skinning

def make_rig(coll):
    arm = bpy.data.armatures.new(RIG)
    rig = bpy.data.objects.new(RIG, arm)
    coll.objects.link(rig)
    rig.show_in_front = True
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, parent) in BONES.items():
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail, eb.roll = head, tail, 0.0
        if parent:
            eb.parent = arm.edit_bones[parent]
            eb.use_connect = name.startswith("shin")
        if name.startswith(("forearm", "hand")):
            eb.inherit_scale = "NONE"  # a stretched upper arm must not stretch the hand
        eb.use_deform = name not in CONTROLS
    bpy.ops.object.mode_set(mode="OBJECT")
    for side in ("L", "R"):
        ik = rig.pose.bones[f"shin.{side}"].constraints.new("IK")
        ik.target, ik.subtarget = rig, f"foot.{side}"
        ik.pole_target, ik.pole_subtarget = rig, f"knee.{side}"
        ik.pole_angle = math.radians(-90)
        ik.chain_count = 2
    return rig


def skin(obj, rig, weights, subsurf=1):
    """weights(co) -> {bone: weight}. Adds Armature (+ Subsurf) before any other modifier."""
    groups = {}
    for v in obj.data.vertices:
        for bone, w in weights(v.co).items():
            if w <= 0:
                continue
            if bone not in groups:
                groups[bone] = obj.vertex_groups.new(name=bone)
            groups[bone].add([v.index], w, "REPLACE")
    obj.parent = rig
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    obj.modifiers.move(len(obj.modifiers) - 1, 0)
    if subsurf:
        sub = obj.modifiers.new("Subsurf", "SUBSURF")
        sub.levels = subsurf
        sub.render_levels = subsurf + 1
        obj.modifiers.move(len(obj.modifiers) - 1, 1)
    return obj


def rigid(bone):
    return lambda co: {bone: 1.0}


def blend(lo_bone, hi_bone, z0, z1):
    """lo_bone below z0, hi_bone above z1, linear in between."""
    def w(co):
        t = min(1.0, max(0.0, (co.z - z0) / (z1 - z0)))
        return {lo_bone: 1.0 - t, hi_bone: t}
    return w


def robe_weights(co):
    """Chest above the waist, hips below; the skirt also follows the thighs a little, so
    it swings with the knees instead of hanging like a rigid bell."""
    t = min(1.0, max(0.0, (co.z - 1.0) / 0.2))
    k = 0.4 * smooth(0.95, 0.4, co.z)
    side = min(1.0, max(0.0, 0.5 + co.x / 0.16))
    return {"chest": t, "hips": (1 - t) * (1 - k),
            "thigh.L": (1 - t) * k * side, "thigh.R": (1 - t) * k * (1 - side)}


# --------------------------------------------------------------------------- model

# Robe: horizontal ellipses (z, rx, ry, cy). A-line: narrow chest, a soft belly pushing the
# front out (cy), flaring to a mid-calf hem.
ROBE = [
    (0.5, 0.300, 0.232, 0.0), (0.54, 0.297, 0.230, 0.0), (0.66, 0.282, 0.224, -0.015),
    (0.80, 0.262, 0.214, -0.03), (0.95, 0.245, 0.205, -0.035), (1.08, 0.233, 0.186, -0.02),
    (1.20, 0.223, 0.165, -0.005), (1.34, 0.219, 0.153, 0.0), (1.42, 0.207, 0.143, 0.0),
    (1.47, 0.172, 0.123, 0.0), (1.50, 0.118, 0.097, 0.0), (1.515, 0.045, 0.045, 0.0), (1.52, 0.0, 0.0, 0.0),
]


def robe_ring(z):
    zs = [s[0] for s in ROBE]
    z = min(max(z, zs[0]), zs[-1])
    k = max(i for i in range(len(zs) - 1) if zs[i] <= z) if z < zs[-1] else len(zs) - 2
    f = (z - zs[k]) / (zs[k + 1] - zs[k])
    a, b = ROBE[k], ROBE[k + 1]
    return tuple(a[i] + (b[i] - a[i]) * f for i in (1, 2, 3))


def build_body(coll, rig):
    skin_m, robe_m = mat("skin"), mat("robe", 0.78)

    robe = loft("J_robe", coll, robe_m, [zsec(z, max(rx, 0.004), max(ry, 0.004), cy=cy) for z, rx, ry, cy in ROBE],
                ring=40)
    for v in robe.data.vertices:  # a soft wave along the hem, like loose cloth
        k = smooth(0.74, 0.5, v.co.z)
        if k > 0:
            th = math.atan2(v.co.x, -v.co.y)
            f = 1 + 0.03 * k * math.sin(5 * th + 0.8)
            v.co.x *= f
            v.co.y *= f
    skin(robe, rig, robe_weights)

    # V-neck: skin showing through the collar, a thin patch lying on the robe
    def vneck_surf(u, v):
        z = 1.31 + 0.19 * v
        rx, ry, cy = robe_ring(z)
        half = math.radians(31) * v ** 0.9
        th = (2 * u - 1) * half
        return Vector((rx * math.sin(th), cy - ry * math.cos(th), z))

    skin(shell("J_vneck", coll, skin_m, vneck_surf, 8, 10, lambda u, v: 0.006, inner=0.006),
         rig, rigid("chest"))

    for side, x in (("L", 1), ("R", -1)):
        # the leg runs up under the robe so bent knees never open a gap at the hem
        leg = loft(f"J_leg_{side}", coll, skin_m, [
            zsec(z, r, r * 0.95, cx=LEG_X * x) for z, r in
            ((0.04, 0.055), (0.15, 0.062), (0.30, 0.068), (0.45, 0.067), (0.6, 0.07), (0.75, 0.072), (0.88, 0.07))],
            ring=20)
        skin(leg, rig, blend(f"shin.{side}", f"thigh.{side}", KNEE_Z - 0.06, KNEE_Z + 0.06))
        foot = blobs(f"J_foot_{side}", coll, skin_m, [
            ((LEG_X * x, -0.07, 0.045), (0.07, 0.13, 0.042), (0, 0, 0)),
            ((LEG_X * x, 0.02, 0.06), (0.058, 0.06, 0.05), (0, 0, 0))])
        skin(foot, rig, rigid(f"foot.{side}"))
        sandal = blobs(f"J_sandal_{side}", coll, mat("sandal"), [
            ((LEG_X * x, -0.06, 0.012), (0.085, 0.165, 0.014), (0, 0, 0)),
            ((LEG_X * x, -0.1, 0.075), (0.074, 0.022, 0.016), (math.radians(-20), 0, 0))])
        skin(sandal, rig, rigid(f"foot.{side}"))


def build_arms(coll, rig):
    skin_m, robe_m = mat("skin"), mat("robe", 0.78)
    # Each sleeve is two rigid tubes with round ends meeting at the elbow pivot, so a
    # hard bend (hand to face) can't fold the mesh into itself and flip its outline.
    er = 0.065  # sleeve radius at the elbow

    def dome(cx, z, r, down):
        return [zsec(z + (-1 if down else 1) * r * a, r * math.sqrt(1 - a * a), r * math.sqrt(1 - a * a), cx=cx)
                for a in (0.45, 0.75, 0.93)]

    for side, x in (("L", 1), ("R", -1)):
        ex, ez = 0.27 * x, 1.08
        upper = [zsec(1.47, 0.045, 0.045, cx=0.215 * x), zsec(1.43, 0.068, 0.068, cx=0.235 * x),
                 zsec(1.30, 0.068, 0.068, cx=0.250 * x), zsec(ez, er, er, cx=ex)]
        skin(loft(f"J_sleeve_{side}", coll, robe_m, upper + dome(ex, ez, er, True), ring=24),
             rig, rigid(f"upper_arm.{side}"))
        lower = [zsec(ez, er, er, cx=ex), zsec(0.95, 0.068, 0.068, cx=0.278 * x),
                 zsec(0.84, 0.075, 0.075, cx=0.287 * x), zsec(0.80, 0.079, 0.079, cx=0.290 * x),
                 zsec(0.795, 0.05, 0.05, cx=0.290 * x)]
        skin(loft(f"J_cuff_{side}", coll, robe_m, dome(ex, ez, er, False)[::-1] + lower, ring=24),
             rig, rigid(f"forearm.{side}"))
        skin(build_hand(coll, side, x), rig, rigid(f"hand.{side}"))


def build_hand(coll, side, x):
    """Simpsons hand (thumb + three fingers) hanging from the wrist, palm facing the body,
    thumb forward. Fingers fan out a little and curl towards the palm."""
    skin_m = mat("skin")
    wx, wz = 0.29 * x, 0.79

    def at(dx, dy, dz):
        return (wx + dx * x, dy, wz + dz)

    parts = [blobs(f"_palm_{side}", coll, skin_m, [
        (at(0, 0, -0.004), (0.03, 0.034, 0.04), (0, 0, 0)),
        (at(0, 0.004, -0.068), (0.028, 0.054, 0.056), (0, 0, 0))], segs=24)]
    for k, (dy, length) in enumerate(((-0.034, 0.078), (0.0, 0.086), (0.034, 0.078))):
        spread = dy * 0.45
        parts.append(sweep(f"_finger{k}_{side}", coll, skin_m,
                           [at(0.0, dy, -0.095), at(-0.006, dy + spread * 0.6, -0.095 - length * 0.55),
                            at(-0.018, dy + spread, -0.095 - length)],
                           [0.0185, 0.019, 0.0195], n=10, ring=14))
    parts.append(sweep(f"_thumb_{side}", coll, skin_m,
                       [at(-0.006, -0.03, -0.04), at(-0.016, -0.068, -0.07), at(-0.024, -0.082, -0.105)],
                       [0.019, 0.0185, 0.018], n=10, ring=14))
    return merge(f"J_hand_{side}", coll, skin_m, parts)


# Head surface: horizontal ellipses (z, rx, ry, cy), face towards -Y. The cranium is a
# Simpsons cylinder; below the moustache it narrows into the jaw and a chin hidden by the beard.
SKULL = [
    (1.42, 0.050, 0.045, -0.075), (1.47, 0.095, 0.085, -0.055), (1.54, 0.125, 0.118, -0.035),
    (1.62, 0.134, 0.138, -0.020), (1.72, 0.140, 0.147, -0.006), (1.85, 0.142, 0.150, 0.0),
    (1.93, 0.139, 0.147, 0.0), (1.975, 0.128, 0.135, 0.0), (2.005, 0.104, 0.109, 0.0),
    (2.025, 0.063, 0.066, 0.0), (2.034, 0.0, 0.0, 0.0),
]
EYE_R = 0.057
EYE_Z = 1.852
HANG_Z = 1.74  # below this the hair hangs straight instead of following the jaw
MUZZLE = 0.07  # how far the Simpsons muzzle (moustache, lip, chin) juts out of the face
# The head is modelled at a comfortable size, then scaled about the collar: in the source
# it is about a quarter of his height.
HEAD_SCALE = 0.84
HEAD_PIVOT = Vector((0.0, 0.0, 1.47))
HAIR_TOP = 0.02  # hair thickness on the crown
HEAD_LIFT = 0.065  # a long neck under the beard: the chin sits on the collar, not the chest


def to_head(obj):
    """Scale a freshly built head part about the collar and lift it (before skinning)."""
    lift = Vector((0.0, 0.0, HEAD_LIFT))
    for v in obj.data.vertices:
        v.co = HEAD_PIVOT + (v.co - HEAD_PIVOT) * HEAD_SCALE + lift
    return obj


def hair_top():
    """Height of the top of the hair above his feet (the camera frames on it)."""
    return HEAD_PIVOT.z + (SKULL[-1][0] + HAIR_TOP - HEAD_PIVOT.z) * HEAD_SCALE + HEAD_LIFT


def muzzle(z):
    return MUZZLE * smooth(1.49, 1.6, z) * (1 - smooth(1.68, 1.77, z))


def skull_ring(z):
    zs = [s[0] for s in SKULL]
    z = min(max(z, zs[0]), zs[-1])
    k = max(i for i in range(len(zs) - 1) if zs[i] <= z) if z < zs[-1] else len(zs) - 2
    f = (z - zs[k]) / (zs[k + 1] - zs[k])
    f = f * f * (3 - 2 * f)  # smoothstep between rows keeps the profile free of creases
    a, b = SKULL[k], SKULL[k + 1]
    return tuple(a[i] + (b[i] - a[i]) * f for i in (1, 2, 3))


def head_point(theta, z):
    """theta in radians, 0 = straight ahead (-Y), positive towards his left (+X)."""
    rx, ry, cy = skull_ring(z)
    c = math.cos(theta)
    return Vector((rx * math.sin(theta), cy - (ry + muzzle(z) * max(0.0, c) ** 2) * c, z))


def outward(theta):
    return Vector((math.sin(theta), -math.cos(theta), 0.0))


def smooth(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def build_head(coll, rig):
    skin_m, hair_m = mat("skin"), mat("hair", 0.8)
    head = rigid("head")

    steps = 40
    z0, z1 = SKULL[0][0], SKULL[-1][0]
    rows = []
    for i in range(steps + 1):
        z = z0 + (z1 - z0) * i / steps
        rx, ry, cy = skull_ring(z)
        rows.append(zsec(z, max(rx, 0.004), max(ry, 0.004), cy=cy))
    skull = loft("J_skull", coll, skin_m, rows, ring=32)
    for v in skull.data.vertices:  # push the muzzle out, exactly as head_point() does
        rx, ry, cy = skull_ring(v.co.z)
        c = -(v.co.y - cy) / max(ry, 1e-4)
        if c > 0:
            v.co.y -= muzzle(v.co.z) * c ** 3
    skin(to_head(skull), rig, head)

    # Simpsons ears, just in front of the hanging hair
    for x, side in ((1, "L"), (-1, "R")):
        th = math.radians(92) * x
        c = head_point(th, 1.765) + outward(th) * 0.028
        skin(to_head(blobs(f"J_ear_{side}", coll, skin_m, [
            (c, (0.02, 0.042, 0.06), (0, 0, 0)),
            (c + outward(th) * 0.013 + Vector((0, -0.008, -0.004)), (0.011, 0.024, 0.034), (0, 0, 0))])), rig, head)

    # eyes: Simpsons balls touching in the middle, half sunk into the face
    eyes, pupils = [], []
    for x in (1, -1):
        c = Vector((EYE_R * x * 1.02, -0.112, EYE_Z))
        eyes.append((c, (EYE_R,) * 3, (0, 0, 0)))
        look = Vector((0, -math.cos(math.radians(2)), -math.sin(math.radians(2))))
        pupils.append((c + look * EYE_R * 0.98, (0.013, 0.004, 0.013), (math.radians(2), 0, 0)))
    skin(to_head(blobs("J_eyes", coll, mat("white", 0.85), eyes)), rig, head)
    skin(to_head(blobs("J_pupils", coll, mat("black"), pupils, outline=False)), rig, head, subsurf=0)
    # upper lids: level caps over the top of each eye, half-lidded and calm (a tilt reads sad or stern)
    for x, side in ((1, "L"), (-1, "R")):
        c = Vector((EYE_R * x * 1.02, -0.112, EYE_Z))
        lid = cap(f"J_lid_{side}", coll, skin_m, c, EYE_R * 1.08, 0.42,
                  rot=(math.radians(-8), 0, 0))
        skin(to_head(lid), rig, head)

    # nose: a short Simpsons sausage, pointing forward and a little down
    skin(to_head(sweep("J_nose", coll, skin_m, [(0, -0.135, 1.805), (0, -0.175, 1.792), (0, -0.212, 1.778)],
                       [0.027, 0.029, 0.031], n=12, ring=20)), rig, head)

    # beard: a thick patch over the jaw, from sideburn to sideburn, ending in a point
    span = math.radians(104)  # wraps under the jaw to meet the hanging hair

    def beard_surf(u, v):
        th = -span + 2 * span * u
        a = abs(th) / span
        top = 1.605 + 0.05 * smooth(0.1, 0.6, a) + 0.09 * smooth(0.75, 0.95, a)  # cheeks bare
        bottom = 1.47 + 0.085 * a ** 0.7  # a point at the chin
        return head_point(th, bottom + (top - bottom) * v)

    def beard_thick(u, v):
        a = abs(2 * u - 1)
        body = (math.sin(math.pi * v) ** 0.5) * (1 - a ** 4) ** 0.5
        chin = (1 - a) ** 1.5 * (1 - v) ** 1.2
        return 0.01 + 0.014 * body + 0.032 * chin

    skin(to_head(shell("J_beard", coll, hair_m, beard_surf, 40, 14, beard_thick)), rig, head)

    # moustache: a bushy bar riding on the muzzle, ends drooping into the beard
    for x, side in ((1, "L"), (-1, "R")):
        pts = [head_point(math.radians(a) * x, z) + outward(math.radians(a) * x) * 0.03
               for a, z in ((0, 1.703), (25, 1.696), (55, 1.665), (80, 1.61))]
        skin(to_head(sweep(f"J_moustache_{side}", coll, hair_m, pts, [0.04, 0.037, 0.026, 0.013], n=16,
                           ring=16, squash=0.8)), rig, head)
    # lower lip: the yellow band showing between moustache and beard
    lip = [head_point(math.radians(a), 1.633) + outward(math.radians(a)) * 0.006 for a in (-30, 0, 30)]
    skin(to_head(sweep("J_lip", coll, skin_m, lip, [0.016], n=10, ring=12, squash=0.8)), rig, head)

    # hair: a shell over the cranium; behind the ears it hangs straight to the shoulders
    def hair_low(th):
        a = abs(math.degrees(th))
        parting = 0.03 * math.exp(-(a / 7) ** 2)  # centre parting lifts the hairline
        ragged = 0.012 * math.sin(13 * th) * (1 - smooth(60, 90, a))  # a messy fringe
        hairline = 1.94 + parting + ragged - 0.06 * (min(a, 75) / 75) ** 2
        temple = hairline + (1.84 - hairline) * smooth(70, 88, a)  # puffy over the ear tops
        curtain = 1.405 + 0.018 * math.sin(7 * th)
        return temple + (curtain - temple) * smooth(110, 126, a)  # long hair only behind the ears

    def hair_surf(u, v):
        th = math.pi * (2 * u - 1)  # u=0.5 is the front
        lo = hair_low(th)
        z = lo + (SKULL[-1][0] - lo) * v
        if z >= HANG_Z:
            return head_point(th, z)
        p = head_point(th, HANG_Z)
        flare = 1 + 0.12 * (HANG_Z - z)
        return Vector((p.x * flare, p.y * flare + 0.02 * (HANG_Z - z), z))

    def hair_thick(u, v):
        th = math.pi * (2 * u - 1)
        back = 0.5 - 0.5 * math.cos(th)  # 0 front, 1 back
        locks = 0.5 + 0.5 * math.sin(11 * th)  # lumpy locks show on the silhouette
        side = math.sin(th) ** 2 * (1 - smooth(0.0, 0.5, v))  # bushy at the temples
        return HAIR_TOP + (0.05 * back + 0.02 * side + 0.012 * locks) * (1 - v) ** 1.2  # pole closes

    skin(to_head(shell("J_hair", coll, hair_m, hair_surf, 72, 30, hair_thick, wrap_u=True)),
         rig, blend("chest", "head", 1.42, 1.56))

    halo_z = HEAD_PIVOT.z + (2.25 - HEAD_PIVOT.z) * HEAD_SCALE + HEAD_LIFT
    halo = torus("J_halo", coll, mat("halo", 0.85), (0, 0, halo_z), 0.16 * HEAD_SCALE, 0.011)
    skin(halo, rig, head, subsurf=0)


def build(coll):
    rig = make_rig(coll)
    build_body(coll, rig)
    build_arms(coll, rig)
    build_head(coll, rig)
    return rig


# --------------------------------------------------------------------------- animation
# Joint rotations in degrees (x, y, z), about axes aligned with the rest pose
# (X = his left, Y = backwards, Z = up). For the left arm, -Y lifts it outward
# and up; for the right arm, +Y. Negative X swings an arm forward. A hand's Z
# twists it about the forearm.
POSES = {
    "up": {
        "L": ((0, -183, 0), (-8, 0, 0), (0, 0, 90)),
        "R": ((-5, 0, 0), (-40, 8, 0), (0, 0, -20)),
    },
    "wave_a": {
        "L": ((0, -178, 0), (-10, 0, -14), (28, 0, 90)),
        "R": ((-5, 1, 0), (-48, 12, 0), (10, 0, -30)),
    },
    "wave_b": {
        "L": ((0, -186, 0), (-4, 0, 12), (-22, 0, 90)),
        "R": ((-5, 0, 0), (-42, 9, 0), (-5, 0, -30)),
    },
    "face": {
        "L": ((-48, -22, 0), (-145, 0, 0), (0, 0, 60)),
        "R": ((-8, 2, 0), (-42, 10, 0), (0, 0, -20)),
    },
    "beckon": {
        "L": ((-18, -6, 0), (-95, 0, -55), (0, 0, 0)),
        "R": ((-20, 14, 0), (-64, 0, 0), (60, 0, 90)),
    },
    "beckon_b": {
        "L": ((-18, -6, 0), (-95, 0, -55), (0, 0, 0)),
        "R": ((-16, 18, 0), (-68, 0, 0), (25, 0, 90)),
    },
}


def bone_rotation(pbone, euler_deg):
    """Rotation given in rest-pose axes -> the bone's local quaternion."""
    r = Euler([math.radians(a) for a in euler_deg], "XYZ").to_matrix()
    b = pbone.bone.matrix_local.to_3x3().normalized()
    return (b.inverted() @ r @ b).to_quaternion()


# Two cartoon cheats from the source, applied to the raised left arm in the up/wave poses:
# the arm stretches so the hand reaches well above the halo (upper arm, forearm scale), and
# the open palm keeps facing the viewer while he turns.
# Cartoon timing: the source is drawn at 10 fps, so each of its frames is held for two or
# three of ours instead of easing smoothly from pose to pose. False = smooth motion.
STEPPED = True

RAISED = {"up", "wave_a", "wave_b"}
STRETCH = (1.22, 1.15)
ARM_LEAN = 26  # degrees back, so facing screen-left the arm sits behind his face


def animate(rig):
    pb = rig.pose.bones
    for p in pb:
        p.rotation_mode = "QUATERNION"
    previous = {}
    for key in LAYOUT["figure"]["timeline"]:
        f = remake_frame(key["frame"])
        pose = POSES[key["pose"]]
        raised = key["pose"] in RAISED
        rig.rotation_euler.z = math.radians(-key["yaw"])
        rig.keyframe_insert("rotation_euler", index=2, frame=f)
        targets = {}
        for side in ("L", "R"):
            sh, el, wr = pose[side]
            if raised and side == "L":
                wr = (wr[0], wr[1], wr[2] - key["yaw"])
                sh = (sh[0] + ARM_LEAN * min(1.0, max(0.0, key["yaw"] / 90)), sh[1], sh[2])
            targets[f"upper_arm.{side}"] = sh
            targets[f"forearm.{side}"] = el
            targets[f"hand.{side}"] = wr
        for name, rot in targets.items():
            q = bone_rotation(pb[name], rot)
            if name in previous and previous[name].dot(q) < 0:
                q.negate()  # stay on the same hemisphere so keys interpolate the short way
            previous[name] = q
            pb[name].rotation_quaternion = q
            pb[name].keyframe_insert("rotation_quaternion", frame=f)
        for name, s in (("upper_arm.L", STRETCH[0]), ("forearm.L", STRETCH[1])):
            pb[name].scale = (1.0, s if raised else 1.0, 1.0)
            pb[name].keyframe_insert("scale", frame=f)
    animate_body(rig)
    if STEPPED:  # sample the smooth motion once per source frame and hold it
        hold(rig, step_frames())


# The body under the arms, one row per source frame, read off the source drawings.
# dip: knee bend 0..1 (hips drop by DIP), sway: hips sideways (+ his left), thrust: hips
# forward, tilt: hips roll (+ leans his upper body to his left), lean: chest roll on top
# of that, pitch: chest leans back (+), roll/nod/turn: head tilt to his left (+), nod
# down (+), turn towards screen-left like the yaw (+).
DIP = 0.09
BODY_KEYS = ("dip", "sway", "thrust", "tilt", "lean", "pitch", "roll", "nod", "turn")
BODY = {
    #     dip   sway   thrust tilt lean pitch roll nod turn
    0:  (0.2, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    2:  (0.3, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    3:  (1.0, 0.0, -0.03, 0, 0, -6, 0, 4, 0),
    4:  (1.0, 0.0, -0.03, 0, 0, -5, 0, 3, 0),
    5:  (0.4, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    6:  (0.15, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    7:  (0.0, -0.02, 0.0, -2, 3, 0, -4, 0, 0),
    8:  (0.6, -0.04, 0.0, -3, 5, 0, 4, 0, 0),
    9:  (1.0, -0.05, 0.0, -4, 6, 0, -4, 2, 0),
    10: (0.4, -0.02, 0.0, -2, 3, 0, 4, 0, 0),
    11: (0.2, 0.0, 0.0, 0, 2, 0, 9, 2, 8),
    12: (0.6, 0.0, 0.08, 0, 0, 9, 0, 6, 12),
    13: (0.7, 0.0, 0.09, 0, 0, 10, 0, 7, 12),
    14: (0.6, 0.0, 0.08, 0, 0, 9, 3, 5, 12),
    15: (0.5, 0.0, 0.06, 0, 0, 7, 3, 3, 12),
    16: (0.1, 0.0, 0.02, 0, 0, 3, -3, -4, 10),
    17: (0.0, 0.0, 0.0, 0, 0, 2, -4, -5, 10),
    18: (0.1, 0.0, 0.02, 0, 0, 3, -3, -3, 10),
    19: (0.4, 0.0, 0.05, 0, 0, 6, 0, 2, 12),
    20: (0.5, 0.0, 0.06, 0, 0, 7, 3, 4, 12),
    21: (0.7, 0.0, 0.09, 0, 0, 10, 3, 7, 12),
    22: (0.7, 0.0, 0.08, 0, 0, 9, 0, 6, 12),
    23: (0.5, 0.0, 0.05, 0, 0, 6, 0, 3, 12),
    24: (0.2, 0.0, 0.0, 0, 2, 0, 9, 2, 8),
    25: (0.9, 0.0, 0.0, 0, 0, 0, 0, 3, 0),
    26: (0.8, -0.02, 0.0, -2, 3, 0, 4, 0, 0),
    27: (0.0, -0.06, 0.0, -5, 8, 0, -4, 0, 0),
    28: (0.9, -0.05, 0.0, -4, 6, 0, 4, 2, 0),
    29: (0.4, -0.05, 0.0, -4, 7, 0, 0, 0, 0),
    30: (0.3, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    31: (0.6, 0.0, -0.02, 0, 0, -3, 0, 2, 0),
    33: (1.0, 0.0, -0.03, 0, 0, -5, 0, 3, 0),
    34: (0.9, 0.0, -0.03, 0, 0, -4, 0, 2, 0),
    35: (0.8, 0.0, -0.02, 0, 0, -2, 0, 0, 0),
    36: (0.4, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    37: (1.0, -0.1, 0.0, -6, 11, 0, 0, 0, 0),
    38: (1.0, -0.1, 0.0, -6, 11, 0, 0, 0, 0),
    39: (0.7, -0.06, 0.0, -4, 7, 0, 0, 0, 0),
    40: (0.2, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
}


def animate_body(rig):
    pb = rig.pose.bones
    hips_rest = pb["hips"].bone.matrix_local.to_3x3().normalized()
    keys = dict(BODY)
    keys[LAYOUT["source"]["frames"]] = BODY[0]  # close the loop
    for src, row in sorted(keys.items()):
        b = dict(zip(BODY_KEYS, row))
        f = remake_frame(src)
        pb["hips"].location = hips_rest.inverted() @ Vector((b["sway"], -b["thrust"], -b["dip"] * DIP))
        pb["hips"].keyframe_insert("location", frame=f)
        for name, rot in (("hips", (0, b["tilt"], 0)), ("chest", (-b["pitch"], b["lean"], 0)),
                          ("head", (b["nod"], b["roll"], -b["turn"]))):
            pb[name].rotation_quaternion = bone_rotation(pb[name], rot)
            pb[name].keyframe_insert("rotation_quaternion", frame=f)
