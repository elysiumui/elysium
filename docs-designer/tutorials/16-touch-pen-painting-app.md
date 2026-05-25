# Touch and pen painting app

Time: 60 minutes. Difficulty: Advanced.

Author a full painting application as a single `.esk`: canvas,
brush picker, color swatch, undo / redo, save as PNG. Ships with
the user's tablet pressure / tilt mapped to the painted strokes.

## Prerequisites

- Designer installed.
- A pen tablet (Wacom, Apple Pencil, Surface Pen, Huion, XP-Pen).
- Familiarity with the [Brush quick start](../brush/quick-start.md).

## The window

`File > New Skin`, 1024 x 720. Default rectangular window with
a title bar: this is a real app, not a widget. `Window > Toggle
Title Bar` if you want chrome-less.

## Layout

Author with the three columns common in painting apps:

| Region | Size | Contents |
|---|---|---|
| Left toolbox | 80 wide | Brush, Erase, Fill, Eyedrop buttons |
| Center canvas | 700 x 700 | The paint surface |
| Right panel | 240 wide | Brush size / opacity sliders, color picker, layer list |

Use the Designer's Row + Col + Stack containers (or hand-place
each placement).

## The canvas

The center is one big `image` placement with a writable
`PaintMask`. Set `kind = "image"`, `width = height = 700`,
`paint_mask = true`.

The framework's brush system writes strokes into this mask layer
when the Brush tool is active.

## Wire the toolbox buttons

Each button switches the active tool:

```python
@window.on("toolbox_brush.click")
def use_brush(event):
    api.set_tool("brush")
```

(`api.set_tool` is the Designer's tool-switch API; in your runtime
app, simulate via the framework's Tool registry.)

## Brush size + opacity sliders

Slider bindings in the document:

```json
{ "id": "size_slider", "kind": "slider",
  "x": 16, "y": 64, "width": 200, "height": 24,
  "min": 1, "max": 200, "value": 24, "label": "Size" }
```

Tap the slider; the brush size updates live. Same for opacity.

## Color picker

Drop a `kind: "color_picker"` placement with `width: 200, height:
200`. The picker exposes a `change` hook with the new color.

## Layers

The user wants per-layer painting. Use the framework's per-
placement layer model:

- "Layer 1" is the canvas's default layer.
- "Add Layer" button creates a new transparent layer on top.
- Toggle visibility and reorder in the right-panel layer list.

For v1 simplicity, support 4 layers; expand later.

## Undo / redo

The framework's stroke history is per-placement. Bind:

```python
@window.on("undo.click")
def undo(event):
    window.canvas.undo_stroke()

@window.on("redo.click")
def redo(event):
    window.canvas.redo_stroke()
```

`Cmd+Z` / `Ctrl+Z` are handled by the framework automatically
when the canvas has focus.

## Save as PNG

```python
@window.on("save.click")
def save(event):
    window.canvas.export_png("/path/to/painting.png")
```

The export captures every visible layer composited into one PNG.

## Tablet calibration

First-run flow: `Preferences > Tablet > Calibrate Pressure`.
Three test strokes; the Designer remaps pressure to your hand's
typical range.

## Test

`Run > Preview Skin`. Paint with the pen. The strokes should
respond to pressure (size + opacity) and tilt (Bristle / Pattern
engines).

## Ship

```sh
elysium pack painter.py --name "Painter" \
  --identifier dev.example.painter --include painter.esk
```

## What you exercised

- Three-column app layout in the Designer.
- `kind: "image"` with `paint_mask`.
- Brush + Erase + Fill + Eyedrop tool integration.
- Slider + color_picker components.
- Layer list.
- Per-placement stroke history (undo / redo).
- `export_png` for saving.

## See also

- [Brush > Quick start](../brush/quick-start.md)
- [Brush > Touch and dynamics](../brush/touch-and-dynamics.md)
- [Touch and pen input reference](../reference/touch-and-pen-input.md)
