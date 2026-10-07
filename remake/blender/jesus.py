"""The figure: Simpsons-style Jesus, modelled from code, skinned to an armature.

Feet at z=0, facing -Y, +X is his left, the top of his hair at 2.0. Proportions are measured
from the source frames and a model sheet drawn from them: head ~28% of his height, robe to
mid-calf, shoulders ~0.5 wide.

build(coll) returns the armature object; animate(rig) keys the turn and the
poses from reference/layout.json.
"""
import json
import math
import os
import random

import bpy
from mathutils import Euler, Vector

from kit import (LAYOUT, OUTLINED, REMAKE, blobs, constant, cap, hitch, hold, loft, mat, merge, remake_frame, shell, slab, smooth_outline,
                 step_frames, sweep, torus, zsec)

RIG = "Jesus_Rig"

# bone: (head, tail, parent)
BONES = {
    "root": ((0, 0, 0), (0, 0, 0.3), None),
    "hips": ((0, 0, 0.85), (0, 0, 1.15), "root"),
    "chest": ((0, 0, 1.15), (0, 0, 1.45), "hips"),
    "head": ((0, 0, 1.47), (0, 0, 1.95), "chest"),  # pivots at the neck, under the beard
}
SHOULDER = (0.222, 1.42)  # (x, z) of the joints on his left side
ELBOW = (0.262, 1.13)
WRIST = (0.284, 0.86)
LEG_X = 0.11
KNEE_Z = 0.47
ANKLE_Z = 0.09
for _s, _x in (("L", 1), ("R", -1)):
    BONES[f"upper_arm.{_s}"] = ((SHOULDER[0] * _x, 0, SHOULDER[1]), (ELBOW[0] * _x, 0, ELBOW[1]), "chest")
    BONES[f"forearm.{_s}"] = ((ELBOW[0] * _x, 0, ELBOW[1]), (WRIST[0] * _x, 0, WRIST[1]), f"upper_arm.{_s}")
    BONES[f"hand.{_s}"] = ((WRIST[0] * _x, 0, WRIST[1]), (0.29 * _x, 0, 0.64), f"forearm.{_s}")
    # legs: knees bend (a hint of bend in the rest pose tells the IK which way), feet stay
    # planted on foot bones that hang off the root, knees aim at poles in front
    BONES[f"thigh.{_s}"] = ((LEG_X * _x, 0, 0.85), (LEG_X * _x, -0.015, KNEE_Z), "hips")
    BONES[f"shin.{_s}"] = ((LEG_X * _x, -0.015, KNEE_Z), (LEG_X * _x, 0, ANKLE_Z), f"thigh.{_s}")
    BONES[f"foot.{_s}"] = ((LEG_X * _x, 0, ANKLE_Z), (LEG_X * _x, -0.2, 0.03), "root")
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
# Proportions, in units where the top of his hair is at 2.0 and his soles at 0, measured from
# the source frames and the model sheet: head (hair top to beard tip) ~28% of his height,
# eyes at 1.78, beard tip at 1.40, shoulders at 1.40, hem at 0.38, back hair down to 1.34.

# Robe: horizontal ellipses (z, rx, ry, cy). Long and nearly straight, a soft belly pushing
# the front out (cy), the hem at mid-calf.
ROBE = [
    (0.4, 0.257, 0.205, 0.0), (0.44, 0.255, 0.203, 0.0), (0.6, 0.246, 0.197, -0.01),
    (0.8, 0.236, 0.191, -0.02), (0.95, 0.229, 0.186, -0.024), (1.08, 0.222, 0.177, -0.016),
    (1.2, 0.217, 0.168, -0.006), (1.32, 0.216, 0.16, 0.0), (1.4, 0.212, 0.154, 0.0),
    (1.44, 0.2, 0.146, 0.0), (1.47, 0.176, 0.132, 0.0), (1.495, 0.136, 0.112, 0.0), (1.512, 0.085, 0.085, 0.0),
    (1.52, 0.04, 0.04, 0.0), (1.524, 0.0, 0.0, 0.0),
]
HEM_Z = ROBE[0][0]


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
                ring=48)
    for v in robe.data.vertices:  # a soft wave along the hem, like loose cloth
        k = smooth(HEM_Z + 0.22, HEM_Z, v.co.z)
        if k > 0:
            th = math.atan2(v.co.x, -v.co.y)
            f = 1 + 0.028 * k * math.sin(5 * th + 0.8)
            v.co.x *= f
            v.co.y *= f
    skin(robe, rig, robe_weights)

    # V-neck: skin showing through the collar, a thin patch lying on the robe, deep as on the sheet
    def vneck_surf(u, v):
        z = 1.35 + 0.16 * v
        rx, ry, cy = robe_ring(z)
        half = math.radians(34) * v ** 0.85
        th = (2 * u - 1) * half
        return Vector((rx * math.sin(th), cy - ry * math.cos(th), z))

    skin(shell("J_vneck", coll, skin_m, vneck_surf, 8, 12, lambda u, v: 0.006, inner=0.006),
         rig, rigid("chest"))
    # the neck rising out of the collar, under the beard
    skin(loft("J_neck", coll, skin_m, [zsec(1.4, 0.082, 0.074, cy=0.0), zsec(1.52, 0.084, 0.076, cy=-0.005),
                                         zsec(1.64, 0.086, 0.08, cy=-0.01)],
              ring=24), rig, blend("chest", "head", 1.47, 1.53))

    for side, x in (("L", 1), ("R", -1)):
        # the leg runs up under the robe so bent knees never open a gap at the hem
        leg = loft(f"J_leg_{side}", coll, skin_m, [
            zsec(z, r, r * 0.95, cx=LEG_X * x) for z, r in
            ((0.05, 0.062), (0.12, 0.068), (0.24, 0.074), (0.38, 0.075), (0.55, 0.074), (0.72, 0.072), (0.9, 0.068))],
            ring=20)
        skin(leg, rig, blend(f"shin.{side}", f"thigh.{side}", KNEE_Z - 0.06, KNEE_Z + 0.06))
        skin(build_foot(coll, side, x), rig, rigid(f"foot.{side}"))
        skin(build_sandal(coll, side, x), rig, rigid(f"foot.{side}"))


