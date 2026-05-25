# Bend / Twist / Sine

The three deformers that cover the most common motion needs:
curving a long shape (Bend), spiraling it around its axis (Twist),
and rippling it (Sine).

## Bend

Curves geometry along an axis.

| Parameter | Default | Effect |
|---|---|---|
| axis | Y | Which axis the bend curls around |
| angle_deg | 0 | -180 to 180; total bend angle from start to end |
| start | 0.0 | Where the bend begins (0..1 along axis) |
| end | 1.0 | Where the bend ends |
| falloff | 0.0 | 0 = no falloff, 1 = full ease at start and end |

Common uses:

- A flag pole + flag, where the pole stays straight (falloff = 0,
  start = 0.5).
- An arched window frame (axis = Z, angle_deg = 30, start = 0).
- A bending tree limb in a procedural scene.

## Twist

Rotates geometry around an axis as a function of position along
that axis.

| Parameter | Default | Effect |
|---|---|---|
| axis | Y | Which axis the twist runs along |
| angle_deg | 0 | Total twist from start to end |
| start | 0.0 | Where twist begins |
| end | 1.0 | Where twist ends |
| profile | linear | linear / ease_in / ease_out / sine: how twist accumulates |

Common uses:

- A ribbon banner (axis = Y, angle = 90, profile = ease_out).
- DNA-helix decoration.
- A wrung-out cloth-like shape stacked under a Bend.

## Sine

Adds a sine wave displacement along an axis.

| Parameter | Default | Effect |
|---|---|---|
| axis | X | Which axis the wave runs along |
| amplitude | 10 | Pixels of displacement at the peak |
| wavelength | 100 | Pixels per cycle |
| phase_deg | 0 | Animatable; offset of the wave |
| direction | Y | Which axis the displacement points along |
| envelope | none | none / triangle / sin: modulate amplitude along axis |

Common uses:

- Animated flag wave (axis = X, direction = Y, animate phase).
- Rippling water surface decoration.
- Wing edge oscillation on a static butterfly skin.

Animating `phase_deg` over time at constant rate produces a
traveling wave. The Aurora Clock tutorial's breathing glow could
also be authored as a Sine on the glow placement's scale.

## Combining Bend + Twist + Sine

The classic "flag in the wind" stack: Bend (small angle, animated)
+ Sine (high amplitude, animated phase). Stack Bend first so it
shapes the flag's overall droop; Sine adds the ripple on top.

For a wing-flap, Bend (large angle, animated) is usually enough on
its own. Add Sine with a low amplitude and short wavelength for
a feather-ruffle effect on top.

## Animating

`Animate > Toggle Auto Key` + scrub the timeline + drag any
deformer slider. The framework records a key on each frame change.

For sine animations, drag `phase_deg` from 0 → 360 over the
desired number of frames. The Graph Editor's tangent type should
be `Linear` (constant rate) for a steady wave; `Auto Tangent` for
a slightly springy wave.

## Layering with masks

A flag should bend only past the pole. Combine Bend with a
[render part mask](../modeling/render-part-mask.md):

1. Vertex-select the "after the pole" portion of the flag.
2. `Mesh > Render Part Mask > From Vertex Selection`.
3. Add the Bend deformer; it respects the mask automatically.

## Performance

All three deformers are leaves on the GPU compute path and are
~0.1 ms per 10,000 vertices. Stacking five is still under 1 ms.

## See also

- [Deformers index](index.md): the full deformer catalog.
- [Animation > Keyframes](../animation/keyframes.md): animating
  the parameters above.
