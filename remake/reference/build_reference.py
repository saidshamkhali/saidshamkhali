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
DRAWING_PAD = 15   # GIF pixels around a prop's box, room for its bigger drawings (a shout reaches 12 above it)
GROUP_REACH = 12   # GIF pixels past its box that a prop's silhouette is followed when grouping its frames
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
    # the greys run on into the whites: the toasters' pale top faces and rims are grey, not
    # wing white and not "anything else" (which used to turn them into black lids)
    neutral = (mx - mn < 45) & (mn > 90) & ~bg
    lab[neutral] = 2                                              # grey: metal, clock faces, worms
    lab[((mn > 205) | (neutral & (a.mean(-1) > 212))) & ~bg] = 3  # white: wings, teeth
    lab[(r > 150) & (g > 100) & (b < 110) & (r - b > 70)] = 4     # yellow: bells, toast, clock bells
    lab[(r > 150) & (r - g > 50) & (b > 90) & ~bg] = 5            # pink: lips
    lab[(r > 150) & (g < 90) & (b < 100)] = 6                     # red: tongues
    # the toast's brown and pink crust is toast too (lips are pink with more blue than green)
    lab[(lab == 7) & (r > 110) & (r - b > 45) & (g - b > 15)] = 4
    lab[mx < 100] = 1                                             # ink: outlines, slots, handles, mouths
    return lab


SPECK = 12  # cells: a smaller patch of a colour is noise (a GIF pixel is nine cells)
HOLE = 60   # cells: a smaller hole in a colour, or in the drawing, is texture or noise, filled
TICKS = 12  # tick marks round a clock face, as long and wide as drawn: these shares of the face's radius
TICK_LEN = 0.13
TICK_WIDTH = 0.085
# only the big clock has tick marks: the band round its face's edge is 3-5% marks darker than
# the face, the small clocks' plain faces under 1%
TICK_MARKED = 0.015


def components(mask):
    """The 4-connected patches of a boolean mask: each cell's patch number (0 outside the mask)
    and each patch's size in cells (index 0 unused)."""
    import numpy as np
    h, w = mask.shape
    inside = mask.ravel().tolist()
    lab = [0] * (h * w)
    sizes = [0]
    for start in np.flatnonzero(mask).tolist():
        if lab[start]:
            continue
        n = len(sizes)
        lab[start] = n
        todo, count = [start], 0
        while todo:
            k = todo.pop()
            count += 1
            y, x = divmod(k, w)
            for nb, ok in ((k - w, y > 0), (k + w, y < h - 1), (k - 1, x > 0), (k + 1, x < w - 1)):
                if ok and inside[nb] and not lab[nb]:
                    lab[nb] = n
                    todo.append(nb)
        sizes.append(count)
    return np.array(lab).reshape(h, w), np.array(sizes)


def fill_holes(mask, cells):
    """mask with every hole in it (a patch outside it that doesn't reach the edge) smaller than
    `cells` filled in."""
    import numpy as np
    lab, sizes = components(~mask)
    small = sizes < cells
    small[0] = False
    small[np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))] = False
    return mask | small[lab]


def regrow(lab, cells, labels, steps=None):
    """Give each of `cells` the label of a neighbour with one of `labels`, growing in from the
    edges of the patch, one cell per step (all the way, or `steps` cells). Returns the new labels
    and the cells left over."""
    import numpy as np
    lab, todo = lab.copy(), cells.copy()
    lab[todo] = 255
    k = 0
    while todo.any() and (steps is None or k < steps):
        k += 1
        new = lab.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.full_like(lab, 255)
            nb[max(dy, 0):lab.shape[0] + min(dy, 0), max(dx, 0):lab.shape[1] + min(dx, 0)] = \
                lab[max(-dy, 0):lab.shape[0] + min(-dy, 0), max(-dx, 0):lab.shape[1] + min(-dx, 0)]
            take = todo & (new == 255) & np.isin(nb, labels)
            new[take] = nb[take]
        grown = todo & (new != 255)
        if not grown.any():
            break
        lab, todo = new, todo & ~grown
    return lab, todo


