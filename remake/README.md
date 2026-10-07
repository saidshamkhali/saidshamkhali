# Homer's Web Page in 3D

A 3D remake of `jesus-christ-homer.gif` (41 frames, 498x318, 10 fps), toon-shaded with outlines (concept A in `concepts/`), rendered at 25 fps.

## Layout

| Path | What |
|---|---|
| `concepts/` | Style concepts. A (toon + outlines) is the chosen one |
| `reference/layout.json` | Prop positions, figure yaw/pose timeline and prop cycle lengths, measured from the GIF. The Blender script reads this |
| `reference/build_reference.py` | Regenerates the reference sheets and `reference/frames/` |
| `reference/contact_sheet.png` | Every source frame, numbered |
| `reference/figure_sheet.png` | The figure, zoomed, with yaw/pose per frame |
| `reference/layout.png` | Frame 0 with every prop box drawn |
| `blender/build_scene.py` | Entry point: camera, title, floor, lights, placement, rendering |
| `blender/jesus.py` | The figure: modelled in code, skinned to an armature, poses and timeline |
| `blender/props.py` | Toasters, alarm clocks, bells, lips and worms, each with its own loop |
| `blender/kit.py` | Shared settings, toon materials, mesh builders, keyframe helpers |
| `make_gif.py` | Rendered frames to a looping GIF via ffmpeg |

## What the original does

- **Figure**: one full turn per loop, never at a constant speed. Back view (frames 0-2) → quick turn through facing screen-left (3-4) → front, waving (6-10) → hand to face (11) → beckoning with his right arm, swaying (12-23) → hand to face (24) → waving again (25-29) → turn through facing screen-right (31-35) → back view (36-40).
- **Props**: 14 of them in five kinds. Clocks, bells and toasters run on a ~0.6 s cycle, the lips open and close every ~0.9 s, and the worms wiggle slowly. Same-type props are offset in phase.

## Loop timing

25 fps × 105 frames = 4.2 s (original: 4.1 s). GIF delays are whole hundredths of a second and browsers slow anything under 2/100 s, so 25 fps (4/100 s) plays exactly. 105 frames divides into whole prop cycles (15, 21 and 35 frames), so the loop has no seam.

## Run

Blender 5.x, either the app or the `bpy` module (`pip install bpy`, Python 3.13):

```bash
python remake/reference/build_reference.py
python remake/blender/build_scene.py --still 1 39 70
python remake/blender/build_scene.py --render
python remake/make_gif.py
```

With the Blender app instead: `blender --background --python remake/blender/build_scene.py -- --render`.

The script writes `remake/blender/homers_web_page.blend`, so you can open the scene and keep working in the UI.

## The figure

`jesus.py` builds him from lofted cross-sections and ellipsoid blobs: robe with V-neck, sleeves, four-finger hands, sandals, Simpsons head with heavy lids, beard, moustache, long hair and halo. Every part is skinned to the `Jesus_Rig` armature (`root`, `hips`, `chest`, `head`, `upper_arm/forearm/hand.L/R`), so the elbows bend smoothly. Poses are in `POSES`, written in rest-pose axes, and keyed from the timeline in `layout.json`. The turn is the armature object's Z rotation.
