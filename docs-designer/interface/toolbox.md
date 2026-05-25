# Toolbox

The vertical strip along the left edge of the window hosts 17
tools, grouped into three accordion sections: **Controls**, **Tools**,
**Shapes**. Click any tool to activate it; tools are also bound to
single-key shortcuts inspired by Maya's QWERTY conventions.

## Controls

| Tool | Hotkey | Purpose |
|---|---|---|
| Select | Q | Pick a placement; drag to box-select |
| Lasso Select | Shift+Q | Freeform drag selection region |
| Paint Select | Ctrl+Shift+Q | Brush-painted selection over many placements |
| Hand | (hold Space) | Pan the canvas without changing selection |
| Move | W | Translate selection |
| Rotate | E | Rotate selection (yaw / pitch / roll on Mesh3D) |
| Scale | R | Scale selection around its pivot |
| Pivot Edit | D-drag or Insert | Move a placement's pivot point |
| Zoom | (mouse wheel) | Magnifier; click-drag, Alt-click for zoom out |

## Tools

| Tool | Hotkey | Purpose |
|---|---|---|
| Brush | B | Paint on the selected placement's mask |
| Erase | Shift+B | Erase from the same mask |
| Fill | G | Flood fill / set `color_fill` on a placement |
| Eyedrop | I | Sample a tileable swatch from an Image and add to brush palette |
| Landmark | L | Pair source ↔ target points for TPS texture transfer |
| Camera Distance | (vertical drag) | Mesh3D `mesh_dist` adjustment |

## Shapes

| Tool | Hotkey | Purpose |
|---|---|---|
| Pen | P | Freehand path: drag to record |
| Bezier | Shift+P | Click-to-add anchors with drag handles |
| Rectangle | M | Drag a rectangle placement |
| Ellipse | F | Drag an ellipse placement |
| Line | / | Drag a line placement |
| Polygon | Shift+M | Click-to-add corner points; double-click to close |
| Region | Ctrl+M | Drag a free region placement (lasso shape) |

## Active-tool feedback

The currently-active tool's icon highlights with the theme accent
color. The cursor changes to match (move arrows, crosshair, brush
nib). The [Tool Properties dock](tool-properties-dock.md) at the
bottom of the screen shows the tool's options live.

## Customizing the toolbox

`File > Preferences > Toolbox` lets you:

- Reorder tools within sections.
- Hide tools you do not use.
- Add custom-script tools (developer feature).

Customizations save per-user.

## Modifier conventions

A few modifiers are consistent across every tool:

| Modifier | Effect |
|---|---|
| Shift | Add to selection / constrain to axis on move / lock aspect on scale |
| Alt | Remove from selection / orbit camera (with Move) / sample on Brush |
| Ctrl | Smaller increment / open context menu / toggle snap on Move |
| Space (held) | Switch to Hand temporarily; release returns to previous tool |
| Esc | Cancel the current tool's in-progress drag |

## Tablet and pen

When the Designer detects a tablet, the Brush and Erase tools route
pressure to **size** and tilt to **rotation** by default. The
[Brush > Touch and dynamics](../brush/touch-and-dynamics.md) page
covers the full mapping.