def morph(m, grow):
    """Grow (grow > 0) or shrink a boolean mask by `grow` cells (a square)."""
    import numpy as np
    from PIL import Image, ImageFilter
    im = Image.fromarray((m * 255).astype(np.uint8))
    f = ImageFilter.MaxFilter(grow * 2 + 1) if grow > 0 else ImageFilter.MinFilter(-grow * 2 + 1)
    return np.asarray(im.filter(f)) > 0


def clean_labels(rgb, kind):
    """The drawing's colour labels (colour_labels), cleaned: each colour a few clean patches
    and the ink only where the drawing has lines.
    - Pale pixels that match no colour (the anti-aliasing between two colours, a highlight) take
      the colour next to them; dark ones are ink. Small patches of sky inside the drawing (a pale
      blue highlight on chrome) are treated the same way, so they don't show the sky through it.
    - A mode filter merges the upscaler's speckle into its surroundings.
    - Specks of a colour, and thin red (the texture lines on lips; a tongue is thick), take the
      colour round them. Closed lips have no tongue: all their red is lip.
    - Small holes in a colour (the texture lines and dots inside closed lips, a dark speck) are
      filled with it. Thin strips of colour (a toaster's rim, a row of teeth, the toast standing
      in its slot) are kept: they're the drawing, and used to turn into ink."""
    import numpy as np
    from PIL import Image, ImageFilter
    lab = colour_labels(rgb)
    sky, _ = components(lab == 0)
    sizes = np.bincount(sky.ravel())
    edge = np.unique(np.concatenate([sky[0], sky[-1], sky[:, 0], sky[:, -1]]))
    small = sizes < HOLE
    small[0] = False
    small[edge] = False
    lab[small[sky]] = 7
    a = rgb.astype(int)
    pale = (lab == 7) & (a @ np.array([0.3, 0.59, 0.11]) >= 135)
    lab, _ = regrow(lab, pale, [2, 3, 4, 5, 6], steps=4)
    lab[(lab == 7) | (lab == 255)] = 1
    if kind == "toaster":  # the toast is one colour: its pink and red crust is toast
        lab[(lab == 5) | (lab == 6)] = 4
    if kind == "lips":  # grey in a mouth is the teeth's shade
        lab[lab == 2] = 3
    lab = np.asarray(Image.fromarray(lab).filter(ImageFilter.ModeFilter(3))).copy()
    red = lab == 6
    noise = red & ~morph(morph(red, -2), 2)
    if kind == "lips" and morph(morph(rgb.max(-1) < 70, -2), 2).sum() <= 200:
        noise = red
    for c in (2, 3, 4, 5, 6):
        patches, sizes = components(lab == c)
        noise |= (sizes < SPECK)[patches] & (patches > 0)
    lab, left = regrow(lab, noise, [1, 2, 3, 4, 5, 6])
    lab[left] = 1
    for c in (2, 3, 4, 5, 6):
        m = lab == c
        lab[fill_holes(m, HOLE) & ~m & (lab != 0)] = c
    if kind == "alarm_clock":
        lab = clock_face(lab, rgb)
    return lab


