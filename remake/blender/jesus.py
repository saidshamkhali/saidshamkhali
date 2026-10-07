"""The figure: Simpsons-style Jesus, modelled from code, skinned to an armature.

Feet at z=0, facing -Y, +X is his left. Proportions are measured from the
source frames: head ~26% of the height, robe to mid-calf, shoulders ~0.5 wide.

build(coll) returns the armature object; animate(rig) keys the turn and the
poses from reference/layout.json.
"""
import math

import bpy
from mathutils import Euler

from kit import LAYOUT, blobs, loft, mat, remake_frame, torus, zsec

RIG = "Jesus_Rig"

# bone: (head, tail, parent)
BONES = {
    "root": ((0, 0, 0), (0, 0, 0.3), None),
    "hips": ((0, 0, 0.9), (0, 0, 1.2), "root"),
    "chest": ((0, 0, 1.2), (0, 0, 1.5), "hips"),
    "head": ((0, 0, 1.52), (0, 0, 1.95), "chest"),
}
for _s, _x in (("L", 1), ("R", -1)):
    BONES[f"upper_arm.{_s}"] = ((0.235 * _x, 0, 1.43), (0.27 * _x, 0, 1.08), "chest")
    BONES[f"forearm.{_s}"] = ((0.27 * _x, 0, 1.08), (0.29 * _x, 0, 0.79), f"upper_arm.{_s}")
    BONES[f"hand.{_s}"] = ((0.29 * _x, 0, 0.79), (0.30 * _x, 0, 0.6), f"forearm.{_s}")


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
            eb.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
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


# --------------------------------------------------------------------------- model

def build_body(coll, rig):
    skin_m, robe_m = mat("skin"), mat("robe", 0.78)

    robe = loft("J_robe", coll, robe_m, [
        zsec(0.36, 0.265, 0.205), zsec(0.40, 0.268, 0.208), zsec(0.55, 0.258, 0.198),
        zsec(0.80, 0.240, 0.180), zsec(1.00, 0.226, 0.165), zsec(1.20, 0.232, 0.158),
        zsec(1.36, 0.240, 0.150), zsec(1.43, 0.225, 0.140), zsec(1.48, 0.170, 0.115),
        zsec(1.51, 0.090, 0.080), zsec(1.515, 0.02, 0.02),
    ], ring=32)
    skin(robe, rig, blend("hips", "chest", 1.0, 1.2))

    # V-neck: a thin tapered strip of skin lying on the chest
    vneck = []
    for i in range(7):
        z = 1.49 - 0.2 * i / 6
        half = 0.09 * (1 - i / 6) + 0.004
        front = -0.15 - 0.012 * (i / 6)
        vneck.append(zsec(z, half, 0.012, cy=front))
    skin(loft("J_vneck", coll, skin_m, vneck, ring=16), rig, rigid("chest"), subsurf=1)

    neck = loft("J_neck", coll, skin_m, [zsec(1.46, 0.075, 0.07), zsec(1.6, 0.075, 0.07)], ring=20)
    skin(neck, rig, rigid("head"))

    for side, x in (("L", 1), ("R", -1)):
        leg = loft(f"J_leg_{side}", coll, skin_m, [
            zsec(0.04, 0.055, 0.055, cx=0.095 * x), zsec(0.15, 0.062, 0.06, cx=0.095 * x),
            zsec(0.30, 0.068, 0.064, cx=0.095 * x), zsec(0.45, 0.066, 0.062, cx=0.095 * x)], ring=20)
        skin(leg, rig, rigid("root"))
        foot = blobs(f"J_foot_{side}", coll, skin_m, [
            ((0.095 * x, -0.07, 0.045), (0.07, 0.13, 0.042), (0, 0, 0)),
            ((0.095 * x, 0.02, 0.06), (0.058, 0.06, 0.05), (0, 0, 0))])
        skin(foot, rig, rigid("root"))
        sandal = blobs(f"J_sandal_{side}", coll, mat("sandal"), [
            ((0.095 * x, -0.06, 0.012), (0.085, 0.165, 0.014), (0, 0, 0)),
            ((0.095 * x, -0.1, 0.075), (0.074, 0.022, 0.016), (math.radians(-20), 0, 0))])
        skin(sandal, rig, rigid("root"))


