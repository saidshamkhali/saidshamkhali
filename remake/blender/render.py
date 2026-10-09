"""Render the committed scene as it is, without rebuilding it.

Run with Blender 5.x:
    blender -b remake/blender/homers_web_page.blend --python remake/blender/render.py -- [options]
or with the bpy module (pip install bpy), which opens homers_web_page.blend itself:
    python remake/blender/render.py [options]

Options:
    --still N [N ...]  render these frames to remake/render/stills/still_####.png
    --render           render the whole loop to remake/render/frames/frame_####.png
    --percent P        render resolution percentage (default: the file's own)

Everything else (engine, resolution, samples, frame range) comes from the file's own
scene settings, so hand edits made in the Blender UI show up. The .blend is never saved.
make_gif.py turns the frames into the GIF.
"""
import glob
import os
import re
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REMAKE = os.path.dirname(HERE)
BLEND = os.path.join(HERE, "homers_web_page.blend")


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    elif "blender" in os.path.basename(sys.argv[0]).lower():
        argv = []
    else:
        argv = sys.argv[1:]
    opts = {"still": [], "render": False, "percent": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--still":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                opts["still"].append(int(argv[i])); i += 1
        elif a == "--render":
            opts["render"] = True; i += 1
        elif a == "--percent":
            opts["percent"] = int(argv[i + 1]); i += 2
        else:
            raise SystemExit(f"unknown option {a}")
    if not opts["still"] and not opts["render"]:
        raise SystemExit("nothing to render: pass --still N [N ...] and/or --render")
    return opts


def stale_frames(out, last):
    """Frames left over from a longer loop; make_gif.py would pick them up."""
    extra = []
    for p in glob.glob(os.path.join(out, "frame_*.png")):
        m = re.fullmatch(r"frame_(\d+)\.png", os.path.basename(p))
        if m and int(m.group(1)) > last:
            extra.append(os.path.basename(p))
    return sorted(extra)


def main():
    opts = parse_args()
    if not bpy.data.filepath:  # bpy module: nothing loaded yet
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    print("rendering", bpy.data.filepath)
    scene = bpy.context.scene
    if opts["percent"]:
        scene.render.resolution_percentage = opts["percent"]
    if scene.render.image_settings.file_format != "PNG":
        print("output format", scene.render.image_settings.file_format, "-> PNG for this run")
        scene.render.image_settings.file_format = "PNG"

    if opts["still"]:
        out = os.path.join(REMAKE, "render", "stills")
        os.makedirs(out, exist_ok=True)
        for f in opts["still"]:
            scene.frame_set(f)
            scene.render.filepath = os.path.join(out, f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
            print("rendered", scene.render.filepath)
    if opts["render"]:
        out = os.path.join(REMAKE, "render", "frames")
        os.makedirs(out, exist_ok=True)
        scene.render.filepath = os.path.join(out, "frame_")
        bpy.ops.render.render(animation=True)
        print(f"rendered frames {scene.frame_start}-{scene.frame_end} to", out)
        extra = stale_frames(out, scene.frame_end)
        if extra:
            print(f"warning: {len(extra)} older frames past the loop end are still in {out} "
                  f"({extra[0]} ...); delete them before make_gif.py")


if __name__ == "__main__":
    main()
