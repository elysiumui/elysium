# Constraints

A constraint couples one placement's transform to another's. Use
them when a placement should follow some other placement's
position, rotation, scale, or any combination, without parenting
the two.

## The five constraints

| Constraint | Menu | Channels carried |
|---|---|---|
| Parent | `Rigging > Constraints > Parent` | Translate + Rotate + Scale (everything) |
| Point | `Rigging > Constraints > Point` | Translate only |
| Orient | `Rigging > Constraints > Orient` | Rotate only |
| Aim | `Rigging > Constraints > Aim` | Rotation so the constrained's forward axis aims at the target |
| Scale | `Rigging > Constraints > Scale` | Scale only |

## Create a constraint

1. Click the **target** placement first (the source of motion).
2. Shift-click the **constrained** placement (the follower).
3. Choose a constraint from the menu.

The constraint is stored on the constrained placement and re-
evaluates every frame.

## Parent vs Parenting

Two confusingly-named concepts:

- **Edit > Parent**: hierarchical parent. The constrained placement
  becomes a child in the scene graph; its transforms are
  interpreted in the parent's local space.
- **Constraints > Parent**: keeps the placement at the same scene
  level but copies the target's world transform each frame.

Use Edit > Parent when both placements should move together as a
group. Use Constraints > Parent when the follower should mirror
the target's world position but keep its own scene-graph parent
(useful for "this prop follows the character's hand without
becoming part of the character's hierarchy").

## Aim constraint

Aim is the trickiest. It rotates the constrained so its **forward
axis** points at the target's position. Common uses:

- Eyes following the camera or another character.
- A spotlight tracking a moving subject.
- An IK arm rotating its hand to point at a target.

Properties:

- **Aim vector**: which local axis points at the target (X by default).
- **Up vector**: which local axis stays oriented "up".
- **World up object**: what defines "up" (defaults to world Y).

## Mixing multiple constraints

A placement can carry several constraints simultaneously. They
evaluate in stack order; each constraint operates on whatever the
previous one produced. Reorder by dragging in the Properties pane.

Common mix: Point + Orient + Scale = same as Parent, but you can
animate the Point's `weight` to slide the follower in/out without
also blending rotation or scale.

## Weight

Every constraint has a 0..1 weight. Animate the weight to fade a
constraint in or out. At 0 the constrained's own transform takes
over; at 1 the constraint fully controls.

## Clear

`Rigging > Constraints > Clear (Selected)` removes every
constraint on the selected placement (asks for confirmation).

To remove just one constraint, expand the Properties pane's
Constraints section and click the X next to the entry you want
gone.

## Performance

Constraints evaluate per frame on the CPU as part of the scene
graph update. Each costs about 1 μs. A rig with 50 constraints
is sub-millisecond per frame.

## See also

- [Joint chains](joint-chains.md): common targets for constraints.
- [IK 2-bone](ik-2-bone.md): when to constrain vs solve IK.
