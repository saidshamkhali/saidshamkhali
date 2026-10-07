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
    "hair": "#4A2812",
    "sandal": "#6B3A1E",
    "halo": "#ECECF2",
    "white": "#FFFFFF",
    "black": "#1A1A1A",
    "metal": "#C3C7CE",
    "slot": "#3A3A40",
    "toast": "#E9A84C",
    "clock": "#2A2A2E",
    "clockface": "#F4F2EA",
    "gold": "#FFC81E",
    "lips": "#E8607E",
    "mouth": "#6E1222",
    "tongue": "#E2405A",
    "worm": "#F2A7B9",
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


def add_outlines(cam):
    """Inverted-hull outlines, sized so they read as ~OUTLINE_PX on screen."""
    bpy.context.view_layer.update()
    om = outline_material()
    half_w = SENSOR / 2 / LENS
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    for obj in OUTLINED:
        depth = max(0.5, (obj.matrix_world.translation - cam.matrix_world.translation).dot(fwd))
        world_px = 2 * depth * half_w / RES_X
        scale = max(obj.matrix_world.to_scale())
        obj.data.materials.append(om)
        m = obj.modifiers.new("Outline", "SOLIDIFY")
        m.thickness = OUTLINE_PX * world_px / scale
        m.offset = 1.0
        m.use_flip_normals = True
        m.use_even_offset = True
        m.use_rim = False
        m.material_offset = 1
        obj.visible_shadow = True


# --------------------------------------------------------------------------- keyframes

def bake(obj, path, index, fn):
    """Keyframe obj.path[index] = fn(t) on every frame, t in [0, 1) over the loop."""
    for f in range(1, LOOP + 2):
        t = (f - 1) / LOOP
        getattr(obj, path)[index] = fn(t)
        obj.keyframe_insert(path, index=index, frame=f)


def bake_value(owner, prop, fn):
    for f in range(1, LOOP + 2):
        setattr(owner, prop, fn((f - 1) / LOOP))
        owner.keyframe_insert(prop, frame=f)


def wave(t, cycles, phase=0.0):
    return math.sin(2 * math.pi * (t * cycles + phase))


def saw(t, cycles, phase=0.0):
    return (t * cycles + phase) % 1.0
