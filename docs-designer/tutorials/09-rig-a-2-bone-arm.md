# Rig a 2-bone arm

Time: 40 minutes. Difficulty: Intermediate.

Take a simple arm mesh and rig it with a 3-joint chain + 2-bone
IK, then paint weights for clean deformation. The "first real rig"
tutorial.

## Prerequisites

- An arm mesh (`.obj` or `.gltf`). Any rigged or unrigged arm
  works; the [examples/butterfly](https://github.com/elysiumui/elysium/tree/main/examples)
  repo has one.
- Finished the [Blue Morpho tutorial](../getting-started/butterfly/index.md).

## Import the mesh

`File > Import > 3D Model…` and pick your arm. `View > Frame All`
(`A`) to center it.

## Create the joint chain

1. Press F3 (Rigging menu set).
2. `Rigging > Create Joint Chain (3)`. Three joints appear along
   the world Y axis.
3. Switch to Move tool (`W`) and drag each joint into position:
   - **shoulder** at the arm's shoulder.
   - **elbow** at the elbow bend.
   - **wrist** at the wrist.
4. Right-click each joint > **Rename** to give them clear names.

## Orient the joints

`Rigging > Orient Joint > All in Chain` aligns each joint's local
axes so X points toward its child.

## Bind skin

1. Select the arm mesh.
2. Shift-click the shoulder (chain root).
3. `Rigging > Bind Skin to Selected Mesh`.

The Designer assigns initial weights by distance.

## Add 2-bone IK

1. Select the wrist (chain tip).
2. `Rigging > Solve 2-Bone IK on Selected Chain`.

An IK handle placement appears at the wrist. Move it; the chain
follows.

## Paint weights

The auto-bind is approximate. Refine:

1. Select the elbow joint.
2. `Rigging > Paint Weights > Set Active Joint (from selection)`.
3. `B` to activate Brush; the mesh tints by current weight.
4. Paint elbow weight onto the upper-forearm region (vertices
   that should bend with the elbow).
5. Repeat for the wrist with the lower-forearm and hand.

`Rigging > Paint Weights > Smooth Selected` smooths a hard
boundary between two joints' influence.

## Animate a wave

1. F4 (Animation menu set).
2. Frame 1: IK handle at neutral. Press `S` to set a key.
3. Frame 12: drag IK handle up and right (the arm raises). `S`.
4. Frame 24: back to neutral. `S`.

`Space` to play. The arm waves.

## Cleanup

`G` to open Graph Editor. Select all keys, click **Auto Tangent**
in the toolbar. Curves soften.

## Export

`File > Export > .esk Bundle`. The bundle ships the rig + a
24-frame wave animation track.

## What you exercised

- Joint chain creation + orient.
- Skin bind.
- 2-bone IK solver.
- Paint weights.
- Keyframing on an IK handle.
- Graph Editor cleanup.

## See also

- [Rigging index](../rigging/index.md)
- [Paint weights](../rigging/paint-weights.md)
- [Animation index](../animation/index.md)
