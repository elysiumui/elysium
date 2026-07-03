# Lasso selection

The Lasso tool draws a freeform region and selects every placement
(or, for Mesh3D, every vertex) whose center falls inside the
region. It is the right tool for selecting top-N% of a wing, a
corner of a reference image, or a clump of irregularly-placed
shapes.

## Activate

| Path | Action |
|---|---|
| Toolbox > Controls > Lasso Select | Click the icon |
| Keyboard | `Shift+Q` |

The cursor becomes a pen icon. Drag freely to outline the region;
the trailing edge auto-closes when you release.

## Modifier behavior

| Modifier | Effect |
|---|---|
| Shift | Add lassoed items to current selection |
| Alt | Subtract lassoed items from current selection |
| Ctrl | Intersect: keep only what's both lassoed and currently selected |
| (none) | Replace selection |

## Selection mode

The [Tool Properties dock](../interface/tool-properties-dock.md)
under the View Panel shows the lasso's options:

- **Mode**: Replace / Add / Subtract / Intersect (same as the
  modifiers above, made sticky).
- **Through obscured**: include placements hidden behind others.
  Off by default.
- **Closed region only**: only count items inside a fully closed
  lasso. On by default; off treats the lasso as an open path and
  selects everything within a threshold distance of the path.

## Mesh3D vertex selection

When a Mesh3D placement is **selected** at the time you start the
lasso, the tool selects vertices instead of placements. The
selected vertices show as orange dots in the View Panel.

Use vertex-mode lasso to:

- Select the top 20% of wing vertices for a localized texture mask
  (see [Render part mask](render-part-mask.md)).
- Pick the corner of a model for landmark placement.
- Highlight a sub-region before a deformer is applied.

To return to placement-mode lasso, click empty canvas to deselect
the Mesh3D, then lasso.

## Practical patterns

### Select all landmark dots inside the wing

With the lasso (placement mode), drag around the wing area: every
landmark pair whose center is inside the lasso becomes selected.

### Pick the top of a hill of placements

In a scene with 30 confetti placements, lasso just the top fifteen.
The lasso's freeform shape is faster than Shift-clicking each one.

### Quick exclusion

Hold Alt and lasso a hand-shaped exclusion region around a few
placements you want to **not** be in the selection. Done in one
gesture.

## Tablet support

With a pen, the lasso recognizes pressure (stable vs jittery) and
applies a small amount of stroke smoothing. A confident long
stroke produces a clean lasso even on a noisy line.

## Paint Select alternative

For brush-style "paint over what you want" selection (instead of
outlining), see [Paint Select](../interface/toolbox.md) (`Ctrl+Shift+Q`).
Paint Select is better when the items you want do not sit inside
one closed region.

## See also

- [Toolbox](../interface/toolbox.md): the other 16 toolbox tools.
- [Render part mask](render-part-mask.md): what to do with a
  selection of vertices.
