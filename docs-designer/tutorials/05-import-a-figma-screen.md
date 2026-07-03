# Import a Figma screen

Time: 20 minutes. Difficulty: Beginner.

Bring a Figma frame into the Designer and wire one button. The
fast path from a designer's Figma to a runnable Elysium skin.

## Prerequisites

- A Figma URL pointing to a specific frame.
- A Figma personal access token in `Preferences > Imports > Figma > Token`.

## Import

`File > Import > Figma URL…` and paste the link. The Designer:

1. Fetches the frame's JSON via the Figma REST API.
2. Maps each Figma node to an Elysium placement.
3. Resolves text styles, colors, and auto-layout into placements
   and a Stack / Row / Col structure.
4. Downloads any image fills as embedded assets.

A progress dialog reports each step.

## What maps

| Figma | Elysium |
|---|---|
| Rectangle / Ellipse | `rectangle` / `ellipse` |
| Vector path | `path` |
| Text | `label` |
| Frame with Auto Layout (horizontal / vertical) | `row` / `col` |
| Frame (none) | `stack` |
| Image fill | embedded asset + `image` placement |
| Drop shadow | `shadow` field |
| Inner shadow | `inner_shadow` field |
| Gradient fill | linear / radial gradient string |
| Component instance | flattened placement |

Components flatten on import: the Designer does not preserve
Figma's instance / override relationship. Re-author master
components manually if needed.

## Inspect

After import, the canvas shows the frame. Each placement is in
the Project Explorer; click to select.

## Wire a button

The imported Figma "Button" component (or text-on-rectangle group)
became one or more placements. To make it interactive:

1. Select the placement that should receive clicks (usually the
   background rectangle).
2. In the Properties pane, set `kind` to `button` (drop-down).
3. Set `label` to whatever the text says.
4. Save (`Cmd/Ctrl+S`).

The placement now emits a `<id>.click` hook the framework can bind.

## Test

`Run > Preview Skin` launches a borderless transparent window
loading the live skin. Click your wired button; the status line
toasts "click fired: <id>".

## Export

`File > Export > .esk Bundle`. Hand off to the runtime side.

## What you exercised

- Figma REST API import.
- Auto-layout to layout-container mapping.
- Promoting a placement to interactive.
- Run > Preview Skin verification.

## See also

- [SVG / Figma / Lottie importing](../importing/svg-figma-lottie.md)
- [SVG icon-pack skin](07-svg-icon-pack-skin.md)
