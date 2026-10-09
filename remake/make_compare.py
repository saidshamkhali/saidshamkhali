"""The original and the remake side by side, frame for frame, as a looping animation.

    python remake/make_compare.py [--height 400] [--formats webp,gif] [--out remake/render/compare]

Reads the original GIF from the repo root and the rendered loop from
remake/render/frames/frame_####.png (one frame per source frame, at 10 fps).
"""
import argparse
import glob
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--height", type=int, default=400)
ap.add_argument("--formats", default="webp,gif")
ap.add_argument("--out", default=os.path.join(HERE, "render", "compare"))
args = ap.parse_args()

gif = Image.open(os.path.join(REPO, "jesus-christ-homer.gif"))
ours = sorted(glob.glob(os.path.join(HERE, "render", "frames", "frame_*.png")))
if len(ours) != gif.n_frames:
    raise SystemExit(f"{len(ours)} rendered frames, expected {gif.n_frames} (render the loop at 10 fps first)")


def font(size):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


H = args.height
W = round(H * gif.width / gif.height)
gap, label = 8, max(14, H // 22)
with tempfile.TemporaryDirectory() as tmp:
    for k, path in enumerate(ours):
        gif.seek(k)
        a = gif.convert("RGB").resize((W, H), Image.LANCZOS)
        b = Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
        sheet = Image.new("RGB", (W * 2 + gap, H), (20, 20, 24))
        sheet.paste(a, (0, 0))
        sheet.paste(b, (W + gap, 0))
        d = ImageDraw.Draw(sheet)
        for x, text in ((8, "Original"), (W + gap + 8, "3D remake")):
            d.text((x, H - label - 8), text, fill=(255, 255, 255), font=font(label), stroke_width=2,
                   stroke_fill=(20, 20, 24))
        sheet.save(os.path.join(tmp, f"c_{k:04d}.png"))
    src = ["-framerate", "10", "-i", os.path.join(tmp, "c_%04d.png")]
    jobs = {
        "gif": ["-vf", "split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none", "-loop", "0"],
        "webp": ["-c:v", "libwebp_anim", "-quality", "90", "-compression_level", "6", "-loop", "0"],
        "mp4": ["-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "16"],
    }
    for fmt in args.formats.split(","):
        out = f"{os.path.splitext(args.out)[0]}.{fmt}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, *jobs[fmt], out], check=True)
        print(f"{out}  {os.path.getsize(out) / 1e6:.2f} MB")
