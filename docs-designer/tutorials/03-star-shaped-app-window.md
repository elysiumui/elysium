# Star-shaped app window

Time: 20 minutes. Difficulty: Beginner.

Three ways to author non-rectangular window shapes in the Designer.
Skin produces just the outline; you can wire content later or
ship it as an empty showcase.

## 1. Polygon tool (geometric star)

1. `File > New Skin`, 320 x 320.
2. Toolbox > Shapes > Polygon (`Shift+M`).
3. Click each star point in turn (10 clicks for a 5-point star),
   then press Enter to close the path.
4. `Window > Set Shape From Selection`.

This produces a perfectly regular star.

## 2. Pen tool (hand-drawn)

For an irregular hand-drawn star:

1. Toolbox > Shapes > Pen (`P`).
2. Drag a path, lift to break, drag again: the smoothing in the
   Tool Properties dock controls jitter.
3. Close the path with Enter or click your starting anchor.
4. `Window > Set Shape From Selection`.

Looser, more organic look.

## 3. Path boolean (composed)

For a stylized star built from primitives:

1. Drop two rectangles (`M`) overlapping at 45 degrees offset.
2. Drop a circle (`F`) at their center.
3. Lasso all three; `Path > Combine > Union`.
4. `Window > Set Shape From Selection`.

Easier to tweak per-corner radii later by editing the input
shapes.

## Test the shape

`Run > Preview Skin` opens a separate window with the shape
applied. Drag it around your desktop; click corners (outside the
star) to confirm clicks pass through.

## A note on the SVG path

Whichever method you use, the result is stored as an SVG path in
the bundle's `manifest.json`:

```json
"window": { "shape": { "kind": "path", "path_d": "M 160,16 L …" } }
```

Hand-edit if you need pixel-perfect coordinates.

## What you exercised

- Polygon tool.
- Pen tool.
- Path boolean Union.
- `Window > Set Shape From Selection`.
- Preview Skin for verification.

## See also

- [Borderless music widget](02-borderless-music-widget.md)  
  apply this shape to a music skin.
- [Borderless windows](../borderless/index.md): full guide.
