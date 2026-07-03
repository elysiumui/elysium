# Path booleans

The four path-boolean operations combine 2D shape placements
(`rounded_rect`, `ellipse`, `path`, `polygon`, `region`) into a
single new path. Useful for authoring window outlines, hit-test
regions, and decorative cutouts.

## The four operations

| Operation | Menu | Result |
|---|---|---|
| Union | `Path > Combine > Union` | All pixels in any input shape |
| Intersect | `Path > Combine > Intersect` | Only pixels in **all** input shapes |
| Subtract | `Path > Combine > Subtract` | First shape minus the rest |
| Exclude | `Path > Combine > Exclude` | XOR: pixels in exactly one input |

## Run an operation

1. Select two or more 2D shape placements (Shift-click).
2. Open the `Path > Combine` submenu and pick the operation.
3. The Designer replaces the selected shapes with a new `path`
   placement whose `path_d` is the result.

Undo (`Cmd+Z` / `Ctrl+Z`) restores the inputs if the result is
not what you wanted.

## When the order matters

- **Union**, **Intersect**, **Exclude**: order-independent.
- **Subtract**: the first selected shape is the subject; the rest
  are subtracted from it. The Designer subtracts in selection
  order, which matches click order.

To rearrange: deselect, click the intended subject first, then
Shift-click the cutters.

## Result placement

The new placement keeps the **subject's** fill, stroke, opacity,
shadow, and other style fields. Inputs disappear from the canvas
but remain in the undo history. To preserve the inputs as well,
duplicate them first (`Cmd+D`) and operate on the copies.

## Self-intersecting shapes

Self-intersecting paths produce sensible results (the boolean
operations treat them with the non-zero winding rule by default).
Switch to even-odd rule per-shape via the Properties pane's
`fill_rule` field.

## Boolean on a window shape

A common workflow is authoring a window's hit-test path by
combining simple shapes:

1. Drop a rounded-rect.
2. Drop two small circles on the corners for tabs.
3. Lasso all three.
4. `Path > Combine > Union`.
5. With the resulting path selected: `Window > Set Shape From
   Selection`.

The window's hit-test region updates to the new shape.

## Performance

Booleans run on the CPU using the framework's geometry pipeline
(Skia path ops). A complex result with hundreds of vertices is
still under 1 ms; you will not notice the latency.

## Limitations

- 2D only. Mesh3D placements are not eligible inputs; for 3D
  boolean operations export to a DCC.
- Curves with non-zero-area open ends are auto-closed before the
  operation.
- Stroked-only paths (no fill) are treated as their stroked area
  during the boolean (the stroke becomes a polygon).

## See also

- [Arrange and align](arrange-and-align.md): combine booleans
  with alignment for precise authoring.
- [Borderless windows](../borderless/index.md): using a combined
  path as a window's hit region.
