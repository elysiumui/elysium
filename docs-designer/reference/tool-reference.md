# Tool reference

Every toolbox tool with its hotkey, action id, and one-line
purpose. Use as a quick lookup; the [Toolbox](../interface/toolbox.md)
page covers each in context.

## Controls

| Tool | Hotkey | Action id | Purpose |
|---|---|---|---|
| Select | Q | `tool.select` | Pick a placement; drag to box-select |
| Lasso Select | Shift+Q | `tool.lasso_select` | Freeform drag selection |
| Paint Select | Ctrl+Shift+Q | `tool.paint_select` | Brush-painted selection |
| Hand | Space (hold) | `tool.hand` | Pan without changing selection |
| Move | W | `tool.move` | Translate selection |
| Rotate | E | `tool.rotate` | Rotate selection |
| Scale | R | `tool.scale` | Scale around pivot |
| Pivot Edit | D-drag / Insert | `tool.pivot_edit` | Move a placement's pivot |
| Zoom | (wheel) | `tool.zoom` | Magnifier |

## Tools (paint family)

| Tool | Hotkey | Action id | Purpose |
|---|---|---|---|
| Brush | B | `tool.brush` | Paint into a mask |
| Erase | Shift+B | `tool.erase` | Erase from a mask |
| Fill | G | `tool.fill` | Flood-fill a region |
| Eyedrop | I | `tool.eyedrop` | Sample a swatch |
| Landmark | L | `tool.landmark` | Pair source ↔ target points for TPS transfer |
| Camera Distance | (vertical drag) | `tool.camera_dist` | Mesh3D `mesh_dist` |

## Shapes

| Tool | Hotkey | Action id | Purpose |
|---|---|---|---|
| Pen | P | `tool.pen` | Freehand path |
| Bezier | Shift+P | `tool.bezier` | Click-anchor + drag-handle path |
| Rectangle | M | `tool.rect` | Drag a rectangle |
| Ellipse | F | `tool.ellipse` | Drag an ellipse |
| Line | / | `tool.line` | Drag a line |
| Polygon | Shift+M | `tool.polygon` | Click corners; double-click to close |
| Region | Ctrl+M | `tool.region` | Drag a free region |

## Programmatic switching

```python
from elysium_designer import api
api.set_tool("brush")
api.tool_property("size_px", 24)
```

The same action ids appear in the
[Aether tool reference](aether-tool-reference.md) under
`tool.*`.

## See also

- [Toolbox](../interface/toolbox.md)
- [Keyboard shortcuts](keyboard-shortcuts.md)
