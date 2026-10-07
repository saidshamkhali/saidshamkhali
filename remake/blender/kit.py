"""Shared helpers for the remake scripts: settings, materials, mesh builders, keyframing."""
import json
import math
import os

import bpy
import bmesh  # after bpy: the pip bpy module only exposes bmesh once bpy is loaded
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REMAKE = os.path.dirname(HERE)

with open(os.path.join(REMAKE, "reference", "layout.json"), encoding="utf-8") as f:
    LAYOUT = json.load(f)

SRC_W = LAYOUT["source"]["width"]
SRC_H = LAYOUT["source"]["height"]
SRC_FRAMES = LAYOUT["source"]["frames"]

# 25 fps is the smoothest a GIF plays exactly (delays are in 1/100 s).
# 105 frames = 4.2 s, close to the original 4.1 s, and divisible into whole
# prop cycles (0.6 s = 15 frames, ~0.84 s = 21, 1.4 s = 35) so the loop is seamless.
FPS = 25
LOOP = 105
RES_X, RES_Y = 1200, 768  # 1.5625:1, same shape as the 498x318 original

LENS = 85.0
SENSOR = 36.0
OUTLINE_PX = 2.2       # outline width at RES_X


# --------------------------------------------------------------------------- utils

def srgb(hex_color):
    """'#RRGGBB' -> linear RGB tuple (material colours are linear)."""
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def remake_frame(src_frame):
    """Source GIF frame (0..41) -> remake frame (1..LOOP+1)."""
    return 1 + src_frame * LOOP / SRC_FRAMES


def cycles_per_loop(period_s):
    return max(1, round(LOOP / FPS / period_s))


def link(obj, coll):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)


