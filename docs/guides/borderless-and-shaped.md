# Borderless and shaped windows

Borderless transparent windows are Elysium's signature. This guide
explains the model, the API, and the per-OS quirks.

## The model

An OS window in Elysium has two independent "shapes":

| Shape | What it controls |
|---|---|
| **Outer bounds** | The rectangular region the OS allocates for your window |
| **Hit region** | The SVG path (inside the bounds) that actually receives input |

The outer bounds is what the OS knows about; the hit region is
what the user perceives. Clicks inside the bounds but outside the
hit region "fall through" to whatever is underneath.

## Make a borderless window

```python
import elysium as ely

app = ely.App(title="…", identifier="dev.example.app")
window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 360),
)
app.run()
```

You get a 360x360 rectangular transparent window with no chrome.

## Add a hit region

```python
ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"
window.set_hit_test_path(ELLIPSE)
```

SVG path data is the lingua franca. Now only clicks inside the
ellipse register; clicks in the corners pass through.

## Common shapes

| Shape | Path (for a 360 x 360 bounds) |
|---|---|
| Ellipse | `M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z` |
| Rounded rect (radius 28) | `M 28,0 L 332,0 A 28,28 0 0 1 360,28 L 360,332 A 28,28 0 0 1 332,360 L 28,360 A 28,28 0 0 1 0,332 L 0,28 A 28,28 0 0 1 28,0 Z` |
| Star (5-point) | (composed via path-boolean Union of two pentagons) |
| Butterfly | (authored in the Designer, exported via `Window > Set Shape From Selection`) |

For complex shapes, author in the Designer and export.

## Draggable without a title bar

By default the entire hit region is draggable: pressing and
dragging anywhere inside it moves the window. Refine the
behavior per-placement:

```python
window.set_drag_threshold(4)            # px before drag starts
window.btn_play.drag_window = False     # this control isn't a drag handle
```

The framework distinguishes click vs drag via the threshold. Set
it high to make a touch-screen friendly window; low for a snappy
desktop one.

## Per-OS quirks

### macOS

- Vibrancy (translucent backdrop) is opt-in:
  `window.set_blur_behind(True, material=12)`. Material 12 is HUD,
  3 is title bar, 21 is under-window.
- Shadow is on by default; disable with `set_has_shadow(False)`.
- Borderless windows pick up Mission Control / Spaces behavior
  from the parent process; tag the App appropriately if you need
  pinned-window behavior.

### Windows

- DWM extends the shadow to the rectangular bounds, not the hit
  region. For a tight shadow matching the shape, disable DWM
  shadow with `set_has_shadow(False)` and paint your own.
- Click-through on transparent regions works out of the box.
- The taskbar entry shows whatever you put in
  `App(title="…")`; pick a name that reads in 16-char Alt+Tab.

### Linux (Wayland)

- Hit-test path is supported on KDE, GNOME 44+, and Sway.
- Window-move uses the compositor's xdg-toplevel `move`
  protocol; falls back gracefully on compositors that don't
  expose it.
- Transparency: requires a compositor (composited by default on
  every modern desktop).

### Linux (X11)

- Older compositors may not honor the hit-test path strictly;
  the framework warns at runtime if it detects this.

## Multi-monitor

Cross-DPI moves recompute the surface automatically. A 2x
Retina window dragged to a 1x external monitor scales smoothly
without re-loading the skin.

## Verification

A quick mental checklist for "is this borderless / shaped right":

1. Drag a corner over a file on your desktop: does the file
   receive the click?
2. Move the window between monitors: does the shape stay sharp?
3. Hold Alt+Tab: does the entry show the right title?
4. Quit and relaunch: does the window appear at the right
   position?

For position persistence see [Recipes: persist window
geometry](../recipes/21-persist-window-geometry.md).

## See also

- [Windowing](windowing.md): multiple windows, modals,
  always-on-top.
- [Recipes: open a borderless window](../recipes/01-open-borderless-window.md)
- [Recipes: star-shaped hit region](../recipes/02-star-shaped-hit-region.md)
- [Architecture](architecture.md): where windows sit in the
  data flow.
