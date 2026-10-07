"""Fit the figure's pose to the original GIF, frame by frame.

    blender -b remake/blender/homers_web_page.blend --python remake/blender/fit_pose.py -- [options]

Options:
    --frames A-B     source frames to fit (default 0-40)
    --passes N       coordinate-descent passes, each with half the step size (default 3)
    --out PATH       where to write the offsets (default remake/reference/pose_fit.json; a
                     partial run writes PATH with only its frames, merge them with --merge)
    --fix N=V,...    hold these offsets at fixed values instead of fitting them (e.g. yaw=0
                     where the silhouette alone would rather turn him than move an arm)
    --merge A B ...  merge partial result files into --out and stop

For each source frame, the figure's silhouette is rendered at the GIF's own size from the
scene camera and compared with the GIF's silhouette (reference/frames/masks.npz, written by
reference/build_reference.py). The offsets in jesus.FIT_PARAMS (how far he slides across
the screen, the turn, dip, lean and the arm angles) are nudged one at a time to raise the
overlap, with a small penalty for straying from the designed pose. The designed pose is the
starting point; an existing pose_fit.json is the first guess. jesus.animate() bakes the result in.
"""
import json
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jesus  # noqa: E402
from kit import REMAKE, remake_frame  # noqa: E402

# step (first pass), bound: units for slide and dip, degrees for the rest
SEARCH = {
    "slide": (0.03, 0.35), "yaw": (6.0, 45.0), "dip": (0.02, 0.12), "tilt": (3.0, 15.0), "pitch": (3.0, 15.0),
    "armL_x": (8.0, 60.0), "armL_y": (8.0, 60.0), "elbowL": (10.0, 70.0),
    "armR_x": (8.0, 60.0), "armR_y": (8.0, 60.0), "elbowR": (10.0, 70.0),
}
PENALTY = 0.02          # cost of an offset at its bound, in IoU
REGION = (60, 262, 165, 315)  # rows, cols of the GIF compared (the figure and its reach)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"frames": (0, 40), "passes": 3, "out": jesus.FIT_FILE, "merge": None, "fix": {}}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--frames":
            lo, hi = argv[i + 1].split("-"); opts["frames"] = (int(lo), int(hi)); i += 2
        elif a == "--passes":
            opts["passes"] = int(argv[i + 1]); i += 2
        elif a == "--fix":
            opts["fix"] = {n: float(v) for n, v in (kv.split("=") for kv in argv[i + 1].split(","))}; i += 2
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


class Fitter:
    def __init__(self):
        self.scene = bpy.context.scene
        self.rig = bpy.data.objects["Jesus_Rig"]
        self.masks = np.load(os.path.join(REMAKE, "reference", "frames", "masks.npz"))["masks"]
        self.tmp = os.path.join(bpy.app.tempdir or os.environ.get("TEMP", "."), f"fit_{os.getpid()}.png")
        r = self.scene.render
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x, r.resolution_y, r.resolution_percentage = self.masks.shape[2], self.masks.shape[1], 100
        r.film_transparent = True
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        r.image_settings.compression = 0
        r.filepath = self.tmp
        self.scene.display.render_aa = "OFF"
        self.scene.display.shading.light = "FLAT"
        keep = {o.name for o in self.rig.children} - {"J_halo"}
        for o in self.scene.objects:
            if o.type in {"MESH", "FONT", "CURVE"}:
                o.hide_render = o.name not in keep
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
        f = remake_frame(k)
        self.scene.frame_set(int(f), subframe=f - int(f))
        rig = self.rig
        rig.location = rig["base_location"]  # not animated here: undo the last frame's slide
        self.base = (rig.location.copy(), rig.rotation_euler.copy(),
                     {p.name: (p.location.copy(), p.rotation_quaternion.copy(), p.scale.copy()) for p in rig.pose.bones})

    def pose(self, params):
        rig = self.rig
        loc, rot, bones = self.base
        rig.location, rig.rotation_euler = loc, rot
        for name, (l, q, s) in bones.items():
            pb = rig.pose.bones[name]
            pb.location, pb.rotation_quaternion, pb.scale = l, q, s
        jesus.apply_offsets(rig, params, self.right)

    def iou(self, params, k):
        self.pose(params)
        bpy.ops.render.render(write_still=True)
        self.renders += 1
        img = bpy.data.images.load(self.tmp, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        ours = px[3::4].reshape(h, w)[::-1] > 0.5
        r0, r1, c0, c1 = REGION
        a, b = self.masks[k][r0:r1, c0:c1], ours[r0:r1, c0:c1]
        return (a & b).sum() / max(1, (a | b).sum())

    def cost(self, params, k):
        pen = sum((params.get(p, 0.0) / SEARCH[p][1]) ** 2 for p in SEARCH)
        return 1 - self.iou(params, k) + PENALTY * pen

    def fit(self, k, guess, passes, fix=None):
        self.capture(k)
        anim = self.rig.animation_data
        act, slot = anim.action, anim.action_slot
        anim.action = None
        try:
            fix = fix or {}
            p = {n: fix.get(n, guess.get(n, 0.0)) for n in SEARCH}
            best = self.cost(p, k)
            start = 1 - best + PENALTY * 0  # rough IoU before
            steps = {n: s for n, (s, _) in SEARCH.items()}
            for _ in range(passes):
                for n in (n for n in SEARCH if n not in fix):
                    improved = True
                    while improved:
                        improved = False
                        for d in (steps[n], -steps[n]):
                            q = dict(p)
                            q[n] = max(-SEARCH[n][1], min(SEARCH[n][1], p[n] + d))
                            if q[n] == p[n]:
                                continue
                            c = self.cost(q, k)
                            if c < best - 1e-4:
                                best, p, improved = c, q, True
                                break
                steps = {n: s / 2 for n, s in steps.items()}
            return p, self.iou(p, k), start
        finally:
            anim.action = act
            anim.action_slot = slot


def main():
    opts = parse_args()
    if opts["merge"]:
        frames = {}
        for path in opts["merge"]:
            with open(path, encoding="utf-8") as f:
                frames.update({int(k): v for k, v in json.load(f)["frames"].items()})
        write(opts["out"], frames)
        print(f"merged {len(frames)} frames into {opts['out']}")
        return
    fitter = Fitter()
    prior = jesus.load_fit()
    lo, hi = opts["frames"]
    out, prev = {}, None
    t0 = time.time()
    for k in range(lo, hi + 1):
        guess = prior.get(k) or prev or {}
        p, iou, before = fitter.fit(k, guess, opts["passes"], opts["fix"])
        out[k], prev = p, p
        print(f"frame {k:2d}: IoU {before:.3f} -> {iou:.3f}  " +
              " ".join(f"{n}={v:+.3g}" for n, v in p.items() if abs(v) > 1e-6), flush=True)
        write(opts["out"], out)
    print(f"{fitter.renders} renders in {time.time() - t0:.0f} s")


main()
