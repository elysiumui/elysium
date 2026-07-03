# SVG icon-pack skin

Time: 35 minutes. Difficulty: Intermediate.

Build a skin that bundles 20 SVG icons and exposes a picker to
choose one. Demonstrates SVG import, asset bundling, and dynamic
icon swapping at runtime.

## Prerequisites

- 20 SVG icons (any icon set: Lucide, Phosphor, Heroicons all work).
- Familiarity with the [Blue Morpho tutorial](../getting-started/butterfly/index.md).

## Import the SVGs

`File > Import > SVG…` and pick all 20 (Shift / Ctrl select in the
file dialog). Each SVG becomes:

- A `path` placement at its origin.
- An entry in the Assets tab.

For consistent positioning, drop all SVGs at (0, 0); we will
position them per-instance later.

## Make them swappable

The trick is to bundle the SVGs as **named assets** rather than as
discrete placements. Right-click each in the Project Explorer >
**Convert to Asset**. Now they live under `assets/icons/<name>.svg`
in the bundle and are referenced by name from a single placement.

Add a generic icon placement:

```json
{ "id": "current_icon", "kind": "path",
  "x": 100, "y": 100, "width": 64, "height": 64,
  "path_d": "{{asset:icons/star.svg#path}}",
  "fill": "#a78bfaff" }
```

The `{{asset:…}}` template references an SVG asset's path data by
name. Switching the asset swaps the visual.

## Author the picker

Add a Row of 20 small "selector" rectangles at the bottom of the
canvas, each with `id = "pick_<name>"`. Each will be a button.

Or compose programmatically at load time with the framework's
`window.add_placement(...)`.

## Hook handlers

Each `pick_<name>.click` updates `current_icon.path_d` to the
selected asset's path. The runtime side:

```python
@window.on("pick_star.click")
def use_star(event):
    window.current_icon.path_d = window.skin.asset("icons/star.svg").path_d
# ...repeat per icon, or compose via a loop.
```

## Theme tint

To let users pick a tint color too, add a small Row of swatches
and bind:

```python
@window.on("swatch_violet.click")
def violet(event):
    window.current_icon.fill = "#a78bfaff"
```

## Export

`File > Export > .esk Bundle`. The bundle contains all 20 SVGs
under `assets/icons/`. Total size ~30 KB for a typical pack.

## What you exercised

- Multi-file SVG import.
- Converting placements to named assets.
- `{{asset:…}}` template references.
- Picker UI authored as small selector buttons.

## See also

- [Importing SVG / Figma / Lottie](../importing/svg-figma-lottie.md)
- [Multi-window dashboard](15-multi-window-dashboard.md): pattern
  for composing many small placements.
