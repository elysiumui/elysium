# MASH scatter

MASH (Maya's procedural toolkit name; here used generically) is the
Designer's procedural duplication system. Drop a placement, point
MASH at it, and get many copies arranged according to a generator.

## Create

`Procedural > MASH > Create Scatter…` opens a small dialog:

| Field | Default | Notes |
|---|---|---|
| Source | (none) | Pick the placement to duplicate |
| Count | 20 | Number of copies |
| Generator | Grid | Grid / Random / Along Curve / On Mesh |
| Spacing | 50 px | For Grid |
| Region | full canvas | Bounding region for placement |

Click Create; the Designer drops a "MASH set" placement that owns
N instances of the source. The instances move together when the
MASH set moves.

## Generators

### Grid

Even spacing in a configurable grid. Parameters:

- **Rows / Cols**: 2D grid layout.
- **Spacing X / Y**: pixels between instances.
- **Stagger**: offset every other row for honeycomb.

Use for backgrounds, button grids, repetitive icons.

### Random

Random positions within a region. Parameters:

- **Seed**: integer; same seed = same layout.
- **Min distance**: minimum spacing between instances (Poisson-
  like sampling).

Use for confetti, leaves on a forest floor, stars.

### Along curve

Distribute along a Bezier or NURBS curve. Parameters:

- **Curve**: pick a curve placement.
- **Mode**: even spacing / pressure-modulated / random along t.
- **Align tangent**: rotate instances to follow curve tangent.

Use for a string of pearls, fairy lights, a feather running along
a wing edge.

### On mesh

Distribute on a Mesh3D's surface. Parameters:

- **Mesh**: target Mesh3D placement.
- **Density**: instances per unit area.
- **Align to normal**: rotate instances to align with mesh normals.

Use for scattering tiny butterflies across a hero butterfly's
wing, or fluff onto a hide.

## Per-instance variation

The MASH set's Properties pane has a **Variation** section that
modulates each instance's parameters:

- Rotation jitter (degrees per axis).
- Scale jitter (multiplier per axis).
- Color jitter (HSV deltas).
- Index-based: explicitly per-instance values from a list.

A 0.0 - 0.3 rotation jitter on a confetti scatter is the
difference between "rectangles in a grid" and "celebration".

## Animating the layout

The MASH set's count, spacing, and generator parameters are all
animatable. A grid that grows from 1 to 100 instances over 60
frames is a clean "build" animation.

For per-instance animation (each instance has a slightly different
phase or amplitude), enable the **per-instance time offset** in
the Variation panel. The instance's animation track samples at a
seeded offset; you get organic-looking waves of motion.

## Bake to placements

`Procedural > MASH > Bake to Placements` converts every instance
into a regular Placement. The MASH set disappears; you have N
independent placements you can hand-edit.

Bake when:

- You want to hand-tune a specific instance (impossible while
  it's procedural).
- You are shipping the scene to a renderer that does not honor
  procedural sets.

## Performance

Procedural instances render at near-zero per-instance overhead
(GPU instancing via the framework's `DisplayList` instance API).
A 10,000-instance grid is comfortably real time.

## v1 limitations

- Single source per MASH set; multi-source mixed scatters are
  roadmap.
- "On Mesh" generator picks per-face uniformly; weighted face
  picking by paint mask is roadmap.

## See also

- [Curves index](../curves/index.md): author the curve used by
  the Along Curve generator.
- [Animation index](../animation/index.md): animate MASH
  parameters.
