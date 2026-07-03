# Rigidbody

The rigidbody solver is built on Bullet Physics: rigid shapes
collide with each other and with the world, transferring momentum
realistically. Use for any motion that depends on objects bouncing
off each other.

## Create

| Menu | What you get |
|---|---|
| `Simulation > Bullet > Add Rigidbody (selected)` | Default solid rigidbody |
| `Simulation > Bullet > Add Bouncy Rigidbody (selected)` | Same with high restitution + low friction |

The selection becomes a rigidbody. Its placement transform is now
driven by the physics solver each frame.

## Parameters

| Parameter | Default | Bouncy default | Effect |
|---|---|---|---|
| mass | 1.0 | 1.0 | kg-equivalent (relative) |
| restitution | 0.2 | 0.9 | "Bounciness" 0..1 |
| friction | 0.5 | 0.05 | Surface friction 0..1 |
| linear_damping | 0.0 | 0.0 | Velocity drag |
| angular_damping | 0.05 | 0.05 | Spin drag |
| static | false | false | When true, body cannot move but other bodies bounce off it |
| collider_shape | auto | auto | box / sphere / convex_hull / mesh |

## Collider shapes

The solver needs a collision shape, which can be different from
the rendered shape:

- **auto**: pick box for rectangle, sphere for ellipse, convex hull
  for everything else.
- **box**: fast; use for cuboid placements.
- **sphere**: fastest; use for round placements.
- **convex_hull**: medium speed; approximate any shape as a
  convex shell.
- **mesh**: slow; only for static bodies (mesh-mesh dynamic is
  not supported in v1).

Tune in Properties pane > Simulation > **Collider Shape**.

## World setup

The Bullet solver runs in a per-project world. Configure global
parameters in `Simulation > Bullet > World Settings…`:

- **Gravity** (default: 0, 800, 0 px/s²; world Y points down).
- **Substeps per frame** (default 4; more = stiffer / more
  accurate).
- **Sleep threshold** (default 0.05 px/s; bodies below this
  velocity stop simulating, save CPU).

## Static bodies as walls

For a floor, wall, or any non-moving obstacle, mark a rigidbody as
**static**. It does not move but other bodies collide with it.
Useful for boundary geometry around a domino layout, for example.

## Triggering motion

A static rigidbody at frame 0 with `static: false` set on frame 10
(via animation) "wakes up" at frame 10 and begins simulating. Use
this for explicit "fall now" triggers.

Alternatively, apply an impulse: `Simulation > Bullet > Apply
Impulse to Selected…` adds a one-shot velocity to a body. Animate
the impulse via the same dialog at a later frame.

## Bake

Like the other solvers, run through the timeline once to cache,
then `Simulation > Bake to Keys` to commit to per-frame keys for
export.

## Limitations (v1)

- Mesh-mesh dynamic collision is not supported (use convex_hull
  for dynamic bodies).
- Hinge / slider / spring constraints between bodies are roadmap.
- Cloth-rigidbody two-way interaction is rudimentary; cloth
  drapes over static rigidbodies, but a dynamic rigidbody does
  not respond to cloth.

## See also

- [Simulation index](index.md)
- [Cloth](cloth.md), [Hair](hair.md)
