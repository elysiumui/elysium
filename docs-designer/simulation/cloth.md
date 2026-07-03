# Cloth

The cloth solver is a position-based-dynamics (PBD) mesh simulator
suitable for flags, capes, banners, and any draping fabric.

## Create

| Menu | What you get |
|---|---|
| `Simulation > Create nCloth Patch (8×10)` | 80-vertex patch, fast iteration |
| `Simulation > Create nCloth Patch (12×14)` | 168-vertex patch, more detail |

A flat rectangular sheet appears at the cursor. Use the Move tool
to position it and the Rotate tool to orient.

## Pin vertices

A cloth patch with no pinned vertices falls to the ground (or
floats in zero gravity). Pin the corners or edge to attach it.

1. With the cloth selected, switch to vertex mode (`V`).
2. Lasso the vertices you want pinned.
3. `Simulation > Cloth > Pin Selected Vertices`.

Pinned vertices are locked to their initial positions (or, with
**Pin to Placement**, glued to another placement's transform). A
flag-pole + flag is pin-the-leftmost-vertices to the pole.

## Parameters

In the Properties pane:

| Parameter | Default | Effect |
|---|---|---|
| stretch_stiffness | 0.95 | How resistant to stretching (1.0 = inextensible) |
| bend_stiffness | 0.5 | How resistant to folding |
| damping | 0.1 | Velocity damping per step |
| friction | 0.4 | Self-collision friction |
| thickness | 1.5 px | Self-collision thickness |
| affected_by_wind | true | Whether forces in the scene apply |
| iterations | 8 | PBD constraint iterations per step (more = stiffer / more stable) |

For a flag, default values work. For a stiff cape, raise
bend_stiffness to 0.8. For a sheer veil, lower stretch_stiffness
to 0.5.

## Wind

`Simulation > Forces > Add Wind…` adds a global wind to the
scene. The cloth's `affected_by_wind: true` opts it in.

Wind parameters: direction (vector), strength (px/s²),
turbulence (0..1), noise scale (in pixels).

A flag-on-pole with a 200 px/s² wind at 0.3 turbulence reads
convincingly. Animate the wind direction over a few seconds for
gusts.

## Self-collision

Off by default (cheap). Toggle **self_collide** on in the Properties
pane for capes that fold over themselves; runtime cost roughly
2x's.

## Collision with other objects

The cloth collides with placements tagged as **collider**. Mark a
placement as collider in its Properties pane > Simulation >
**Acts as Collider**. Useful for a cloth draping over a model.

## Cache

Running a simulation through the timeline auto-caches the result.
The cache lives next to the project file at
`<project>.esk/sim_cache/<placement_id>.bin`. Re-scrub plays back
from the cache instantly.

To force a re-sim: `Simulation > Recompute Cache` or change any
simulation parameter (the cache invalidates automatically).

## Bake

`Simulation > Bake to Keys` writes per-frame keys for every vertex
on the cloth's animation track. The cloth-sim solver is then
removed; the placement plays back as a hand-keyed mesh.

Bake before exporting if you want predictable runtime behavior
that does not depend on the runtime re-simulating.

## See also

- [Simulation index](index.md)
- [Hair](hair.md), [Rigidbody](rigidbody.md)
