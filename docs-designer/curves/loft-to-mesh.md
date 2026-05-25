# Loft to mesh

A loft builds a surface that runs through a sequence of input
curves. The Designer's loft is the fastest way to author smooth
3D geometry from 2D curves.

## Setup

1. Author two or more cross-section curves. They can be Bezier or
   NURBS, open or closed, and do not need the same vertex count.
2. Position them along the loft axis (typically the z-axis).
3. Select them all (Shift-click) in the order you want the loft to
   traverse.
4. `Surfaces > Loft to Mesh`.

The Designer creates a new Mesh3D placement and hides (but does
not delete) the input curves.

## Options dialog

The `Loft to Mesh` action opens a small dialog:

| Option | Default | Notes |
|---|---|---|
| Sections | input count | How many curves to interpolate between |
| Smoothness | 24 | Subdivisions across each section |
| Across | linear | linear / bezier / nurbs interpolation between curves |
| Caps | open | open / close-at-ends / close-both |
| UV mapping | cylindrical | cylindrical / planar / preserved |

The defaults produce a smooth surface with reasonable topology.

## Cross-curve resampling

Loft requires curves with matched parametrization. The Designer
auto-resamples each input curve to a common vertex count. To
control this:

- **Resample**: on by default. Picks the highest vertex count of
  any input curve and resamples the others to match.
- **Reverse direction**: per-curve toggle if a section comes out
  flipped (look for inside-out shading; flip the offending curve).
- **Align**: re-align the curves' first CVs so they line up along
  the loft direction; toggles off when you want a twist.

## Closed vs open lofts

- Inputs all open → open loft (a strip).
- Inputs all closed → closed loft (a tube).
- Inputs mixed → undefined; the Designer warns and treats them as
  open.

For a Möbius strip, set Reverse direction on every other curve.

## After lofting

The resulting Mesh3D placement has standard transform / mask /
material properties. To re-author:

1. Right-click the Mesh3D placement > Show Source Curves.
2. Edit the curves.
3. The loft auto-re-runs and updates the mesh in real time.

The link between curves and mesh is non-destructive; the curves
remain editable so long as the Mesh3D placement is in the project.

## UV mapping

The Designer offers three UV strategies:

- **Cylindrical**: U follows the cross-curve direction, V follows
  the along-curve direction. Best for tube-like lofts.
- **Planar**: U / V are world-space x / z of the input curves.
  Best when you want textures to "lay flat" across the surface.
- **Preserved**: keeps each input curve's U coordinate and
  interpolates V from input index. Best when the cross-sections
  carry meaningful texture coordinates already (rare).

## Performance

A 24-section x 24-smoothness loft creates ~576 quads (~1152
triangles). The Designer handles up to ~10,000-quad lofts in real
time; beyond that, prefer authoring topology in a DCC and
importing.

## Limitations

- Loft is one-directional only (along a single sweep). For
  bidirectional surfaces (think of a checkerboard of curves),
  loft pairs separately and combine via the boolean tools.
- No spline-sweep "rail" mode in v1; the loft moves linearly /
  smoothly between sections.

## See also

- [Curves index](index.md): author the input curves first.
- [NURBS](nurbs.md): predictable cross-sections for analytic
  lofts.
- [Importing 3D models](../importing/3d-models.md): when to
  loft vs DCC and import.
