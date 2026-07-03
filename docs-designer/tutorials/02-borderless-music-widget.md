# Borderless music widget

Time: 25 minutes. Difficulty: Beginner.

Author a compact star-shaped now-playing widget skin in the
Designer. The Designer side of the
[framework tutorial of the same name](https://docs.elysiumui.com/tutorials/borderless-music-widget/).

## Prerequisites

- Designer installed.
- Finished the [Blue Morpho tutorial](../getting-started/butterfly/index.md).

## Author the star

1. `File > New Skin`, name "Music widget", size 200 x 200.
2. With the Polygon tool (`Shift+M`), trace a 5-point star at
   coordinates: (100,10), (120,75), (190,75), (135,115),
   (155,180), (100,140), (45,180), (65,115), (10,75), (80,75).
3. Select the polygon; in the Properties pane set
   `fill = linear-gradient(135deg, #18113c 0%, #2a1a5a 100%)` and
   `stroke = #a78bfa66`.

## Set the window shape

With the star selected, `Window > Set Shape From Selection`. The
canvas updates with a faint outline showing the window's hit
region.

## Add buttons

From the Toolbox > Shapes, drop three Orb buttons:

- `btn_prev` at (65, 105), radius 14, glyph "prev".
- `btn_play` at (100, 100), radius 20, glyph "play".
- `btn_next` at (135, 105), radius 14, glyph "next".

For each, in the Properties pane set:

- `fill`: radial gradient violet-to-pink.
- `stroke`: `#fbcfe8aa`.

## Hooks

Right-click each button > **Expose hook** (or just save: the
Designer auto-exposes `click` on every button).

## Export

`File > Export > .esk Bundle`. You now have a `widget.esk/`
folder. Hand it to the
[framework tutorial](https://docs.elysiumui.com/tutorials/borderless-music-widget/)
for runtime wiring.

## What you exercised

- Polygon tool authoring.
- `Window > Set Shape From Selection`.
- Orb button placement kind.
- `.esk` export.

## See also

- [Star-shaped app window](03-star-shaped-app-window.md): practice
  the shape-authoring step on its own.
- [Aether scaffold a settings panel](08-aether-scaffold-settings-panel.md)
