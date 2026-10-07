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
| `blender/homers_web_page.blend` | The scene. Tracked, and the source of truth once edited in the UI |
| `blender/render.py` | Renders the tracked .blend as it is |
| `blender/tweaks.py` | Carries UI edits across a rebuild, and writes `scene_manifest.txt` |
| `blender/scene_manifest.txt` | Text summary of the .blend, so its changes show up in diffs |
| `fonts/` | Ultra (Apache 2.0, by Astigmatic), the title font, packed into the .blend |
| `tools/pre-commit` | Git hook that refreshes the manifest when the .blend is staged |
| `make_gif.py` | Rendered frames to a looping GIF via ffmpeg |

## What the original does

- **Figure**: one full turn per loop, never at a constant speed. Back view (frames 0-2) → quick turn through facing screen-left (3-4) → front, waving (6-10) → hand to face (11) → beckoning with his right arm, swaying (12-23) → hand to face (24) → waving again (25-29) → turn through facing screen-right (31-35) → back view (36-40).
- **Props**: 14 of them in five kinds. Clocks, bells and toasters run on a ~0.6 s cycle, the lips open and close every ~0.9 s, and the worms curl the middle of their body up into a tight loop and flatten out again about once a second, without going anywhere. Same-type props are offset in phase. Everything is drawn at 10 fps, so each pose is held for a tenth of a second.

## Loop timing

25 fps × 105 frames = 4.2 s (original: 4.1 s). GIF delays are whole hundredths of a second and browsers slow anything under 2/100 s, so 25 fps (4/100 s) plays exactly. Every prop runs a whole number of cycles per loop (clocks, bells and toasters 7, lips 5, worms 4), so the loop has no seam.

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

`jesus.py` builds him from parametric surfaces:

- **Head:** a Simpsons cylinder (`SKULL` rows) with a muzzle pushed out where the moustache, lip and chin sit. It has eyes that touch, half-closed lids, a short nose, ears and a bushy moustache. It's modelled at a comfortable size, then scaled down and lifted about the collar (`HEAD_SCALE`, `HEAD_LIFT`), so it's about a quarter of his height, as in the source.
- **Beard and hair:** thick shells lying on the head surface (`kit.shell`). The beard covers the jaw and chin and leaves the cheeks bare. The hair has a centre parting, a ragged fringe and puffy temples, and hangs straight behind the ears.
- **Robe:** an A-line (`ROBE` rows) with a soft belly, a wavy hem at mid-calf and a V-neck patch lying on it.
- **Sleeves:** two rigid tubes each, meeting at the elbow, so a hard bend can't fold the mesh and flip its outline.
- **Hands:** a thumb and three fingers.

Every part is skinned to the `Jesus_Rig` armature: `root`, `hips`, `chest`, `head`, `upper_arm/forearm/hand.L/R`, and IK legs (`thigh/shin.L/R` aimed at `foot.L/R`, knees pointing at `knee.L/R`). The feet stay planted while the hips move, and the knees bend. Animation comes from three places:

- **Arms:** `POSES`, written in rest-pose axes, keyed from the timeline in `layout.json`.
- **Turn:** the armature object's Z rotation, keyed from the same timeline (one key per source frame through the turns).
- **Body:** `BODY`, one row per source frame, read off the source drawings. It holds the knee dip, hip sway, thrust and roll, the chest's lean and pitch, and the head's tilt, nod and turn. This is the wiggle: the dips during the turns, the hip swing while waving, and the forward rock and head bob while beckoning.
- **Timing:** with `STEPPED = True` (the default) the figure moves like the 10 fps original. Its motion is sampled once per source frame and each pose is held for two or three of our frames (constant interpolation, `kit.hold`). Set it to `False` for smooth motion. `props.STEPPED` does the same for the props: they're keyed once per source frame and held, and the clocks then flip left and right on every held frame instead of shimmying. With both on, the whole picture changes only on the original's 41 beats, so the GIF is also about half the size.

Two cartoon cheats copy the source in the raised-arm poses:

- the left arm stretches (bone scale), so the hand reaches well above the halo;
- the palm keeps facing the viewer while he turns, and facing screen-left the arm leans back behind his face.

The camera distance is solved so the top of his hair (`jesus.hair_top()`) lands on `figure.head_top`, with his feet on `figure.feet`.

## Working in the live Blender

The Blender MCP add-on lets Claude run code in the open Blender. Rebuild parts of the scene there by reloading `kit`, `jesus` and `props` and calling their builders on the existing rig and prop roots. Never call `build_scene.build()` in the live app: it resets to factory settings and drops the MCP add-on. Build headless instead and open the result.

## Source of truth and syncing

`blender/homers_web_page.blend` is tracked in git and is the source of truth once it has been edited in the UI. The scripts can still rebuild it, and `blender/tweaks.json` carries the hand edits across a rebuild.

- `build_scene.py` regenerates the scene from code and overwrites the .blend (don't run it while the file is open in the UI). At the end of the build it re-applies `tweaks.json` if it exists.
- `render.py` renders the tracked .blend as it is, with its own scene settings, to the same `render/stills/` and `render/frames/` names, and never saves it.
- `tweaks.py export` builds a fresh scene from the scripts into a temp file, compares the .blend against it and writes only the differences to `tweaks.json`: object transforms by name, material base colours (sRGB hex) and the title's font, offset and spacing. Mesh, keyframe and modifier edits are not captured; it lists the ones it notices under `not_captured`, and objects found in only one of the files under `unmatched`. Export right after editing in the UI, before changing the scripts, or script changes show up as tweaks too.
- `tweaks.py apply` re-applies `tweaks.json` to the open file (`--save PATH` writes a copy).
- `tweaks.py manifest` writes `blender/scene_manifest.txt`, a sorted text summary of the .blend (objects, transforms, modifiers, materials, keyframe counts, camera, title, render settings), so .blend changes show up in diffs.
- `tools/pre-commit` regenerates and stages the manifest whenever the .blend is staged. Install it once with `cp remake/tools/pre-commit "$(git rev-parse --git-common-dir)/hooks/pre-commit"`. The hooks folder is shared by all worktrees, so it does nothing where `remake/` doesn't exist. It finds Blender through `$BLENDER`, the default Windows install or `blender` on the PATH.

```bash
blender -b remake/blender/homers_web_page.blend --python remake/blender/render.py -- --still 1 39 70
blender -b remake/blender/homers_web_page.blend --python remake/blender/render.py -- --render [--percent 50]
blender -b remake/blender/homers_web_page.blend --python remake/blender/tweaks.py -- export
blender -b remake/blender/homers_web_page.blend --python remake/blender/tweaks.py -- manifest
blender -b other.blend --python remake/blender/tweaks.py -- apply --save other_tweaked.blend
```

So the loop is: edit in the UI and save, run `tweaks.py export`, then commit the .blend together with `tweaks.json` (the hook adds the manifest). Set `REMAKE_NO_TWEAKS=1` for a build without the tweaks; export sets it for its own build.
