"""Fit the figure's pose to the original GIF, frame by frame.

    blender -b remake/blender/homers_web_page.blend --python remake/blender/fit_pose.py -- [options]

Options:
    --frames LIST    source frames to fit, e.g. 0-40 (the default), 12,14 or 2-4,6 (held and reused
                     frames are skipped, they copy)
    --loss L         "regions" (default when reference/frames/regions.npz exists) or "silhouette"
    --iters N        CMA-ES generations per frame (default 60)
    --out PATH       where to write the offsets (default remake/reference/pose_fit.json; a
                     partial run writes PATH with only its frames, merge them with --merge)
    --fix N=V,...    hold these offsets at fixed values instead of fitting them (e.g. yaw=0
                     where the drawing alone would rather turn him than move an arm)
    --part robe      a second pass over the hips and robe alone (ROBE_PARAMS), scored on the lower
                     half of the figure (averaged with the whole), the rest of the pose held at the fitted values
    --merge A B ...  merge partial result files into --out and stop

For each source frame the figure is rendered from the scene camera and compared with the GIF.
With the "regions" loss he is drawn in flat colours, one per region (skin, hair/beard/sandals,
robe), at twice the GIF's size, and compared region by region with reference/frames/regions.npz
(the upscaled original, see reference/build_reference.py), so the fit sees his hands in front of
the robe, his face and his feet, not just his outline; the outline counts too. Each hand the
designed pose shows also scores how much of it lands on skin in the drawing, so the fit can't
win pixels by tucking a hand behind the robe. The "silhouette" loss compares the outline alone
with reference/frames/masks.npz.

The offsets in jesus.FIT_PARAMS are searched together with CMA-ES (covariance matrix adaptation,
the usual tool for a few dozen coupled parameters), starting from the existing pose_fit.json,
with a small penalty for straying from the designed pose: a wide search, then a narrow one from
the best pose found. jesus.animate() bakes the result in.

The robe pass (--part robe) is there because the robe's swing and flare change little of the
whole figure's score: against the pose penalty they barely move in the full fit, though the
drawn robe is about a fifth wider at the hips while he beckons, and narrower side-on. With the hips, robe, legs and
feet counted twice and a lighter penalty, the hem follows the drawings.
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jesus  # noqa: E402
from kit import LAYOUT, REMAKE, remake_frame  # noqa: E402

# bound of each offset (degrees, units for slide/dip/feet, a fraction for stretch)
BOUND = {
    "slide": 0.35, "yaw": 45.0, "dip": 0.12, "tilt": 15.0, "pitch": 15.0, "twist": 30.0,
    "head_x": 20.0, "head_y": 20.0, "head_z": 30.0,
    "armL_x": 60.0, "armL_y": 60.0, "armL_z": 60.0, "elbowL": 70.0, "stretchL": 0.3,
    "armR_x": 60.0, "armR_y": 60.0, "armR_z": 60.0, "elbowR": 70.0, "stretchR": 0.3,
    "footL_x": 0.16, "footL_y": 0.25, "footR_x": 0.16, "footR_y": 0.25,
    "sway": 0.1, "thrust": 0.1, "lean": 15.0, "skirt_x": 25.0, "skirt_y": 25.0, "flare": 0.4,
    "wristL": 60.0, "wristR": 60.0,
}
PENALTY = 0.02          # cost of an offset at its bound, in IoU
ROBE_PARAMS = ("sway", "thrust", "tilt", "skirt_x", "skirt_y", "flare")
ROBE_PENALTY = 0.004    # the robe pass: the hem may follow the drawing
REGION = (60, 262, 165, 315)  # rows, cols of the GIF compared (the figure and its reach)
CLASSES = {1: "skin", 2: "dark", 3: "robe"}
COLOURS = {1: (1, 0, 0, 1), 2: (0, 1, 0, 1), 3: (0, 0, 1, 1)}
HAND_COLOURS = {"L": (1, 0, 0.15, 1), "R": (1, 0.15, 0, 1)}  # skin, each hand told apart by a touch of another colour
HAND_WEIGHT = 0.5  # each visible hand's term, against 1 for each region
MATERIAL_CLASS = {"skin": 1, "white": 1, "black": 1, "hair": 2, "sandal": 2, "robe": 3}  # eyes read as skin, as drawn


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    regions = os.path.exists(os.path.join(REMAKE, "reference", "frames", "regions.npz"))
    opts = {"frames": list(range(41)), "loss": "regions" if regions else "silhouette", "iters": 60,
            "out": jesus.FIT_FILE, "merge": None, "fix": {}, "part": "all"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--frames":
            opts["frames"] = [k for part in argv[i + 1].split(",") for k in
                              (range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1))]; i += 2
        elif a == "--loss":
            opts["loss"] = argv[i + 1]; i += 2
        elif a == "--iters":
            opts["iters"] = int(argv[i + 1]); i += 2
        elif a == "--fix":
            opts["fix"] = {n: float(v) for n, v in (kv.split("=") for kv in argv[i + 1].split(","))}; i += 2
        elif a == "--part":
            opts["part"] = argv[i + 1]; i += 2
        elif a == "--out":
            opts["out"] = os.path.abspath(argv[i + 1]); i += 2
        elif a == "--merge":
            i += 1
            opts["merge"] = []
            while i < len(argv) and not argv[i].startswith("--"):
                opts["merge"].append(argv[i]); i += 1
        else:
            raise SystemExit(f"unknown option {a}")
    return opts


def write(path, frames):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"note": "per source frame offsets on top of the designed poses, fitted by blender/fit_pose.py",
                   "params": list(jesus.FIT_PARAMS),
                   "frames": {str(k): {p: round(v, 4) for p, v in sorted(d.items()) if abs(v) > 1e-6}
                              for k, d in sorted(frames.items())}}, f, indent=1)


def cmaes(f, x0, sigma=0.15, iters=60, seed=0):
    """Minimise f over [-1, 1]^n from x0 with CMA-ES (Hansen's standard settings). Returns the
    best point seen and its value."""
    rng = np.random.default_rng(seed)
    n = len(x0)
    lam = 4 + int(3 * math.log(n))
    mu = lam // 2
    w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    w /= w.sum()
    mueff = 1 / (w ** 2).sum()
    cc = (4 + mueff / n) / (n + 4 + 2 * mueff / n)
    cs = (mueff + 2) / (n + mueff + 5)
    c1 = 2 / ((n + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0.0, math.sqrt((mueff - 1) / (n + 1)) - 1) + cs
    chin = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
    m = np.clip(np.array(x0, float), -1, 1)
    C, B, D = np.eye(n), np.eye(n), np.ones(n)
    ps, pc = np.zeros(n), np.zeros(n)
    best = (f(m), m.copy())
    for g in range(iters):
        z = rng.standard_normal((lam, n))
        xs = np.clip(m + sigma * (z * D) @ B.T, -1, 1)
        fx = np.array([f(x) for x in xs])
        order = np.argsort(fx)
        if fx[order[0]] < best[0]:
            best = (fx[order[0]], xs[order[0]].copy())
        ys = (xs[order[:mu]] - m) / sigma
        ymean = w @ ys
        m = m + sigma * ymean
        inv_sqrt = B @ np.diag(1 / D) @ B.T
        ps = (1 - cs) * ps + math.sqrt(cs * (2 - cs) * mueff) * inv_sqrt @ ymean
        hsig = np.linalg.norm(ps) / math.sqrt(1 - (1 - cs) ** (2 * (g + 1))) / chin < 1.4 + 2 / (n + 1)
        pc = (1 - cc) * pc + hsig * math.sqrt(cc * (2 - cc) * mueff) * ymean
        C = ((1 - c1 - cmu) * C + c1 * (np.outer(pc, pc) + (1 - hsig) * cc * (2 - cc) * C)
             + cmu * (ys.T * w) @ ys)
        sigma *= math.exp((cs / damps) * (np.linalg.norm(ps) / chin - 1))
        D2, B = np.linalg.eigh((C + C.T) / 2)
        D = np.sqrt(np.maximum(D2, 1e-20))
        if sigma * D.max() < 2e-3:
            break
    return best


class Fitter:
    def __init__(self, loss, part="all"):
        self.loss, self.part = loss, part
        self.scene = bpy.context.scene
        self.rig = bpy.data.objects[jesus.RIG]
        ref = os.path.join(REMAKE, "reference", "frames")
        if loss == "regions":
            d = np.load(os.path.join(ref, "regions.npz"))
            self.target, self.scale = d["regions"], int(d["scale"])
        else:
            self.target, self.scale = np.load(os.path.join(ref, "masks.npz"))["masks"], 1
        self.tmp = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), f"fit_{os.getpid()}.png")
        r = self.scene.render
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x = LAYOUT["source"]["width"] * self.scale
        r.resolution_y = LAYOUT["source"]["height"] * self.scale
        r.resolution_percentage = 100
        r.film_transparent = True
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        r.image_settings.compression = 0
        r.filepath = self.tmp
        r0, r1, c0, c1 = REGION
        r.use_border, r.use_crop_to_border = True, True
        r.border_min_x, r.border_max_x = c0 / LAYOUT["source"]["width"], c1 / LAYOUT["source"]["width"]
        r.border_min_y, r.border_max_y = 1 - r1 / LAYOUT["source"]["height"], 1 - r0 / LAYOUT["source"]["height"]
        self.scene.display.render_aa = "OFF"
        shading = self.scene.display.shading
        shading.light = "FLAT"
        shading.color_type = "OBJECT"
        keep = {o.name for o in self.rig.children} - {"J_halo"}
        for coll in bpy.data.collections:  # whole collections: traced props key their own visibility
            coll.hide_render = self.rig.name not in coll.objects
        for o in self.scene.objects:
            if o.type in {"MESH", "FONT", "CURVE"}:
                o.hide_render = o.name not in keep
                if o.name in keep:
                    mat = o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
                    o.color = COLOURS[MATERIAL_CLASS.get(mat, 1)]
                    if o.name.startswith("J_hand_"):
                        o.color = HAND_COLOURS[o.name[-1]]
                    for m in o.modifiers:  # the viewport's subdivision: the same outline at this size, a lot faster
                        if m.type == "SUBSURF":
                            m.render_levels = m.levels
        self.right = jesus.screen_right()
        self.reanimate_without_fit()
        self.renders = 0

    def reanimate_without_fit(self):
        saved = jesus.FIT_FILE
        jesus.FIT_FILE = os.path.join(REMAKE, "__no_fit__.json")
        rig = self.rig
        rig.animation_data_clear()
        for p in rig.pose.bones:
            p.location = (0, 0, 0)
            p.scale = (1, 1, 1)
        if "base_location" in rig:
            rig.location = rig["base_location"]
        jesus.animate(rig)
        jesus.FIT_FILE = saved

    def capture(self, k):
        self.k = k
        for p in self.rig.pose.bones:  # channels the animation doesn't key stay at rest, not at the last trial
            p.location, p.rotation_quaternion, p.scale = (0, 0, 0), (1, 0, 0, 0), (1, 1, 1)
        f = remake_frame(k)
        self.scene.frame_set(int(f), subframe=f - int(f))
        rig = self.rig
        rig.location = rig["base_location"]  # not animated here: undo the last frame's slide
        self.base = (rig.location.copy(), rig.rotation_euler.copy(),
                     {p.name: (p.location.copy(), p.rotation_quaternion.copy(), p.scale.copy()) for p in rig.pose.bones})
        r0, r1, c0, c1 = (v * self.scale for v in REGION)
        self.want = self.target[k][r0:r1, c0:c1]
        self.hand_area = {}
        # the lower half of the figure, hair top to soles: hips, robe, legs and feet
        hair = np.nonzero((self.want == 2).sum(1) > 4)[0]
        body = np.nonzero((self.want != 0).sum(1) > 2)[0]
        self.lower = hair[0] + (body[-1] - hair[0]) // 2 if len(hair) and len(body) else 0

    def measure_hands(self):
        """How big each hand shows in the designed pose (call with the action off): the hands
        term only counts the hands it shows (not the one behind his head), and hiding one
        scores as a miss."""
        self.hand_area = {}
        self.pose({})
        hands = self.hands(self.render())
        self.hand_area = {side: 0.6 * m.sum() for side, m in hands.items() if m.sum() > 30}

    def pose(self, params):
        """The pose jesus.animate() would bake for these offsets: the body's, then the head
        re-aimed as aim_head does (the face keeps pointing where HEAD_YAW says while the fitted
        yaw turns the body), then the head's own."""
        rig = self.rig
        loc, rot, bones = self.base
        rig.location, rig.rotation_euler = loc, rot
        for name, (l, q, s) in bones.items():
            pb = rig.pose.bones[name]
            pb.location, pb.rotation_quaternion, pb.scale = l, q, s
        jesus.apply_offsets(rig, params, self.right)
        if self.k in jesus.HEAD_YAW and params.get("yaw"):
            head = rig.pose.bones["head"]
            head.rotation_quaternion = jesus.bone_rotation(head, (0, 0, params["yaw"])) @ head.rotation_quaternion
        jesus.apply_head_offsets(rig, params)

    def render(self):
        bpy.ops.render.render(write_still=True)
        self.renders += 1
        img = bpy.data.images.load(self.tmp, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        return px.reshape(h, w, 4)[::-1]

    @staticmethod
    def hands(px):
        """Each hand's visible pixels: skin with its touch of blue (left) or green (right)."""
        skin = (px[..., 3] > 0.5) & (px[..., 0] > 0.5)
        touch = lambda c: (px[..., c] > 0.05) & (px[..., c] < 0.5)  # noqa: E731
        return {"L": skin & touch(2), "R": skin & touch(1)}

    def score(self, params):
        """1 = a perfect match."""
        self.pose(params)
        px = self.render()
        want = self.want
        if want.shape != px.shape[:2]:
            px = px[:want.shape[0], :want.shape[1]]
        if self.loss == "silhouette":
            fg = px[..., 3] > 0.5
            return (want & fg).sum() / max(1, (want | fg).sum())
        ious = self.ious(want, px)
        if self.part == "robe":  # the lower half counts as much again; the whole keeps the torso in place
            return float((np.mean(ious) + np.mean(self.ious(want[self.lower:], px[self.lower:]))) / 2)
        terms = []
        if self.hand_area:  # each hand should land on skin the drawing shows: not robe, not hidden
            hands = self.hands(px)
            for side, area in self.hand_area.items():
                h = hands[side]
                terms.append(((h & (want == 1)).sum()) / max(h.sum(), area))
        return float((np.sum(ious) + HAND_WEIGHT * np.sum(terms)) / (len(ious) + HAND_WEIGHT * len(terms)))

    @staticmethod
    def ious(want, px):
        """Overlap of each region, and of the outline."""
        fg = px[..., 3] > 0.5
        ours = np.zeros(fg.shape, np.uint8)
        ours[fg & (px[..., 0] > 0.5)] = 1
        ours[fg & (px[..., 1] > 0.5)] = 2
        ours[fg & (px[..., 2] > 0.5)] = 3
        care = want != 4  # outlines and props: no say
        ious = []
        for c in CLASSES:
            a, b = (want == c) & care, (ours == c) & care
            u = (a | b).sum()
            if u:
                ious.append((a & b).sum() / u)
        sil_t = want != 0
        ious.append((sil_t & fg).sum() / max(1, (sil_t | fg).sum()))
        return ious

    def fit(self, k, guess, iters, fix):
        self.capture(k)
        anim = self.rig.animation_data
        act, slot = anim.action, anim.action_slot
        anim.action = None
        self.measure_hands()
        robe = self.part == "robe"
        names = [n for n in (ROBE_PARAMS if robe else jesus.FIT_PARAMS) if n not in fix]
        penalty = ROBE_PENALTY if robe else PENALTY
        try:
            def params(x):
                p = dict(guess) if robe else {}  # the robe pass holds the rest of the pose
                p.update({n: v * BOUND[n] for n, v in zip(names, x)})
                p.update(fix)
                return p

            def cost(x):
                return 1 - self.score(params(x)) + penalty * float(np.sum(np.asarray(x) ** 2))

            x0 = np.array([max(-1.0, min(1.0, guess.get(n, 0.0) / BOUND[n])) for n in names])
            before = self.score(params(x0))
            # a wide search, then a narrow one from the best pose it found: from a pose that
            # already fits well, wide steps that move every offset at once rarely beat it
            c, x = cmaes(cost, x0, sigma=0.12, iters=iters // 2, seed=k)
            c2, x2 = cmaes(cost, x, sigma=0.035, iters=iters - iters // 2, seed=k + 1000)
            p = params(x2 if c2 < c else x)
            return p, self.score(p), before
        finally:
            anim.action = act
            anim.action_slot = slot


def main():
    opts = parse_args()
    if opts["merge"]:
        frames = {k: v for k, v in jesus.load_fit().items()}
        for path in opts["merge"]:
            with open(path, encoding="utf-8") as f:
                frames.update({int(k): v for k, v in json.load(f)["frames"].items()})
        held = LAYOUT["source"].get("held_frames", [])
        for k in sorted(held):  # held frames repeat the one before
            if k - 1 in frames:
                frames[k] = dict(frames[k - 1])
        write(opts["out"], frames)
        print(f"merged {len(opts['merge'])} files into {opts['out']}")
        return
    fitter = Fitter(opts["loss"], opts["part"])
    prior = jesus.load_fit()
    skip = set(LAYOUT["source"].get("held_frames", [])) | set(jesus.REUSE)
    out = {}
    t0 = time.time()
    for k in opts["frames"]:
        if k in skip:
            continue
        p, score, before = fitter.fit(k, prior.get(k, {}), opts["iters"], opts["fix"])
        out[k] = p
        print(f"frame {k:2d}: match {before:.3f} -> {score:.3f}  " +
              " ".join(f"{n}={v:+.3g}" for n, v in p.items() if abs(v) > 1e-6), flush=True)
        write(opts["out"], out)
    print(f"{fitter.renders} renders in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
