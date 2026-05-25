# Skin binding

Skin binding wires a Mesh3D placement to a joint chain so the
mesh deforms when the joints move. The Designer's bind is a
simple, distance-weighted skinning model that produces good
results for the kinds of geometry shipped with skins.

## Setup

1. Position your [joint chain](joint-chains.md) where you want
   the mesh to bend.
2. Select the Mesh3D placement.
3. Shift-click the **root** joint of the chain (the topmost
   parent).
4. `Rigging > Bind Skin to Selected Mesh`.

The Designer assigns each mesh vertex to one or more joints based
on proximity and joint segment direction. After binding, moving
any joint moves the mesh.

## What "bind" stores

Each vertex gains a small weights table:

```
vertex 412:
  shoulder_L = 0.0
  elbow_L    = 0.18
  wrist_L    = 0.82
```

Weights sum to 1.0 per vertex. The framework computes the deformed
position as a weighted blend of the joint transformations.

The default binding uses 4 weights per vertex; configurable up to
8 in `Preferences > Rigging > Max Weights Per Vertex`. More
weights smooth the deformation but cost more per-frame compute.

## Verify the bind

1. Select the wrist joint.
2. Rotate it 30° around its hinge axis.
3. The mesh should follow smoothly.

If the mesh moves rigidly (no smooth bending) → the wrist's
influence is too narrow; increase the bind radius.

If the mesh tears or stretches oddly → vertices are getting weight
from the wrong joints; recompute with a smaller bind radius, or
adjust by hand via [Paint weights](paint-weights.md).

## Bind options

`Rigging > Bind Skin to Selected Mesh > Options…` exposes:

| Option | Default | Notes |
|---|---|---|
| Bind radius | auto | How far a joint's influence reaches; auto uses the joint segment length |
| Max weights | 4 | Per-vertex weight slots |
| Falloff | inverse_distance_squared | Distance metric |
| Heat map | off | Visualize per-vertex weight count |

Heat map renders the mesh tinted by how many joints influence
each vertex: blue (1 influence, rigid) → red (8 influences, very
smooth). Useful for finding spots that need painting.

## Apply Skin Deform

`Rigging > Apply Skin Deform (from current joint pose)` is
destructive: it bakes the current deformed positions into the
mesh's base vertices and removes the bind. Use to:

- Lock in a pose as the new rest position.
- Free the per-frame compute when the deformation is final.

This is the opposite of `Reset Bind Pose`; both are irreversible
(short of undo).

## Reset Bind Pose

`Rigging > Reset Bind Pose` returns every joint to the pose it was
in when you ran Bind Skin. Useful when you have moved joints
during animation and want to get back to the rest pose without
manually keying every joint to zero.

## Unbinding

`Rigging > Unbind Skin` removes the binding. The mesh stays where
it is (in whatever deformed state it was at the time); joints
revert to free transforms.

## See also

- [Joint chains](joint-chains.md): create the chain you bind to.
- [Paint weights](paint-weights.md): fine-tune per-vertex weights.
- [IK 2-bone](ik-2-bone.md): pose the chain to drive deformation.
