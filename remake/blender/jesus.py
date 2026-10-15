"""The figure: Simpsons-style Jesus, modelled from code and rigged in layers, the way animators
rig a robed figure: a skeleton, a hidden body skinned to it, and the robe riding on the body.

Feet at z=0, facing -Y, +X is his left, the top of his hair at 2.0. Proportions are measured
from the source frames (upscaled, see the README) and a model sheet drawn from them: head ~28%
of his height, robe to just below the knee, shoulders ~0.5 wide.

build(coll) returns the armature object; animate(rig) keys the turn and the
poses from reference/layout.json.
"""
import json
import math
import os

import bpy
from mathutils import Euler, Vector

from kit import (LAYOUT, REMAKE, add_shape, blobs, constant, cap, hitch, hold, lathe, loft, mat, merge, remake_frame, shell, slab, smooth_outline,
                 step_frames, sweep, zsec)

RIG = "Jesus_Rig"

# The skeleton. The hips are their own bone under a "torso" control, so they swing out while
# a two-bone spine keeps the shoulders where they were (with the chest hanging off the hips,
# moving the hips dragged his whole upper body along).
# bone: (head, tail, parent)
BONES = {
    "root": ((0, 0, 0), (0, 0, 0.3), None),
    "torso": ((0, 0, 1.0), (0, 0, 1.2), "root"),  # control: lowers the whole body when he dips
    "hips": ((0, 0, 1.0), (0, 0, 0.8), "torso"),  # the pelvis, pivoting at the waist
    "spine": ((0, 0, 1.0), (0, 0, 1.22), "torso"),
    "chest": ((0, 0, 1.22), (0, 0, 1.45), "spine"),
    "head": ((0, 0, 1.47), (0, 0, 1.95), "chest"),  # pivots at the neck, under the beard
    # a hip on each side, only in the body under the robe: pushed out, the robe bulges over
    # one hip as the drawings do when he leans his weight onto it
    "hip.L": ((0.15, 0, 0.94), (0.15, 0, 0.8), "hips"),
    "hip.R": ((-0.15, 0, 0.94), (-0.15, 0, 0.8), "hips"),
    # the skirt of the robe, hanging from the waist: swings the hem and flares it (bone scale)
    "skirt": ((0, 0, 1.0), (0, 0, 0.45), "hips"),
    # the halo rides on the head but keeps level, tipping towards the camera on some drawings
    "halo": ((0, 0, 2.155), (0, 0, 2.255), "head"),
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
CONTROLS = {"knee.L", "knee.R", "torso"}  # helpers that don't deform


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
        if name.startswith(("forearm", "hand", "upper_arm", "head", "thigh", "chest")):
            # a stretched upper arm must not stretch the hand, nor a slimmer waist the chest, head
            # and limbs
            eb.inherit_scale = "NONE"
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


def auto_skin(obj, rig, bones):
    """Blender's automatic weights (bone heat, as Ctrl+P > With Automatic Weights) from these
    bones only; adds the Armature modifier."""
    deform = {b.name: b.use_deform for b in rig.data.bones}
    for b in rig.data.bones:
        b.use_deform = b.name in bones
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    for b in rig.data.bones:
        b.use_deform = deform[b.name]
    return obj


def ride(obj, rig, body, subsurf=1):
    """Let obj follow the body's surface (Surface Deform, bound in the rest pose) instead of
    the bones: cloth on a body."""
    obj.parent = rig
    mod = obj.modifiers.new("Body", "SURFACE_DEFORM")
    mod.target = body
    obj.modifiers.move(len(obj.modifiers) - 1, 0)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.surfacedeform_bind(modifier=mod.name)
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get())  # the bind happens on evaluation
    if subsurf:
        sub = obj.modifiers.new("Subsurf", "SUBSURF")
        sub.levels = subsurf
        sub.render_levels = subsurf + 1
        obj.modifiers.move(len(obj.modifiers) - 1, 1)
    return obj


def build_body_hull(coll, rig):
    """The body under the robe, hidden: chest, waist and hips, and below them the space his
    legs fill down to the hem, just inside the robe. Skinned with automatic weights to the
    spine, hips and legs, plus a share of the skirt bone towards the hem (so the hem still
    swings and flares)."""
    zs = [HEM_Z + 0.04 * i for i in range(int((1.44 - HEM_Z) / 0.04) + 1)] + [z for z, *_ in ROBE if z > 1.44]
    body = loft("J_body", coll, mat("skin"), [zsec(z, max(rx * 0.92, 0.004), max(ry * 0.92, 0.004), cy=cy)
                                             for z in zs for rx, ry, cy in [robe_ring(z)]], ring=32, outline=False)
    for v in body.data.vertices:  # the same seat as the robe
        rx, ry, cy = robe_ring(v.co.z)
        back = max(0.0, (v.co.y - cy) / max(ry, 1e-3)) ** 2
        v.co.y += 0.055 * back * seat(v.co.z)
    auto_skin(body, rig, {"hips", "hip.L", "hip.R", "spine", "chest", "thigh.L", "thigh.R", "shin.L", "shin.R"})
    skirt = body.vertex_groups.new(name="skirt")
    groups = {g.index: g for g in body.vertex_groups}
    for v in body.data.vertices:
        k = 0.6 * smooth(1.02, 0.5, v.co.z)
        if k <= 0:
            continue
        for ge in v.groups:
            groups[ge.group].add([v.index], ge.weight * (1 - k), "REPLACE")
        skirt.add([v.index], k, "REPLACE")
    body.hide_render = True
    body["helper"] = True  # not drawn: the fitter and the renders leave it out
    body.hide_set(True)
    return body