def foot_frame(x):
    """Place foot geometry: local (across, forward, up) -> world, toes turned out a little."""
    turn = math.radians(9) * x

    def at(a, f, u):
        dx, dy = a, -f
        return (LEG_X * x + dx * math.cos(turn) - dy * math.sin(turn), dx * math.sin(turn) + dy * math.cos(turn), u)
    return at, turn


def build_foot(coll, side, x):
    """A big Simpsons foot: a rounded body, a heel, and four toes peeking out of the sandal."""
    skin_m = mat("skin")
    at, turn = foot_frame(x)
    parts = [blobs(f"_foot_{side}", coll, skin_m, [
        (at(0, 0.09, 0.05), (0.072, 0.14, 0.045), (0, 0, turn)),
        (at(0, -0.005, 0.062), (0.064, 0.064, 0.056), (0, 0, turn))], segs=24)]
    toes = [(-0.047, 0.212, 0.022), (-0.016, 0.228, 0.024), (0.016, 0.226, 0.023), (0.046, 0.21, 0.021)]
    if x < 0:
        toes = [(-a, f, r) for a, f, r in toes]
    parts.append(blobs(f"_toes_{side}", coll, skin_m,
                       [(at(a, f, 0.044), (r, r * 1.2, r * 0.9), (0, 0, turn)) for a, f, r in toes], segs=16))
    return merge(f"J_foot_{side}", coll, skin_m, parts)


def build_sandal(coll, side, x):
    """A thick dark sole a little bigger than the foot, and a broad strap over the forefoot."""
    sole_m = mat("sandal")
    at, turn = foot_frame(x)
    sole = [(0.0, -0.08), (0.058, -0.074), (0.08, 0.0), (0.088, 0.12), (0.082, 0.21), (0.05, 0.26),
            (0.0, 0.272), (-0.05, 0.26), (-0.082, 0.21), (-0.088, 0.12), (-0.08, 0.0), (-0.058, -0.074)]
    pts = smooth_outline(sole, 40)
    s = slab(f"_sole_{side}", coll, sole_m, [(a, f) for a, f in pts], 0.034, plane="XZ", offset=0.0, bevel=0.01)
    # slab() lays the outline in XZ; turn it flat and into place
    for v in s.data.vertices:
        a, depth, f = v.co.x, v.co.y, v.co.z
        p = at(a, f, 0.017 + depth)
        v.co = Vector(p)
    strap = sweep(f"_strap_{side}", coll, sole_m,
                  [at(-0.078, 0.13, 0.034), at(-0.05, 0.135, 0.088), at(0.0, 0.138, 0.104),
                   at(0.05, 0.135, 0.088), at(0.078, 0.13, 0.034)], [0.024], n=16, ring=12, squash=0.45)
    return merge(f"J_sandal_{side}", coll, sole_m, [s, strap])