def new_collection(name, parent=None):
    coll = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def empty(name, coll, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.2
    coll.objects.link(obj)
    obj.location = loc
    if parent:
        obj.parent = parent
    return obj


def keep_world(obj, parent):
    """Parent obj without moving it."""
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = mw


# --------------------------------------------------------------------------- materials

MATS = {}


def new_material(name):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None and hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat


def toon(name, hex_color, shadow=0.72, threshold=0.12, softness=0.03):
    """Flat colour lit by a 2-band ramp: full colour in light, colour*shadow in shade."""
    if name in MATS:
        return MATS[name]
    mat = new_material(name)
    nt = mat.node_tree
    n, l = nt.nodes, nt.links
    out = n.new("ShaderNodeOutputMaterial")
    diff = n.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2rgb = n.new("ShaderNodeShaderToRGB")
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "LINEAR"
    e0, e1 = ramp.color_ramp.elements
    e0.position, e0.color = threshold - softness, (shadow, shadow, shadow, 1)
    e1.position, e1.color = threshold + softness, (1, 1, 1, 1)
    mult = n.new("ShaderNodeVectorMath")
    mult.operation = "MULTIPLY"
    mult.inputs[0].default_value = srgb(hex_color)
    emit = n.new("ShaderNodeEmission")
    l.new(diff.outputs["BSDF"], s2rgb.inputs["Shader"])
    l.new(s2rgb.outputs["Color"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], mult.inputs[1])
    l.new(mult.outputs["Vector"], emit.inputs["Color"])
    l.new(emit.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = srgb(hex_color) + (1,)
    MATS[name] = mat
    return mat


def flat(name, hex_color):
    if name in MATS:
        return MATS[name]
    mat = new_material(name)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    out = n.new("ShaderNodeOutputMaterial")
    emit = n.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = srgb(hex_color) + (1,)
    l.new(emit.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = srgb(hex_color) + (1,)
    MATS[name] = mat
    return mat


def outline_material():
    mat = flat("Outline", "#141414")
    mat.use_backface_culling = True
    return mat


PALETTE = {
    "bg": "#86C5E3",
    "skin": "#FFD90F",
    "robe": "#E2E0EC",
    "hair": "#3B2015",
    "sandal": "#6B3A1E",
    "halo": "#ECECF2",
    "white": "#FFFFFF",
    "black": "#1A1A1A",
    "metal": "#C6C8CC",
    "slot": "#3A3A40",
    "toast": "#E9A84C",
    "clock": "#2A2A2E",
    "clockface": "#F4F2EA",
    "gold": "#FFC81E",
    "lips": "#C8608C",
    "mouth": "#6E1222",
    "tongue": "#D23A50",
    "worm": "#B4AFC0",
}


def mat(key, shadow=0.72):
    return toon(key, PALETTE[key], shadow)


# --------------------------------------------------------------------------- meshes

OUTLINED = []


def finish(obj, material, coll, outline=True, smooth=True, bevel=0.0):
    obj.data.materials.clear()
    obj.data.materials.append(material)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    link(obj, coll)
    if bevel:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 4
        m.limit_method = "ANGLE"
    if outline:
        OUTLINED.append(obj)
    return obj


def sphere(name, coll, material, loc, scale=(1, 1, 1), rot=(0, 0, 0), r=1.0, **kw):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, material, coll, **kw)


def box(name, coll, material, loc, size, rot=(0, 0, 0), bevel=0.0, **kw):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, material, coll, smooth=bevel > 0, bevel=bevel, **kw)


def cylinder(name, coll, material, loc, r, depth, rot=(0, 0, 0), r2=None, verts=32, **kw):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj = finish(obj, material, coll, **kw)
    # keep the caps flat-looking
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = min(r, depth) * 0.15
    m.segments = 3
    m.limit_method = "ANGLE"
    obj.modifiers.move(len(obj.modifiers) - 1, 0)
    return obj


def lathe(name, coll, material, profile, loc=(0, 0, 0), segs=40, **kw):
    """Revolve a (radius, z) profile around Z."""
    mesh = bpy.data.meshes.new(name)
    verts, faces = [], []
    n = len(profile)
    for s in range(segs):
        a = 2 * math.pi * s / segs
        for r, z in profile:
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for s in range(segs):
        s2 = (s + 1) % segs
        for i in range(n - 1):
            faces.append((s * n + i, s2 * n + i, s2 * n + i + 1, s * n + i + 1))
    mesh.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.location = loc
    return finish(obj, material, coll, **kw)


def torus(name, coll, material, loc, major, minor, rot=(0, 0, 0), **kw):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=48,
                                     minor_segments=12, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    return finish(obj, material, coll, **kw)


def zsec(z, rx, ry, cx=0.0, cy=0.0):
    """Horizontal elliptical cross-section for loft()."""
    return Vector((cx, cy, z)), Vector((1, 0, 0)), Vector((0, 1, 0)), rx, ry


def loft(name, coll, material, sections, ring=24, **kw):
    """Closed smooth surface through cross-sections, capped at both ends.
    sections: (center, u, v, ru, rv); ring point = center + ru*cos(a)*u + rv*sin(a)*v."""
    bm = bmesh.new()
    rings = []
    for c, u, v, ru, rv in sections:
        rings.append([bm.verts.new(c + ru * math.cos(2 * math.pi * j / ring) * u
                                   + rv * math.sin(2 * math.pi * j / ring) * v) for j in range(ring)])
    for a, b in zip(rings, rings[1:]):
        for j in range(ring):
            bm.faces.new((a[j], a[(j + 1) % ring], b[(j + 1) % ring], b[j]))
    for rv_, (c, *_rest) in ((rings[0], sections[0]), (rings[-1], sections[-1])):
        hub = bm.verts.new(c)
        for j in range(ring):
            bm.faces.new((rv_[j], rv_[(j + 1) % ring], hub))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return finish(obj, material, coll, **kw)


def blobs(name, coll, material, items, segs=24, **kw):
    """One mesh made of ellipsoids: items are (location, radii, euler_radians)."""
    bm = bmesh.new()
    for loc, radii, rot in items:
        m = Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*radii, 1))
        bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=1.0, matrix=m)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return finish(obj, material, coll, **kw)


def spline(points, n):
    """n+1 samples of a Catmull-Rom curve through points (ends clamped)."""
    pts = [Vector(p) for p in points]
    pts = [pts[0]] + pts + [pts[-1]]
    segs = len(pts) - 3
    out = []
    for i in range(n + 1):
        t = i / n * segs
        k = min(int(t), segs - 1)
        f = t - k
        p0, p1, p2, p3 = pts[k:k + 4]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f))
    return out


