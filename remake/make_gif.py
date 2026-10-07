"""Turn the rendered loop into a looping GIF with ffmpeg.

    python remake/make_gif.py [--width 800] [--colors 128] [--out remake/render/preview.gif]

Reads remake/render/frames/frame_####.png (from build_scene.py --render).
Plays at 25 fps: GIF delays are whole 1/100 s, so 25 fps (4/100 s) is exact.
"""
import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=int, default=800)
ap.add_argument("--colors", type=int, default=128)
ap.add_argument("--fps", type=int, default=25)
ap.add_argument("--out", default=os.path.join(HERE, "render", "preview.gif"))
args = ap.parse_args()

filters = (
    f"scale={args.width}:-1:flags=lanczos,split[a][b];"
    f"[a]palettegen=max_colors={args.colors}:stats_mode=full[p];"
    "[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
)
subprocess.run([
    "ffmpeg", "-y", "-loglevel", "error",
    "-framerate", str(args.fps),
    "-i", os.path.join(HERE, "render", "frames", "frame_%04d.png"),
    "-vf", filters, "-loop", "0", args.out,
], check=True)
print(f"{args.out}  {os.path.getsize(args.out) / 1e6:.2f} MB")
