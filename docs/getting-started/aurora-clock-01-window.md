# Aurora Clock 1. Open a borderless ellipse window

Time: 6 minutes.

## What you are building

Five short chapters take you from an empty file to a borderless,
transparent, ellipse-shaped desktop clock with a sweeping
second-hand arc, a breathing aurora glow, and a theme-toggle button.

This chapter ships the window: borderless, transparent, no title
bar, and clipped to an ellipse so clicks outside the ellipse pass
through to whatever is underneath.

![Aurora Clock chapter 1 result: an empty ellipse outline floating on the desktop](../assets/aurora-clock-ch1.png)

## Prerequisites

- Elysium installed: `pip install elysium-ui` (or `uv pip install elysium-ui`).
- Python 3.10 or newer.
- Verify with `python -c "import elysium; print(elysium.__version__)"`.

If the import errors with "native extension not built", see
[troubleshooting](troubleshooting.md).

## A minimum borderless window

Create `aurora_clock.py` with the following code:

```python
import elysium as ely

app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")

window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 360),
)

app.run()
```

Run it:

```sh
python aurora_clock.py
```

A 360 by 360 transparent window appears in the center of your
display. There is no title bar and no system chrome. Quit by sending
SIGINT (Ctrl+C in the terminal that launched it).

The window is currently rectangular: clicks anywhere in the 360x360
area are captured by the window. Next we shape it.

## Clip to an ellipse

Elysium uses SVG path data to describe non-rectangular windows. The
`set_hit_test_path` method tells the OS which pixels inside the
window count as "real": clicks on those pixels reach the window,
clicks elsewhere fall through to the desktop or the app beneath.

An ellipse fitting our 360x360 window is two SVG arcs:

```
M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z
```

Update `aurora_clock.py`:

```python
import elysium as ely

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"

app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")

window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 360),
)
window.set_hit_test_path(ELLIPSE)

app.run()
```

Run again. The window is still a 360x360 rectangle for the OS, but
clicks outside the ellipse pass through. Test by clicking the corner
of the window over a file on your desktop: the file gets the click,
not the clock.

## Make the window draggable

Borderless windows have nowhere to grab. Elysium exposes a
"window-drag" intent: when set on a hit-test region, dragging that
region with the primary mouse button moves the window the same way
dragging a title bar would.

For now the entire ellipse is draggable by default since we have no
inner content yet. We will refine this in chapter 5 once the clock
face appears.

## macOS, Windows, Linux notes

- **macOS**: borderless windows lose vibrancy by default. We turn
  that back on later with `window.set_blur_behind(True)`.
- **Windows**: DWM extends the shadow under the rectangular bounds.
  The `set_has_shadow(False)` call in chapter 5 trims that to the
  ellipse.
- **Linux (Wayland)**: hit-test paths work; window-drag relies on
  the compositor's `move` protocol. KDE, GNOME 44+, and Sway all
  honor it.

## Checkpoint

You should see:

- A 360x360 transparent window with no chrome.
- An invisible ellipse hit region: clicks inside ellipse hit the
  window, clicks in corners pass through.
- Clean exit on Ctrl+C.

Continue to [chapter 2: draw the clock face](aurora-clock-02-clockface.md).