def build_arms(coll, rig):
    skin_m, robe_m = mat("skin"), mat("robe", 0.78)
    for side, x in (("L", 1), ("R", -1)):
        sleeve = loft(f"J_sleeve_{side}", coll, robe_m, [
            zsec(1.47, 0.05, 0.05, cx=0.215 * x), zsec(1.43, 0.078, 0.078, cx=0.235 * x),
            zsec(1.30, 0.080, 0.080, cx=0.250 * x), zsec(1.08, 0.075, 0.075, cx=0.270 * x),
            zsec(0.95, 0.082, 0.082, cx=0.278 * x), zsec(0.83, 0.098, 0.098, cx=0.287 * x),
            zsec(0.79, 0.104, 0.104, cx=0.290 * x), zsec(0.785, 0.06, 0.06, cx=0.290 * x),
        ], ring=24)
        skin(sleeve, rig, blend(f"forearm.{side}", f"upper_arm.{side}", 1.03, 1.13))

        # four-finger cartoon hand hanging from the wrist, palm facing the body
        wx, wz = 0.29 * x, 0.79
        curl = math.radians(10) * x

        def at(dx, dy, dz):
            return (wx + dx * x, dy, wz + dz)
        items = [
            (at(0, 0, -0.01), (0.036, 0.036, 0.04), (0, 0, 0)),
            (at(0, 0, -0.075), (0.033, 0.062, 0.066), (0, 0, 0)),
            (at(-0.032, -0.055, -0.075), (0.021, 0.021, 0.046), (math.radians(35), 0, 0)),
        ]
        for dy in (-0.036, 0.0, 0.036):
            items.append((at(-0.006, dy, -0.155), (0.024, 0.021, 0.052), (0, curl, 0)))
        skin(blobs(f"J_hand_{side}", coll, skin_m, items, segs=20), rig, rigid(f"hand.{side}"))


