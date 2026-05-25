# Motion paths

A motion path is a visual curve in the canvas showing the
trajectory of an animated placement's translate channel. Two
features ride on it: visualization (see the path the placement
will follow) and constrain-to-path (replace translate keys with a
curve to follow).

## Visualize

With an animated placement selected, `Animate > Motion Paths >
Show` draws a curve in the View Panel passing through every keyed
position. Tick marks along the curve show key positions; spacing
between ticks indicates speed (close ticks = slow, far ticks =
fast).

Useful for catching:

- A trajectory that pops backward between keys.
- Curves that ease out too sharply.
- Unintentional bumps in what should be a smooth path.

`Animate > Motion Paths > Hide` removes the overlay.

## Edit-in-place

With Show on, drag the small key handles directly in the View
Panel to reposition the underlying translate keys. The keys on the
time slider update in real time; the placement's animation follows.

Useful for "this descent path needs to swing wider here": drag
the midpoint and the in/out tangents adjust automatically.

## Constrain to a curve

`Animate > Motion Paths > Attach to Curve…` opens a small dialog
asking which curve to follow. Pick any Bezier or NURBS curve from
the project; the placement removes its translate keys and instead
animates the curve's `t` parameter (0..1) over the timeline.

Now keying `t` from 0 to 1 over 60 frames moves the placement
along the curve's entire length over that duration. Easing
applies to `t`, not directly to position, so a slow-in / slow-out
on `t` produces the same on the position automatically.

The Butterfly Banner tutorial's descent could be authored this way:
draw a gentle S-curve from offscreen to the center, attach the
butterfly placement, key `t` from 0 → 1 with cubic ease-out.

## Constraint properties

| Property | Effect |
|---|---|
| t | The animatable parameter (0..1) |
| follow_tangent | Rotate placement so its forward axis follows the curve direction |
| up_axis | Which placement axis is "up"; matters with follow_tangent |
| world_up | World vector used to compute roll |
| bank | Add a banking rotation proportional to curve curvature |

`follow_tangent` is the difference between "a butterfly drifting
along a path" (off: orientation independent of motion) and "a
fighter jet flying along a path" (on: orientation locked).

## Detach

`Animate > Motion Paths > Detach from Curve` un-constrains the
placement, leaving its translate channel back in direct-key mode.
The current `t` value is sampled to produce a single translate
key at the current frame.

## Use with rigs

Motion paths combine cleanly with rigs: attach the root joint to
a path; the rest of the chain follows via the bind. The IK
handles can independently animate to control the body's pose as
the rig sweeps along the curve.

## See also

- [Curves and NURBS](../curves/index.md): author the curve.
- [Constraints](../rigging/constraints.md): alternative ways to
  couple placements to others.
