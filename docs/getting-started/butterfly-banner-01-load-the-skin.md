# Butterfly Banner 1. Load the skin

Time: 6 minutes.

## What you are building

Three short chapters take the `.esk` you produced in the Designer's
[Blue Morpho to Monarch tutorial](https://designer.elysiumui.com/getting-started/butterfly/)
and turn it into the official Elysium logo treatment: a butterfly-
shaped borderless transparent window that descends from the top of
the screen, flaps its wings, and unfurls the Elysium wordmark behind
it.

This chapter ships the static load. You will see the hybrid Monarch
(wearing the Blue Morpho's iridescent pattern) frozen at the center
of a borderless window with the path-shaped hit region the Designer
recorded.

![Butterfly Banner chapter 1: the hybrid butterfly model rendered into a transparent butterfly-shaped window](../assets/butterfly-banner-ch1.png)

## Prerequisites

You need a `butterfly.esk` produced by chapter 8 of the Designer
tutorial. If you did not run that tutorial:

- Either run it now (it takes ~45 minutes total),
- Or download the prebuilt `butterfly.esk` from
  [the examples folder of the elysium repo](https://github.com/elysiumui/elysium/tree/main/examples/butterfly).

Place `butterfly.esk` next to your Python script for this tutorial.

## Minimum loader

Create `banner.py`:

```python
from pathlib import Path
import elysium as ely

SKIN = str(Path(__file__).parent / "butterfly.esk")

app = ely.App(title="Elysium Banner", identifier="dev.elysium.banner")

window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(960, 540),
)
window.load_skin(SKIN)

app.run()
```

Run it. The window is 960 by 540 (the full banner canvas size).
The butterfly sits frozen in the center. Notice:

- The background outside the butterfly's silhouette is fully
  transparent: your desktop wallpaper bleeds through everywhere
  except the butterfly itself.
- The Designer's `Window > Set Shape > From Selection` step (chapter
  8) baked the butterfly outline into the manifest. The framework
  reads that on `load_skin` and applies it as the window's hit
  region automatically: no `set_hit_test_path` call needed in this
  script.

## Confirm the bundle loaded

Hover the butterfly: clicks register. Click in the empty area
between the wings and the abdomen: clicks pass through. The OS sees
a 960x540 rectangle, but the user experience is "a butterfly on the
desktop".

If clicks register everywhere inside the bounding box, the manifest
either does not carry a window shape or your Designer build did not
write one. Re-run chapter 8 of the Designer tutorial.

## Inspect the loaded skin

The framework gives you a `Skin` object for the loaded bundle:

```python
print(window.skin.manifest)
print(window.skin.placements)
```

Sample output:

```
{
  'id': 'dev.elysium.butterfly',
  'name': 'Butterfly',
  'version': '0.1.0',
  'window': { 'shape': { 'kind': 'path', 'path_d': 'M ...' } }
}
[<Mesh3D id="butterfly">, <Light id="dir_light">]
```

The Designer wrote two placements: a `Mesh3D` (the butterfly model
with its baked PBR textures) and a directional `Light`. The
framework instantiates both at load time.

## Why pre-bake?

The Designer's render and bake pipeline ran one-time and burned the
results into the `.esk` bundle:

- The mesh and the baked PBR textures are static.
- The wing flap animation in chapter 8 is a 24-frame keyframe track
  on `butterfly.left_wing.rotateZ` and `.right_wing.rotateZ`.

For runtime, the framework has only to play back the recorded
animation and render the mesh. That keeps the banner trivially
cheap: ~2% CPU, ~30 MB VRAM at 60 fps on a baseline GPU.

## Play the wing flap

The recorded animation lives in the skin. Play it on a loop:

```python
window.skin.animations["wing_flap"].play(loop=True)
```

Run again. The wings now flap at the cadence you set in the
Designer (default 24 frames at 24 fps = 1 second per flap).

That is the static load done. Chapter 2 makes it descend.

## Checkpoint

- A butterfly-shaped borderless transparent window.
- Wings flapping on a loop.
- Empty areas between wings and abdomen pass clicks through.

Continue to [chapter 2: flight animation](butterfly-banner-02-flight-animation.md).
