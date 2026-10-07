"""Turn the rendered loop into looping animations with ffmpeg.

    python remake/make_gif.py [--width 800] [--colors 256] [--formats gif,webp,mp4] [--out remake/render/preview]

Reads remake/render/frames/frame_####.png (from build_scene.py --render or render.py --render)
and writes OUT.gif, OUT.webp and/or OUT.mp4:
  gif   256 colours, for anywhere. Plays at 10 fps like the original: GIF delays are whole
        1/100 s, so 10/100 s is exact.
  webp  animated WebP, full colour and much smaller; GitHub READMEs show it like a GIF.
  mp4   H.264 for video players and the web.
"""
import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=int, default=800)
ap.add_argument("--colors", type=int, default=256)
ap.add_argument("--fps", type=int, default=10)
ap.add_argument("--formats", default="gif,webp")
ap.add_argument("--out", default=os.path.join(HERE, "render", "preview"))
args = ap.parse_args()

src = ["-framerate", str(args.fps), "-i", os.path.join(HERE, "render", "frames", "frame_%04d.png")]
scale = f"scale={args.width}:-2:flags=lanczos"
jobs = {
    "gif": ["-vf", f"{scale},split[a][b];[a]palettegen=max_colors={args.colors}:stats_mode=full[p];"
                   "[b][p]paletteuse=dither=none:diff_mode=rectangle", "-loop", "0"],
    "webp": ["-vf", scale, "-c:v", "libwebp_anim", "-lossless", "0", "-quality", "92",
             "-compression_level", "6", "-loop", "0"],
    "mp4": ["-vf", f"{scale},format=yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
            "-movflags", "+faststart"],
}
out = os.path.splitext(args.out)[0]
for fmt in args.formats.split(","):
    path = f"{out}.{fmt}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, *jobs[fmt], path], check=True)
    print(f"{path}  {os.path.getsize(path) / 1e6:.2f} MB")
