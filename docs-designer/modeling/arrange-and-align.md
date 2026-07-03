# Arrange and align

The `Arrange` menu groups alignment and z-order operations. Where
the lasso lets you grab a group of placements, Arrange lets you
position them precisely.

## Align (six entries)

| Entry | Effect |
|---|---|
| `Arrange > Align Left` | All selected placements share the leftmost x of the selection |
| `Arrange > Align Center` | All share the horizontal center x |
| `Arrange > Align Right` | All share the rightmost x |
| `Arrange > Align Top` | All share the topmost y |
| `Arrange > Align Middle` | All share the vertical center y |
| `Arrange > Align Bottom` | All share the bottommost y |

Run with two or more placements selected. The reference value comes
from the selection's bounding box; pivots stay where they were.

## Distribute (three entries)

`Arrange > Distribute Horizontally`, `Distribute Vertically`,
`Distribute Both`. Spaces three-or-more placements evenly between
the outermost two. Pivots move so spacing reads from edge to edge.

## Z-order

| Entry | Effect |
|---|---|
| `Arrange > Bring Forward` | One step up in draw order |
| `Arrange > Bring to Front` | All the way up |
| `Arrange > Send Backward` | One step down |
| `Arrange > Send to Back` | All the way down |

Draw order is also visible (and drag-reorderable) in the
[Project Explorer's Objects tab](../interface/project-explorer.md).

## Anchor + nudge

After an align, the selection's bounding box may have moved.
Nudge it back with arrow keys (1 pixel) or Shift+arrow (10 pixel).
Holding Alt while pressing arrow keys nudges only one anchor
(useful when the selected placements should not share their pivots).

## Snap during align

Hold Ctrl during an align to additionally snap the result to the
nearest grid line. `View > Toggle Grid` shows the grid for
reference; grid size is configured in `Preferences > Snapping`.

## Aligning to a specific placement

By default, align uses the **selection's** bounding box. To align
to a specific placement instead:

1. Click that placement first.
2. Shift-click the others.
3. `Arrange > Align Left/etc. > To Active`.

"To Active" is a submenu under each align entry that uses the
last-clicked (active) placement as the anchor instead of the
bounding box. The active placement shows a brighter selection
outline.

## Aligning to canvas

`Arrange > Align Left to Canvas` (and the rest) align relative to
the canvas (0..width / 0..height), not the selection or active
placement. Useful for centering a single placement on its window.

## See also

- [Toolbox > Snap to Grid](../interface/toolbox.md): snap during
  drag.
- [Path booleans](path-booleans.md): combine alignment with
  boolean ops for tight authoring loops.