def rigid(bone):
    return lambda co: {bone: 1.0}


def blend(lo_bone, hi_bone, z0, z1):
    """lo_bone below z0, hi_bone above z1, linear in between."""
    def w(co):
        t = min(1.0, max(0.0, (co.z - z0) / (z1 - z0)))
        return {lo_bone: 1.0 - t, hi_bone: t}
    return w


# --------------------------------------------------------------------------- model
# Proportions, in units where the top of his hair is at 2.0 and his soles at 0, measured from
# the source frames and the model sheet: head (hair top to beard tip) ~28% of his height,
# eyes at 1.78, beard tip at 1.40, shoulders at 1.40, hem at 0.38, back hair down to 1.34.

# Robe: horizontal ellipses (z, rx, ry, cy). Long, pinched at the waist, the hips swelling below
# it and tucking in a little at the hem (measured row by row on the drawings), a soft belly
# pushing the front out (cy), the hem just below the knee.
ROBE = [
    (0.445, 0.25, 0.2, 0.0), (0.48, 0.251, 0.199, 0.0), (0.6, 0.25, 0.196, -0.01),
    (0.74, 0.25, 0.19, -0.018), (0.86, 0.228, 0.18, -0.024), (0.98, 0.196, 0.168, -0.024),
    (1.1, 0.188, 0.162, -0.014), (1.22, 0.196, 0.16, -0.006), (1.32, 0.204, 0.158, 0.0), (1.4, 0.208, 0.154, 0.0),
    (1.44, 0.2, 0.146, 0.0), (1.47, 0.176, 0.132, 0.0), (1.495, 0.136, 0.112, 0.0), (1.512, 0.085, 0.085, 0.0),
    (1.52, 0.04, 0.04, 0.0), (1.524, 0.0, 0.0, 0.0),
]
HEM_Z = ROBE[0][0]


def seat(z):
    """How far the seat bulges out behind his hips, by height: low and tight, the small of his back
    hollow above it."""
    return math.exp(-((z - 0.80) / 0.10) ** 2)


def flat_hem(robe):
    """Flatten the hem as the camera sees it: drawn, it's one straight line with square corners, but
    an ellipse seen from above sags in the middle. A Geometry Nodes modifier after the body (so it
    works whichever way he faces and however the fit squashes him) drops each hem point by how far it
    lies behind the hem's point nearest the camera, times the slope of the camera's view, so the
    whole hem projects onto one line."""
    cam = bpy.context.scene.camera
    if cam is None:
        return
    nt = bpy.data.node_groups.new("FlatHem", "GeometryNodeTree")
    nt.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    nt.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, link = nt.nodes, nt.links.new

    def math_node(op, a=None, b=None, clamp=False):
        m = n.new("ShaderNodeMath")
        m.operation = op
        m.use_clamp = clamp
        for sock, v in zip(m.inputs, (a, b)):
            if isinstance(v, (int, float)):
                sock.default_value = v
            elif v is not None:
                link(v, sock)
        return m.outputs[0]

    def vec_node(op, a, b=None):
        m = n.new("ShaderNodeVectorMath")
        m.operation = op
        link(a, m.inputs[0])
        if b is not None:
            link(b, m.inputs[1])
        return m.outputs["Value" if op in ("LENGTH", "DOT_PRODUCT") else "Vector"]

    def ground(vec):  # (x, y, 0)
        sep, comb = n.new("ShaderNodeSeparateXYZ"), n.new("ShaderNodeCombineXYZ")
        link(vec, sep.inputs["Vector"])
        link(sep.outputs["X"], comb.inputs["X"])
        link(sep.outputs["Y"], comb.inputs["Y"])
        return comb.outputs["Vector"], sep.outputs["Z"]

    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    rest = n.new("GeometryNodeInputNamedAttribute")
    rest.data_type = "FLOAT"
    rest.inputs["Name"].default_value = "rest_z"
    weight = n.new("ShaderNodeMapRange")  # 1 at the hem, fading out over the lowest 0.12 of the robe
    weight.interpolation_type = "SMOOTHSTEP"
    weight.inputs["From Min"].default_value = HEM_Z + 0.12
    weight.inputs["From Max"].default_value = HEM_Z
    link(rest.outputs["Attribute"], weight.inputs["Value"])
    info = n.new("GeometryNodeObjectInfo")
    info.transform_space = "RELATIVE"
    info.inputs["Object"].default_value = cam
    cam_flat, cam_z = ground(info.outputs["Location"])
    slope = math_node("DIVIDE", math_node("SUBTRACT", cam_z, HEM_Z), vec_node("LENGTH", cam_flat))
    pos_flat, _ = ground(n.new("GeometryNodeInputPosition").outputs["Position"])
    toward = vec_node("DOT_PRODUCT", pos_flat, vec_node("NORMALIZE", cam_flat))
    hem = n.new("FunctionNodeCompare")  # the hem's own row
    hem.data_type = "FLOAT"
    hem.operation = "LESS_THAN"
    link(rest.outputs["Attribute"], hem.inputs["A"])
    hem.inputs["B"].default_value = HEM_Z + 0.005
    front = n.new("GeometryNodeAttributeStatistic")
    front.data_type = "FLOAT"
    front.domain = "POINT"
    link(gin.outputs["Geometry"], front.inputs["Geometry"])
    link(hem.outputs["Result"], front.inputs["Selection"])
    link(toward, front.inputs["Attribute"])
    behind = math_node("SUBTRACT", front.outputs["Max"], toward, clamp=True)
    drop = math_node("MULTIPLY", math_node("MULTIPLY", behind, slope), weight.outputs["Result"])
    offset = n.new("ShaderNodeCombineXYZ")
    link(math_node("MULTIPLY", drop, -1.0), offset.inputs["Z"])
    setpos = n.new("GeometryNodeSetPosition")
    link(gin.outputs["Geometry"], setpos.inputs["Geometry"])
    link(offset.outputs["Vector"], setpos.inputs["Offset"])
    link(setpos.outputs["Geometry"], gout.inputs["Geometry"])
    mod = robe.modifiers.new("FlatHem", "NODES")
    mod.node_group = nt
    robe.modifiers.move(len(robe.modifiers) - 1, robe.modifiers.find("Body") + 1)