def clock_face(lab, rgb):
    """An alarm clock's face, redrawn clean. The upscaler leaves it lumpy and the mode filter
    eats its tick marks (they're a GIF pixel each), which makes the ring round it look heavy and
    uneven. The face becomes the ellipse that fits it best, with the hands (the ink through its
    middle) kept as drawn, and, if the drawing (rgb) has them, TICKS small notches round its
    edge, the first one towards the bells, so they lean with the clock."""
    import math

    import numpy as np
    face = lab == 2
    if face.sum() < 200:
        return lab
    disc = fill_holes(morph(morph(face, 3), -3), face.size)  # the face with the hands closed over
    ys, xs = np.nonzero(disc)
    cy, cx = ys.mean(), xs.mean()
    evals, axes = np.linalg.eigh(np.cov(np.stack([ys - cy, xs - cx])))
    radii = 2 * np.sqrt(evals)  # a solid ellipse's second moments are a quarter of its radii squared
    yy, xx = np.mgrid[:lab.shape[0], :lab.shape[1]]
    rel = np.stack([yy - cy, xx - cx], -1).astype(float)
    ell = (((rel @ axes) / radii) ** 2).sum(-1)
    inside = ell <= 1
    patches, _ = components(inside & ~face)
    hands = np.isin(patches, np.unique(patches[(ell <= 0.5) & (patches > 0)])) & (patches > 0)
    lab = lab.copy()
    lab[face & ~inside] = 1
    lab[inside & ~hands] = 2
    lab[inside & hands] = 1
    lum = rgb.astype(int) @ np.array([0.3, 0.59, 0.11])
    band = (ell > 0.72 ** 2) & (ell < 0.92 ** 2) & ~morph(hands, 2)  # where the ticks are, away from the hands
    plain = np.median(lum[face & (ell < 0.6 ** 2)])
    if not band.any() or (lum[band] < plain - 40).mean() < TICK_MARKED:
        return lab
    by, bx = np.nonzero(lab == 4)
    top = math.atan2(by.mean() - cy, bx.mean() - cx) if len(by) else -math.pi / 2
    r = radii.mean()
    for k in range(TICKS):
        a = top + 2 * math.pi * k / TICKS
        d = np.array([math.sin(a), math.cos(a)])
        edge = 1 / math.sqrt((((d @ axes) / radii) ** 2).sum())
        along = rel @ d
        across = np.abs(rel @ np.array([-d[1], d[0]]))
        lab[inside & (along > edge - TICK_LEN * r) & (across <= TICK_WIDTH * r / 2)] = 1
    return lab


REP_SLACK = 0.02  # a drawing is traced from its most typical frame, or one this close that's cleaner


def blotches(rgb):
    """Cells of other colours or ink enclosed by a colour: the texture and noise the upscaler
    drew into a frame (the closed lips' wrinkles in some frames, none in others)."""
    lab = colour_labels(rgb)
    return int(sum((fill_holes(lab == c, 4 * HOLE) & (lab != c) & (lab != 0)).sum() for c in (2, 3, 4, 5, 6)))


def drawing_parts(rgb, kind):
    """A drawing split into its parts (boolean masks, PART_NAMES): the ink is the whole drawing,
    every colour lies on it as drawn, so the line-art shows between them. The labels are cleaned
    first (clean_labels); parts too small to read are dropped."""
    lab = clean_labels(rgb, kind)
    whole = morph(fill_holes(lab != 0, HOLE), -1)
    parts = {"ink": whole}
    for i, name in enumerate(PART_NAMES[1:], start=2):
        m = (lab == i) & whole
        if m.sum() >= 30:
            parts[name] = m
    return parts


def silhouette(crop, steps=None):
    """A prop's own silhouette in a crop of DRAWING_PAD round its box: what isn't sky inside the
    box, grown out through what isn't sky, `steps` cells at most (all the way with None)."""
    import numpy as np
    m = ~((crop[..., 2].astype(int) > 150) & (crop[..., 2].astype(int) - crop[..., 0] > 30))
    keep = np.zeros_like(m)
    pad = DRAWING_PAD * DRAWING_CELL
    keep[pad:m.shape[0] - pad, pad:m.shape[1] - pad] = m[pad:m.shape[0] - pad, pad:m.shape[1] - pad]
    k = 0
    while steps is None or k < steps:
        k += 1
        grown = keep.copy()
        grown[1:] |= keep[:-1]
        grown[:-1] |= keep[1:]
        grown[:, 1:] |= keep[:, :-1]
        grown[:, :-1] |= keep[:, 1:]
        grown &= m
        if (grown == keep).all():
            break
        keep = grown
    return keep


def unrle(runs, w, h):
    """The boolean mask back from rle()."""
    import numpy as np
    m = np.zeros((h, w), bool)
    for i, row in enumerate(runs.split(";")):
        v = [int(x) for x in row.split(",")] if row else []
        for a, k in zip(v[::2], v[1::2]):
            m[i, a:a + k] = True
    return m


# props too small to trace cleanly, and the bigger prop whose drawings they show (borrow_drawings)
BORROWED = {"toaster_s": "toaster_l", "toaster_tr": "toaster_l"}
BORROW_SCALES = [0.55 + 0.01 * k for k in range(31)]  # a copied prop's size against the one it copies
BORROW_SHIFT = 4  # cells a copied drawing may move from where its silhouette's centre puts it