def sweep(name, coll, material, points, radii, n=24, ring=16, squash=1.0, up=(0, 0, 1), **kw):
    """Round-ended tube along a smooth curve through points; radii are interpolated along it.
    squash scales the section along the 'up' side (less than 1 = flatter)."""
    path = spline(points, n)
    rs = [radii[0]] if len(radii) == 1 else None
    if rs is None:
        rs = [r.x for r in spline([(r, 0, 0) for r in radii], n)]
    else:
        rs = rs * (n + 1)
    up = Vector(up)
    sections = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, n)] - path[max(i - 1, 0)]).normalized()
        v = (up - t * up.dot(t))
        if v.length < 1e-4:
            v = Vector((0, 1, 0)) - t * t.y
        v.normalize()
        u = t.cross(v)
        sections.append((p, u, v, rs[i], rs[i] * squash))
    # round the ends: rings shrinking along the tangent
    for end in (0, -1):
        p, u, v, ru, rv = sections[end]
        t = (path[1] - path[0]).normalized() if end == 0 else (path[-1] - path[-2]).normalized()
        caps = []
        for a in (0.45, 0.75, 0.93):
            k = math.sqrt(1 - a * a)
            caps.append((p + t * (ru * a) * (-1 if end == 0 else 1), u, v, ru * k, rv * k))
        sections = (caps[::-1] + sections) if end == 0 else (sections + caps)
    return loft(name, coll, material, sections, ring=ring, **kw)


def shell(name, coll, material, surf, nu, nv, outer, inner=0.004, wrap_u=False, axis=(0.0, 0.0), **kw):
    """A thick patch lying on a surface: surf(u, v) -> point, u and v in [0, 1].
    outer(u, v) is the thickness outward, inner the inset below the surface. Outward is
    away from the vertical axis through `axis` (x, y). wrap_u closes the patch around in u;
    rows where every u gives the same point (a pole) collapse cleanly."""
    ax = Vector((axis[0], axis[1], 0))
    eps = 1e-3
    us = [i / nu for i in range(nu)] if wrap_u else [i / nu for i in range(nu + 1)]
    vs = [j / nv for j in range(nv + 1)]

    def normal(u, v):
        p = surf(u, v)
        du = surf(min(u + eps, 1.0), v) - surf(max(u - eps, 0.0), v)
        dv = surf(u, min(v + eps, 1.0)) - surf(u, max(v - eps, 0.0))
        n = du.cross(dv)
        radial = p - Vector((ax.x, ax.y, p.z))
        if n.length < 1e-9:
            n = radial if radial.length > 1e-6 else Vector((0, 0, 1))
        n.normalize()
        if n.dot(radial) < 0 or (radial.length < 1e-6 and n.z < 0):
            n = -n
        return p, n

    bm = bmesh.new()
    O, I = [], []
    for u in us:
        orow, irow = [], []
        for v in vs:
            p, n = normal(u, v)
            orow.append(bm.verts.new(p + n * outer(u, v)))
            irow.append(bm.verts.new(p - n * inner))
        O.append(orow)
        I.append(irow)
    nU = len(us)
    ucount = nU if wrap_u else nU - 1
    for i in range(ucount):
        i2 = (i + 1) % nU
        for j in range(nv):
            bm.faces.new((O[i][j], O[i2][j], O[i2][j + 1], O[i][j + 1]))
            bm.faces.new((I[i][j + 1], I[i2][j + 1], I[i2][j], I[i][j]))
    # rims along the open borders
    border = []
    for i in range(ucount):
        border.append(((i, 0), ((i + 1) % nU, 0)))
        border.append((((i + 1) % nU, nv), (i, nv)))
    if not wrap_u:
        for j in range(nv):
            border.append(((0, j + 1), (0, j)))
            border.append(((nU - 1, j), (nU - 1, j + 1)))
    for (a, b) in border:
        try:
            bm.faces.new((O[a[0]][a[1]], I[a[0]][a[1]], I[b[0]][b[1]], O[b[0]][b[1]]))
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj["outline_even"] = False
    return finish(obj, material, coll, **kw)