def build_arms(coll, rig):
    robe_m = mat("robe", 0.78)
    # Each sleeve is two rigid tubes with round ends meeting at the elbow pivot, so a
    # hard bend (hand to face) can't fold the mesh into itself and flip its outline.
    er = 0.066  # sleeve radius at the elbow

    def dome(cx, z, r, down):
        return [zsec(z + (-1 if down else 1) * r * a, r * math.sqrt(1 - a * a), r * math.sqrt(1 - a * a), cx=cx)
                for a in (0.45, 0.75, 0.93)]

    for side, x in (("L", 1), ("R", -1)):
        sx, sz = SHOULDER
        ex, ez = ELBOW
        wx, wz = WRIST
        upper = [zsec(sz + 0.045, 0.03, 0.03, cx=(sx - 0.03) * x), zsec(sz + 0.025, 0.055, 0.055, cx=(sx - 0.008) * x),
                 zsec(sz - 0.03, 0.064, 0.064, cx=sx * x), zsec(sz - 0.13, 0.066, 0.066, cx=(sx + 0.016) * x),
                 zsec(ez, er, er, cx=ex * x)]
        skin(loft(f"J_sleeve_{side}", coll, robe_m, upper + dome(ex * x, ez, er, True), ring=24),
             rig, rigid(f"upper_arm.{side}"))
        lower = [zsec(ez, er, er, cx=ex * x), zsec(ez - 0.13, 0.068, 0.068, cx=(ex + 0.009) * x),
                 zsec(wz + 0.03, 0.08, 0.08, cx=(wx - 0.003) * x), zsec(wz, 0.086, 0.086, cx=wx * x),
                 zsec(wz - 0.004, 0.055, 0.055, cx=wx * x)]
        skin(loft(f"J_cuff_{side}", coll, robe_m, dome(ex * x, ez, er, False)[::-1] + lower, ring=24),
             rig, rigid(f"forearm.{side}"))
        skin(build_hand(coll, side, x), rig, rigid(f"hand.{side}"))


HAND = 1.22  # Simpsons hands are big: the palm is about the size of an eye


def hand_mesh(coll, side, x, curl):
    """Simpsons hand (thumb + three fingers) hanging from the wrist, palm facing the body,
    thumb forward. curl 0: fingers straight and fanned a little; 1: bent down into a cup (the
    beckoning "come here"), not a fist."""
    skin_m = mat("skin")
    wx, wz = WRIST
    wx *= x
    k = HAND

    def at(dx, dy, dz):
        return (wx + dx * k * x, dy * k, wz + dz * k)

    def finger(dy, length, c):
        """Base, knuckle, tip: straight down at c=0, folded towards the palm (-dx) at c=1."""
        spread = dy * 0.45 * (1 - c)
        base = (0.0, dy, -0.095)
        a1, a2 = math.radians(8 + 64 * c), math.radians(16 + 92 * c)  # bend at the knuckle, then the tip: a cup
        l1, l2 = length * 0.55, length * 0.45
        mid = (base[0] - l1 * math.sin(a1), dy + spread * 0.6, base[2] - l1 * math.cos(a1))
        tip = (mid[0] - l2 * math.sin(a2), dy + spread, mid[2] - l2 * math.cos(a2))
        return [at(*base), at(*mid), at(*tip)]

    parts = [blobs(f"_palm_{side}", coll, skin_m, [
        (at(0, 0, -0.004), (0.03 * k, 0.034 * k, 0.04 * k), (0, 0, 0)),
        (at(0, 0.004, -0.068), (0.028 * k, 0.054 * k, 0.056 * k), (0, 0, 0))], segs=24)]
    for n, (dy, length) in enumerate(((-0.034, 0.078), (0.0, 0.086), (0.034, 0.078))):
        parts.append(sweep(f"_finger{n}_{side}", coll, skin_m, finger(dy, length, curl),
                           [0.0185 * k, 0.019 * k, 0.0195 * k], n=10, ring=14))
    tc = 0.5 * curl
    parts.append(sweep(f"_thumb_{side}", coll, skin_m,
                       [at(-0.006, -0.03, -0.04), at(-0.016 - 0.02 * tc, -0.068 + 0.012 * tc, -0.07),
                        at(-0.024 - 0.04 * tc, -0.082 + 0.03 * tc, -0.105 + 0.02 * tc)],
                       [0.019 * k, 0.0185 * k, 0.018 * k], n=10, ring=14))
    return merge(f"J_hand_{side}", coll, skin_m, parts)


def build_hand(coll, side, x):
    """The open hand, with a "curl" shape key that folds the fingers into the palm."""
    hand = hand_mesh(coll, side, x, 0.0)
    curled = hand_mesh(coll, side, x, 1.0)
    hand.shape_key_add(name="Basis")
    key = hand.shape_key_add(name="curl")
    for v, w in zip(key.data, curled.data.vertices):
        v.co = w.co
    data = curled.data
    if curled in OUTLINED:
        OUTLINED.remove(curled)
    bpy.data.objects.remove(curled, do_unlink=True)
    bpy.data.meshes.remove(data)
    hand["outline_even"] = False  # folded fingers make sharp creases that spike an even outline
    return hand


# Head surface: horizontal ellipses (z, rx, ry, cy), face towards -Y. A tall Simpsons dome
# down to the jaw, which ends at the chin just under the mouth; the goatee hangs below that,
# in front of a thick neck. Measured on the model sheet (hair top 2.0, soles 0).
SKULL = [
    (1.583, 0.02, 0.02, -0.072), (1.595, 0.068, 0.062, -0.062), (1.62, 0.1, 0.098, -0.044),
    (1.66, 0.118, 0.122, -0.024), (1.71, 0.124, 0.134, -0.01), (1.77, 0.123, 0.138, 0.0),
    (1.84, 0.12, 0.137, 0.0), (1.89, 0.113, 0.129, 0.0), (1.93, 0.098, 0.112, 0.0),
    (1.958, 0.074, 0.085, 0.0), (1.975, 0.042, 0.048, 0.0), (1.981, 0.0, 0.0, 0.0),
]
EYE_R = 0.047
EYE_X = 0.069
EYE_Z = 1.79
EYE_Y = -0.112
HANG_Z = 1.7    # below this the hair hangs straight instead of following the head
MUZZLE = 0.045  # how far the Simpsons muzzle (moustache, lip, chin) juts out of the face
HAIR_TOP = 0.02  # hair thickness on the crown
EAR_Z = 1.725