def robe_ring(z):
    zs = [s[0] for s in ROBE]
    z = min(max(z, zs[0]), zs[-1])
    k = max(i for i in range(len(zs) - 1) if zs[i] <= z) if z < zs[-1] else len(zs) - 2
    f = (z - zs[k]) / (zs[k + 1] - zs[k])
    a, b = ROBE[k], ROBE[k + 1]
    return tuple(a[i] + (b[i] - a[i]) * f for i in (1, 2, 3))


def build_body(coll, rig):
    skin_m, robe_m = mat("skin"), mat("robe", 0.9)  # the drawn robe is flat: only a faint shade band

    robe = loft("J_robe", coll, robe_m, [zsec(z, max(rx, 0.004), max(ry, 0.004), cy=cy) for z, rx, ry, cy in ROBE],
                ring=48)
    for v in robe.data.vertices:  # a soft wave along the hem, like loose cloth
        k = smooth(HEM_Z + 0.22, HEM_Z, v.co.z)
        if k > 0:
            th = math.atan2(v.co.x, -v.co.y)
            f = 1 + 0.028 * k * math.sin(5 * th + 0.8)
            v.co.x *= f
            v.co.y *= f
    for v in robe.data.vertices:  # the seat: in profile the robe bulges out behind his hips
        rx, ry, cy = robe_ring(v.co.z)
        back = max(0.0, (v.co.y - cy) / max(ry, 1e-3)) ** 2
        v.co.y += 0.06 * back * seat(v.co.z)
    rest = robe.data.attributes.new("rest_z", "FLOAT", "POINT")
    rest.data.foreach_set("value", [v.co.z for v in robe.data.vertices])
    ride(robe, rig, build_body_hull(coll, rig))  # the robe rides on the body, not on the bones
    flat_hem(robe)

    # V-neck: skin showing through the collar, a thin patch lying on the robe: a short, wide V with
    # straight sides, as drawn. Under it a dark one a little bigger draws the collar's edges on both
    # sides (an outline shell would hide on the side turning away from the camera)
    def vneck_surf(edge=0.0, drop=0.0):  # edge: how far the sides reach out past the V's
        def surf(u, v):
            z = 1.39 - drop + (0.12 + drop) * v
            rx, ry, cy = robe_ring(z)
            half = math.radians(46) * max(0.0, z - 1.39) / 0.12 + edge / rx
            th = (2 * u - 1) * half
            return Vector((rx * math.sin(th), cy - ry * math.cos(th), z))
        return surf

    skin(shell("J_vneck", coll, skin_m, vneck_surf(), 8, 12, lambda u, v: 0.006, inner=0.006, outline=False),
         rig, rigid("chest"), subsurf=0)
    skin(shell("J_collar", coll, mat("black"), vneck_surf(0.008, 0.012), 8, 12, lambda u, v: 0.0035, inner=0.005,
               outline=False), rig, rigid("chest"), subsurf=0)
    # the neck rising out of the collar, under the beard
    skin(loft("J_neck", coll, skin_m, [zsec(1.4, 0.082, 0.074, cy=0.0), zsec(1.52, 0.084, 0.076, cy=-0.005),
                                         zsec(1.64, 0.086, 0.08, cy=-0.01)],
              ring=24), rig, blend("chest", "head", 1.47, 1.53))

    for side, x in (("L", 1), ("R", -1)):
        # the leg runs up under the robe so bent knees never open a gap at the hem, and down inside
        # the foot so a leg the fit bends less (shorter) never shows its end above the ankle. Above the
        # hem, where it never shows, it slims, so a leg angled back can't poke out through the cloth
        leg = loft(f"J_leg_{side}", coll, skin_m, [
            zsec(z, r, r * 0.95, cx=LEG_X * x) for z, r in
            ((0.02, 0.045), (0.05, 0.062), (0.12, 0.068), (0.24, 0.074), (0.38, 0.075), (0.44, 0.074), (0.52, 0.058),
             (0.62, 0.052), (0.75, 0.052), (0.9, 0.052))],
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
    # slab() lays the outline in XZ; turn it flat and into place, a hair above the floor: a sole lying
    # on it z-fights, and its outline frays into a sawtooth along the ground
    lift = 0.008
    for v in s.data.vertices:
        a, depth, f = v.co.x, v.co.y, v.co.z
        p = at(a, f, lift + 0.017 + depth)
        v.co = Vector(p)
    strap = sweep(f"_strap_{side}", coll, sole_m,
                  [at(-0.078, 0.13, lift + 0.034), at(-0.05, 0.135, lift + 0.088), at(0.0, 0.138, lift + 0.104),
                   at(0.05, 0.135, lift + 0.088), at(0.078, 0.13, lift + 0.034)], [0.024], n=16, ring=12, squash=0.45)
    return merge(f"J_sandal_{side}", coll, sole_m, [s, strap])


def build_arms(coll, rig):
    robe_m = mat("robe", 0.9)
    # Each sleeve is two rigid tubes with round ends meeting at the elbow pivot, so a
    # hard bend (hand to face) can't fold the mesh into itself and flip its outline.
    er = 0.058  # sleeve radius at the elbow

    def dome(cx, z, r, down):
        return [zsec(z + (-1 if down else 1) * r * a, r * math.sqrt(1 - a * a), r * math.sqrt(1 - a * a), cx=cx)
                for a in (0.45, 0.75, 0.93)]

    for side, x in (("L", 1), ("R", -1)):
        sx, sz = SHOULDER
        ex, ez = ELBOW
        wx, wz = WRIST
        upper = [zsec(sz + 0.04, 0.045, 0.045, cx=(sx - 0.03) * x), zsec(sz + 0.02, 0.058, 0.058, cx=(sx - 0.008) * x),
                 zsec(sz - 0.03, 0.058, 0.058, cx=sx * x), zsec(sz - 0.13, 0.058, 0.058, cx=(sx + 0.016) * x),
                 zsec(ez, er, er, cx=ex * x)]
        skin(loft(f"J_sleeve_{side}", coll, robe_m, upper + dome(ex * x, ez, er, True), ring=24),
             rig, rigid(f"upper_arm.{side}"))
        lower = [zsec(ez, er, er, cx=ex * x), zsec(ez - 0.13, 0.058, 0.058, cx=(ex + 0.009) * x),
                 zsec(wz + 0.03, 0.06, 0.06, cx=(wx - 0.003) * x), zsec(wz, 0.064, 0.064, cx=wx * x),
                 zsec(wz - 0.004, 0.05, 0.05, cx=wx * x)]
        skin(loft(f"J_cuff_{side}", coll, robe_m, dome(ex * x, ez, er, False)[::-1] + lower, ring=24),
             rig, rigid(f"forearm.{side}"))
        skin(build_hand(coll, side, x), rig, rigid(f"hand.{side}"))


HAND = 1.22  # Simpsons hands are big: the palm is about the size of an eye


def hand_mesh(coll, side, x, curl):
    """Simpsons hand (thumb + three fingers) hanging from the wrist, palm facing the body,
    thumb forward. curl 0: fingers straight and fanned a little; 1: drooping from the knuckles
    and still spread (the beckoning "come here"), as the drawings show it: never folded under
    the palm, which reads as a fist from the camera."""
    skin_m = mat("skin")
    wx, wz = WRIST
    wx *= x
    k = HAND

    def at(dx, dy, dz):
        return (wx + dx * k * x, dy * k, wz + dz * k)

    def finger(dy, length, c):
        """Base, knuckle, tip: straight down at c=0, folded towards the palm (-dx) at c=1."""
        spread = dy * 0.45 * (1 - 0.4 * c)
        base = (0.0, dy, -0.095)
        a1, a2 = math.radians(8 + 42 * c), math.radians(16 + 58 * c)  # bend at the knuckle, then the tip: a droop
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
    add_shape(hand, hand_mesh(coll, side, x, 1.0), "curl")
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
EYE_R = 0.033
LOOK = 6         # degrees the pupils aim down from level
PUPIL = 0.0085   # pupil radius
LID_CUT = -0.08  # where the lid's edge cuts the eye, in eye radii above its centre (below 0: past halfway)
LID_TILT = 20    # degrees the lid's edge is tipped back, square to the camera's view
EYE_X = 0.066
EYE_Z = 1.83
EYE_Y = -0.118  # half out of the face, as Simpsons eyes are
HANG_Z = 1.7    # below this the hair hangs straight instead of following the head
MUZZLE = 0.045  # how far the Simpsons muzzle (moustache, lip, chin) juts out of the face
HAIR_TOP = 0.02  # hair thickness on the crown
HALO = (0.165, 0.014, 0.012)  # the halo's radius, and its band's half width and half thickness
SIDEBURN = 1.715  # the hair at the sides comes down the temples onto the beard
EAR_TH, EAR_Z, EAR_OUT = 102, 1.73, 0.058  # where the ear pokes through the side hair (degrees round from the face)
EAR = (0.02, 0.014, 0.032)  # its half sizes: narrow, thin (outwards) and tall
# The beard below the jaw, (z, rx, ry, cy) sections: round the neck from the jaw into the collar,
# then the point hanging in front of it down to the top of the V-neck.
BEARD_NECK = [(1.628, 0.104, 0.1, -0.036), (1.6, 0.108, 0.1, -0.04), (1.57, 0.104, 0.097, -0.04),
              (1.54, 0.099, 0.094, -0.036), (1.515, 0.094, 0.091, -0.032), (1.495, 0.088, 0.087, -0.03)]
BEARD_POINT = [(1.612, 0.072, 0.04, -0.136), (1.585, 0.076, 0.042, -0.136), (1.555, 0.068, 0.038, -0.136),
               (1.525, 0.052, 0.032, -0.139), (1.497, 0.032, 0.024, -0.142), (1.475, 0.013, 0.013, -0.145),
               (1.468, 0.002, 0.002, -0.145)]


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

    # ears: just a small yellow oval showing through the side hair, behind the sideburn
    for x, side in ((1, "L"), (-1, "R")):
        th = math.radians(EAR_TH) * x
        skin(blobs(f"J_ear_{side}", coll, skin_m, [(head_point(th, EAR_Z) + outward(th) * EAR_OUT, EAR, (0, 0, th))],
                   segs=20), rig, head)

    # eyes: Simpsons balls half out of the face, a nose-width apart, high under the fringe
    eyes, pupils = [], []
    # half closed, the calm look the drawings give him: the pupils sit just under the lids,
    # looking out level
    look = math.radians(LOOK)
    for x in (1, -1):
        c = Vector((EYE_X * x, EYE_Y, EYE_Z))
        eyes.append((c, (EYE_R,) * 3, (0, 0, 0)))
        d = Vector((0.06 * -x, -math.cos(look), -math.sin(look))).normalized()  # a touch cross-eyed, as drawn
        pupils.append((c + d * EYE_R * 0.98, (PUPIL, 0.004, PUPIL), (look, 0, 0)))
    eyeballs = blobs("J_eyes", coll, mat("white", 0.93), eyes)
    eyeballs["outline_px"] = 1.0  # a full-weight line rings the near eye like a monocle; the lid draws the strong line
    skin(eyeballs, rig, head)
    skin(blobs("J_pupils", coll, mat("black"), pupils, outline=False), rig, head, subsurf=0)
    # upper lids: half spheres whose straight edge runs across the middle of the eye as the camera
    # sees it (it looks down on him from about 20 degrees, so the edge is tipped back by as much)
    for x, side in ((1, "L"), (-1, "R")):
        c = Vector((EYE_X * x, EYE_Y, EYE_Z))
        skin(cap(f"J_lid_{side}", coll, skin_m, c, EYE_R * 1.07, LID_CUT, rot=(math.radians(-LID_TILT), 0, 0)), rig, head)

    # nose: the long Simpsons sausage from between the eyes, forward and down, its tip just above the moustache
    skin(sweep("J_nose", coll, skin_m, [(0, -0.12, 1.79), (0, -0.17, 1.762), (0, -0.2, 1.722)],
               [0.017, 0.018, 0.021], n=12, ring=20), rig, head)

    # moustache: one straight bar across the muzzle, jutting out past the nose in profile (the source
    # draws it as a dark cigar), its tips drooping a little at the edges of the face. The ends dip: they
    # sit further back, so from the camera above a level bar would read as a smile
    for x, side in ((1, "L"), (-1, "R")):
        pts = [head_point(math.radians(a) * x, z) + outward(math.radians(a) * x) * off
               for a, z, off in ((0, 1.69, 0.05), (16, 1.688, 0.05), (30, 1.682, 0.047), (42, 1.672, 0.043), (47, 1.66, 0.037))]
        bar = sweep(f"J_moustache_{side}", coll, hair_m, pts, [0.021, 0.021, 0.02, 0.017, 0.012], n=20, ring=18, squash=0.62)
        bar["outline_px"] = 1.6
        skin(bar, rig, head)
    # lower lip: a broad, flat yellow band just under the moustache, above the beard
    lip = [head_point(math.radians(a), 1.645) + outward(math.radians(a)) * 0.014 for a in (-36, -18, 0, 18, 36)]
    lip = [p - Vector((0, 0, 0.006)) if abs(i - 2) == 2 else p for i, p in enumerate(lip)]  # ends dipped, or it smiles from above
    skin(sweep("J_lip", coll, skin_m, lip, [0.016], n=12, ring=12, squash=0.65), rig, head)

    # the beard hangs from the jaw down the front and sides of his neck into the collar, so his neck
    # never shows (beard in front, hair behind), as in every drawing
    skin(loft("J_beard_neck", coll, hair_m, [zsec(z, rx, ry, cy=cy) for z, rx, ry, cy in BEARD_NECK], ring=32),
         rig, blend("chest", "head", 1.49, 1.53))
    # and comes to a point on his chest, at the top of the V-neck, flattened front to back
    skin(loft("J_goatee", coll, hair_m, [zsec(z, rx, ry, cy=cy) for z, rx, ry, cy in BEARD_POINT], ring=24), rig, head)
    # beard band: along the jaw from the goatee up to the sideburns in front of the ears, covering
    # the cheeks up to the moustache (the source shows no skin between them)
    span = math.radians(98)

    def band_surf(u, v):  # the chin itself is under the goatee, so the band only runs from its sides
        th = math.copysign(span * (0.3 + 0.7 * abs(2 * u - 1)), 2 * u - 1)
        a = abs(th) / span
        bottom = 1.584 + 0.012 * a
        top = 1.63 + 0.04 * smooth(0.3, 0.45, a) + 0.105 * smooth(0.45, 0.88, a)  # up the cheeks to the hair
        return head_point(th, bottom + (top - bottom) * v)

    def band_thick(u, v):  # full under the jaw, thin where it climbs to the sideburns
        a = abs(2 * u - 1)
        return 0.01 + 0.022 * math.sin(math.pi * v) ** 0.6 * (1 - 0.6 * a)

    for half, side in ((0, "R"), (1, "L")):
        skin(shell(f"J_beard_{side}", coll, hair_m, lambda u, v, h=half: band_surf(0.5 * h + 0.5 * u, v),
                   22, 8, band_thick), rig, head)

    # hair: a cap with a pointed lock dipping onto the forehead and two fringe locks over its
    # corners, covering the temples down to the ears, then one solid mass hanging behind the ears
    # to the shoulders (the upscaled source shows a smooth shape with a soft, even bottom edge)
    def hair_low(th):
        deg = math.degrees(th)
        a = abs(deg)
        peak = -0.05 * math.exp(-((deg + 9) / 7) ** 2)  # the pointed lock, just off centre
        arch = -0.085 * (min(a, 62) / 62) ** 1.6  # a high forehead, the hairline arching down to the sides
        locks = -0.02 * math.exp(-((a - 60) / 9) ** 2)  # small locks at the forehead corners: a clean hairline
        hairline = 1.955 + peak + arch + locks
        temple = hairline + (SIDEBURN - hairline) * smooth(64, 86, a)  # down the temples to the beard
        # the long hair hangs behind the ears and neck, lower at the sides than at the back: seen from
        # above, that reads as a level cut over the shoulders. A few pointed locks at the bottom
        curtain = 1.425 + 0.04 * smooth(115, 170, a) + 0.006 * math.sin(7 * th)
        curtain -= 0.02 * max(0.0, math.sin(9 * th)) ** 4 * smooth(100, 140, a)
        return temple + (curtain - temple) * smooth(96, 140, a)

    def hair_surf(u, v):
        th = math.pi * (2 * u - 1)  # u=0.5 is the front
        lo = hair_low(th)
        z = lo + (SKULL[-1][0] - lo) * v
        hang = HANG_Z + 0.05 * math.sin(th) ** 2  # at the sides it leaves the head higher, so it never pinches in
        if z >= hang:
            p = head_point(th, z)
            k = 1 + 0.32 * smooth(1.90, 1.975, z)  # a flat-topped cap with square corners, as drawn
            return Vector((p.x * k, p.y * k, z))
        p = head_point(th, hang)
        drop = hang - z
        # tiers stepping out down the back and sides
        wavy = 0.03 * math.sin(drop * 65 + th * 3) * min(1.0, drop * 6) * (0.5 - 0.5 * math.cos(th))
        # spreads out sideways over the shoulders, less front to back
        x, y = p.x * (1 + 2.0 * drop + wavy), p.y * (1 + 0.45 * drop + wavy) + 0.02 * drop
        if z < 1.52:  # draped over the robe's shoulders, never sunk into them
            rx, ry, cy = robe_ring(z)
            e = math.hypot(x / (rx + 0.012), (y - cy) / (ry + 0.012))
            if e < 1:
                x, y = x / e, cy + (y - cy) / e
        return Vector((x, y, z))

    def hair_thick(u, v):
        th = math.pi * (2 * u - 1)
        back = 0.5 - 0.5 * math.cos(th)  # 0 front, 1 back
        wave = 0.5 + 0.5 * math.sin(11 * th)  # soft lumps on the silhouette
        side = math.sin(th) ** 2 * (1 - smooth(0.0, 0.75, v))  # puffy round the face and down the sides
        volume = 0.012 * math.sin(math.pi * min(1.0, v * 1.6)) * (1 - v)  # rounds the top of the head
        return HAIR_TOP + volume + (0.04 * back + 0.016 * side + 0.006 * wave) * (1 - v) ** 1.1  # pole closes

    skin(shell("J_hair", coll, hair_m, hair_surf, 84, 36, hair_thick, wrap_u=True),
         rig, blend("chest", "head", 1.45, 1.56))

    # a flat, chunky hoop about as wide as his head: a band wider than it is thick, like the drawings'
    # grey ring. It has its own bone, tipped towards the camera per drawing (HALO_TILT)
    ring = [(HALO[0] + HALO[1] * math.cos(t), BONES["halo"][0][2] + HALO[2] * math.sin(t))
            for t in (2 * math.pi * i / 16 for i in range(17))]
    halo = lathe("J_halo", coll, mat("halo", 0.9), ring, segs=64)
    halo["outline_px"] = 1.2  # a fine line: the source's halo is faint
    skin(halo, rig, rigid("halo"), subsurf=0)


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
    "face": {  # left hand up behind his head, scratching it; only the sleeve shows
        "L": ((-153, -2, 55), (-110, 0, 0), (0, 0, 60)),
        "R": ((-8, 2, 0), (-42, 10, 0), (0, 0, -20)),
    },
    "beckon": {  # left hand resting across his waist, right palm down, fingers drooping
        "L": ((-8, -5, 0), (-80, 0, -36), (0, 0, -70)),
        "R": ((-20, 14, 0), (-64, 0, 0), (0, 0, 90)),
    },
    "beckon_b": {
        "L": ((-8, -5, 0), (-80, 0, -36), (0, 0, -70)),
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
        apply_head_fit(rig)
        apply_reuse(rig)
        hitch(rig)
    animate_halo(rig)
    animate_hands(rig)


# How far the halo tips towards the camera, per source frame, in degrees. The camera looks down on his
# head from about 17 degrees, so a level halo would read as a wide-open ellipse: while he beckons
# (12-23) the drawings show it half that open, and whenever his arm is up almost edge-on.
HALO_TILT = {k: 7.0 if 12 <= k <= 23 else 10.0 if k in (11, 24) else 12.0 for k in range(41)}


def animate_halo(rig):
    """Key the halo bone on every source frame: level in the world (whatever the head does), then
    tipped about the screen's horizontal by HALO_TILT, its front edge up."""
    from mathutils import Matrix
    scene = bpy.context.scene
    pb = rig.pose.bones.get("halo")
    if pb is None:
        return
    right = screen_right()
    n = LAYOUT["source"]["frames"]
    for k in range(n + 1):
        f = remake_frame(k)
        scene.frame_set(int(f), subframe=f - int(f))
        level = rig.matrix_world.to_3x3().normalized() @ pb.bone.matrix_local.to_3x3().normalized()
        world = (Matrix.Rotation(math.radians(-HALO_TILT.get(k % n, 0.0)), 3, right) @ level).to_4x4()
        world.translation = (rig.matrix_world @ pb.matrix).translation
        pb.matrix = rig.matrix_world.inverted() @ world
        pb.keyframe_insert("rotation_quaternion", frame=f)
        pb.keyframe_insert("scale", frame=f)
    constant(rig)


# Finger curl per source frame, read off the (upscaled) drawings: the beckoning hand (his
# right) folds its fingers down twice ("come here"); the hand on his belly beckons along with
# it, from pointing to an open claw and back, closing into a fist in between.
CURL = {
    "R": {0: 0.2, 11: 0.3, 12: 0.0, 13: 0.0, 14: 1.0, 15: 1.0, 16: 0.6, 17: 0.0, 18: 0.0, 19: 0.45,
          20: 0.55, 21: 1.0, 22: 1.0, 23: 0.0, 24: 0.2},
    "L": {0: 0.0, 11: 0.15, 12: 0.15, 14: 0.35, 16: 0.3, 17: 0.4, 18: 0.75, 19: 0.2, 21: 0.35, 23: 0.15,
          24: 0.3, 25: 0.0},
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
# reference/pose_fit.json holds, per source frame, offsets found by fitting the figure to the
# original frame by frame (see fit_pose.py): how far he slides across the screen, the turn,
# dip, tilt and twist of his body, the hips' sway and thrust under the chest's lean, the swing
# and flare of the skirt, the head's nod, roll and turn, the arm angles and stretch (a cartoon
# cheat: the drawings make his arms longer when they reach), the wrists' bend, and where his
# feet stand. They sit on top of the designed poses above, so the poses stay readable and the
# fit only nudges them. Degrees for angles, units for the slide, dip, sway, thrust and feet,
# a fraction for stretch and flare.
FIT_PARAMS = ("slide", "yaw", "dip", "tilt", "pitch", "twist", "head_x", "head_y", "head_z",
              "armL_x", "armL_y", "armL_z", "elbowL", "stretchL", "armR_x", "armR_y", "armR_z", "elbowR", "stretchR",
              "footL_x", "footL_y", "footR_x", "footR_y",
              "sway", "thrust", "lean", "skirt_x", "skirt_y", "flare", "wristL", "wristR", "hipL", "hipR", "girth", "hipgirth", "kneeL", "kneeR")
HEAD_PARAMS = ("head_x", "head_y", "head_z")  # applied after aim_head, on top of where it points the face
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


FIT_BONES = ("hips", "chest", "skirt", "upper_arm.L", "forearm.L", "hand.L", "upper_arm.R", "forearm.R", "hand.R",
             "foot.L", "foot.R", "torso", "spine", "hip.L", "hip.R", "thigh.L", "thigh.R")


def apply_offsets(rig, p, right=None):
    """Add one frame's fitted body offsets to the pose the rig is in now (not keyed); the
    head's are added by apply_head_offsets."""
    get = lambda k: p.get(k, 0.0)  # noqa: E731
    pb = rig.pose.bones
    rig.location += (right or screen_right()) * get("slide")
    rig.rotation_euler.z += math.radians(-get("yaw"))
    # the dip lowers the whole body; the sway and thrust move the hips alone
    torso_rest = pb["torso"].bone.matrix_local.to_3x3().normalized()
    pb["torso"].location += torso_rest.inverted() @ Vector((0, 0, -get("dip")))
    hips_rest = pb["hips"].bone.matrix_local.to_3x3().normalized()
    pb["hips"].location += hips_rest.inverted() @ Vector((get("sway"), -get("thrust"), 0))
    # the spine bends half of the lean, pitch and twist, the chest the rest: a curve, not a kink
    upper = (-get("pitch") / 2, get("lean") / 2, -get("twist") / 2)
    pb["spine"].rotation_quaternion = bone_rotation(pb["spine"], upper) @ pb["spine"].rotation_quaternion
    for name, rot in (("hips", (0, get("tilt"), 0)), ("chest", upper),
                      ("skirt", (get("skirt_x"), get("skirt_y"), 0)),
                      ("upper_arm.L", (get("armL_x"), get("armL_y"), get("armL_z"))), ("forearm.L", (get("elbowL"), 0, 0)),
                      ("hand.L", (get("wristL"), 0, 0)),
                      ("upper_arm.R", (get("armR_x"), get("armR_y"), get("armR_z"))), ("forearm.R", (get("elbowR"), 0, 0)),
                      ("hand.R", (get("wristR"), 0, 0))):
        if any(rot):
            pb[name].rotation_quaternion = bone_rotation(pb[name], rot) @ pb[name].rotation_quaternion
    for side, x in (("L", 1), ("R", -1)):
        out = get(f"hip{side}")
        if out:  # outward from his middle
            hip = pb[f"hip.{side}"]
            hip.location += hip.bone.matrix_local.to_3x3().normalized().inverted() @ Vector((x * out, 0, 0))
    # squash and stretch: the drawings slim his body when he turns side-on or away, the waist
    # (girth) and the hips (hipgirth) each on their own; the chest, head and limbs keep their size
    for name, g in (("spine", get("girth")), ("hips", get("hipgirth"))):
        if g:
            pb[name].scale.x *= 1 + g
            pb[name].scale.z *= 1 + g
    for side in ("L", "R"):
        k = get(f"knee{side}")
        if k:  # a cartoon cheat: the leg stretches a little and, its foot planted, bends at the knee
            pb[f"thigh.{side}"].scale.y *= 1 + k  # the shin inherits it
    flare = get("flare")
    if flare:  # the hem widens all round (bone x and z), not longer
        pb["skirt"].scale.x *= 1 + flare
        pb["skirt"].scale.z *= 1 + flare
    for side in ("L", "R"):
        s = get(f"stretch{side}")
        if s:
            for name in (f"upper_arm.{side}", f"forearm.{side}"):
                pb[name].scale.y *= 1 + s
        x, y = get(f"foot{side}_x"), get(f"foot{side}_y")
        if x or y:  # +x to his left, +y forward
            foot = pb[f"foot.{side}"]
            foot.location += foot.bone.matrix_local.to_3x3().normalized().inverted() @ Vector((x, -y, 0))


def apply_head_offsets(rig, p):
    """The head's fitted nod, roll and turn (+ towards screen-left), on top of aim_head."""
    rot = (p.get("head_x", 0.0), p.get("head_y", 0.0), -p.get("head_z", 0.0))
    if any(rot):
        pb = rig.pose.bones["head"]
        pb.rotation_quaternion = bone_rotation(pb, rot) @ pb.rotation_quaternion


# Where his face points, read off the drawings: degrees towards screen-left, 0 facing us. In
# every front-facing frame he looks off to screen-left, a three-quarter view, whichever way
# his body faces. Frames not listed keep the head in line with the body (the turns).
HEAD_YAW = {3: 85, 4: 85, 5: 75, 6: 47, 7: 47, 8: 40, 9: 35, 10: 45, 11: 45, 12: 42, 13: 42, 14: 42, 15: 42, 16: 40,
            17: 40, 18: 40, 19: 42, 20: 42, 21: 42, 22: 42, 23: 42, 24: 45, 25: 40, 26: 40, 27: 35,
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
REUSE = {24: (11, 5, {}), 27: (9, 0, {})}


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
            for name in FIT_BONES:
                for path in ("location", "rotation_quaternion", "scale"):
                    rig.pose.bones[name].keyframe_insert(path, frame=fk)
    constant(rig)


def apply_fit(rig):
    """Bake the fitted offsets into the held keys, one source frame at a time."""
    fit = load_fit()
    if not fit:
        return
    scene = bpy.context.scene
    right = screen_right()
    channels = [(rig, "location"), (rig, "rotation_euler")]
    for name in FIT_BONES:
        pb = rig.pose.bones[name]
        channels += [(pb, "location"), (pb, "rotation_quaternion"), (pb, "scale")]
    # first key every channel as it stands on every frame, so a channel nothing animated yet (a
    # foot, a bone's scale) holds its own value on each frame instead of the last frame's offset
    for f in step_frames():
        scene.frame_set(int(f), subframe=f - int(f))
        for owner, path in channels:
            owner.keyframe_insert(path, frame=f)
    constant(rig)
    for k, p in sorted(fit.items()):
        f = remake_frame(k)
        scene.frame_set(int(f), subframe=f - int(f))
        rig.location = rig["base_location"]  # the slide is keyed here, so don't let it pile up
        apply_offsets(rig, p, right)
        for owner, path in channels:
            owner.keyframe_insert(path, frame=f)
    constant(rig)


def apply_head_fit(rig):
    """Bake the head's fitted offsets, after aim_head has pointed the face."""
    fit = {k: p for k, p in load_fit().items() if any(p.get(n) for n in HEAD_PARAMS)}
    scene = bpy.context.scene
    pb = rig.pose.bones["head"]
    for k, p in sorted(fit.items()):
        f = remake_frame(k)
        scene.frame_set(int(f), subframe=f - int(f))
        apply_head_offsets(rig, p)
        pb.keyframe_insert("rotation_quaternion", frame=f)
    constant(rig)


# The body under the arms, one row per source frame, read off the source drawings.
# dip: knee bend 0..1 (the body drops by DIP), sway: hips sideways (+ his left), thrust: hips
# forward, tilt: hips roll, lean: the upper body's roll (spine and chest), pitch: chest leans back (+), roll/nod/turn: head tilt to his left (+), nod
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
    torso_rest = pb["torso"].bone.matrix_local.to_3x3().normalized()
    keys = dict(BODY)
    keys[LAYOUT["source"]["frames"]] = BODY[0]  # close the loop
    for src, row in sorted(keys.items()):
        b = dict(zip(BODY_KEYS, row))
        f = remake_frame(src)
        pb["torso"].location = torso_rest.inverted() @ Vector((0, 0, -b["dip"] * DIP))
        pb["torso"].keyframe_insert("location", frame=f)
        pb["hips"].location = hips_rest.inverted() @ Vector((b["sway"], -b["thrust"], 0))
        pb["hips"].keyframe_insert("location", frame=f)
        upper = (-b["pitch"] / 2, b["lean"] / 2, 0)  # half in the spine, half in the chest
        pb["spine"].rotation_quaternion = bone_rotation(pb["spine"], upper)
        pb["spine"].keyframe_insert("rotation_quaternion", frame=f)
        for name, rot in (("hips", (0, b["tilt"], 0)), ("chest", upper),
                          ("head", (b["nod"], b["roll"], -b["turn"]))):
            pb[name].rotation_quaternion = bone_rotation(pb[name], rot)
            pb[name].keyframe_insert("rotation_quaternion", frame=f)
