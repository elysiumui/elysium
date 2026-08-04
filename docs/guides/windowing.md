# Windowing

Multi-window apps, modals, popovers, always-on-top, edge snapping,
multi-monitor, DPI. The [borderless-and-shaped](borderless-and-shaped.md)
guide covers what makes one window look right; this guide covers
having more than one.

## Multiple windows

```python
import elysium as ely

app = ely.App(title="My App", identifier="dev.example.app")
main = app.window(transparent=True, title_bar=False, initial_size=(720, 480))
side = app.window(transparent=True, title_bar=False, initial_size=(280, 480))
main.load_skin("main.esk/")
side.load_skin("side.esk/")
app.run()
```

Each `app.window(...)` returns a fresh window with its own Skin,
Canvas, hook proxy, and event surface. Signals shared between them
just work: an effect can read a signal in one window's handler
and mutate a placement in another window's skin.

## Modal windows

A modal is a window that takes focus and (typically) blocks input
to its parent until dismissed:

```python
dialog = app.window(
    transparent=True, title_bar=False,
    initial_size=(420, 220),
    parent=main,          # link to the parent
    modal=True,           # block input to parent
)
dialog.load_skin("confirm.esk/")
```

While `modal=True`, the parent window's hit region rejects clicks
until the modal closes. The modal's own close (close button click
handler or `dialog.close()`) restores the parent's input.

## Always-on-top

```python
window.set_window_level(level=3)  # 0 = normal, 3 = floating, 5 = screen saver
```

Levels map to OS-specific concepts:

| Level | macOS | Windows | Linux |
|---|---|---|---|
| 0 | normal | normal | normal |
| 1 | floating | TOPMOST | x11/wlr level=top |
| 3 | dock | TOPMOST + stay on top | level=top + pinned |
| 5 | screen saver | TOPMOST + screen saver | best-effort |

Use level 3 for status widgets, palettes, HUDs.

## Edge snapping

```python
window.set_edge_snap(distance=12)   # px from any screen edge to trigger
```

When the user drags the window within `distance` pixels of any
edge of the active monitor, it snaps to the edge on release. Per-
edge enable/disable via the dict variant:

```python
window.set_edge_snap(distance={"left": 12, "right": 12, "top": 0, "bottom": 12})
```

## Position and size

```python
window.set_outer_position(x, y)        # in monitor coordinates
window.resize(width, height)
window.cursor_position                  # (x, y) relative to window
```

For persistence between launches see
[Recipes: persist window geometry](../recipes/21-persist-window-geometry.md).

## Multi-monitor and display fitting

A window is sized against the display it opens on. `initial_size` is a
**request**: it is clamped to what the screen can actually show and the window
is centred there, so a window never opens larger than the display it lands on.
This matters most for borderless windows — one that opens taller than the
screen has no title bar to drag back into view.

```python
# On a 1920x1080 display this is honoured exactly. At 150% scaling
# (1280x720 logical) it is reduced to fit, rather than overflowing.
win = app.window(initial_size=(1200, 800))
```

Pass `fit_to_display=False` to opt out — only useful when you deliberately
want a window bigger than the screen, e.g. for offscreen capture.

Read the display back from the window:

```python
win.scale_factor          # 1.0 at 100%, 2.0 Retina, 1.5 at Windows 150%
win.monitor               # dict, or None in a headless session
```

`monitor` reports **logical** pixels — the same units as `surface_size` and
`outer_position`, and the units layout code uses:

| key | meaning |
| --- | --- |
| `name` | OS display name |
| `x`, `y`, `width`, `height` | the full display, in the virtual desktop |
| `work_x`, `work_y`, `work_width`, `work_height` | the area a window should stay inside — reserves room for the menu bar / taskbar / dock |
| `scale_factor` | that display's scaling |
| `is_primary` | whether it is the primary display |

To place a window yourself — e.g. top-left of its display's usable area:

```python
m = win.monitor
if m:
    win.set_outer_position(m["work_x"], m["work_y"])
```

Both values track the display the window is *currently* on, so dragging it to
a monitor with different scaling updates them.

!!! note "Work area is an approximation"
    winit exposes no work-area API, so `work_*` reserves a fixed fraction of
    the display rather than querying the real menu-bar/taskbar rectangle. It is
    deliberately conservative: a window placed inside it is always fully
    visible, but it may leave a little more room than strictly necessary.

## Popovers and dropdowns

The `Popover` component handles small-window-anchored-to-another-
placement scenarios (settings popover in the Pomodoro tutorial,
context menus, tooltips). It is not a separate OS window; it lives
inside the parent window's skin.

For pop-up windows that **are** separate OS windows (e.g. browser-
like menubar dropdowns), use a regular `app.window(...)` with
`level=3` and a small initial_size, and position with
`set_outer_position`.

## Closing

```python
window.close()      # close one window
app.quit()          # shut down the whole app
```

`close()` on the last open window does not automatically quit the
app: the App keeps running until you call `app.quit()`. This
matches macOS conventions; on Windows / Linux you may want to
auto-quit when the last window closes:

```python
@main.on("window.closed")
def maybe_quit(event):
    if not app.has_open_windows():
        app.quit()
```

## Per-window settings

A handful of properties are per-window, not per-app:

- `set_blur_behind(True, material=12)` (macOS)
- `set_has_shadow(True/False)`
- `set_ignores_mouse(True/False)`: passes every event through
- `set_window_level(level)`

The full reference is on the [Window API page](../api/elysium.md).

## See also

- [Borderless and shaped](borderless-and-shaped.md)
- [Architecture](architecture.md): where Windows sit in the
  model.
- [Recipes: open a second window](../recipes/06-second-window-from-button.md)
- [Recipes: modal with return value](../recipes/07-modal-returns-value.md)