def build_head(coll, rig):
    skin_m, hair_m = mat("skin"), mat("hair", 0.8)
    head = rigid("head")

    skull = loft("J_skull", coll, skin_m, [
        zsec(1.55, 0.13, 0.13), zsec(1.58, 0.155, 0.155), zsec(1.65, 0.168, 0.165),
        zsec(1.80, 0.172, 0.168), zsec(1.92, 0.168, 0.162), zsec(1.98, 0.145, 0.14),
        zsec(2.02, 0.09, 0.09), zsec(2.035, 0.02, 0.02)], ring=28)
    skin(skull, rig, head)

    eyes = blobs("J_eyes", coll, mat("white", 0.85), [
        ((0.07, -0.135, 1.855), (0.072, 0.072, 0.072), (0, 0, 0)),
        ((-0.07, -0.135, 1.855), (0.072, 0.072, 0.072), (0, 0, 0))])
    skin(eyes, rig, head)
    pupils = blobs("J_pupils", coll, mat("black"), [
        ((0.064, -0.203, 1.848), (0.014, 0.008, 0.014), (0, 0, 0)),
        ((-0.064, -0.203, 1.848), (0.014, 0.008, 0.014), (0, 0, 0))], outline=False)
    skin(pupils, rig, head, subsurf=0)
    lids = blobs("J_lids", coll, skin_m, [  # heavy upper lids: the calm, half-closed look
        ((0.07, -0.133, 1.92), (0.076, 0.076, 0.045), (math.radians(-12), 0, 0)),
        ((-0.07, -0.133, 1.92), (0.076, 0.076, 0.045), (math.radians(-12), 0, 0))])
    skin(lids, rig, head)

    nose = blobs("J_nose", coll, skin_m, [((0, -0.215, 1.785), (0.037, 0.07, 0.037), (math.radians(-10), 0, 0))])
    skin(nose, rig, head)

    beard = blobs("J_beard", coll, hair_m, [
        ((0, -0.05, 1.66), (0.186, 0.152, 0.13), (0, 0, 0)),
        ((0, -0.12, 1.575), (0.105, 0.085, 0.095), (0, 0, 0)),
        ((0.05, -0.207, 1.716), (0.072, 0.034, 0.028), (0, math.radians(18), 0)),
        ((-0.05, -0.207, 1.716), (0.072, 0.034, 0.028), (0, math.radians(-18), 0))])
    skin(beard, rig, head)

    hair = loft("J_hair", coll, hair_m, [
        zsec(1.25, 0.06, 0.03, cy=0.11), zsec(1.30, 0.15, 0.06, cy=0.11), zsec(1.38, 0.19, 0.09, cy=0.10),
        zsec(1.50, 0.21, 0.12, cy=0.09), zsec(1.62, 0.215, 0.14, cy=0.08), zsec(1.75, 0.21, 0.15, cy=0.07),
        zsec(1.88, 0.20, 0.16, cy=0.05), zsec(1.94, 0.19, 0.18, cy=0.02), zsec(1.98, 0.175, 0.175),
        zsec(2.02, 0.14, 0.14), zsec(2.045, 0.07, 0.07), zsec(2.055, 0.02, 0.02)], ring=32)
    skin(hair, rig, blend("chest", "head", 1.4, 1.55))

    halo = torus("J_halo", coll, mat("halo", 0.85), (0, 0, 2.17), 0.155, 0.012)
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
        "L": ((0, -168, 0), (-12, 0, 0), (0, 0, 90)),
        "R": ((0, 10, 0), (-12, 0, 0), (0, 0, 0)),
        "hips": (0, 0, 0),
    },
    "wave_a": {
        "L": ((0, -150, 0), (-20, 0, 0), (25, 0, 90)),
        "R": ((0, 10, 0), (-12, 0, 0), (0, 0, 0)),
        "hips": (0, 2, 0),
    },
    "wave_b": {
        "L": ((0, -178, 0), (-5, 0, 0), (-25, 0, 90)),
        "R": ((0, 10, 0), (-12, 0, 0), (0, 0, 0)),
        "hips": (0, -2, 0),
    },
    "face": {
        "L": ((-48, -22, 0), (-145, 0, 0), (0, 0, 60)),
        "R": ((-25, 32, 0), (-25, 0, 0), (0, 0, 0)),
        "hips": (0, 0, 0),
    },
    "beckon": {
        "L": ((-18, -6, 0), (-95, 0, -55), (0, 0, 0)),
        "R": ((-55, 10, 0), (-58, 0, 0), (0, 0, -90)),
        "hips": (0, 3, 0),
    },
    "beckon_b": {
        "L": ((-18, -6, 0), (-95, 0, -55), (0, 0, 0)),
        "R": ((-45, 16, 0), (-68, 0, 0), (0, 0, -90)),
        "hips": (0, -3, 0),
    },
}


def bone_rotation(pbone, euler_deg):
    """Rotation given in rest-pose axes -> the bone's local quaternion."""
    r = Euler([math.radians(a) for a in euler_deg], "XYZ").to_matrix()
    b = pbone.bone.matrix_local.to_3x3().normalized()
    return (b.inverted() @ r @ b).to_quaternion()


def animate(rig):
    pb = rig.pose.bones
    for p in pb:
        p.rotation_mode = "QUATERNION"
    previous = {}
    for key in LAYOUT["figure"]["timeline"]:
        f = remake_frame(key["frame"])
        pose = POSES[key["pose"]]
        rig.rotation_euler.z = math.radians(-key["yaw"])
        rig.keyframe_insert("rotation_euler", index=2, frame=f)
        targets = {"hips": pose["hips"]}
        for side in ("L", "R"):
            sh, el, wr = pose[side]
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
