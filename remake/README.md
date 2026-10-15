# Homer's Web Page in 3D

A 3D remake of `jesus-christ-homer.gif` (41 frames, 498x318, 10 fps), toon-shaded with outlines (concept A in `concepts/`), at the original's own 10 fps.

## Layout

| Path | What |
|---|---|
| `concepts/` | Style concepts. A (toon + outlines) is the chosen one |
| `reference/layout.json` | Prop positions (each prop's outline in frame 0: the traced props are cut out around it, the worms sized to it), figure yaw/pose timeline and prop cycle lengths, measured from the GIF. The Blender script reads this |
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
  - **Eyes:** small, half out of the face, a little more than a nose-width apart, high under the fringe, under half-closed lids: the calm look of every drawing. The camera looks down on him from about 20°, so each lid's straight edge is tipped back by as much, to run across the middle of the eye as the camera sees it. The pupils sit just under the lids, looking out level.
  - **Moustache:** one straight bar across the muzzle, its tips drooping a little at the edges of the face. It juts out past the nose in profile, like the original's dark cigar.
  - **The rest:** a long nose ending just above the moustache, a broad flat lower lip under it, and for ears small yellow ovals that show through the hair at the sides, as the drawings have them.
- **Beard and hair:** shells lying on the head surface (`kit.shell`).
  - **Beard:** climbs the cheeks to the hair and runs along the jaw, then wraps the neck down into the collar and hangs to a point at the top of the V-neck. His neck never shows: beard in front, hair behind.
  - **Hair:** a flat-topped cap with square corners, a clean hairline and one pointed lock dipping onto the forehead. It comes down the temples onto the beard, then hangs as one mass that drapes over the shoulders, lower at the sides than at the back (from the camera above, that reads as the drawings' level cut), stepping out in tiers to a few pointed locks.
- **Halo:** a flat, chunky slate hoop, about as wide as his head, on its own bone: it stays level whatever the head does and tips towards the camera by `HALO_TILT` per drawing, almost edge-on whenever his arm is up and half open while he beckons, as drawn.
- **Robe:** long, pinched at the waist, the hips swelling below it and tucking in a little at the hem (measured row by row on the drawings), the shoulders up at mouth level so the beard hangs over the chest, a soft belly, a short wide V-neck with straight sides, and a hem just below the knee. A dark shell a little bigger than the V-neck, under it, draws the collar's edge on both sides (an outline shell would hide on the side turning away from the camera).
  - **A straight hem:** drawn, the hem is one straight line with square corners, but an ellipse seen from above sags in the middle. A Geometry Nodes modifier (`flat_hem`) after the body drops each hem point by how far it lies behind the hem's point nearest the camera, times the slope of the camera's view, so the whole hem lands on one line whichever way he faces.
- **Sleeves:** slim, even tubes cut square at the wrist, two rigid ones each, meeting at the elbow, so a hard bend can't fold the mesh and flip its outline.
- **Hands:** big, a thumb and three fingers. At rest a mitten, as the raised hand is drawn: the fingers straight and side by side (their outlines still draw the lines between them), the thumb out. Two shape keys bend them: `curl` folds the fingers in towards a fist, still together, and the thumb with them; `claw` reaches them out of the palm, fanned, and hooks them at the tips, the beckoning "come here". Hooked at the knuckles instead, they hang straight down out of the palm, a stubby paw from the camera. Both keys start at 0 (Blender adds a key at full strength), so a hand nothing keys stays open. Both are relative to the open hand, so they add up: a frame shouldn't key both high.
- **Feet:** big and low, in near-black sandals like the original's: a long, thick sole slab reaching well past the toes, lifted a hair off the floor, and a thin flat strap hugging the foot just behind the toes. The yellow foot shows behind the strap and the four toes in front of it, in a darker orange than the skin, as drawn; a broader strap covers the foot like a slipper's upper.

He's rigged in layers, the way animators rig a robed figure:

- **Skeleton:** the `Jesus_Rig` armature. A `torso` control carries the hips and a two-bone spine (`spine`, `chest`) on their own, so the hips swing out and roll while the spine curves back and keeps his shoulders and head where they were. `head` and `upper_arm/forearm/hand.L/R` hang off the chest, and `halo` off the head; the legs are IK chains (`thigh/shin.L/R` aimed at `foot.L/R`, knees pointing at `knee.L/R`), so the feet stay planted and the knees bend. Two small `hip.L/R` bones push one hip out at a time, and `skirt` hangs from the waist to the hem to swing and flare it. The `spine` and `hips` bones also scale across (squash and stretch): the drawings slim his waist and hips when he turns side-on or away. The chest, head, arms and legs don't inherit that scale, so they keep their size. And each thigh can stretch a little (the shin with it): with the foot planted, the longer leg bends at the knee, the drawings' crouch in the turns without lowering his head.
- **Body:** `J_body`, hidden: his body under the robe, from the shoulders down to the hem, skinned to the spine, chest, hips and legs with Blender's automatic weights (bone heat), plus a share of `skirt` towards the hem. The legs inside the robe are slimmer above the hem, where they never show, so a leg angled back in the turns can't poke out through the cloth.
- **Robe:** it rides on the body through a Surface Deform modifier instead of being weighted to bones itself, so it follows the hips, the legs and the bend of the spine together.

The head, hands, sleeves, legs and feet are skinned straight to their bones. Animation comes from three places:

- **Arms:** `POSES`, written in rest-pose axes, keyed from the timeline in `layout.json`.
- **Turn:** the armature object's Z rotation, keyed from the same timeline (one key per source frame through the turns).
- **Body:** `BODY`, one row per source frame, read off the source drawings. It holds the knee dip, hip sway, thrust and roll, the upper body's lean and pitch (shared by the spine and chest), and the head's tilt, nod and turn. This is the wiggle: the dips during the turns, the hip swing while waving, and the forward rock and head bob while beckoning.
- **Fit:** `reference/pose_fit.json`, per source frame offsets on top of all that, found by `fit_pose.py`. It works like this:
  - **What it compares:** it draws him from the scene camera in flat colours, one per region (skin, hair/beard/sandals, robe), at twice the GIF's size. It compares each region with `reference/frames/regions.npz`, the same regions read off the upscaled original, and the outline counts too. So it sees his hands in front of the robe, his face and his feet, not just his outline.
  - **What it adjusts:** 37 offsets at once: the slide across the screen; the turn and dip of his body; the hips' sway, thrust and roll, and each hip pushed out or in; the upper body's lean, pitch and twist; the girth of the waist and of the hips; each knee's bend; the skirt's swing (forward and sideways) and flare; the head's nod, roll and turn; each arm's three angles, elbow bend and stretch (a cartoon cheat: the drawings make his arms longer when they reach); each wrist's bend; and where his feet stand.
  - **Hands:** each hand the designed pose shows also scores the share of it that lands on skin in the drawing. Without that, the fitter wins pixels by tucking a hand behind the robe.
  - **Robe pass:** `--part robe` refits only the hips, legs and skirt (sway, thrust, roll, each hip, both girths, the knees, swing and flare), with the rest of the pose held, and counts the lower half of the figure twice. In the full fit those barely move: against the pose penalty, a wider hem changes too little of the whole figure's score. Yet in the beckoning frames the drawn robe is about a fifth wider at the hips than the model's, and side-on about a fifth narrower.
  - **How it searches:** with CMA-ES (covariance matrix adaptation, the standard tool for a few dozen coupled parameters), with a small penalty for straying from the designed pose. The shape controls (girth, flare, the hips, the knees, the skirt's swing) pay a quarter of it: they change too little of the whole figure's score to move against the full penalty, yet the drawings use them. It searches wide first, then narrow around the best pose so far: from a pose that already fits, wide steps that move every offset at once almost never beat it.
  - **Skipped frames:** held frames and the second wave's reused drawings copy their frame.
  - **Held offsets:** where the score and the drawing disagree, the frame is refitted with an offset held (`--fix`). The side-on turns (3–5, 33–35) hold a 5% knee bend: the knee hides under the hem in the flat renders, so the score can't see the drawings' crouch, and with the bend held the rest of the pose fits as well as before. Frame 25 holds its turn at 45°, or the fitter turns him to hide an arm.
  - **Running it:** re-run it after changing the model or the poses. It takes a few minutes a frame, so split it over processes and merge the parts: `blender -b remake/blender/homers_web_page.blend -t 2 --python remake/blender/fit_pose.py -- --frames 0-10 --out part1.json`, then `-- --merge part1.json part2.json ...`, then the same again with `--part robe --iters 40`. It's CPU-bound: about a dozen processes at two threads each use a 24-thread machine; two dozen at once crash Blender on startup.
- **Hands:** `CURL`, the finger curl per source frame: the beckoning hand folds its fingers down twice ("come here"). The hand on his belly beckons with it: it points, opens into a claw, closes into a fist and points again. Between the waves, the left hand goes up behind his head (frames 11 and 24) and only the sleeve shows.
- **Timing:** with `STEPPED = True` (the default) the figure moves like the 10 fps original: its motion is sampled once per source frame and held (constant interpolation, `kit.hold`), then the fit and the hitches are applied. Set it to `False` for smooth motion (without the fit). `props.STEPPED` does the same for the props: they're keyed once per source frame and held, and the clocks then flip left and right on every held frame instead of shimmying. With both on, the whole picture changes only on the original's 41 beats, so the GIF is also about half the size.

Two cartoon cheats copy the source in the raised-arm poses:

- the left arm stretches (bone scale), so the hand reaches well above the halo;
- the palm keeps facing the viewer while he turns, and facing screen-left the arm leans back behind his face.

The camera distance is solved so the top of his hair (`jesus.hair_top()`) lands on `figure.head_top`, with his feet on `figure.feet`.

## The props

Each prop in the original flips between a handful of drawings: a mouth between five, a clock between three, a toaster's wing through a six-frame beat. So the mouths, toasters, clocks and bells are those drawings, traced and blown up into 3D:

- **Tracing:** `build_reference.py` reads them off the upscaled frames into `reference/prop_drawings.json`. It groups each prop's frames by silhouette into its drawings and traces the most typical frame of each, or one nearly as typical that the upscaler drew fewer blotches into (the closed left mouth has wrinkles in two of its frames and none in the others). Each drawing is split into coloured parts, with the colours sampled from the original, plus the ink: the whole drawing, whose dark line-art shows between the colours. It also records which drawing every frame shows.
- **Cleaning:** the colours are cleaned before they're split, so the ink is only the drawing's lines (`clean_labels`). Pale pixels between two colours take the colour next to them, so a toaster's pale top face and rims stay grey, and the toast's brown crust is toast, where they used to turn into black lids. A small 3x3 mode filter merges the upscaler's speckle but keeps thin strips: a rim, the toast standing in its slot, a row of teeth. Specks of a colour and small holes in one (the texture lines on lips, a dark speck) are filled in from round them, and a pale blue highlight on chrome doesn't show the sky through it.
- **Clock faces** are redrawn clean (`clock_face`): the ellipse that fits the face and the hands kept as drawn. The big clock's face also gets its twelve tick marks back round the edge (a GIF pixel each, so the mode filter would lose them), the first one towards the bells so they lean with the clock. The two small clocks are drawn with plain faces, so they get none.
- **The small toasters** (`toaster_s`, `toaster_tr`) are the big toaster's drawing at 0.7 of its size, and at 30 pixels wide the upscaler invents their detail, so their own tracings came out as dark lumps. They show `toaster_l`'s drawings scaled down instead (`borrow_drawings`), the one that covers each group of their frames best, so they keep their own timing.
- **Inflating:** `props.py` blows each part up into a soft 3D shape with `kit.inflate`, the "Teddy" trick for turning cartoon drawings into models. The surface rises with the distance from the edge: round where the part is thin, flat-topped where it's wide. The ink sits just behind the colours, and only it gets a thin outline, round the whole drawing. The drawings' colours are flat, so their shade is barely darker than the light. The coloured parts end their modifiers with one that moves nothing (`Hold`): with the subdivision last, Blender would subdivide them on the GPU on every render but the first after the file loads, so the first frame came out a shade off the rest and frame 1, a held copy of it, didn't match.
- **Showing:** each drawing goes back exactly where it was traced (`build_scene.place_drawing`): its grid is turned parallel to the image plane, so it projects as an undistorted copy at one scale, on the ray through the grid's centre, at the depth where one of its GIF pixels covers one pixel of the frame. On every frame only the drawing the original shows is visible. So the wings beat, the bells swing, the clocks jolt and the mouths shout drawing for drawing, each drawing in its place and at its size in the frame, the bigger ones (a wing up, a shout) included.

The worms are modelled instead: at three pixels tall their drawings trace into noise. Each is one smooth tube with round ends, ringed by nine slate stripes that lean a little, like the drawn ones. They curl their middle up on the beats measured in `reference/prop_tracks.json`, without going anywhere: a low hump, an arch with a hole under it and, curled all the way, a tall Omega whose sides lean out. The body and stripes are built at five curls and blend between them (shape keys). Two cartoon cheats keep the drawings' arch: the ends pull in less than the body's length allows, and the loop stands a little taller. `worm_l`'s curl is read off the upscaled frames: it's the smallest worm, and in the dithered GIF its top edge jumps by whole pixels, which squashed its track. That file holds every prop's state per frame (a mouth's drawing from whether its teeth show, a bell's tilt, the toaster's wing and toast, a clock's lean, a worm's arch). It also drives the models `props.py` still has for every prop, used when there are no traces.

The worms are sized to their outline in frame 0 by their length, and lie along the camera's horizontal, so they read level anywhere in the frame (turned to face the camera, one off to the side would slant).

## The look

Concept A: flat colours, a thin toon band and outlines, on a flat sky-blue page.

- **Colours:** the figure's are the GIF's own (`kit.PALETTE`). The materials are emission, so the Standard view transform renders the hexes as they are. A sun from camera-left only decides which side of a shape falls in the toon band (`kit.toon`): a crisp step down to the colour times its shadow factor. The robe's is faint (0.9), since the drawings have no shading.
- **No cast shadows:** the original has none, and the sun's left a grey smudge beside every prop, a long smear from his feet and a grainy shade on his legs that changed with every pose. Instead a soft patch of shade under each sandal stands him on the page, like concept A's contact shadows, following each foot (`build_scene.contact_shadow`). The props float, as drawn.
- **Outlines:** an inverted shell round every object (`kit.add_outline`), 1.9 px at 1200 wide, in a dark shade of the colour it rings, as the drawings have them (`kit.LINE`): slate round the robe, the halo and the worms, dark brown round his skin, near-black round the hair and sandals and round the traced props' ink.
- **Inner lines:** where a hanging sleeve sinks into the robe its shell is buried, yet the drawings run a line down the arm there (the back views, the waves, the turns). A Grease Pencil Line Art object draws the lines where surfaces sink into the robe (`build_scene.inner_lines`): down the sleeves, and along both edges of the V-neck and under the hair. Not at the elbow, where a sleeve's two tubes meet, nor where the legs cross the hem. It's computed at render time only, and about doubles the render time of a frame; `INNER_LINES = False` skips it.
- **The floor** sits at z = -0.03, below the soles' outline shells: cutting through them, it left a comb of light teeth under each sole.
- **The title:** Ultra, emboldened with the curve's offset (0.02) enough to close the slits between its serifs, which read as hairline cracks through H, m, e and W.

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
