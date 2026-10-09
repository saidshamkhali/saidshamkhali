"""Make hand edits to the .blend visible in diffs and repeatable from the scripts.

Run with Blender 5.x on a .blend:
    blender -b remake/blender/homers_web_page.blend --python remake/blender/tweaks.py -- MODE [options]
or with the bpy module (pip install bpy), which opens homers_web_page.blend itself:
    python remake/blender/tweaks.py MODE [options]

Modes:
    manifest   write a sorted, diff-friendly text summary of the file
               (default: remake/blender/scene_manifest.txt)
    export     build a fresh scene from the scripts into a temp .blend, compare the file
               against it and write the differences (default: remake/blender/tweaks.json)
    apply      re-apply tweaks.json to the open scene (build_scene.py does this at the end
               of build() when remake/blender/tweaks.json exists)

Options:
    --out PATH       file to write (manifest, export)
    --against PATH   export: compare against this .blend instead of building a fresh one
    --tweaks PATH    apply: tweaks file to read (default: remake/blender/tweaks.json)
    --save PATH      apply: save the result here (the open file itself is never saved)

tweaks.json only holds what can be re-applied on top of a build: object transforms
(location, rotation_euler, scale) by object name, material base colours as sRGB
#RRGGBB, and the title's font file, offset, space_character and space_word. Edits to
meshes, keyframes, modifiers or anything else are not captured; export lists the ones
it notices under "not_captured", and objects or materials found in only one of the
two files under "unmatched".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REMAKE = os.path.dirname(HERE)
BLEND = os.path.join(HERE, "homers_web_page.blend")
TWEAKS = os.path.join(HERE, "tweaks.json")
MANIFEST = os.path.join(HERE, "scene_manifest.txt")
MODES = ("manifest", "export", "apply")

TRANSFORMS = ("location", "rotation_euler", "scale")
TITLE_FLOATS = ("offset", "space_character", "space_word")
TOL = 1e-5


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    elif "blender" in os.path.basename(sys.argv[0]).lower():
        argv = []
    else:
        argv = sys.argv[1:]
    if not argv or argv[0] not in MODES:
        raise SystemExit(f"usage: tweaks.py {'|'.join(MODES)} [options]")
    opts = {"mode": argv[0], "out": None, "against": None, "tweaks": TWEAKS, "save": None}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "--against", "--tweaks", "--save"):
            opts[a[2:]] = os.path.abspath(argv[i + 1]); i += 2
        else:
            raise SystemExit(f"unknown option {a}")
    return opts


# --------------------------------------------------------------------------- reading

def to_hex(rgb):
    """Linear RGB -> '#RRGGBB' sRGB; the inverse of kit.srgb."""
    out = "#"
    for c in rgb[:3]:
        c = min(max(c, 0.0), 1.0)
        s = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out += f"{round(s * 255):02X}"
    return out


def color_socket(mat):
    """(kind, socket) holding a material's base colour. Toon materials (kit.toon) keep it
    in the Vector Math multiply, flat ones (kit.flat) in the Emission colour."""
    nt = mat.node_tree
    if nt is not None:
        for kind, idname, key in (("toon", "ShaderNodeVectorMath", 0),
                                  ("flat", "ShaderNodeEmission", "Color"),
                                  ("principled", "ShaderNodeBsdfPrincipled", "Base Color")):
            for n in nt.nodes:
                if n.bl_idname != idname or (kind == "toon" and n.operation != "MULTIPLY"):
                    continue
                sock = n.inputs[key]
                if not sock.is_linked:
                    return kind, sock
    return "viewport", None


def base_color(mat):
    kind, sock = color_socket(mat)
    return tuple(sock.default_value)[:3] if sock else tuple(mat.diffuse_color)[:3]


def toon_shadow(mat):
    for n in mat.node_tree.nodes if mat.node_tree else ():
        if n.bl_idname == "ShaderNodeValToRGB":
            return n.color_ramp.elements[0].color[0]
    return None


def file_name(path):
    return re.split(r"[\\/]", path)[-1]


def title_object():
    obj = bpy.data.objects.get("Title")
    if obj is not None and obj.type == "FONT":
        return obj
    fonts = sorted((o for o in bpy.context.scene.objects if o.type == "FONT"), key=lambda o: o.name)
    return fonts[0] if fonts else None


def title_settings():
    obj = title_object()
    if obj is None:
        return None
    c = obj.data
    out = {"object": obj.name, "font": file_name(c.font.filepath) if c.font else None,
           "font_path": bpy.path.abspath(c.font.filepath) if c.font else None}
    for k in TITLE_FLOATS:
        out[k] = getattr(c, k)
    return out


def anim_ids(obj):
    """Datablocks whose animation belongs to this object: itself and its shape keys."""
    ids = [obj]
    keys = getattr(obj.data, "shape_keys", None) if obj.data is not None else None
    if keys is not None:
        ids.append(keys)
    return ids


def action_fcurves(action, slot=None):
    if not getattr(action, "is_action_layered", False) and hasattr(action, "fcurves"):
        return list(action.fcurves)  # legacy actions (Blender < 4.4)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                if slot is None or bag.slot == slot:
                    out += list(bag.fcurves)
    return out


def object_fcurves(id_):
    ad = id_.animation_data
    if ad is None or ad.action is None:
        return []
    return action_fcurves(ad.action, getattr(ad, "action_slot", None))


def animated_channels(obj):
    return sorted({(fc.data_path, fc.array_index) for fc in object_fcurves(obj)
                   if fc.data_path in TRANSFORMS})


def key_fingerprint(obj):
    """Cheap signature of an object's keyframes, to notice edits we can't carry over."""
    n, total = 0, 0.0
    for id_ in anim_ids(obj):
        for fc in object_fcurves(id_):
            for k in fc.keyframe_points:
                n += 1
                total += k.co[0] + k.co[1]
    return [n, round(total, 4)]


def snapshot():
    """Plain-Python copy of what export compares, taken at the first frame."""
    scene = bpy.context.scene
    scene.frame_set(scene.frame_start)
    objects = {}
    for o in scene.objects:
        objects[o.name] = {
            **{k: list(getattr(o, k)) for k in TRANSFORMS},
            "animated": [list(c) for c in animated_channels(o)],
            "keys": key_fingerprint(o),
            "mesh": [len(o.data.vertices), len(o.data.polygons)] if o.type == "MESH" else None,
        }
    materials = {m.name: to_hex(base_color(m)) for m in bpy.data.materials}
    return {"objects": objects, "materials": materials, "title": title_settings()}


# --------------------------------------------------------------------------- manifest

def num(v, nd=4):
    return f"{round(v, nd) + 0.0:.{nd}f}"  # + 0.0 turns -0.0 into 0.0


def vec(v, nd=4):
    return " ".join(num(x, nd) for x in v)


def deg(v):
    return vec([x * 57.29577951308232 for x in v])


def fmt(v):
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return str(v)
    if isinstance(v, float):
        return f"{v:.4g}"
    if hasattr(v, "name"):
        return v.name
    try:
        return "(" + ",".join(fmt(x) for x in v) + ")"
    except TypeError:
        return str(v)


MOD_KEYS = {
    "SOLIDIFY": ("thickness", "offset", "use_flip_normals", "use_even_offset", "use_quality_normals",
                 "use_rim", "material_offset"),
    "BEVEL": ("width", "segments", "limit_method", "harden_normals"),
    "SUBSURF": ("levels", "render_levels"),
    "ARMATURE": ("object", "use_vertex_groups", "use_deform_preserve_volume"),
    "MIRROR": ("use_axis", "mirror_object"),
    "ARRAY": ("count", "relative_offset_displace"),
    "DISPLACE": ("strength", "mid_level"),
    "SMOOTH": ("factor", "iterations"),
    "WEIGHTED_NORMAL": ("weight", "keep_sharp"),
}


def object_lines(o):
    head = f"{o.name}  {o.type}"
    if o.parent:
        head += f"  parent={o.parent.name}"
        if o.parent_type == "BONE":
            head += f":{o.parent_bone}"
    lines = [head]
    if o.rotation_mode in ("QUATERNION", "AXIS_ANGLE"):
        rot = f"rot_quat {vec(o.rotation_quaternion)}"
    else:
        rot = f"rot_deg {deg(o.rotation_euler)}" + ("" if o.rotation_mode == "XYZ" else f" {o.rotation_mode}")
    lines.append(f"  loc {vec(o.location)}  {rot}  scale {vec(o.scale)}")
    flags = [f for f, on in (("hide_render", o.hide_render), ("hide_viewport", o.hide_viewport),
                             ("no_shadow", not o.visible_shadow)) if on]
    if flags:
        lines.append("  flags " + " ".join(flags))
    d = o.data
    if o.type == "MESH":
        line = f"  mesh {d.name} verts {len(d.vertices)} faces {len(d.polygons)}"
        if d.shape_keys:
            line += f" shape_keys {len(d.shape_keys.key_blocks)}"
        lines.append(line)
    elif o.type == "ARMATURE":
        lines.append(f"  armature {d.name} bones {len(d.bones)}")
    elif o.type == "CAMERA":
        lines.append(f"  camera lens {num(d.lens)} sensor {num(d.sensor_width)} {d.sensor_fit} "
                     f"clip {num(d.clip_start)}-{num(d.clip_end)}")
    elif o.type == "LIGHT":
        line = f"  light {d.type} energy {num(d.energy)} color {to_hex(d.color)}"
        if d.type == "SUN":
            line += f" angle_deg {num(d.angle * 57.29577951308232)}"
        lines.append(line)
    elif o.type == "EMPTY":
        lines.append(f"  empty {o.empty_display_type} size {num(o.empty_display_size)}")
    if getattr(o, "material_slots", None) and len(o.material_slots):
        lines.append("  materials " + ", ".join(s.material.name if s.material else "-" for s in o.material_slots))
    for m in o.modifiers:
        keys = MOD_KEYS.get(m.type, ())
        settings = " ".join(f"{k}={fmt(getattr(m, k))}" for k in keys if hasattr(m, k))
        lines.append(f"  modifier {m.name} {m.type} {settings}".rstrip())
    for c in o.constraints:
        lines.append(f"  constraint {c.name} {c.type}")
    for id_, label in zip(anim_ids(o), ("action", "shape_key_action")):
        ad = id_.animation_data
        if ad is not None and ad.action is not None:
            lines.append(f"  {label} {ad.action.name}")
    return lines


def walk(coll, path, out):
    out.append((path, coll))
    for ch in sorted(coll.children, key=lambda c: c.name):
        walk(ch, f"{path}/{ch.name}", out)
    return out


def manifest_text():
    scene = bpy.context.scene
    scene.frame_set(scene.frame_start)
    r = scene.render
    L = ["# Scene manifest, generated by: tweaks.py manifest (do not edit by hand).",
         "# Rotations in degrees, values at the first frame of the loop.", ""]

    L += ["[render]",
          f"engine {r.engine}",
          f"resolution {r.resolution_x}x{r.resolution_y} {r.resolution_percentage}%",
          f"fps {r.fps}/{num(r.fps_base)}",
          f"frames {scene.frame_start}-{scene.frame_end}",
          f"view_transform {scene.view_settings.view_transform} look {scene.view_settings.look}",
          f"film_transparent {r.film_transparent}",
          f"format {r.image_settings.file_format}"]
    if hasattr(scene, "eevee"):
        L.append(f"eevee_samples {scene.eevee.taa_render_samples}")
    world = scene.world
    if world is not None and world.node_tree is not None:
        bg = next((n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeBackground"), None)
        if bg is not None:
            L.append(f"world {to_hex(bg.inputs['Color'].default_value)} strength {num(bg.inputs['Strength'].default_value)}")
    L.append("")

    cam = scene.camera
    if cam is not None:
        L += [f"[camera] {cam.name}",
              f"loc {vec(cam.location)}",
              f"rot_deg {deg(cam.rotation_euler)}",
              f"lens {num(cam.data.lens)} sensor {num(cam.data.sensor_width)} {cam.data.sensor_fit}", ""]

    t = title_settings()
    if t is not None:
        c = bpy.data.objects[t["object"]].data
        L += [f"[title] {t['object']}",
              f"text {c.body}",
              f"font {t['font']}",
              *(f"{k} {num(t[k])}" for k in TITLE_FLOATS),
              f"extrude {num(c.extrude)} size {num(c.size)} align {c.align_x} {c.align_y}", ""]

    L.append("[materials]")
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        kind, _ = color_socket(m)
        line = f"{m.name}  {kind}  {to_hex(base_color(m))}"
        if to_hex(m.diffuse_color) != to_hex(base_color(m)):
            line += f"  viewport {to_hex(m.diffuse_color)}"
        shadow = toon_shadow(m) if kind == "toon" else None
        if shadow is not None:
            line += f"  shadow {num(shadow, 3)}"
        L.append(line)
    L.append("")

    L.append("[actions]")
    for a in sorted(bpy.data.actions, key=lambda a: a.name):
        fcs = action_fcurves(a)
        keys = sum(len(fc.keyframe_points) for fc in fcs)
        lo, hi = a.frame_range
        L.append(f"{a.name}  fcurves {len(fcs)}  keys {keys}  frames {num(lo, 1)}-{num(hi, 1)}")
    L.append("")

    for path, coll in walk(scene.collection, scene.collection.name, []):
        L.append(f"== {path} ({len(coll.objects)} objects)")
        for o in sorted(coll.objects, key=lambda o: o.name):
            L += object_lines(o)
        L.append("")
    return "\n".join(L)


def write_manifest(path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(manifest_text())
    print("wrote", path)


# --------------------------------------------------------------------------- export

def fresh_build():
    """Build the scene from the scripts, without tweaks.json, into a temp .blend."""
    tmp = tempfile.mkdtemp(prefix="hwp_build_")
    out = os.path.join(tmp, "fresh.blend")
    script = os.path.join(HERE, "build_scene.py")
    binary = bpy.app.binary_path
    if binary and "blender" in os.path.basename(binary).lower():
        cmd = [binary, "-b", "--factory-startup", "--python", script, "--", "--save", out]
    else:  # bpy module
        cmd = [sys.executable, script, "--save", out]
    print("building a fresh scene:", " ".join(cmd))
    env = dict(os.environ, REMAKE_NO_TWEAKS="1")
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(out):
        sys.stdout.write(res.stdout[-4000:] + res.stderr[-4000:])
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("fresh build failed, see the output above")
    return tmp, out


def differs(a, b, skip=()):
    return any(i not in skip and abs(x - y) > TOL for i, (x, y) in enumerate(zip(a, b)))


def diff(cur, ref):
    objects, not_captured = {}, []
    for name in sorted(set(cur["objects"]) & set(ref["objects"])):
        a, b = cur["objects"][name], ref["objects"][name]
        animated = {tuple(c) for c in a["animated"] + b["animated"]}
        entry = {}
        for k in TRANSFORMS:
            skip = {i for p, i in animated if p == k}
            if differs(a[k], b[k], skip):
                entry[k] = [round(x, 6) for x in a[k]]
        if entry:
            objects[name] = entry
        if a["keys"] != b["keys"]:
            not_captured.append(f"{name}: keyframes differ")
        if a["mesh"] != b["mesh"]:
            not_captured.append(f"{name}: mesh differs ({b['mesh']} -> {a['mesh']} verts/faces)")

    materials = {n: cur["materials"][n] for n in sorted(set(cur["materials"]) & set(ref["materials"]))
                 if cur["materials"][n] != ref["materials"][n]}

    title = {}
    ta, tb = cur["title"], ref["title"]
    if ta and tb:
        if ta["font"] != tb["font"]:
            title["font"] = ta["font"]
            title["font_path"] = ta["font_path"]
        for k in TITLE_FLOATS:
            if abs(ta[k] - tb[k]) > TOL:
                title[k] = round(ta[k], 6)
    elif ta or tb:
        not_captured.append("title: only in " + ("the .blend" if ta else "the fresh build"))

    out = {"objects": objects, "materials": materials, "title": title}
    unmatched = {
        "objects_only_in_blend": sorted(set(cur["objects"]) - set(ref["objects"])),
        "objects_only_in_build": sorted(set(ref["objects"]) - set(cur["objects"])),
        "materials_only_in_blend": sorted(set(cur["materials"]) - set(ref["materials"])),
        "materials_only_in_build": sorted(set(ref["materials"]) - set(cur["materials"])),
    }
    unmatched = {k: v for k, v in unmatched.items() if v}
    if unmatched:
        out["unmatched"] = unmatched
    if not_captured:
        out["not_captured"] = not_captured
    return out


def dump(data):
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    # keep number lists on one line: [1.0, 2.0, 3.0]
    return re.sub(r"\[\s+(-?[\d.eE+-]+(?:,\s+-?[\d.eE+-]+)*)\s+\]",
                  lambda m: "[" + " ".join(m.group(1).split()) + "]", text) + "\n"


def export(opts):
    source = bpy.data.filepath
    cur = snapshot()
    tmp = None
    against = opts["against"]
    if against is None:
        tmp, against = fresh_build()
    try:
        bpy.ops.wm.open_mainfile(filepath=against, load_ui=False)
        ref = snapshot()
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    data = diff(cur, ref)
    path = opts["out"] or TWEAKS
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(data))
    print(f"compared {source} against {'a fresh build' if tmp else against}")
    print(f"wrote {path}: {len(data['objects'])} objects, {len(data['materials'])} materials, "
          f"{len(data['title'])} title settings")
    for k, v in data.get("unmatched", {}).items():
        print(f"  {k}: {', '.join(v)}")
    for line in data.get("not_captured", []):
        print("  not captured:", line)


# --------------------------------------------------------------------------- apply

def find_font(name, hint=None):
    if name == "<builtin>":
        return bpy.data.fonts.load("<builtin>", check_existing=True)
    for f in bpy.data.fonts:
        if file_name(f.filepath).lower() == name.lower():
            return f
    dirs = [os.path.dirname(hint)] if hint else []
    dirs += [os.path.join(REMAKE, "fonts"),
             os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
             os.path.expanduser("~/Library/Fonts"), "/Library/Fonts", "/System/Library/Fonts/Supplemental"]
    for d in dirs:
        p = os.path.join(d, name)
        if d and os.path.exists(p):
            return bpy.data.fonts.load(p, check_existing=True)
    for d in ("/usr/share/fonts", os.path.expanduser("~/.local/share/fonts")):
        for root, _, files in os.walk(d):
            if name in files:
                return bpy.data.fonts.load(os.path.join(root, name), check_existing=True)
    return None


def apply_tweaks(path=TWEAKS):
    """Re-apply a tweaks.json made by export to the current scene."""
    from kit import srgb  # noqa: E402  (kit reads layout.json; only needed here)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    missing = []
    for name, entry in data.get("objects", {}).items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(f"object {name}")
            continue
        for k in TRANSFORMS:
            if k in entry:
                setattr(obj, k, entry[k])
    for name, hex_color in data.get("materials", {}).items():
        mat = bpy.data.materials.get(name)
        if mat is None:
            missing.append(f"material {name}")
            continue
        rgb = srgb(hex_color)
        _, sock = color_socket(mat)
        if sock is not None:
            sock.default_value = rgb if len(sock.default_value) == 3 else rgb + (sock.default_value[3],)
        mat.diffuse_color = rgb + (mat.diffuse_color[3],)
    title = data.get("title", {})
    if title:
        obj = title_object()
        if obj is None:
            missing.append("title")
        else:
            if "font" in title:
                font = find_font(title["font"], title.get("font_path"))
                if font is None:
                    missing.append(f"font {title['font']}")
                else:
                    obj.data.font = font
            for k in TITLE_FLOATS:
                if k in title:
                    setattr(obj.data, k, title[k])
    bpy.context.view_layer.update()
    print(f"applied {path}: {len(data.get('objects', {}))} objects, {len(data.get('materials', {}))} "
          f"materials, {len(title)} title settings")
    for m in missing:
        print("  not found, skipped:", m)


# --------------------------------------------------------------------------- main

def main():
    opts = parse_args()
    if not bpy.data.filepath:  # bpy module: nothing loaded yet
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    if opts["mode"] == "manifest":
        write_manifest(opts["out"] or MANIFEST)
    elif opts["mode"] == "export":
        export(opts)
    else:
        sys.path.insert(0, HERE)
        apply_tweaks(opts["tweaks"])
        if opts["save"]:
            bpy.ops.wm.save_as_mainfile(filepath=opts["save"], copy=True)
            print("saved", opts["save"])


if __name__ == "__main__":
    main()
