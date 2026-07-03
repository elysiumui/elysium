# Joint chains

A joint chain is the skeleton that drives a skinned mesh. The
Designer offers two quick-create entries (3-joint and 5-joint
chains) plus an Insert Joint action for fine-grained edits.

## Create a 3-joint chain

`Rigging > Create Joint Chain (3)` drops three connected joints
into the scene. The Designer positions them along the world Y axis
by default; drag them into place after.

A 3-joint chain is the right starting point for:

- An arm (shoulder → elbow → wrist).
- A finger (proximal → middle → distal phalanx).
- A leg (hip → knee → ankle).
- A butterfly wing (root → mid → tip).

## Create a 5-joint chain

`Rigging > Create Joint Chain (5)` adds two extra joints. Right for:

- A spine (5 joints from pelvis to neck).
- A tail (5 joints from base to tip).
- A snake-like creature.

## Insert a single joint

`Rigging > Insert Single Joint` drops one unparented joint at the
cursor. Useful when you need to add an extra joint mid-chain, or
when starting a chain from a non-axis position.

To wire it into an existing chain: select the new joint, Shift-
click the intended parent, choose `Edit > Parent`.

## Joint placements

Joints are regular placements with `kind = "joint"`. They render
in the View Panel as small spheres connected by lines. The
Properties pane exposes:

| Property | Effect |
|---|---|
| name | Display name (e.g. "shoulder_L") |
| translateXYZ | Position |
| rotateXYZ | Local rotation |
| jointOrient | Rest-pose offset (typically set once via Orient Joint) |
| radius | Sphere display size |
| parent | Parent joint placement id |
| segment_length | (computed from parent → this distance) |

## Positioning

With the Move tool (`W`) active, drag each joint to the desired
position. Holding Ctrl snaps to grid; holding Shift constrains to
the parent-axis line so you can extend a chain without bending.

For symmetric setups (left arm + right arm), author one side and
mirror with `Rigging > Mirror Selected Chain`. The mirror axis is
configurable in the Properties pane (default X = 0).

## Orient

`Rigging > Orient Joint…` aligns each joint's local axes so that:

- X points toward the child joint.
- Y is "up" relative to the parent's plane.
- Z is the cross product.

A well-oriented chain makes IK behave predictably and lets you
hand-rotate single channels (`rotateZ`) to bend the chain.

Auto-orient on a fresh chain via the menu; revisit if you drag a
joint far from its initial position.

## Naming

Joint names matter for animation: the [Code Link](../code-link/index.md)
bridge uses joint names as channel paths
(`window.butterfly.left_wing.rotateZ`). Use clear, consistent names:

- Body sides as suffixes: `_L`, `_R`, `_C` (center).
- Hierarchy as nested paths under the mesh: `butterfly.shoulder_L`.

Right-click a joint in the [Project Explorer](../interface/project-explorer.md)
> **Rename** to update.

## Visualizing

`View > Show Joints` toggles the joint overlay. Useful when the
joints clutter the viewport during painting / texturing passes.

## See also

- [Skin binding](skin-binding.md): connect the chain to the mesh.
- [IK 2-bone](ik-2-bone.md): pose the chain with a target.
- [Constraints](constraints.md): couple joints to other
  placements.