def hair_top():
    """Height of the top of the hair above his feet (the camera frames on it)."""
    return SKULL[-1][0] + HAIR_TOP


def muzzle(z):
    return MUZZLE * smooth(1.585, 1.625, z) * (1 - smooth(1.67, 1.73, z))


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

    steps = 48
    z0, z1 = SKULL[0][0], SKULL[-1][0]
    rows = []
    for i in range(steps + 1):
        z = z0 + (z1 - z0) * i / steps
        rx, ry, cy = skull_ring(z)
        rows.append(zsec(z, max(rx, 0.004), max(ry, 0.004), cy=cy))
    skull = loft("J_skull", coll, skin_m, rows, ring=40)
    for v in skull.data.vertices:  # push the muzzle out, exactly as head_point() does
        rx, ry, cy = skull_ring(v.co.z)
        c = -(v.co.y - cy) / max(ry, 1e-4)
        if c > 0:
            v.co.y -= muzzle(v.co.z) * c ** 3
    skin(skull, rig, head)

    # Simpsons ears: a C-shaped rim opening towards the face, lying on the side of the head
    for x, side in ((1, "L"), (-1, "R")):
        th = math.radians(93) * x
        base = head_point(th, EAR_Z)
        rim = []
        for k in range(9):  # from the top front, round the back, to the lobe at the bottom front
            a = math.radians(-70 + 290 * k / 8)
            rim.append(base + outward(th) * 0.014 + Vector((0, 0.022 * math.sin(a), 0.036 * math.cos(a))))
        parts = [sweep(f"_ear_rim_{side}", coll, skin_m, rim, [0.011, 0.012, 0.012, 0.012, 0.012, 0.012, 0.012, 0.013, 0.014],
                       n=24, ring=12, squash=0.7, up=tuple(outward(th))),
                 blobs(f"_ear_bowl_{side}", coll, skin_m, [(base + outward(th) * 0.004, (0.01, 0.02, 0.03), (0, 0, 0))])]
        skin(merge(f"J_ear_{side}", coll, skin_m, parts), rig, head)

    # eyes: big Simpsons balls bulging out of the face, a nose-width apart
    eyes, pupils = [], []
    look = math.radians(10)  # a calm gaze, the pupils right under the heavy lids
    for x in (1, -1):
        c = Vector((EYE_X * x, EYE_Y, EYE_Z))
        eyes.append((c, (EYE_R,) * 3, (0, 0, 0)))
        d = Vector((0.06 * -x, -math.cos(look), -math.sin(look))).normalized()  # a touch cross-eyed, as drawn
        pupils.append((c + d * EYE_R * 0.98, (0.011, 0.004, 0.011), (look, 0, 0)))
    skin(blobs("J_eyes", coll, mat("white", 0.93), eyes), rig, head)
    skin(blobs("J_pupils", coll, mat("black"), pupils, outline=False), rig, head, subsurf=0)
    # heavy upper lids: level caps over the top half of each eye, relaxed and half-closed
    for x, side in ((1, "L"), (-1, "R")):
        c = Vector((EYE_X * x, EYE_Y, EYE_Z))
        skin(cap(f"J_lid_{side}", coll, skin_m, c, EYE_R * 1.07, -0.02, rot=(math.radians(-4), 0, 0)), rig, head)

    # nose: the long Simpsons sausage from between the eyes, pointing forward and a little down
    skin(sweep("J_nose", coll, skin_m, [(0, -0.115, 1.758), (0, -0.168, 1.74), (0, -0.212, 1.724)],
               [0.022, 0.024, 0.029], n=12, ring=20), rig, head)

    # handlebar moustache: thick under the nose, sweeping out over the cheeks, the ends drooping
    for x, side in ((1, "L"), (-1, "R")):
        pts = [head_point(math.radians(a) * x, z) + outward(math.radians(a) * x) * off
               for a, z, off in ((0, 1.685, 0.03), (15, 1.684, 0.034), (32, 1.674, 0.04), (48, 1.656, 0.048))]
        # the handlebar ends leave the face: out past the cheeks, drooping, with a little upturn
        end = pts[-1]
        pts += [end + Vector((0.036 * x, 0.012, -0.024)), end + Vector((0.06 * x, 0.022, -0.038)),
                end + Vector((0.075 * x, 0.03, -0.033))]
        skin(sweep(f"J_moustache_{side}", coll, hair_m, pts, [0.037, 0.044, 0.042, 0.034, 0.024, 0.014, 0.006],
                   n=28, ring=18, squash=0.74), rig, head)
    # lower lip: the yellow band showing between moustache and goatee
    lip = [head_point(math.radians(a), 1.628) + outward(math.radians(a)) * 0.004 for a in (-26, 0, 26)]
    skin(sweep("J_lip", coll, skin_m, lip, [0.013], n=10, ring=12, squash=0.8), rig, head)

    # goatee: a pointed tuft hanging from the chin in front of the neck, flattened front to back
    chin = head_point(0, 1.608)
    goatee = [(1.609, 0.052, 0.034, 0.022), (1.6, 0.06, 0.038, 0.016), (1.57, 0.058, 0.036, 0.01),
              (1.535, 0.046, 0.03, 0.006), (1.5, 0.028, 0.022, 0.004), (1.474, 0.01, 0.01, 0.004),
              (1.466, 0.002, 0.002, 0.004)]
    skin(loft("J_goatee", coll, hair_m, [zsec(z, rx, ry, cy=chin.y + dy + ry * 0.2) for z, rx, ry, dy in goatee],
              ring=24), rig, head)
    # beard band: along the jaw from the goatee up to the sideburns in front of the ears
    span = math.radians(98)

    def band_surf(u, v):  # the chin itself is under the goatee, so the band only runs from its sides
        th = math.copysign(span * (0.3 + 0.7 * abs(2 * u - 1)), 2 * u - 1)
        a = abs(th) / span
        bottom = 1.584 + 0.012 * a
        top = 1.605 + 0.13 * smooth(0.3, 1.0, a) ** 1.2
        return head_point(th, bottom + (top - bottom) * v)

    def band_thick(u, v):  # full under the jaw, thin where it climbs to the sideburns
        a = abs(2 * u - 1)
        return 0.01 + 0.022 * math.sin(math.pi * v) ** 0.6 * (1 - 0.6 * a)

    for half, side in ((0, "R"), (1, "L")):
        skin(shell(f"J_beard_{side}", coll, hair_m, lambda u, v, h=half: band_surf(0.5 * h + 0.5 * u, v),
                   22, 8, band_thick), rig, head)

    # hair: a cap with a centre parting and two fringe locks falling over the forehead corners,
    # covering the temples down to the ears, then a long mass hanging behind the ears to just
    # below the shoulders
    def hair_low(th):
        a = abs(math.degrees(th))
        parting = 0.018 * math.exp(-(a / 5) ** 2)
        arch = -0.085 * (min(a, 62) / 62) ** 1.6  # a high forehead, the hairline arching down to the sides
        locks = -0.045 * math.exp(-((a - 60) / 9) ** 2)  # locks falling at the forehead corners
        ragged = 0.007 * math.sin(15 * th) * (1 - smooth(50, 80, a))
        hairline = 1.945 + parting + arch + locks + ragged
        temple = hairline + (EAR_Z + 0.045 - hairline) * smooth(64, 86, a)  # over the ear tops
        curtain = 1.345 + 0.02 * math.sin(7 * th) + 0.05 * smooth(150, 108, a)  # wavy, higher at the sides
        return temple + (curtain - temple) * smooth(108, 126, a)  # the long hair hangs behind the ears and neck

    def hair_surf(u, v):
        th = math.pi * (2 * u - 1)  # u=0.5 is the front
        lo = hair_low(th)
        z = lo + (SKULL[-1][0] - lo) * v
        if z >= HANG_Z:
            return head_point(th, z)
        p = head_point(th, HANG_Z)
        drop = HANG_Z - z
        wavy = 0.05 * math.sin(drop * 24 + th * 3) * min(1.0, drop * 6)
        # spreads out sideways over the shoulders, less front to back
        return Vector((p.x * (1 + 1.25 * drop + wavy), p.y * (1 + 0.45 * drop + wavy) + 0.02 * drop, z))

    def hair_thick(u, v):
        th = math.pi * (2 * u - 1)
        back = 0.5 - 0.5 * math.cos(th)  # 0 front, 1 back
        wave = 0.5 + 0.5 * math.sin(11 * th)  # lumpy locks show on the silhouette
        side = math.sin(th) ** 2 * (1 - smooth(0.0, 0.75, v))  # puffy round the face and down the sides
        volume = 0.012 * math.sin(math.pi * min(1.0, v * 1.6)) * (1 - v)  # rounds the top of the head
        return HAIR_TOP + volume + (0.04 * back + 0.016 * side + 0.012 * wave) * (1 - v) ** 1.1  # pole closes

    skin(shell("J_hair", coll, hair_m, hair_surf, 84, 36, hair_thick, wrap_u=True),
         rig, blend("chest", "head", 1.45, 1.56))

    # locks: flattened, wavy tubes lying on the hanging hair, ending at uneven lengths; their
    # outlines draw the strands and break up the bottom edge, like the source's scribbly hair
    rnd = random.Random(1998)
    lock_parts = []
    angles = [a for a in range(104, 181, 11)]
    for n, deg in enumerate([d * s for d in angles for s in (1, -1) if d * s != -180]):
        th = math.radians(deg + rnd.uniform(-3, 3))
        u = (th / math.pi + 1) / 2
        out = Vector((math.sin(th), -math.cos(th), 0))
        side = out.cross(Vector((0, 0, 1)))
        pts = []
        for k, v in enumerate((0.5, 0.36, 0.24, 0.13, 0.05, 0.0)):
            p = hair_surf(u, v)
            p = p + out * (hair_thick(u, v) + 0.004) + side * 0.012 * math.sin(k * 1.7 + n)
            pts.append(p)
        end = pts[-1] + Vector((0, 0, -rnd.uniform(0.0, 0.06))) + side * rnd.uniform(-0.02, 0.02)
        pts.append(end)
        r = rnd.uniform(0.026, 0.034)
        lock_parts.append(sweep(f"_lock{n}", coll, hair_m, pts, [r, r * 1.05, r, r * 0.9, r * 0.7, r * 0.5, r * 0.25],
                                n=18, ring=12, squash=0.4, up=tuple(out)))
    locks = merge("J_locks", coll, hair_m, lock_parts)
    locks["outline_even"] = False
    skin(locks, rig, blend("chest", "head", 1.45, 1.56))

    halo = torus("J_halo", coll, mat("halo", 0.9), (0, 0, 2.2), 0.2, 0.008, rot=(math.radians(-12), 0, 0))
    halo["outline_px"] = 1.2  # a fine line: the source's halo is faint
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
        "R": ((-4, 16, 0), (-32, 22, 0), (0, 0, -20)),
    },
    "wave_a": {
        "L": ((0, -178, 0), (-10, 0, -14), (28, 0, 90)),
        "R": ((-4, 18, 0), (-38, 26, 0), (10, 0, -30)),
    },
    "wave_b": {
        "L": ((0, -186, 0), (-4, 0, 12), (-22, 0, 90)),
        "R": ((-4, 15, 0), (-34, 22, 0), (-5, 0, -30)),
    },
    "face": {
        "L": ((-48, -22, 0), (-145, 0, 0), (0, 0, 60)),
        "R": ((-8, 2, 0), (-42, 10, 0), (0, 0, -20)),
    },
    "beckon": {  # left hand resting across his waist, right palm down, fingers drooping
        "L": ((-8, -5, 0), (-80, 0, -48), (0, 0, 0)),
        "R": ((-20, 14, 0), (-64, 0, 0), (0, 0, 90)),
    },
    "beckon_b": {
        "L": ((-8, -5, 0), (-80, 0, -48), (0, 0, 0)),
        "R": ((-16, 18, 0), (-68, 0, 0), (0, 0, 90)),
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
    # the fitted slide keys the rig's location, so remember where it stands
    if "base_location" not in rig:
        rig["base_location"] = list(rig.location)
    rig.location = rig["base_location"]
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
        apply_fit(rig)
        aim_head(rig)
        apply_reuse(rig)
        hitch(rig)
    animate_hands(rig)


# Finger curl per source frame, read off the drawings: the beckoning hand (his right) folds
# its fingers down twice ("come here"); the other hand rests half-curled on his belly.
CURL = {
    "R": {0: 0.2, 11: 0.3, 12: 0.0, 13: 0.0, 14: 1.0, 15: 1.0, 16: 0.6, 17: 0.0, 18: 0.0, 19: 0.45,
          20: 0.55, 21: 1.0, 22: 1.0, 23: 0.0, 24: 0.2},
    "L": {0: 0.0, 11: 0.15, 12: 0.3, 24: 0.3, 25: 0.0},
}


def animate_hands(rig):
    """Key each hand's curl shape key on every source frame, held like the rest."""
    n = LAYOUT["source"]["frames"]
    for side, table in CURL.items():
        hand = bpy.data.objects.get(f"J_hand_{side}")
        if hand is None or hand.data.shape_keys is None:
            continue
        kb = hand.data.shape_keys.key_blocks["curl"]
        keys = sorted(table)
        held = set(LAYOUT["source"].get("held_frames", []))
        for k in range(n + 1):
            src = REUSE.get(k % n, (k % n,))[0]
            while src in held:  # a held frame repeats the one before it
                src -= 1
            prev = max(x for x in keys if x <= src)
            kb.value = table[prev]
            kb.keyframe_insert("value", frame=remake_frame(k))
        ad = hand.data.shape_keys.animation_data
        bag = ad.action.layers[0].strips[0].channelbag(ad.action_slot) if ad and ad.action else None
        for fc in (bag.fcurves if bag else []):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


# --------------------------------------------------------------------------- fitted offsets
# reference/pose_fit.json holds, per source frame, small offsets found by fitting the figure's
# silhouette to the original GIF frame by frame (see fit_pose.py): how far he slides across
# the screen, the turn, the dip, the lean and the arm angles. They sit on top of the
# designed poses above, so the poses stay readable and the fit only nudges them.
FIT_PARAMS = ("slide", "yaw", "dip", "tilt", "pitch", "armL_x", "armL_y", "elbowL", "armR_x", "armR_y", "elbowR")
FIT_FILE = os.path.join(REMAKE, "reference", "pose_fit.json")


def load_fit():
    if not os.path.exists(FIT_FILE):
        return {}
    with open(FIT_FILE, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["frames"].items()}


def screen_right():
    """The camera's right vector on the ground plane (the fitted slide moves along it)."""
    cam = bpy.context.scene.camera
    if cam is None:
        return Vector((1, 0, 0))
    r = cam.matrix_world.to_3x3() @ Vector((1, 0, 0))
    r.z = 0
    return r.normalized()


def apply_offsets(rig, p, right=None):
    """Add one frame's fitted offsets to the pose the rig is in now (not keyed)."""
    get = lambda k: p.get(k, 0.0)  # noqa: E731
    pb = rig.pose.bones
    rig.location += (right or screen_right()) * get("slide")
    rig.rotation_euler.z += math.radians(-get("yaw"))
    hips_rest = pb["hips"].bone.matrix_local.to_3x3().normalized()
    pb["hips"].location += hips_rest.inverted() @ Vector((0, 0, -get("dip")))
    for name, rot in (("hips", (0, get("tilt"), 0)), ("chest", (-get("pitch"), 0, 0)),
                      ("upper_arm.L", (get("armL_x"), get("armL_y"), 0)), ("forearm.L", (get("elbowL"), 0, 0)),
                      ("upper_arm.R", (get("armR_x"), get("armR_y"), 0)), ("forearm.R", (get("elbowR"), 0, 0))):
        if any(rot):
            pb[name].rotation_quaternion = bone_rotation(pb[name], rot) @ pb[name].rotation_quaternion


# Where his face points, read off the drawings: degrees towards screen-left, 0 facing us. In
# every front-facing frame he looks off to screen-left, a three-quarter view, whichever way
# his body faces. Frames not listed keep the head in line with the body (the turns).
HEAD_YAW = {5: 70, 6: 47, 7: 47, 8: 40, 9: 35, 10: 45, 11: 45, 12: 55, 13: 55, 14: 55, 15: 55, 16: 52,
            17: 52, 18: 52, 19: 55, 20: 55, 21: 55, 22: 55, 23: 55, 24: 45, 25: 40, 26: 40, 27: 35,
            28: 15, 29: 10, 30: -25, 31: -40}


def aim_head(rig):
    """Turn the head (about the neck) so the face points where HEAD_YAW says, given the
    body's own turn on that frame."""
    from kit import fcurves
    scene = bpy.context.scene
    pb = rig.pose.bones["head"]
    for k, target in HEAD_YAW.items():
        f = remake_frame(k)
        scene.frame_set(int(f), subframe=f - int(f))
        body = -math.degrees(rig.rotation_euler.z)
        turn = (target - body + 180) % 360 - 180
        pb.rotation_quaternion = bone_rotation(pb, (0, 0, -turn)) @ pb.rotation_quaternion
        pb.keyframe_insert("rotation_quaternion", frame=f)
    for fc in fcurves(rig):
        if fc.data_path.endswith('"head"].rotation_quaternion'):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


# The second wave reuses the first wave's drawings, slid across: frame: (drawing reused,
# shift in source pixels, extra fit offsets), measured by matching the GIF's silhouettes to
# each other and tracking where the head went.
REUSE = {24: (11, 5, {}), 25: (10, 3, {"tilt": -4.5}), 27: (9, 0, {})}  # 25: the body slides, the head stays


def source_px():
    """World units per source-GIF pixel at the figure (falls back to a measured value)."""
    cam = bpy.context.scene.camera
    rig = bpy.data.objects.get(RIG)
    if cam is None or rig is None:
        return 0.0145
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    depth = (Vector(rig["base_location"]) - cam.matrix_world.translation).dot(fwd)
    return 2 * depth * (cam.data.sensor_width / 2 / cam.data.lens) / LAYOUT["source"]["width"]


def apply_reuse(rig):
    """Key the reused frames as copies of the frames they reuse, shifted across the screen."""
    from kit import fcurves
    right, px = screen_right(), source_px()
    scene = bpy.context.scene
    for k, (j, dx, extra) in REUSE.items():
        fk, fj = remake_frame(k), remake_frame(j)
        for fc in fcurves(rig):
            v = fc.evaluate(fj)
            if fc.data_path == "location":
                v += right[fc.array_index] * dx * px
            for kp in fc.keyframe_points:
                if abs(kp.co.x - fk) < 1e-3:
                    kp.co.y = v
            fc.update()
        if extra:
            scene.frame_set(int(fk), subframe=fk - int(fk))
            apply_offsets(rig, extra, right)
            for name in ("hips", "chest", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R"):
                rig.pose.bones[name].keyframe_insert("rotation_quaternion", frame=fk)
    constant(rig)


def apply_fit(rig):
    """Bake the fitted offsets into the held keys, one source frame at a time."""
    fit = load_fit()
    if not fit:
        return
    scene = bpy.context.scene
    right = screen_right()
    channels = [(rig, "location"), (rig, "rotation_euler")]
    for name in ("hips", "chest", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R"):
        pb = rig.pose.bones[name]
        channels += [(pb, "location"), (pb, "rotation_quaternion")]
    for k, p in sorted(fit.items()):
        f = remake_frame(k)
        scene.frame_set(int(f), subframe=f - int(f))
        rig.location = rig["base_location"]  # the slide is keyed here, so don't let it pile up
        apply_offsets(rig, p, right)
        for owner, path in channels:
            owner.keyframe_insert(path, frame=f)
    constant(rig)


# The body under the arms, one row per source frame, read off the source drawings.
# dip: knee bend 0..1 (hips drop by DIP), sway: hips sideways (+ his left), thrust: hips
# forward, tilt: hips roll (+ leans his upper body to his left), lean: chest roll on top
# of that, pitch: chest leans back (+), roll/nod/turn: head tilt to his left (+), nod
# down (+), turn towards screen-left like the yaw (+). The turn is mostly set by HEAD_YAW,
# after the fit has settled how his body faces.
DIP = 0.09
BODY_KEYS = ("dip", "sway", "thrust", "tilt", "lean", "pitch", "roll", "nod", "turn")
BODY = {
    #     dip   sway   thrust tilt lean pitch roll nod turn
    0:  (0.2, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    2:  (0.3, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    3:  (1.0, 0.0, -0.03, 0, 0, -6, 0, 4, 0),
    4:  (1.0, 0.0, -0.03, 0, 0, -5, 0, 3, 0),
    5:  (0.4, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    6:  (0.75, 0.0, 0.0, 0, -3, 0, 0, 0, 0),
    7:  (0.6, -0.02, 0.0, -2, -1, 0, -4, 0, 0),
    8:  (0.6, -0.04, 0.0, -3, 1, 0, 4, 0, 0),
    9:  (1.0, -0.05, 0.0, -4, 6, 0, -4, 2, 0),
    10: (0.4, -0.02, 0.0, -2, 0, 0, 4, 0, 0),
    11: (0.2, 0.0, 0.0, 0, 2, 0, 9, 2, 0),
    12: (0.3, 0.0, 0.08, 0, 0, 9, 0, 6, 0),
    13: (0.4, 0.0, 0.09, 0, 0, 10, 0, 7, 0),
    14: (0.3, 0.0, 0.08, 0, 0, 9, 3, 5, 0),
    15: (0.2, 0.0, 0.06, 0, 0, 7, 3, 3, 0),
    16: (0.0, 0.0, 0.02, 0, 0, 3, -3, -4, 0),
    17: (0.0, 0.0, 0.0, 0, 0, 2, -4, -5, 0),
    18: (0.0, 0.0, 0.02, 0, 0, 3, -3, -3, 0),
    19: (0.0, 0.0, 0.05, 0, 0, 6, 0, 2, 0),
    20: (0.0, 0.0, 0.06, 0, 0, 7, 3, 4, 0),
    21: (0.1, 0.0, 0.09, 0, 0, 10, 3, 7, 0),
    22: (0.4, 0.0, 0.08, 0, 0, 9, 0, 6, 0),
    23: (0.35, 0.0, 0.05, 0, 0, 6, 0, 3, 0),
    24: (0.2, 0.0, 0.0, 0, 2, 0, 9, 2, 0),
    25: (0.9, 0.0, 0.0, 0, -5, 0, 0, 3, 0),
    26: (0.8, -0.02, 0.0, -2, -2, 0, 4, 0, 0),
    27: (0.8, -0.06, 0.0, -5, 3, 0, -4, 0, 0),
    28: (1.8, -0.05, 0.0, -4, 0, 0, 4, 2, 0),
    29: (0.4, -0.05, 0.0, -4, 3, 0, 0, 0, 0),
    30: (0.3, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    31: (0.6, 0.0, -0.02, 0, 0, -3, 0, 2, 0),
    33: (1.0, 0.0, -0.03, 0, 0, -5, 0, 3, 0),
    34: (0.9, 0.0, -0.03, 0, 0, -4, 0, 2, 0),
    35: (0.8, 0.0, -0.02, 0, 0, -2, 0, 0, 0),
    36: (0.4, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
    37: (1.0, -0.1, 0.0, -6, 11, 0, 0, 0, 0),
    38: (1.0, -0.1, 0.0, -6, 11, 0, 0, 0, 0),
    39: (0.7, -0.06, 0.0, -4, 7, 0, 0, 0, 0),
    40: (0.5, 0.0, 0.0, 0, 0, 0, 0, 0, 0),
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
