# Rigging

Rigging assembles the bones, weights, and constraints that let an
animator pose geometry. The Designer's rigging is small but covers
the common skin-and-bones pipeline: joint chains, skin binding,
2-bone IK, painted weights, and constraints.

## When you need a rig

Rig when:

- A character or creature placement needs articulated motion (a
  butterfly's wings rotating around their hinge, a flag waving
  from a pole).
- Animating raw vertex positions would be impractical.
- You want pose-able controls instead of direct attribute keys.

Skip rigging for:

- Simple Bend / Twist / Sine motion (use [deformers](../deformers/index.md)).
- Whole-placement transforms (translate / rotate / scale alone).

## The Rigging menu set

Press F3 to switch to Rigging. The menu bar gains:

| Menu | Common entries |
|---|---|
| Skeleton | Create Joint Chain (3 / 5), Insert Single Joint, Orient Joint |
| Skin | Bind Skin to Selected Mesh, Apply Skin Deform |
| Solve | Solve 2-Bone IK on Selected Chain, Pole Vector Constraint |
| Paint | Paint Weights submenu |
| Constraints | Parent, Point, Orient, Aim, Scale, Clear |

These are reachable from the top-level **Rigging** menu in any
set; the menu-set switch just promotes them to the most prominent
positions.

## A minimum rig

1. [Create a joint chain](joint-chains.md) of 3 joints along the
   mesh's shoulder→elbow→wrist line.
2. [Bind skin](skin-binding.md) to the mesh.
3. [Set up 2-bone IK](ik-2-bone.md) between the wrist and the
   shoulder.
4. Move the IK target placement to pose the arm.

Five clicks for a posable arm. Same workflow scales to a
butterfly's left wing or a robotic forelimb.

## Per-vertex weighting

After Bind Skin, every vertex carries one or more joint weights
that determine how it follows the joints. The framework's default
is "rigid" (each vertex follows the closest joint with full
weight); for smooth deformations use
[Paint weights](paint-weights.md) to fine-tune.

## Constraints

Constraints couple one placement's transform to another's:

- **Parent**: child inherits all transforms.
- **Point**: child inherits translation only.
- **Orient**: child inherits rotation only.
- **Aim**: child rotates so its forward axis points at the target.
- **Scale**: child inherits scale only.

See [Constraints](constraints.md).

## v1 limitations

- IK is 2-bone only; FK chains of any length work, but IK
  multi-bone solvers (Spine IK, Spline IK) are roadmap.
- No HumanIK / full skeleton template ships in v1.
- Blendshape rigs are in v1 via `rig.shape_editor` (a basic
  editor); advanced blendshape workflows are roadmap.

## See also

- [Joint chains](joint-chains.md)
- [Skin binding](skin-binding.md)
- [IK 2-bone](ik-2-bone.md)
- [Paint weights](paint-weights.md)
- [Constraints](constraints.md)
