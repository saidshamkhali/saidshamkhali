"""Build the reference sheets for the 3D remake from the original GIF.

    python remake/reference/build_reference.py

Writes next to this file:
  contact_sheet.png  every frame, numbered
  figure_sheet.png   the centre figure, zoomed, with the yaw/pose from layout.json
  layout.png         frame 0 with every prop box from layout.json drawn on top
  prop_tracks.json   each prop's state per frame (mouth open, bell tilt, wing, toast, lean, loop)
  prop_drawings.json every prop's drawings, traced into coloured parts, and which one each frame shows
  frames/            every frame upscaled 3x, masks.npz with the figure's silhouettes and regions.npz
                     with its regions (ignored by git)

prop_drawings.json and regions.npz need frames/x4/, the GIF's frames upscaled 4x with a cartoon
upscaler (see the README); without them those two are skipped.
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


REGION_SCALE = 2  # regions.npz is twice the GIF's size: an eye is then a few pixels across


def classify_regions(rgb):
    """Each pixel's region: 0 background, 1 skin, 2 hair, beard and sandals, 3 robe and halo,
    4 anything else (outlines, which the source draws dark blue-grey, and props)."""
    import numpy as np
    from PIL import Image, ImageFilter
    a = rgb.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    bg = (b > 150) & (b - r > 30)
    lab = np.full(r.shape, 4, np.uint8)
    lab[bg] = 0
    lab[(mn > 140) & (mx - mn < 45) & ~bg] = 3
    lab[(r > 140) & (g > 95) & (b < 110) & (r - b > 80)] = 1
    dark = mx < 95
    # outlines are lines, not regions: keep only dark areas thicker than a line
    d = Image.fromarray((dark * 255).astype(np.uint8))
    thick = np.asarray(d.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))) > 0
    lab[dark & thick] = 2
    return lab


def export_regions():
    """frames/regions.npz: every frame's region map (classify_regions) at REGION_SCALE times
    the GIF's size, read off frames/x4/frame_NN.png: the GIF's frames upscaled 4x with a
    cartoon upscaler, which turns the dithering back into flat colour (see the README).
    blender/fit_pose.py fits his pose to these. Skipped when the upscaled frames aren't there."""
    import numpy as np
    src = os.path.join(HERE, "frames", "x4")
    if not os.path.isdir(src):
        print("no frames/x4/: skipping regions.npz")
        return
    w, h = LAYOUT["source"]["width"] * REGION_SCALE, LAYOUT["source"]["height"] * REGION_SCALE
    maps = []
    for k in range(LAYOUT["source"]["frames"]):
        im = Image.open(os.path.join(src, f"frame_{k:02d}.png")).convert("RGB").resize((w, h), Image.LANCZOS)
        maps.append(classify_regions(np.asarray(im)))
    np.savez_compressed(os.path.join(HERE, "frames", "regions.npz"), regions=np.array(maps), scale=REGION_SCALE)


DRAWING_CELL = 3   # traced drawings: three cells per GIF pixel
DRAWING_PAD = 12   # GIF pixels around a prop's box, room for its bigger drawings
# a drawing's parts, by colour: the ink (the whole drawing, its dark line-art showing between
# the coloured parts) at the back, then the colours
PART_NAMES = ("ink", "grey", "white", "yellow", "pink", "red")
# traced: the worms stay modelled (at three pixels tall their drawings trace into noise)
TRACED_TYPES = ("lips", "toaster", "alarm_clock", "bell")
SAME_DRAWING = 0.9  # silhouette overlap above which two frames show the same drawing


def rle(mask):
    """Rows of a boolean mask as "start,length,start,length;..." runs."""
    import numpy as np
    rows = []
    for row in mask:
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        rows.append(",".join(f"{s},{e - s}" for s, e in zip(starts, ends)))
    return ";".join(rows)


def colour_labels(rgb):
    """Each pixel's colour: 0 sky, then 1 + the index in PART_NAMES, 7 anything else."""
    import numpy as np
    a = rgb.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    bg = (b > 150) & (b - r > 30)
    lab = np.full(r.shape, 7, np.uint8)
    lab[bg] = 0
    lab[(mx - mn < 45) & (mn > 90) & (mx <= 205) & ~bg] = 2      # grey: metal, clock faces, worms
    lab[(mn > 205) & ~bg] = 3                                     # white: wings, teeth
    lab[(r > 150) & (g > 100) & (b < 110) & (r - b > 70)] = 4     # yellow: bells, toast, clock bells
    lab[(r > 150) & (r - g > 50) & (b > 90) & ~bg] = 5            # pink: lips
    lab[(r > 150) & (g < 90) & (b < 100)] = 6                     # red: tongues
    lab[mx < 100] = 1                                             # ink: outlines, slots, handles, mouths
    return lab


def drawing_parts(rgb, kind):
    """A drawing split into its parts (boolean masks, PART_NAMES): the ink is the whole drawing,
    every colour lies on it as drawn, so the line-art shows between them. Specks merge into
    their surroundings; parts too small to read are dropped."""
    import numpy as np
    from PIL import Image, ImageFilter
    raw = colour_labels(rgb)
    lab = np.asarray(Image.fromarray(raw).filter(ImageFilter.ModeFilter(5)))

    def morph(m, grow):
        im = Image.fromarray((m * 255).astype(np.uint8))
        f = ImageFilter.MaxFilter(grow * 2 + 1) if grow > 0 else ImageFilter.MinFilter(-grow * 2 + 1)
        return np.asarray(im.filter(f)) > 0

    whole = morph(lab != 0, -1)
    parts = {"ink": whole}
    for i, name in enumerate(PART_NAMES[1:], start=2):
        m = morph(morph(lab == i, -1), 1) & whole  # open: drop specks thinner than a couple of cells
        if name == "red":  # a tongue is thick and sits in an open mouth; closed lips have thin red texture lines
            m = morph(morph(lab == i, -2), 2) & whole
            if kind == "lips" and morph(morph(rgb.max(-1) < 70, -2), 2).sum() <= 200:
                m[:] = False
        if m.sum() >= 30:
            parts[name] = m
    return parts


