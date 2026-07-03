# Curves and NURBS

The Designer has two kinds of curve placement: **Bezier curves**
(the day-to-day choice) and **NURBS curves** (when you need
analytic precision for lofts and rails). This section covers
authoring both, with a follow-on page on lofting a curve into a
mesh.

## Bezier curves

The most common curve type. Anchors with optional tangent handles.

Tools:

- **Pen** (`P`): drag-record a freehand curve. Smoothed in
  real time using the smoothing parameter in the
  [Tool Properties dock](../interface/tool-properties-dock.md).
- **Bezier** (`Shift+P`): click-to-add anchors with drag handles.
  Same as the Illustrator pen tool.

Editing:

- Click an anchor with the Select tool to expose its tangent
  handles.
- Alt-drag a handle to break tangent continuity (make a corner).
- Right-click an anchor for: Convert to Corner / Smooth, Delete,
  Add Handle, Reset Handles.

Anchors store position + tangent handles + an optional **pressure**
sample (carried through when the curve was authored with a pen).

## NURBS curves

Open `Surfaces > NURBS > Create NURBS Curve` (Modeling menu set).
The Designer drops a basic NURBS curve placement; the
[NURBS page](nurbs.md) covers parameters in depth.

NURBS are the right choice when:

- You want continuous-curvature interpolation (no segments).
- You will loft the curve to a mesh and need predictable cross-
  sections.
- You are matching a curve from a CAD program (most CAD packages
  export NURBS).

## Closed paths

Both Bezier and NURBS curves can be open (a brushstroke) or closed
(a shape). Toggle in the Properties pane: `closed = true`.

A closed curve renders with the placement's fill + stroke; an open
curve renders the stroke only. To convert an open path's
boundary into a closed region, run `Path > Combine > Union` on
itself.

## Stroke parameters

| Property | Effect |
|---|---|
| stroke | Color (CSS hex or theme token) |
| stroke_width | Width in pixels |
| stroke_cap | butt / round / square |
| stroke_join | miter / round / bevel |
| stroke_dash | List of `[on, off]` pixel pairs for dashed |
| width_modulation | `pressure` / `none` / curve sample |

Width modulation by pressure produces calligraphic strokes from
pen-authored curves.

## Curve to mesh

Once a curve is authored, two paths produce a mesh:

- **Stroke as outline mesh**: `Path > Convert > Stroke to Mesh`
  produces a flat extruded ribbon following the curve.
- **Loft**: select two or more curves; `Surfaces > Loft to Mesh`
  builds a surface between them. See
  [Loft to Mesh](loft-to-mesh.md).

## When to skip curves

For straight rectangles, rounded rectangles, ellipses, circles,
and regular polygons, use the matching toolbox primitive (M / F /
Shift+M). Those primitives carry the shape's parameters
(rectangle: width / height / radius) instead of a vertex list, so
they re-author cleanly.

## See also

- [NURBS](nurbs.md): knot vectors, degree, and weight.
- [Loft to Mesh](loft-to-mesh.md): turn a sequence of curves into
  a Mesh3D.
- [Path booleans](../modeling/path-booleans.md): combine curves
  into new paths.
