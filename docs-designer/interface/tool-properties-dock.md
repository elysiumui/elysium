# Tool Properties dock

The Tool Properties dock is the thin row docked under the View
Panel (above the time slider). It shows options for the **currently
active** toolbox tool. Its contents change as you switch tools.

![Tool Properties dock showing the Brush tool's size, opacity, and engine selector](../assets/interface-tool-properties-dock.png)

## Why a dedicated dock?

The Channel Box edits the **selection**. The Properties pane edits
the **active placement** in depth. The Tool Properties dock edits
the **active tool's configuration**: size of the brush nib, snap
distance for the Move tool, stroke smoothness for the Pen, etc.
Each surface stays focused.

## Per-tool contents

The dock changes per tool. The most common configurations:

### Select / Lasso / Paint Select

- Selection mode: Replace / Add / Subtract / Intersect.
- Selection through obscured: on / off.

### Move

- Snap distance (pixels).
- Snap kind: Grid / Vertex / Pivot / Edge.
- Axis lock visualization on / off.

### Rotate

- Snap angle (degrees).
- Axis (XYZ in 3D; Z-only in 2D).
- Local vs World gimbal.

### Scale

- Uniform vs per-axis.
- From pivot vs from bounding box center.

### Brush / Erase

The richest dock. See [Brush > Quick start](../brush/quick-start.md):

- Engine dropdown (6 engines).
- Preset palette (30 built-ins + your saved presets).
- Size slider (with pressure curve preview).
- Opacity slider (with pressure curve preview).
- Color picker (with eyedropper).
- Spacing.
- Texture overlay strength.
- Smoothing.

### Pen / Bezier

- Smoothing.
- Pressure → width mapping (on / off).
- Auto-close path.

### Eyedrop

- Sample size (1px / 3x3 / 5x5).
- Tileable mode (samples a square and tiles it).
- Add to brush palette on pick.

### Landmark

- Pair count remaining (typically 6 for butterflies).
- Snap to nearest vertex on the model side.

## Pin / unpin

The dock's pin button keeps its current width visible even when
switching to a tool that needs less room. Useful when juggling
between Brush and Move during painting.

## Hide

`Window > Toggle Tool Properties Dock` hides it. Most users keep it
on for painting and brushwork; collapse it when working on pure
modeling so the View Panel takes the full height.
