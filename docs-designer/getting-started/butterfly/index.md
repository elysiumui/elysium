# Welcome to the Blue Morpho to Monarch tutorial

In the next 45 minutes you will take the iridescent blue of a Blue Morpho
butterfly and transfer it onto a Monarch 3D model, bake a PBR normal map,
animate the wing flap, and ship a borderless animated `.esk` skin that the
Elysium UI framework loads as a Python app.

The finished skin is the official Elysium logo: a hybrid Monarch wearing the
Blue Morpho's color, pattern, and iridescence, gently flying down the screen
with wings flapping, unfurling the Elysium wordmark behind it.

## What you will build

By the end of chapter 8 you will have produced:

1. A `.esk` skin bundle at `examples/butterfly/butterfly.esk/`.
2. A baked albedo texture at `examples/butterfly/butterfly.esk/textures/butterfly_albedo.png`.
3. A baked normal map at `examples/butterfly/butterfly.esk/textures/butterfly_normal.png`.
4. A short wing flap animation, keyed at frames 1, 12, and 24.
5. A borderless app window shaped like the butterfly's silhouette.

The Elysium UI framework's
[Butterfly Banner tutorial](https://docs.elysiumui.com/getting-started/butterfly-banner-01-load-the-skin/)
takes the `.esk` you produce here and wires it into a running Python app
that flies the butterfly down a real desktop.

## Prerequisites

| Requirement | Why |
|---|---|
| Elysium Designer installed | See [Installation](../../installation/index.md). The Designer ships as a `.app` on macOS, a `.exe` on Windows, or an AppImage on Linux. |
| 4 GB free disk | Source assets are about 2 GB. Bakes add another 500 MB. |
| About 45 minutes | Eight chapters; each is a single screen of work. |

You do not need any 3D modeling experience. You do not need to write Python
during this tutorial; the framework Butterfly Banner tutorial covers the
Python side later.

## The assets you will use

The Designer's example folder ships with everything you need.

| Asset | Path | Purpose |
|---|---|---|
| Monarch 3D model | `examples/butterfly/_3ds/butterfly.3ds` | The geometry you will texture. |
| Blue Morpho photo | `examples/butterfly/iridescentwinged_butterfly.png` | The pattern and color reference. |
| Reference texture | `examples/butterfly/_3ds/texture.bmp` | The original Monarch albedo. We replace this with the bake. |

All three are open-source or photographer-licensed for use with the Designer.

## The eight chapters

| # | Chapter | Time |
|---|---|---|
| 1 | [Open the Designer](01-open-designer.md) | 3 minutes |
| 2 | [Import the Monarch model](02-import-the-monarch-model.md) | 5 minutes |
| 3 | [Import the Blue Morpho reference image](03-import-the-reference-image.md) | 4 minutes |
| 4 | [Set up landmarks](04-set-up-landmarks.md) | 8 minutes |
| 5 | [Run the Polar + Bake + Normal Map pipeline](05-run-polar-pipeline.md) | 5 minutes |
| 6 | [Compare the BBox-Warp pipeline](06-compare-bbox-pipeline.md) | 5 minutes |
| 7 | [Render and export](07-render-and-export.md) | 5 minutes |
| 8 | [Animate the wing flap and ship](08-animate-and-ship.md) | 10 minutes |

Each chapter ends with a checkpoint screenshot so you can verify you are on
track before moving on.

## Conventions

Throughout the tutorial, menu paths are written with `>` separators, like
`Mesh > Transfer Texture > Polar + Bake + Normal Map (PBR)`. Keyboard
shortcuts appear in code formatting: `Cmd+S` on macOS, `Ctrl+S` on Windows
and Linux. When a step needs you to click in the canvas, the exact pixel
target is named (e.g. "click the upper-left wing tip on the photo, then the
matching tip on the model").

When you see a starred entry in a menu, that is a curated recommended
pipeline. The two starred Mesh menu entries (`Polar + Bake + Normal Map (PBR)`
and `BBox-Warp then Landmark Gaps + Bake + Normal Map`) are the workflows
this tutorial covers.

## Ready

Head to [chapter 1](01-open-designer.md) when you are ready.