def export_prop_drawings():
    """prop_drawings.json: every prop's drawings, traced off the upscaled frames (frames/x4/).
    Each prop flips between a few drawings; frames are grouped by their silhouettes, the most
    typical frame of each group is traced into coloured parts (drawing_parts), with the colours
    measured off the original, and every frame records which drawing it shows. props.py
    inflates the parts into 3D. Skipped without frames/x4/."""
    import numpy as np
    src = os.path.join(HERE, "frames", "x4")
    if not os.path.isdir(src):
        print("no frames/x4/: skipping prop_drawings.json")
        return
    n = LAYOUT["source"]["frames"]
    full = [Image.open(os.path.join(src, f"frame_{k:02d}.png")).convert("RGB") for k in range(n)]
    out = {"cell": DRAWING_CELL, "props": {}}
    for p in LAYOUT["props"]:
        if p["type"] not in TRACED_TYPES:
            continue
        x0, y0, x1, y1 = (p["box"][0] - DRAWING_PAD, p["box"][1] - DRAWING_PAD,
                          p["box"][2] + DRAWING_PAD, p["box"][3] + DRAWING_PAD)
        size = ((x1 - x0) * DRAWING_CELL, (y1 - y0) * DRAWING_CELL)
        crops = [np.asarray(im.crop((x0 * 4, y0 * 4, x1 * 4, y1 * 4)).resize(size, Image.LANCZOS)) for im in full]
        # only the prop itself: the connected silhouette under its box (neighbours stay out)
        sil = []
        for c in crops:
            m = ~((c[..., 2].astype(int) > 150) & (c[..., 2].astype(int) - c[..., 0] > 30))
            keep = np.zeros_like(m)
            b0, b1 = DRAWING_PAD * DRAWING_CELL, size[0] - DRAWING_PAD * DRAWING_CELL
            r0, r1 = DRAWING_PAD * DRAWING_CELL, size[1] - DRAWING_PAD * DRAWING_CELL
            keep[r0:r1, b0:b1] = m[r0:r1, b0:b1]
            for _ in range(DRAWING_PAD * DRAWING_CELL):  # grow back into the pad, through the prop only
                grown = keep.copy()
                grown[1:] |= keep[:-1]
                grown[:-1] |= keep[1:]
                grown[:, 1:] |= keep[:, :-1]
                grown[:, :-1] |= keep[:, 1:]
                grown &= m
                if (grown == keep).all():
                    break
                keep = grown
            sil.append(keep)
        groups = []
        for k, m in enumerate(sil):
            for grp in groups:
                ref = sil[grp[0]]
                if (m & ref).sum() / max(1, (m | ref).sum()) > SAME_DRAWING:
                    grp.append(k)
                    break
            else:
                groups.append([k])
        drawings, frame_drawing, colours = [], [0] * n, {}
        for i, grp in enumerate(groups):
            def typical(k):
                return np.mean([(sil[k] & sil[j]).sum() / max(1, (sil[k] | sil[j]).sum()) for j in grp])
            rep = max(grp, key=typical)
            parts = {name: m & sil[rep] for name, m in drawing_parts(crops[rep], p["type"]).items()}
            raw = colour_labels(crops[rep])
            for j, name in enumerate(PART_NAMES, start=1):
                if name in parts:
                    colours.setdefault(name, []).append(crops[rep][(raw == j) & sil[rep]].reshape(-1, 3))
            drawings.append({"frame": rep, "frames": grp, "parts": {name: rle(m) for name, m in parts.items()}})
            for k in grp:
                frame_drawing[k] = i
        palette = {}
        for name, px in colours.items():
            px = np.concatenate(px)
            if len(px):
                palette[name] = "#%02X%02X%02X" % tuple(int(v) for v in np.median(px, 0))
        out["props"][p["id"]] = {"type": p["type"], "origin": [x0, y0], "size": list(size), "palette": palette,
                                 "drawings": drawings, "frame_drawing": frame_drawing}
    with open(os.path.join(HERE, "prop_drawings.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))


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
    """frames/frame_NN.png upscaled 3x for looking at, and frames/gif/frame_NN.png at the GIF's
    own size, the upscaler's input (see the README)."""
    out = os.path.join(HERE, "frames")
    os.makedirs(os.path.join(out, "gif"), exist_ok=True)
    for i, fr in enumerate(frames):
        w, h = fr.size
        fr.resize((w * scale, h * scale), Image.LANCZOS).save(os.path.join(out, f"frame_{i:02d}.png"))
        fr.save(os.path.join(out, "gif", f"frame_{i:02d}.png"))


if __name__ == "__main__":
    frames = load_frames()
    contact_sheet(frames)
    figure_sheet(frames)
    layout_sheet(frames)
    export_frames(frames)
    export_masks(frames)
    export_regions()
    export_prop_drawings()
    export_prop_tracks(frames)
    print(f"{len(frames)} frames -> {HERE}")
