"""Build the reference sheets for the 3D remake from the original GIF.

    python remake/reference/build_reference.py

Writes next to this file:
  contact_sheet.png  every frame, numbered
  figure_sheet.png   the centre figure, zoomed, with the yaw/pose from layout.json
  layout.png         frame 0 with every prop box from layout.json drawn on top
  frames/            every frame upscaled 3x (ignored by git)
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

with open(os.path.join(HERE, "layout.json"), encoding="utf-8") as f:
    LAYOUT = json.load(f)


def load_frames():
    gif = Image.open(os.path.join(REPO, LAYOUT["source"]["file"]))
    frames = []
    for i in range(gif.n_frames):
        gif.seek(i)
        frames.append(gif.convert("RGB"))
    return frames


def font(size):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def label(draw, xy, text, size=18):
    x, y = xy
    f = font(size)
    l, t, r, b = draw.textbbox((x, y), text, font=f)
    draw.rectangle((l - 3, t - 2, r + 3, b + 2), fill="black")
    draw.text((x, y), text, fill="white", font=f)


def pose_at(frame):
    """Nearest timeline key at or before this source frame."""
    keys = LAYOUT["figure"]["timeline"]
    return max((k for k in keys if k["frame"] <= frame), key=lambda k: k["frame"])


def save_small(img, name):
    """Sheets come from a 256-colour GIF, so a palette PNG keeps them small at no visible cost."""
    img.info.pop("transparency", None)  # carried over from the GIF frame, invalid once quantized
    img.quantize(colors=256).save(os.path.join(HERE, name), optimize=True)


def contact_sheet(frames, cols=7):
    w, h = frames[0].size
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "white")
    draw = ImageDraw.Draw(sheet)
    for i, fr in enumerate(frames):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(fr, (x, y))
        label(draw, (x + 6, y + 6), str(i), 20)
    save_small(sheet, "contact_sheet.png")


def figure_sheet(frames, cols=11, scale=2):
    x0, y0, x1, y1 = LAYOUT["figure"]["box"]
    x0, y0, x1, y1 = x0 - 16, y0 - 6, x1 + 16, y1 + 6
    cw, ch = (x1 - x0) * scale, (y1 - y0) * scale
    pad = 40
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGB", (cols * cw, rows * (ch + pad)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, fr in enumerate(frames):
        x, y = (i % cols) * cw, (i // cols) * (ch + pad)
        crop = fr.crop((x0, y0, x1, y1)).resize((cw, ch), Image.LANCZOS)
        sheet.paste(crop, (x, y + pad))
        key = pose_at(i)
        draw.text((x + 4, y + 2), f"{i}", fill="black", font=font(16))
        draw.text((x + 4, y + 20), f"{key['pose']} {key['yaw']}°", fill="#555", font=font(13))
    save_small(sheet, "figure_sheet.png")


def layout_sheet(frames, scale=3):
    w, h = frames[0].size
    img = frames[0].resize((w * scale, h * scale), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    colors = {"alarm_clock": "#d00", "toaster": "#06c", "bell": "#c80",
              "lips": "#c0c", "worm": "#080"}
    for p in LAYOUT["props"]:
        bx = [v * scale for v in p["box"]]
        draw.rectangle(bx, outline=colors[p["type"]], width=3)
        label(draw, (bx[0], bx[3] + 2), f"{p['id']}  ph {p['phase']}", 14)
    bx = [v * scale for v in LAYOUT["figure"]["box"]]
    draw.rectangle(bx, outline="black", width=3)
    fx, fy = (v * scale for v in LAYOUT["figure"]["feet"])
    draw.ellipse((fx - 6, fy - 6, fx + 6, fy + 6), fill="black")
    bx = [v * scale for v in LAYOUT["title"]["box"]]
    draw.rectangle(bx, outline="black", width=2)
    save_small(img, "layout.png")


def export_frames(frames, scale=3):
    out = os.path.join(HERE, "frames")
    os.makedirs(out, exist_ok=True)
    for i, fr in enumerate(frames):
        w, h = fr.size
        fr.resize((w * scale, h * scale), Image.LANCZOS).save(os.path.join(out, f"frame_{i:02d}.png"))


if __name__ == "__main__":
    frames = load_frames()
    contact_sheet(frames)
    figure_sheet(frames)
    layout_sheet(frames)
    export_frames(frames)
    print(f"{len(frames)} frames -> {HERE}")
