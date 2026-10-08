"""Aim his left hand where the original draws it while he beckons.

    blender -b remake/blender/homers_web_page.blend --python remake/blender/fit_hand.py

While he beckons, his left hand rests in front of his belly, inside his silhouette, so
fit_pose.py (which compares silhouettes) can't place it. figure.hand_targets in layout.json
holds where the hand's centre is in those frames, read off frames of the GIF upscaled with a
cartoon upscaler. For each one this searches the left arm's armL_x and elbowL offsets, on top
of what the scene has now, so the hand's centre lands on its target while it stays in front of
his belly, and writes them into reference/pose_fit.json (a held frame copies the one before).
Run it after fit_pose.py, then rebuild.
"""
import json
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jesus  # noqa: E402
from kit import LAYOUT, SRC_H, SRC_W, remake_frame  # noqa: E402

FRONT = 0.26  # the hand's centre stays this far in front of his axis (his belly is about 0.17)


def hand_px(rig, cam):
    """The hand's centre on screen in source pixels, and its depth in rig space (-Y is front)."""
    dg = bpy.context.evaluated_depsgraph_get()
    h = bpy.data.objects["J_hand_L"].evaluated_get(dg)
    p = sum((h.matrix_world @ Vector(c) for c in h.bound_box), Vector()) / 8
    v = world_to_camera_view(bpy.context.scene, cam, p)
    return v.x * SRC_W, (1 - v.y) * SRC_H, (rig.matrix_world.inverted() @ p).y


def fit_frame(rig, cam, k, target):
    scene = bpy.context.scene
    ad = rig.animation_data
    act, slot = ad.action, ad.action_slot
    up, fo = rig.pose.bones["upper_arm.L"], rig.pose.bones["forearm.L"]
    f = remake_frame(k)
    scene.frame_set(int(f), subframe=f - int(f))
    qu, qf = up.rotation_quaternion.copy(), fo.rotation_quaternion.copy()
    ad.action = None  # pose by hand; the action would override it
    best = None
    try:
        def search(xs, es):
            nonlocal best
            for dx in xs:
                up.rotation_quaternion = jesus.bone_rotation(up, (dx, 0, 0)) @ qu
                for de in es:
                    fo.rotation_quaternion = jesus.bone_rotation(fo, (de, 0, 0)) @ qf
                    bpy.context.view_layer.update()
                    x, y, depth = hand_px(rig, cam)
                    cost = ((x - target[0]) ** 2 + (y - target[1]) ** 2 + 0.002 * (dx * dx + de * de)
                            + 4e4 * max(0.0, depth + FRONT) ** 2)
                    if best is None or cost < best[0]:
                        best = (cost, dx, de)
        search(range(-30, 31, 6), range(-42, 43, 6))  # coarse, then fine around the best
        search(range(best[1] - 5, best[1] + 6), range(best[2] - 5, best[2] + 6))
    finally:
        up.rotation_quaternion, fo.rotation_quaternion = qu, qf
        ad.action, ad.action_slot = act, slot
    return best[1], best[2]


def main():
    scene = bpy.context.scene
    rig, cam = bpy.data.objects[jesus.RIG], scene.camera
    targets = {int(k): v for k, v in LAYOUT["figure"]["hand_targets"].items() if k != "note"}
    with open(jesus.FIT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    frames = data["frames"]
    held = set(LAYOUT["source"].get("held_frames", []))
    for k in sorted(targets):
        dx, de = fit_frame(rig, cam, k, targets[k])
        p = frames.setdefault(str(k), {})
        for name, d in (("armL_x", dx), ("elbowL", de)):
            v = round(p.get(name, 0.0) + d, 4)
            if abs(v) > 1e-6:
                p[name] = float(v)
            else:
                p.pop(name, None)
        frames[str(k)] = dict(sorted(p.items()))
        print(f"frame {k:2d}: armL_x {p.get('armL_x', 0):+.0f}  elbowL {p.get('elbowL', 0):+.0f}", flush=True)
    for k in sorted(held):  # held frames repeat the one before
        if k - 1 in targets:
            p = frames.setdefault(str(k), {})
            for name in ("armL_x", "elbowL"):
                if name in frames[str(k - 1)]:
                    p[name] = frames[str(k - 1)][name]
                else:
                    p.pop(name, None)
            frames[str(k)] = dict(sorted(p.items()))
    data["frames"] = {str(k): frames[str(k)] for k in sorted(int(k) for k in frames)}
    with open(jesus.FIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    scene.frame_set(1)


main()
