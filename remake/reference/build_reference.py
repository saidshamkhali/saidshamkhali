"""Build the reference sheets for the 3D remake from the original GIF.

    python remake/reference/build_reference.py

Writes next to this file:
  contact_sheet.png  every frame, numbered
  figure_sheet.png   the centre figure, zoomed, with the yaw/pose from layout.json
  layout.png         frame 0 with every prop box from layout.json drawn on top
  prop_tracks.json   each prop's state per frame (mouth open, bell tilt, wing, toast, lean, loop)
  frames/            every frame upscaled 3x, and masks.npz with the figure's silhouettes (ignored by git)
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


def export_masks(frames):
    """frames/masks.npz: the figure's silhouette in every frame (anything that isn't the blue
    background; the pale halo counts as background), for blender/fit_pose.py."""
    import numpy as np
    from PIL import ImageFilter
    masks = []
    for fr in frames:
        a = np.asarray(fr).astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        bg = (b > 120) & (b - r > 28) & (g - r > 8)
        m = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3))
        masks.append(np.asarray(m) > 0)
    out = os.path.join(HERE, "frames")
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, "masks.npz"), masks=np.array(masks))


def prop_masks(frames, box, pad=4):
    """Per frame: (rgb array, foreground mask) of the region around one prop."""
    import numpy as np
    from PIL import ImageFilter
    x0, y0, x1, y1 = box
    out = []
    for fr in frames:
        a = np.asarray(fr.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))).astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        bg = (b > 120) & (b - r > 28) & (g - r > 8)
        m = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3))
        out.append((a, np.asarray(m) > 0))
    return out


def norm(values, lo=None, hi=None):
    """Scale to 0..1 between the given (or the observed) extremes, clamped."""
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    return [round(min(1.0, max(0.0, (v - lo) / (hi - lo))), 3) if hi != lo else 0.0 for v in values]


HALF_OPEN_DARK = 170  # outline and mouth pixels of the half-open mouth (the closed one has about 160)
TEETH_PX = 12  # white pixels: only the shouting drawings show their teeth
BELL_SWING_PX = 9.0


def track_prop(kind, regions):
    """The prop's state in every frame, read off the drawings. Each track is one value per
    frame, 0..1 or -1..1, that props.py turns into a pose."""
    import numpy as np
    tracks = {}
    tops, bottoms, leans, tilts, wings, toasts, darks, whites = [], [], [], [], [], [], [], []
    for a, m in regions:
        ys, xs = np.nonzero(m)
        tops.append(ys.min() if len(ys) else m.shape[0])
        bottoms.append(ys.max() if len(ys) else 0)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        darks.append(int((m & (r < 90) & (g < 70) & (b < 70)).sum()))
        whites.append(int((m & (r > 200) & (g > 200) & (b > 200)).sum()))
        if kind == "alarm_clock":  # lean: top half's centre against the bottom half's
            h = m.shape[0] // 2
            t, bt = np.nonzero(m[:h]), np.nonzero(m[h:])
            leans.append((t[1].mean() - bt[1].mean()) / h if len(t[1]) and len(bt[1]) else 0.0)
        if kind == "bell":  # tilt: the gold body's centre against the whole bell's top
            gold = m & (r > 150) & (g > 110) & (b < 90)
            gy, gx = np.nonzero(gold)
            dark = m & (r < 90) & (g < 70) & (b < 70)
            dy, dx = np.nonzero(dark[: m.shape[0] // 2])
            tilts.append((gx.mean() - dx.mean()) if len(gx) and len(dx) else 0.0)
        if kind == "toaster":
            white = m & (r > 215) & (g > 215) & (b > 215)
            wy, wx = np.nonzero(white)
            wings.append(-wy.mean() if len(wy) else 0.0)  # higher wing = larger value
            toast = m & (r > 170) & (g > 90) & (g < 175) & (b < 110)
            ty, tx = np.nonzero(toast)
            toasts.append(-ty.min() if len(ty) else -m.shape[0])
    if kind == "worm":  # how far the top edge rises above its lowest drawing
        hi = max(tops)
        tracks["curl"] = norm([hi - t for t in tops], 0)
    if kind == "lips":  # which drawing: teeth showing = a shout (0.55..1 by how tall it is),
        # a dark mouth without teeth = half open (0.35), otherwise closed (0)
        span = [b - t for t, b in zip(tops, bottoms)]
        tall = [s for s, w in zip(span, whites) if w >= TEETH_PX] or [0, 1]
        lo, hi = min(tall), max(tall)
        tracks["open"] = [round(0.55 + 0.45 * (s - lo) / max(1, hi - lo), 3) if w >= TEETH_PX
                          else 0.35 if d >= HALF_OPEN_DARK else 0.0 for s, w, d in zip(span, whites, darks)]
    if kind == "alarm_clock":
        s = max(abs(v) for v in leans) or 1.0
        tracks["lean"] = [round(v / s, 3) for v in leans]
    if kind == "bell":  # pixels the body sits off the handle: 0 upright, about 9 at full swing
        tracks["tilt"] = [round(max(-1.0, min(1.0, v / BELL_SWING_PX)), 3) for v in tilts]
    if kind == "toaster":
        tracks["wing"] = norm(wings)
        tracks["toast"] = norm(toasts)
    return tracks


def export_prop_tracks(frames):
    """prop_tracks.json: every prop's state per frame, so the props move drawing for drawing."""
    out = {}
    for p in LAYOUT["props"]:
        out[p["id"]] = track_prop(p["type"], prop_masks(frames, p["box"], pad=10))  # room to swing
    with open(os.path.join(HERE, "prop_tracks.json"), "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(
            f' "{pid}": {{' + ", ".join(f'"{k}": {json.dumps(v)}' for k, v in t.items()) + "}"
            for pid, t in out.items()) + "\n}\n")


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
    export_masks(frames)
    export_prop_tracks(frames)
    print(f"{len(frames)} frames -> {HERE}")
