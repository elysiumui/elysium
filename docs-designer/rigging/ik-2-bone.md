# 2-Bone IK

An IK (Inverse Kinematics) solver computes the joint rotations
needed to put a specific joint at a specific position. The
Designer's IK is **2-bone**: it solves chains of exactly two
joints between a root and an end-effector (3 joints total).

That covers arms, legs, fingers, and butterfly wings: the most
common rigging needs.

## Setup

1. Have a [3-joint chain](joint-chains.md) ready
   (root → middle → tip).
2. Select the **tip** joint.
3. `Rigging > Solve 2-Bone IK on Selected Chain`.

The Designer:

- Creates an **IK handle** placement at the tip's position.
- Wires the IK solver to compute root.rotateXYZ and middle.rotateZ
  to keep the tip at the IK handle's position.
- The IK handle is what you move; the chain follows.

## Pose the chain

With the Move tool, drag the IK handle. The middle joint bends
naturally to keep the tip glued to the handle. Move the handle
beyond the chain's reach and the IK solver clamps with the chain
fully extended.

Keying the IK handle's translateXYZ animates the pose. Far simpler
than keying root and middle rotations individually.

## Pole vector

For chains in 3D space, the IK solver needs to know which side
the middle joint should bend toward. The **pole vector** is a
second placement that defines the bend plane.

`Rigging > Pole Vector Constraint…` creates a pole-vector
placement and links it to the IK chain. Moving the pole vector
rotates the bend plane (think of pointing an elbow forward vs
sideways).

For 2D chains, the pole vector is implicit (perpendicular to the
view plane) and you can ignore it.

## Switch between IK and FK

A chain can be edited in either mode:

- **IK**: move the IK handle, chain follows.
- **FK**: rotate joints directly, IK handle follows.

Right-click the IK handle > **Switch to FK** (or vice versa). The
Designer auto-matches the current pose so the switch is seamless.

For animation, blending IK ↔ FK over time uses the
`ik_blend` attribute on the chain's root (0 = full FK, 1 = full
IK). Animate this for "I'm walking on the ground (IK) but then
my foot lifts and swings freely (FK)" transitions.

## v1 limitations

- Chains longer than 3 joints (root + 2 mid + tip etc.) are not
  IK-solveable in v1. Use FK for those, or split into multiple
  2-bone chains.
- Spring IK / soft IK are roadmap.
- Stretch IK (where the chain elongates beyond its bone lengths)
  is not in v1.

## Performance

The 2-bone solver is analytic (closed-form), evaluated per chain
per frame. Budget: ~1 μs per chain. Even a fully-rigged character
with 20 IK chains is sub-millisecond.

## See also

- [Joint chains](joint-chains.md): build the chain first.
- [Skin binding](skin-binding.md): connect the chain to a mesh.
- [Constraints](constraints.md): alternative coupling models.
