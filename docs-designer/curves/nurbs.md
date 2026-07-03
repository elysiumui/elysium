# NURBS

NURBS (Non-Uniform Rational B-Spline) curves give you a smooth,
analytic curve with predictable behavior under deformation,
extrusion, and lofting. The Designer's NURBS implementation is
small but complete enough to author CAD-style profiles.

## Create

`Surfaces > NURBS > Create NURBS Curve`. The Designer drops an
empty NURBS curve at the cursor; click on the canvas to add
control points; press Enter or Esc to close authoring.

For closed NURBS: toggle `closed` in the Properties pane.

## Parameters

| Property | Default | Range | Effect |
|---|---|---|---|
| degree | 3 | 1 - 7 | Polynomial order; 3 = cubic (most common) |
| knot_kind | clamped | clamped / open / periodic | Knot vector spacing |
| weights | 1.0 each | 0.1 - 10.0 per CV | Rational weights for the CVs |
| control_points | (authored) | n ≥ degree + 1 | The control polygon |

The degree and knot kind together determine the curve's
continuity. Cubic clamped curves pass through their first and last
CVs, which is usually what you want.

## Editing CVs

- Click any CV to select it; drag to move.
- Shift-click to extend selection.
- Right-click a CV for: Add CV After / Before, Delete CV, Reset
  Weight to 1.0.
- Type a new weight in the Properties pane's `weight` field.

Increasing a CV's weight pulls the curve toward that CV; useful
for steering analytic curves to pass closer to a reference point.

## Insert vs raise degree

To get more shape control without distorting existing geometry:

- **Insert Knot** (`Surfaces > NURBS > Insert Knot`): adds a new
  CV by knot insertion. Curve shape stays identical; you gain a
  new editable point.
- **Raise Degree** (`Surfaces > NURBS > Raise Degree`): raises the
  polynomial order by 1 (adds one CV). Curve shape stays
  identical.

Both are non-destructive.

## Convert between NURBS and Bezier

`Surfaces > Convert > NURBS to Bezier` and the inverse. Convert to
Bezier when you want to edit with tangent handles instead of CVs;
convert to NURBS when you want to loft or use a deformer that
prefers analytic input.

The conversion preserves shape exactly for cubic curves; lower /
higher degrees may introduce sub-pixel error.

## Closing a NURBS

For closed analytic curves choose `knot_kind = periodic` and set
`closed = true`. The curve wraps so its end CV connects smoothly
back to its start CV with full C^(degree-1) continuity.

For a sharp-cornered closed NURBS, use `clamped` + `closed = true`;
the corner appears at the duplicated start/end CV.

## Lofting

Two or more NURBS curves can be lofted into a Mesh3D surface; see
[Loft to Mesh](loft-to-mesh.md). NURBS lofts produce predictable
quad meshes; Bezier lofts approximate.

## Limitations

- NURBS surfaces (not just curves) are on the roadmap but not in
  v1. You can fake them with a series of lofted NURBS curves.
- The Designer's NURBS solver is fixed-precision (double). Very
  long curves (> 10^6 px) may accumulate visible deviation in the
  CV-to-curve evaluator.

## See also

- [Curves index](index.md): Bezier vs NURBS decision.
- [Loft to Mesh](loft-to-mesh.md): turn NURBS curves into a
  surface.