def borrow_drawings(spec, sil, groups, source):
    """Fill in spec (a prop's origin and size) with the drawings of `source`, scaled down: the
    small toasters are the big toaster's drawing at about two thirds of its size, and at 30 GIF
    pixels wide the upscaler invents their detail, so their own drawings trace into dark lumpy
    blobs. One scale fits every frame (the one whose drawings cover the frames' silhouettes
    best). The prop keeps its own drawings' timing: each group of its frames that show one
    drawing (groups) gets the source drawing, and the place, that covers them best. Frame by
    frame the small silhouettes are too noisy to tell two wings apart. sil: the prop's
    silhouette in every frame."""
    import numpy as np
    from collections import Counter
    w, h = spec["size"]
    sw, sh = source["size"]
    drawings = [{name: unrle(runs, sw, sh) for name, runs in dr["parts"].items()} for dr in source["drawings"]]

    def place(mask, s, dx, dy):  # the source grid scaled by s, centred on the prop's grid, moved by (dx, dy)
        nw, nh = round(sw * s), round(sh * s)
        m = np.asarray(Image.fromarray(mask).resize((nw, nh), Image.NEAREST))
        placed = np.zeros((h, w), bool)
        x0, y0 = (w - nw) // 2 + dx, (h - nh) // 2 + dy
        ax, ay = max(0, x0), max(0, y0)
        bx, by = min(w, x0 + nw), min(h, y0 + nh)
        placed[ay:by, ax:bx] = m[ay - y0:by - y0, ax - x0:bx - x0]
        return placed

    def centre(m):
        ys, xs = np.nonzero(m)
        return xs.mean(), ys.mean()

    def fits(s, shift):
        """[frame][drawing] = (overlap, dx, dy): where each source drawing covers each frame best."""
        table = [[(0.0, 0, 0)] * len(drawings) for _ in sil]
        for i, parts in enumerate(drawings):
            base = place(parts["ink"], s, 0, 0)
            bx, by = centre(base)
            for k, m in enumerate(sil):
                mx, my = centre(m)
                cx, cy = round(mx - bx), round(my - by)
                for dy in range(cy - shift, cy + shift + 1):
                    for dx in range(cx - shift, cx + shift + 1):
                        moved = np.zeros_like(base)
                        moved[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = \
                            base[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
                        iou = (moved & m).sum() / max(1, (moved | m).sum())
                        if iou > table[k][i][0]:
                            table[k][i] = (iou, dx, dy)
        return table

    s = max(BORROW_SCALES, key=lambda s: sum(max(f[0] for f in row) for row in fits(s, 1)))
    table = fits(s, BORROW_SHIFT)
    spec["palette"] = source["palette"]
    spec["drawings"], spec["frame_drawing"] = [], [0] * len(sil)
    for g, grp in enumerate(groups):
        i = max(range(len(drawings)), key=lambda i: sum(table[k][i][0] for k in grp))
        where = Counter(table[k][i][1:] for k in grp).most_common(1)[0][0]
        spec["drawings"].append({"frame": grp[0], "from": source["drawings"][i]["frame"], "frames": grp,
                                 "parts": {name: rle(place(m, s, *where)) for name, m in drawings[i].items()}})
        for k in grp:
            spec["frame_drawing"][k] = g


def export_prop_drawings():
    """prop_drawings.json: every prop's drawings, traced off the upscaled frames (frames/x4/).
    Each prop flips between a few drawings; frames are grouped by their silhouettes, and the
    most typical frame of each group (or one nearly as typical with fewer blotches) is traced
    into coloured parts (drawing_parts), with the colours measured off the original. Every frame
    records which drawing it shows. The props in BORROWED show a bigger prop's drawings instead
    (borrow_drawings). props.py inflates the parts into 3D. Skipped without frames/x4/."""
    import numpy as np
    src = os.path.join(HERE, "frames", "x4")
    if not os.path.isdir(src):
        print("no frames/x4/: skipping prop_drawings.json")
        return
    n = LAYOUT["source"]["frames"]
    full = [Image.open(os.path.join(src, f"frame_{k:02d}.png")).convert("RGB") for k in range(n)]
    out = {"cell": DRAWING_CELL, "props": {}}
    sils = {}
    for p in LAYOUT["props"]:
        if p["type"] not in TRACED_TYPES:
            continue
        x0, y0, x1, y1 = (p["box"][0] - DRAWING_PAD, p["box"][1] - DRAWING_PAD,
                          p["box"][2] + DRAWING_PAD, p["box"][3] + DRAWING_PAD)
        size = ((x1 - x0) * DRAWING_CELL, (y1 - y0) * DRAWING_CELL)
        crops = [np.asarray(im.crop((x0 * 4, y0 * 4, x1 * 4, y1 * 4)).resize(size, Image.LANCZOS)) for im in full]
        # only the prop itself: the connected silhouette under its box (neighbours stay out)
        sil = [silhouette(c, GROUP_REACH * DRAWING_CELL) for c in crops]
        groups = []
        for k, m in enumerate(sil):
            for grp in groups:
                ref = sil[grp[0]]
                if (m & ref).sum() / max(1, (m | ref).sum()) > SAME_DRAWING:
                    grp.append(k)
                    break
            else:
                groups.append([k])
        if p["id"] in BORROWED:  # filled in below, once the prop it copies is traced
            sils[p["id"]] = (sil, groups)
            out["props"][p["id"]] = {"type": p["type"], "origin": [x0, y0], "size": list(size)}
            continue
        drawings, frame_drawing, colours = [], [0] * n, {}
        for i, grp in enumerate(groups):
            def typical(k):
                return np.mean([(sil[k] & sil[j]).sum() / max(1, (sil[k] | sil[j]).sum()) for j in grp])
            best = max(typical(k) for k in grp)
            near = [k for k in grp if typical(k) >= best - REP_SLACK]
            rep = min(near, key=lambda k: (blotches(crops[k] * sil[k][..., None]), -typical(k)))
            # the traced drawing is all of the prop: a shout's lip reaches further from the box than
            # the grouping looks (silhouette), and a pale highlight the sky test took for a hole is filled
            solid = fill_holes(silhouette(crops[rep]), HOLE)
            parts = {name: m & solid for name, m in drawing_parts(crops[rep], p["type"]).items()}
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
    for p in LAYOUT["props"]:
        if p["id"] in BORROWED:
            borrow_drawings(out["props"][p["id"]], *sils[p["id"]], out["props"][BORROWED[p["id"]]])
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


# worms whose curl is read off the upscaled frames: worm_l's arch is the smallest, and in the
# dithered GIF its top edge jumps by whole pixels, so its track there comes out squashed (arches
# the drawings show nearly full read as half). The others read the same either way.
X4_CURL = ("worm_l",)


def x4_curl(box):
    """A worm's curl per frame off frames/x4/: how far its top edge rises (to a quarter pixel),
    0 at its lowest, 1 at its highest. None without the upscaled frames."""
    import numpy as np
    src = os.path.join(HERE, "frames", "x4")
    if not os.path.isdir(src):
        return None
    x0, y0, x1, y1 = box
    rise = []
    for k in range(LAYOUT["source"]["frames"]):
        a = np.asarray(Image.open(os.path.join(src, f"frame_{k:02d}.png")).convert("RGB")).astype(int)
        a = a[(y0 - 18) * 4:(y1 + 4) * 4, (x0 - 4) * 4:(x1 + 4) * 4]  # room above for the arch
        body = ~((a[..., 2] > 150) & (a[..., 2] - a[..., 0] > 30))
        rise.append(-np.nonzero(body.sum(1) >= 2)[0].min() / 4)
    return norm(rise)


def export_prop_tracks(frames):
    """prop_tracks.json: every prop's state per frame, so the props move drawing for drawing."""
    out = {}
    for p in LAYOUT["props"]:
        out[p["id"]] = track_prop(p["type"], prop_masks(frames, p["box"], pad=10))  # room to swing
        if p["id"] in X4_CURL:
            out[p["id"]]["curl"] = x4_curl(p["box"]) or out[p["id"]]["curl"]
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
