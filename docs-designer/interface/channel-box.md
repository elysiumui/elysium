# Channel Box

The Channel Box lives in the middle of the right column, between
the Project Explorer and the Properties pane. It is the fast-access
editor for the numeric properties of whatever placement is selected.

![Channel Box showing translateXYZ, rotateZ, and texture_path fields for a Mesh3D selection](../assets/interface-channel-box.png)

## What it shows

Three groups, top to bottom:

| Group | Fields | Notes |
|---|---|---|
| Transform | translateX/Y/Z, rotateX/Y/Z, scaleX/Y/Z | Per-axis numeric edit; click and type, or drag to scrub |
| Visibility | visibility, render_mask | Eye icon toggles draw; mask is for render-time culling |
| Type-specific | varies by placement kind | Mesh3D adds `mesh_dist`, `texture_path`, `material`; Image adds `image_path`; Curve adds `closed`, `width`; Light adds `intensity`, `color`, `falloff` |

Multi-select shows fields that all selected placements share. Edits
apply to every selected placement.

## Keyable channels

Each row's leftmost dot is a **keyable indicator**. Click it to
toggle:

- Filled dot: channel is keyable; setting a value at the current
  frame creates a key.
- Hollow dot: channel is not keyable; values do not animate.
- Locked: a small lock icon appears; the field is read-only.

The Animate menu's `Set Key` and `Toggle Auto Key` honor the
keyable state.

## Scrubbing values

Drag horizontally on a numeric field to nudge the value live. Speed
modifiers:

| Modifier | Effect |
|---|---|
| Shift + drag | 10x speed |
| Ctrl + drag | 0.1x speed |
| Cmd / Win + drag | Snap to whole integers |
| Right-click value | Reset to default; copy expression; lock / unlock |

## Expressions

Right-click any numeric field > **Set Expression…** opens a small
formula editor. You can wire one channel to another with simple
math:

```
left_wing.rotateZ = -right_wing.rotateZ
```

Expressions evaluate every frame and replace direct values. Useful
for mirrors, drivers, and ratchets.

## Hide / show channels

Right-click a field > **Hide** to remove it from the Channel Box
without locking it (use Lock for that). Hidden channels still
animate; this is purely a UI declutter. `Window > Reset Channel
Box` brings everything back.

## Compared to the Properties pane

The Channel Box gives you the most-edited numeric properties at a
glance and supports keying / expressions. The
[Properties pane](properties-pane.md) below shows every property  
including colors, paths, enums, and grouped sub-properties: in a
fuller editor. Most authoring time lives in the Channel Box; the
Properties pane is for the long tail.
