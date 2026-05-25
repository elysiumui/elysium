# Paint weights

After [skin binding](skin-binding.md), per-vertex weights determine
how much each joint influences each vertex. The auto-bind gives
sensible defaults; **paint weights** is the tool for fixing the
spots it gets wrong.

## Set the active joint

`Rigging > Paint Weights > Set Active Joint (from selection)`.
With a joint selected, this tells the painter "the next strokes
write this joint's weights."

The View Panel tints the mesh by current weight: black = 0
influence, white = 1.0 influence, in between = partial.

## Paint

Three painting modes:

| Mode | Menu / Hotkey | Effect |
|---|---|---|
| Normal | `Rigging > Paint Weights > Paint at Cursor` | Stamp weight = brush opacity |
| Strong | `Rigging > Paint Weights > Paint at Cursor (strong)` | Stamp weight = 1.0 regardless of opacity |
| Reset | `Rigging > Paint Weights > Reset to Uniform (0.5 / 0.5)` | Reset selected vertices to balanced between two joints |

The Brush tool's size + opacity in the
[Tool Properties dock](../interface/tool-properties-dock.md) control
the painting strength. Use a soft brush for smooth blends, a hard
brush for sharp boundaries.

## Verify mid-paint

A handy trick: pose the joint to a deformed position before
painting. The mesh deforms with the current weights, so you can
see in real time how your paint changes the deformation.

1. Pose the joint chain via IK / FK to the most extreme pose
   you care about.
2. Switch to Paint Weights.
3. Brush vertices that look wrong; the mesh updates live.
4. Reset the pose when done.

## Weight constraints

Weights are subject to two constraints:

- Per-vertex weights sum to 1.0 (the painter normalizes
  automatically).
- Max-weights-per-vertex caps how many joints can have non-zero
  weight (default 4; configurable to 8). Painting a fifth joint's
  weight onto an already-full vertex pushes out the smallest
  influencing joint.

## Mirror weights

For symmetric rigs, paint one side and mirror to the other:

`Rigging > Paint Weights > Mirror Weights Across X`.

The mirror copies weights from positive-X joints to their `_R`
counterparts (or whatever your mirror naming convention is in
`Preferences > Rigging > Mirror Naming`).

## Smooth

`Rigging > Paint Weights > Smooth Selected` averages weights
between a vertex and its neighbors. Run a few times to soften a
hard boundary between two joints' influence zones.

## Heat map

The same heat-map overlay from
[Skin binding](skin-binding.md) helps find vertices that ended up
with too many or too few influences. Toggle with `View > Skin
Weight Heat Map`.

## Performance

Painting on a 10,000-vertex mesh runs at full pen frame rate
(120 Hz tablets, 60 Hz mice). The Designer batches weight updates
per stroke so the GPU stays warm.

## See also

- [Skin binding](skin-binding.md): set the starting point.
- [Joint chains](joint-chains.md): the joints whose weights you
  paint.
- [Brush > Quick start](../brush/quick-start.md): the brush
  system the painter rides on.
