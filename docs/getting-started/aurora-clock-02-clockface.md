# Aurora Clock 2. Draw the clock face

Time: 7 minutes.

## What we are adding

A static dial: 12 tick marks around the perimeter, an inner ring, a
hairline center dot, and a Label that will show the current time.
Everything draws onto the framework's `Canvas`, which is a Skia
display list composited by wgpu.

![Aurora Clock chapter 2 result: empty dial with 12 ticks and a centered "00:00:00" placeholder](../assets/aurora-clock-ch2.png)

## How the framework draws

Elysium splits "what to render" from "when to render it":

- A **skin** (`.esk` folder on disk) describes visual structure
  declaratively: which shapes, which colors, where they sit.
- A **Python script** wires interaction: event handlers, animations,
  reactive state.

For tutorials we author the skin alongside the Python file. In a
real workflow the Designer authors the skin and your editor wires
the behavior. The Code Link guide covers that flow.

## Create the skin folder

Next to `aurora_clock.py`, create a folder called
`aurora_clock.esk/` with two files:

```
aurora_clock.esk/
  manifest.json
  document.json
```

### `manifest.json`

```json
{
  "schema_version": "1.0",
  "id": "dev.elysium.aurora-clock",
  "name": "Aurora Clock",
  "version": "0.1.0",
  "color_space": "srgb"
}
```

### `document.json`

The document lists the placements that compose the clock face. The
schema is JSON because the file is hand-edited here; the Designer
writes the same JSON.

```json
{
  "placements": [
    {
      "id": "background",
      "kind": "ellipse",
      "x": 0, "y": 0,
      "width": 360, "height": 360,
      "fill": "#0f0d1eff"
    },
    {
      "id": "dial",
      "kind": "ellipse",
      "x": 20, "y": 20,
      "width": 320, "height": 320,
      "stroke": "#a78bfaff",
      "stroke_width": 2.0,
      "fill": "transparent"
    },
    {
      "id": "ticks",
      "kind": "ticks",
      "cx": 180, "cy": 180,
      "inner_radius": 150, "outer_radius": 158,
      "count": 12,
      "stroke": "#c4b5fdff",
      "stroke_width": 2.0
    },
    {
      "id": "center_dot",
      "kind": "ellipse",
      "x": 176, "y": 176,
      "width": 8, "height": 8,
      "fill": "#fbcfe8ff"
    },
    {
      "id": "time_label",
      "kind": "label",
      "x": 120, "y": 168,
      "width": 120, "height": 24,
      "text": "00:00:00",
      "font_family": "system",
      "font_size": 18,
      "fill": "#ffffffff",
      "align": "center"
    }
  ]
}
```

## Load the skin

Update `aurora_clock.py` to load the skin we just authored:

```python
from pathlib import Path

import elysium as ely

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"
SKIN_PATH = str(Path(__file__).parent / "aurora_clock.esk")

app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")

window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 360),
)
window.set_hit_test_path(ELLIPSE)
window.load_skin(SKIN_PATH)

app.run()
```

Run with `python aurora_clock.py`. The window now shows:

- A dark indigo ellipse (the `background` placement).
- A lighter violet ring 20 pixels inside it (the `dial`).
- Twelve violet ticks around the inside of the ring (the `ticks`).
- A small pink dot at the very center.
- The text `00:00:00` in the middle.

We will replace the static text with the actual time in chapter 3.

## Why an ellipse background and a hit-test path?

The `background` placement is what your eye sees. The hit-test path
is what the OS uses to decide where clicks count. The two should
match, otherwise the user can see "the clock" but click areas just
outside its visible edge will still register on the window. Keeping
both at radius 180 around (180,180) keeps them in sync.

## A note on the `ticks` placement kind

`ticks` is a higher-level placement that generates a small group of
line shapes around a circle. It compiles down to the same Path
primitives you would draw by hand. The Designer's
[Tool reference](https://designer.elysiumui.com/reference/tool-reference/)
explains the full kind catalog.

## Checkpoint

You should see:

- The same borderless ellipse from chapter 1, now painted dark indigo.
- A ring + 12 tick marks + a center dot.
- A `00:00:00` label in the middle.

Continue to [chapter 3: wire the reactive clock](aurora-clock-03-reactive-time.md).
