# Lottie loading spinner

Time: 25 minutes. Difficulty: Beginner.

Drop a Lottie animation (`.json` or `.lottie`) into the Designer
and ship a borderless transparent splash window around it. Lottie
files from After Effects or LottieFiles drop straight in.

## Prerequisites

- A Lottie file (free ones on lottiefiles.com).
- Designer installed.

## Import

`File > Import > Lottie…` and pick the file. The Designer:

1. Parses the Lottie JSON.
2. Converts vector layers to `path` placements.
3. Converts pre-comps to grouped placements.
4. Imports the timeline as an Elysium animation track.

A progress dialog confirms each step.

## What maps

| Lottie | Elysium |
|---|---|
| Shape layer | `path` placement |
| Solid layer | `rectangle` placement |
| Image layer | embedded `image` placement |
| Text layer | `label` placement |
| Mask | render-part-mask on the layer |
| Trim path | animated subset of the path |
| Time remap | scaled into the animation track |

Pre-comps become grouped placements; nested timelines flatten into
the main timeline.

## Test the spinner

`View > Show HUD` to confirm the timeline length. Press `Space`
on the time slider to play; the animation should loop. If it
doesn't auto-loop, set `loop = true` in the Animations group of
the Project Explorer.

## Wrap as a splash

1. `Window > Set Shape: Ellipse` to clip the splash to a circle.
2. Resize the window to match the spinner's bounding box plus
   margin.
3. Toggle `Window > Toggle Transparency` if the imported file
   came in with a background.

## Tune the look

Most Lottie spinners are too small for desktop use. Select the
top-level group and scale it 2-3x in the Channel Box. The
animation track scales proportionally.

For color overrides, expand the path placements and edit `fill` /
`stroke` directly. Lottie's color animations remain intact unless
you key new values.

## Export

`File > Export > .esk Bundle`. The `.esk` plays the spinner on
load when wrapped in a runtime app.

## Runtime wiring

```python
import elysium as ely

app = ely.App(title="Splash", identifier="dev.example.splash")
win = app.window(transparent=True, title_bar=False, resizable=False,
                 initial_size=(320, 320))
win.load_skin("spinner.esk/")
win.skin.animations["main"].play(loop=True)
app.run()
```

The loaded skin's animation track plays automatically.

## What you exercised

- `File > Import > Lottie…`.
- Lottie → placement mapping.
- Trim-path and time-remap conversion.
- Ellipse window shape.

## See also

- [SVG / Figma / Lottie importing](../importing/svg-figma-lottie.md)
- [Animation index](../animation/index.md)
