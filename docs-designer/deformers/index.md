# Deformers

A deformer is a non-destructive transform applied on top of a
placement's base geometry. The placement's source vertices stay
unchanged; the deformer computes the deformed positions every
frame. Useful for stylized motion, blend shapes, and procedural
distortion.

## The stack

Each placement carries an ordered **deformer stack**. Deformers
evaluate top-to-bottom; each one takes the previous output as
input. Add, remove, reorder, and bypass per deformer.

The stack lives in the Properties pane > **Deformers** section.

## Built-in deformers

| Name | Effect |
|---|---|
| Bend | Curves geometry along an axis |
| Twist | Rotates geometry around an axis as you move along it |
| Sine | Adds a sine wave along an axis |
| Squash | Squash-and-stretch with a configurable axis |
| Lattice | Bezier-handle cage for arbitrary distortion |
| Wave | Radial sine wave from a center point |
| Noise | Perlin / Worley displacement |
| Cluster | Weighted control via auxiliary placement |

The [Bend / Twist / Sine](bend-twist-sine.md) page covers the
three most common deformers in depth.

## Add a deformer

1. Select the placement.
2. Properties pane > Deformers > **+ Add Deformer** > pick from
   the dropdown.
3. The deformer appears in the stack with its default parameters.
4. The placement's geometry deforms in real time.

## Parameter editing

Each deformer is a small section in the Properties pane. Drag
fields to scrub, type values, or right-click for keying /
expression / lock.

Most deformers have an **axis** parameter: pick X / Y / Z, or
choose **Custom** and define a per-deformer axis vector.

## Animation

Every deformer's numeric parameters are keyable. The
[Animation > Keyframes](../animation/keyframes.md) page covers the
mechanics; the short version: turn on `Animate > Toggle Auto Key`,
scrub the timeline, change a deformer's value, the framework
records a key.

This is how a "flag wave" or a "wing flap" animation is typically
authored: a Sine deformer with an animated phase.

## Falloff and masks

Most deformers expose a **falloff** parameter that ramps the
effect down at the edges of the placement's bounding box. Useful
when you want the body to stay rigid while the tips deform.

For per-vertex weighting, combine with a
[render part mask](../modeling/render-part-mask.md): the deformer
respects the mask, applying only inside the masked region.

## Stack order matters

Bend then Twist ≠ Twist then Bend. Swap by dragging in the
Properties pane's deformer list. The View Panel updates in real
time so you can audition orders.

## Performance

Deformers evaluate on the GPU when possible (compute shader),
fall back to CPU for low-vertex-count cases. Budget per frame:

- Simple deformers (Bend, Sine, Twist, Wave, Noise): ~0.1 ms per
  10,000 vertices.
- Lattice + Cluster: ~0.3 ms per 10,000 vertices (read auxiliary
  data).

Stacking 5 deformers on a 50,000-vertex mesh is still well under
2 ms per frame on a baseline GPU.

## Bypass

The eye icon next to each deformer toggles it on / off without
removing it. Useful when comparing the effect with vs without.

## Apply (destructive)

`Deformers > Apply Stack` bakes the entire deformer stack into the
placement's geometry. The deformers disappear from the stack and
the base vertices update to their deformed positions. Irreversible
(except via undo within the same session).

Apply when the deformer's effect is final and you want to free the
performance budget for downstream work.

## See also

- [Bend / Twist / Sine](bend-twist-sine.md): the three most-used
  deformers in depth.
- [Animation > Keyframes](../animation/keyframes.md): animating
  deformer parameters.
