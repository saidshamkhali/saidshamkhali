# Homer's Web Page in 3D

A 3D remake of `jesus-christ-homer.gif` (41 frames, 498x318, 10 fps), toon-shaded with outlines (concept A in `concepts/`), at the original's own 10 fps.

## Layout

| Path | What |
|---|---|
| `concepts/` | Style concepts. A (toon + outlines) is the chosen one |
| `reference/layout.json` | Prop positions (each prop's outline in frame 0), figure yaw/pose timeline and prop cycle lengths, measured from the GIF. The Blender script reads this |
| `reference/prop_tracks.json` | Each prop's state in every frame of the GIF (mouth open, bell tilt, wing, toast, clock lean, worm loop), written by `build_reference.py` |
| `reference/build_reference.py` | Regenerates the reference sheets, `reference/frames/` and the figure's silhouettes (`frames/masks.npz`) |
| `reference/prop_drawings.json` | The traced props: each prop's drawings split into coloured parts, and which one each frame shows, written by `build_reference.py` from the upscaled frames |
| `reference/pose_fit.json` | Per-frame pose offsets fitted to the original, region by region, by `blender/fit_pose.py` |
| `reference/model_sheet.webp`, `model_apose.webp` | A clean model sheet (front, profile, back, three-quarter) and an A-pose drawing of him, redrawn by an image model from the upscaled frames: references for modelling |
| `reference/contact_sheet.png` | Every source frame, numbered |
| `reference/figure_sheet.png` | The figure, zoomed, with yaw/pose per frame |
| `reference/layout.png` | Frame 0 with every prop box drawn |
| `blender/build_scene.py` | Entry point: camera, title, floor, lights, placement, rendering |
| `blender/jesus.py` | The figure: modelled in code, skinned to an armature, poses and timeline |
| `blender/props.py` | Toasters, alarm clocks, bells, lips and worms, each with its own loop |
| `blender/kit.py` | Shared settings, toon materials, mesh builders, keyframe helpers |
| `blender/fit_pose.py` | Fits the figure's pose to the original, frame by frame, region by region |
| `blender/homers_web_page.blend` | The scene. Tracked, and the source of truth once edited in the UI |
| `blender/render.py` | Renders the tracked .blend as it is |
| `blender/tweaks.py` | Carries UI edits across a rebuild, and writes `scene_manifest.txt` |
| `blender/scene_manifest.txt` | Text summary of the .blend, so its changes show up in diffs |
| `fonts/` | Ultra (Apache 2.0, by Astigmatic), the title font, packed into the .blend |
| `tools/pre-commit` | Git hook that refreshes the manifest when the .blend is staged |
| `make_gif.py` | Rendered frames to a looping GIF, animated WebP and/or MP4 via ffmpeg |

## What the original does

- **Figure**: one full turn per loop, never at a constant speed. Back view (frames 0-2) → quick turn through facing screen-left (3-4) → front, waving (6-10) → hand to face (11) → beckoning with his right arm, swaying (12-23) → hand to face (24) → waving again (25-29) → turn through facing screen-right (31-35) → back view (36-40).
- **Props**: 14 of them in five kinds, each flipping between a few drawings rather than moving smoothly. The bells rest upright for three frames, then ring left-right-left (the left one rests tilted). The lips switch between closed, half open, open and a big shout. The toaster wings are drawn down, level or up while the toast pops, the clocks jolt left and right with their hands rattling, and the worms curl the middle of their body up into an arch and flatten out again without going anywhere. Everything is drawn at 10 fps, so each drawing is held for a tenth of a second.

## Reading the original

The GIF is 498x318 with 256 colours and heavy dithering, and his face is about 30 pixels tall, so fine detail drowns in the dither. Upscaling every frame 4x with a cartoon upscaler ([Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)'s `realesr-animevideov3` model, through `realesrgan-ncnn-vulkan`) cleans the dither into flat colour and clean lines. It showed several things the noise had hidden:

- eyes that sit high under the fringe;
- a moustache that is one straight bar;
- back hair that is a smooth mass ending at the shoulders;
- dark sandals;
- a left hand that beckons along with the right;
- mouths that, when open, are drawn side-on.

The upscaled frames are also data. The pose fit scores the figure against their regions (skin, hair and beard, robe), and the mouths, toasters, clocks and bells are traced from them. The GIF's own pixels still give the outline and the props' tracks. Where the upscaler invents detail (at the scale of the eyes, where two of its models disagree), nothing is taken from it. The frames aren't committed. `build_reference.py` writes the GIF's frames at their own size to `reference/frames/gif/`; upscale them into `reference/frames/x4/` with `realesrgan-ncnn-vulkan -i remake/reference/frames/gif -o remake/reference/frames/x4 -n realesr-animevideov3 -s 4`, then run `build_reference.py` again for `regions.npz` and `prop_drawings.json`.

## Loop timing

The original's own: 41 frames at 10 fps (4.1 s), one of ours for each of its frames. Eight of its frames are whole-frame copies of the one before (`source.held_frames`: 1, 7, 13, 15, 20, 26, 32 and 38), a hitch about every half second, and ours hold on the same frames (`kit.hitch`). Every prop runs a whole number of cycles per loop, so the loop has no seam. The scripts still work at other rates (`kit.FPS`, `kit.LOOP`): the poses are then held for several frames each.

## Run

Blender 5.x, either the app or the `bpy` module (`pip install bpy`, Python 3.13):

```bash
python remake/reference/build_reference.py
python remake/blender/build_scene.py --still 1 39 70
python remake/blender/build_scene.py --render
python remake/make_gif.py
```

With the Blender app instead: `blender --background --python remake/blender/build_scene.py -- --render`.

The profile README shows `jesus-christ-homer-3d.webp` in the repo root, a copy of `render/homers_web_page.webp` (`python remake/make_gif.py --width 1200 --formats webp --out remake/render/homers_web_page`, rendered at `--percent 150`). Copy it over after re-rendering.

The script writes `remake/blender/homers_web_page.blend`, so you can open the scene and keep working in the UI.

## The figure

`jesus.py` builds him from parametric surfaces:

His proportions come from the GIF and from a clean model sheet drawn from it (front, three-quarter, profile and back), checked pixel class by pixel class (skin, hair, robe) against orthographic renders of the model:

- **Head:** a tall Simpsons dome (`SKULL` rows) about 28% of his height, with a muzzle pushed out where the moustache, lip and chin sit.
  - **Eyes:** half out of the face, a nose-width apart, high under the fringe, with thin lids. The camera looks down on him from about 20°, which would push the lids down over the eyes and make him look sleepy, so the lids tip back and the pupils aim up.
  - **Moustache:** one thick straight bar across the muzzle. It juts out past the nose in profile, like the original's dark cigar.
  - **The rest:** a long nose, C-shaped ears, a lower lip under the moustache, and a short pointed beard on the chin in front of a thick neck.
- **Beard and hair:** shells lying on the head surface (`kit.shell`).
  - **Beard:** runs along the jaw to the sideburns and covers the cheeks up to the moustache.
  - **Hair:** a pointed lock dips onto the forehead, with locks at its corners. It covers the temples down to the ears, then hangs behind them as one smooth mass that ends at the shoulders, as the upscaled frames show it.
- **Robe:** long and nearly straight, the shoulders up at mouth level so the beard hangs over the chest, a soft belly, a deep V-neck, and a wavy hem just below the knee that rides up a little at the back.
- **Sleeves:** two rigid tubes each, meeting at the elbow, so a hard bend can't fold the mesh and flip its outline.
- **Hands:** big, a thumb and three fingers, with a `curl` shape key that bends the fingers down into a cup, the beckoning "come here".
- **Feet:** big, with four toes, in near-black sandals like the original's.

Every part is skinned to the `Jesus_Rig` armature: `root`, `hips`, `chest`, `head`, `upper_arm/forearm/hand.L/R`, and IK legs (`thigh/shin.L/R` aimed at `foot.L/R`, knees pointing at `knee.L/R`). The feet stay planted while the hips move, and the knees bend. Animation comes from three places:

- **Arms:** `POSES`, written in rest-pose axes, keyed from the timeline in `layout.json`.
- **Turn:** the armature object's Z rotation, keyed from the same timeline (one key per source frame through the turns).
- **Body:** `BODY`, one row per source frame, read off the source drawings. It holds the knee dip, hip sway, thrust and roll, the chest's lean and pitch, and the head's tilt, nod and turn. This is the wiggle: the dips during the turns, the hip swing while waving, and the forward rock and head bob while beckoning.
- **Fit:** `reference/pose_fit.json`, per source frame offsets on top of all that, found by `fit_pose.py`. It works like this:
  - **What it compares:** it draws him from the scene camera in flat colours, one per region (skin, hair/beard/sandals, robe), at twice the GIF's size. It compares each region with `reference/frames/regions.npz`, the same regions read off the upscaled original, and the outline counts too. So it sees his hands in front of the robe, his face and his feet, not just his outline.
  - **What it adjusts:** 23 offsets at once: the slide across the screen; the turn, dip, tilt, lean and twist of his body; the head's nod, roll and turn; each arm's three angles, elbow bend and stretch (a cartoon cheat: the drawings make his arms longer when they reach); and where his feet stand.
  - **How it searches:** with CMA-ES (covariance matrix adaptation, the standard tool for a few dozen coupled parameters), with a small penalty for straying from the designed pose.
  - **Skipped frames:** held frames and the second wave's reused drawings copy their frame.
  - **Running it:** re-run it after changing the model or the poses. It takes a few minutes a frame, so split it over processes and merge the parts: `blender -b remake/blender/homers_web_page.blend --python remake/blender/fit_pose.py -- --frames 0-10 --out part1.json`, then `-- --merge part1.json part2.json ...`.
- **Hands:** `CURL`, the finger curl per source frame: the beckoning hand folds its fingers down twice ("come here"). The hand on his belly beckons with it: it points, opens into a claw, closes into a fist and points again. Between the waves, the left hand goes up behind his head (frames 11 and 24) and only the sleeve shows.
- **Timing:** with `STEPPED = True` (the default) the figure moves like the 10 fps original: its motion is sampled once per source frame and held (constant interpolation, `kit.hold`), then the fit and the hitches are applied. Set it to `False` for smooth motion (without the fit). `props.STEPPED` does the same for the props: they're keyed once per source frame and held, and the clocks then flip left and right on every held frame instead of shimmying. With both on, the whole picture changes only on the original's 41 beats, so the GIF is also about half the size.

Two cartoon cheats copy the source in the raised-arm poses:

- the left arm stretches (bone scale), so the hand reaches well above the halo;
- the palm keeps facing the viewer while he turns, and facing screen-left the arm leans back behind his face.

The camera distance is solved so the top of his hair (`jesus.hair_top()`) lands on `figure.head_top`, with his feet on `figure.feet`.

## The props

Each prop in the original flips between a handful of drawings: a mouth between five, a clock between three, a toaster's wing through a six-frame beat. So the mouths, toasters, clocks and bells are those drawings, traced and blown up into 3D:

- **Tracing:** `build_reference.py` reads them off the upscaled frames into `reference/prop_drawings.json`. It groups each prop's frames by silhouette into its drawings and traces the most typical frame of each. Each drawing is split into coloured parts, with the colours sampled from the original, plus the ink: the whole drawing, whose dark line-art shows between the colours. It also records which drawing every frame shows.
- **Inflating:** `props.py` blows each part up into a soft 3D shape with `kit.inflate`, the "Teddy" trick for turning cartoon drawings into models. The surface rises with the distance from the edge: round where the part is thin, flat-topped where it's wide. The ink sits just behind the colours, and only it gets a thin outline, round the whole drawing.
- **Showing:** each drawing faces the camera square on, and on every frame only the drawing the original shows is visible. So the wings beat, the bells swing, the clocks jolt and the mouths shout drawing for drawing, each drawing in its place in the frame.

The worms are modelled instead: at three pixels tall their drawings trace into noise. They're chunky ring segments with dark bands between them, and they curl their middle up into an arch on the beats measured in `reference/prop_tracks.json`, without going anywhere. That file holds every prop's state per frame (a mouth's drawing from whether its teeth show, a bell's tilt, the toaster's wing and toast, a clock's lean, a worm's arch). It also drives the models `props.py` still has for every prop, used when there are no traces.

Each prop is sized to its outline in frame 0 (worms by their length, traced props by their width); only the drawing on show counts.

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
