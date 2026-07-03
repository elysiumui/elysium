# Hair

The hair solver is a Verlet rope: a chain of N point masses
connected by stiff distance constraints. Use it for hair, ropes,
tails, antennae, and any "string" that should swing and respond
to motion.

## Create

| Menu | What you get |
|---|---|
| `Simulation > Create Hair Strand` | 8-segment short strand |
| `Simulation > Create Long Hair Strand` | 24-segment long strand |

A vertical chain appears at the cursor. The first (topmost)
vertex is pinned by default; the rest hang.

## Anchor to a placement

Most hair strands should follow some other placement (a head, a
sword pommel, a wing). Set the **anchor**:

1. Select the hair.
2. Properties pane > **Simulation > Anchor** > pick a target
   placement from the scene.
3. The hair's first vertex follows the anchor's transform.

Move the anchor, the hair sways. Animate the anchor, the hair
inherits the motion plus its own physical lag.

## Parameters

| Parameter | Default | Effect |
|---|---|---|
| segments | 8 / 24 | Chain segment count |
| segment_length | auto | Distance between vertices |
| stiffness | 0.7 | Constraint solver stiffness |
| damping | 0.1 | Velocity damping |
| gravity_scale | 1.0 | Multiplier on global gravity |
| affected_by_wind | true | Whether forces apply |
| collide | false | Whether to collide with collider placements |

## Wind sensitivity

Hair reacts strongly to wind: even a gentle wind produces visible
sway. Tune by scaling wind strength globally and / or per-strand
via `gravity_scale` (which also scales wind in this solver).

For multiple hairs that should sway differently (long vs short),
use the same wind but different segment counts and stiffness; the
differences in resonance create natural variation.

## Multi-strand setup

For hair groups, drop multiple `Create Hair Strand` placements
side by side and parent them to a common head. The wind affects
each independently; their slight phase offsets read as a hair
clump.

For thousands of strands, this approach does not scale. Roadmap:
a Hair System solver that simulates a base set and instances the
rest.

## Rendering

A hair strand renders as a stroked Bezier curve following its
vertex positions, with the placement's stroke + stroke_width
applied. For a tapered look (thick at root, thin at tip), set
`width_modulation: distance_from_root` in the Properties pane.

## Use as rope

Rope is the same solver with stiffness raised to 0.95 and
segments increased. For a cable or chain, also set `damping` to
0.3 (rope swings less).

## Bake

Like cloth, hair sim auto-caches per frame. `Simulation > Bake to
Keys` collapses to per-frame keys for export.

## See also

- [Simulation index](index.md)
- [Cloth](cloth.md), [Rigidbody](rigidbody.md)