def cap(name, coll, material, center, radius, cut, rot=(0, 0, 0), segs=32, rings=12, **kw):
    """Closed spherical cap: the part of a sphere above the plane z = cut*radius (local),
    then rotated by rot and moved to center. Used for eyelids."""
    phi_c = math.acos(max(-0.99, min(0.99, cut)))
    bm = bmesh.new()
    m = Matrix.Translation(center) @ Euler(rot).to_matrix().to_4x4()
    top = bm.verts.new(m @ Vector((0, 0, radius)))
    prev = None
    rows = []
    for k in range(1, rings + 1):
        phi = phi_c * k / rings
        rows.append([bm.verts.new(m @ Vector((radius * math.sin(phi) * math.cos(2 * math.pi * s / segs),
                                              radius * math.sin(phi) * math.sin(2 * math.pi * s / segs),
                                              radius * math.cos(phi)))) for s in range(segs)])
    for s in range(segs):
        bm.faces.new((top, rows[0][s], rows[0][(s + 1) % segs]))
    for a, b in zip(rows, rows[1:]):
        for s in range(segs):
            bm.faces.new((a[s], b[s], b[(s + 1) % segs], a[(s + 1) % segs]))
    # flat underside, filled with rings so subdivision keeps it flat
    rb = radius * math.sin(phi_c)
    zc = radius * math.cos(phi_c)
    prev = rows[-1]
    for f in (0.66, 0.33):
        ring_ = [bm.verts.new(m @ Vector((rb * f * math.cos(2 * math.pi * s / segs),
                                          rb * f * math.sin(2 * math.pi * s / segs), zc))) for s in range(segs)]
        for s in range(segs):
            bm.faces.new((prev[s], ring_[s], ring_[(s + 1) % segs], prev[(s + 1) % segs]))
        prev = ring_
    hub = bm.verts.new(m @ Vector((0, 0, zc)))
    for s in range(segs):
        bm.faces.new((prev[s], hub, prev[(s + 1) % segs]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return finish(obj, material, coll, **kw)


def slab(name, coll, material, outline_2d, depth, plane="XZ", offset=0.0, bevel=0.0, **kw):
    """Flat shape cut from an outline and given thickness. outline_2d is a list of (a, b)
    points; plane "XZ" puts them at (a, offset, b) and extrudes along +Y, "YZ" puts them
    at (offset, a, b) and extrudes along +X. Centred on the plane through its thickness."""
    bm = bmesh.new()
    if plane == "XZ":
        to3 = lambda a, b: Vector((a, offset - depth / 2, b))  # noqa: E731
        axis = Vector((0, depth, 0))
    else:
        to3 = lambda a, b: Vector((offset - depth / 2, a, b))  # noqa: E731
        axis = Vector((depth, 0, 0))
    face = bm.faces.new([bm.verts.new(to3(a, b)) for a, b in outline_2d])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=axis, verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    finish(obj, material, coll, smooth=False, **kw)
    if bevel:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
        m.harden_normals = True
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def smooth_outline(points, n):
    """Closed Catmull-Rom loop through 2D points, n samples."""
    pts = [Vector((a, b, 0)) for a, b in points]
    m = len(pts)
    out = []
    for i in range(n):
        t = i / n * m
        k = int(t)
        f = t - k
        p0, p1, p2, p3 = (pts[(k + j) % m] for j in (-1, 0, 1, 2))
        p = 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f)
        out.append((p.x, p.y))
    return out


def merge(name, coll, material, parts, **kw):
    """Join untransformed part objects into one mesh (each part keeps its own outline shell)."""
    bm = bmesh.new()
    for p in parts:
        bm.from_mesh(p.data)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in parts:
        if p in OUTLINED:
            OUTLINED.remove(p)
        data = p.data
        bpy.data.objects.remove(p, do_unlink=True)
        bpy.data.meshes.remove(data)
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return finish(obj, material, coll, **kw)


def tube(name, coll, material, shapes, n=32, ring=16, **kw):
    """Tapered tube along X. shapes[k](u) -> (x, z, radius_y, radius_z) for u in [0, 1].
    shapes[0] is the basis; every further shape becomes a shape key ("key1", ...)."""
    def positions(fn):
        pts = []
        for i in range(n + 1):
            x, z, ry, rz = fn(i / n)
            for j in range(ring):
                a = 2 * math.pi * j / ring
                pts.append((x, max(ry, 1e-3) * math.cos(a), z + max(rz, 1e-3) * math.sin(a)))
        return pts
    faces = [(i * ring + j, i * ring + (j + 1) % ring, (i + 1) * ring + (j + 1) % ring, (i + 1) * ring + j)
             for i in range(n) for j in range(ring)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(positions(shapes[0]), [], faces)
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    if len(shapes) > 1:
        obj.shape_key_add(name="Basis")
        for k, fn in enumerate(shapes[1:], 1):
            key = obj.shape_key_add(name=f"key{k}")
            for v, p in zip(key.data, positions(fn)):
                v.co = p
    return finish(obj, material, coll, **kw)


def add_outline(obj, cam, px=OUTLINE_PX):
    """Inverted-hull outline on one object, sized so it reads as ~px on screen."""
    bpy.context.view_layer.update()
    om = outline_material()
    half_w = SENSOR / 2 / LENS
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    depth = max(0.5, (obj.matrix_world.translation - cam.matrix_world.translation).dot(fwd))
    world_px = 2 * depth * half_w / RES_X
    # an object whose own scale is animated declares the scale its outline is sized for
    own = max(abs(c) for c in obj.scale) or 1.0
    scale = max(obj.matrix_world.to_scale()) / own * obj.get("outline_ref_scale", own)
    if om.name not in obj.data.materials:
        obj.data.materials.append(om)
    m = obj.modifiers.get("Outline") or obj.modifiers.new("Outline", "SOLIDIFY")
    m.thickness = px * world_px / scale
    m.offset = 1.0
    m.use_flip_normals = True
    # even offset keeps lines even on boxy props but spikes on the sharp rims of shells
    m.use_even_offset = bool(obj.get("outline_even", True))
    m.use_quality_normals = True
    m.use_rim = False
    m.material_offset = list(obj.data.materials).index(om)
    obj.visible_shadow = True


def add_outlines(cam):
    for obj in OUTLINED:
        add_outline(obj, cam)


# --------------------------------------------------------------------------- keyframes

def step_frames():
    """Our frames where each source frame starts: hold a pose from one to the next for
    the 10 fps look of the original (the last one is the loop's start again)."""
    return [remake_frame(k) for k in range(SRC_FRAMES + 1)]


def bake(obj, path, index, fn, frames=None):
    """Keyframe obj.path[index] = fn(t), t in [0, 1) over the loop, on every frame or on
    the given (possibly fractional) frames."""
    for f in frames or range(1, LOOP + 2):
        t = (f - 1) / LOOP
        getattr(obj, path)[index] = fn(t)
        obj.keyframe_insert(path, index=index, frame=f)


def constant(obj):
    """Hold every key of obj until the next one (no easing in between)."""
    for fc in fcurves(obj):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def fcurves(obj):
    """The F-curves of obj's action (Blender 5 keeps them in a channelbag per slot)."""
    from bpy_extras import anim_utils
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return []
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(bag.fcurves) if bag else []


def hold(obj, times):
    """Cartoon timing: replace every curve of obj by its values at `times`, each held until
    the next (constant interpolation), like a drawing held for several frames."""
    for fc in fcurves(obj):
        values = [fc.evaluate(t) for t in times]
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(times))
        for kp, t, v in zip(fc.keyframe_points, times, values):
            kp.co = (t, v)
            kp.interpolation = "CONSTANT"
        fc.update()


def wave(t, cycles, phase=0.0):
    return math.sin(2 * math.pi * (t * cycles + phase))


def saw(t, cycles, phase=0.0):
    return (t * cycles + phase) % 1.0
