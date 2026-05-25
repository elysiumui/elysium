# Stylized Music Player 6. Drag and hit-test

Time: 7 minutes.

## What we are adding

Refined drag behavior: the empty parts of the faceplate (the
asymmetric blob, but not the controls) drag the window. Clicking on
a button does not start a drag. We also exclude the scrubber from
drag so dragging the thumb seeks instead of moving the window.

![Stylized Music Player chapter 6: dragging the empty area moves the window; dragging the scrubber thumb seeks; clicking buttons does not move the window](../assets/stylized-music-ch6.gif)

## Two kinds of hit regions

Two SVG paths now matter:

- **Window hit-test path** (`window.set_hit_test_path(FACEPLATE)`):
  decides which OS-level pixels even reach the window. We set this
  in chapter 1.
- **Per-placement drag intent**: tells the framework that pressing
  this specific placement should drag the window rather than treat
  the press as a click.

A click target's drag intent is opt-in. We turned it on for
`faceplate_back` in chapter 1; now we explicitly disable it on every
interactive control.

## Disable drag on interactive controls

In `player.py`, right after `window.load_skin(...)`:

```python
for placement_id in (
    "btn_prev", "btn_play", "btn_next",
    "scrub_track", "scrub_thumb",
    "eq_canvas",
    "art_card",
):
    setattr(window[placement_id], "drag_window", False)
```

Now the orb buttons, scrubber, equalizer, and album art each
receive their own click and drag events without moving the window.

## Refine the drag dead-zone

A common annoyance with shaped windows is starting a drag accidentally
when you meant to click. The framework supports a per-window
"drag threshold": the cursor must move at least N pixels after press
before a drag begins.

```python
window.set_drag_threshold(4)  # pixels
```

A 4-pixel threshold is small enough to feel responsive but large
enough to ignore the hand jitter that turns clicks into drags.

## Visual feedback while dragging

Bind to `window.drag.start` and `window.drag.end` (built-in hooks)
to show a faint outline while dragging:

```python
@window.on("window.drag.start")
def drag_start(event):
    window.faceplate_back.stroke = "#f0abfcff"
    window.faceplate_back.stroke_width = 2.5


@window.on("window.drag.end")
def drag_end(event):
    window.faceplate_back.stroke = "#3b2a78ff"
    window.faceplate_back.stroke_width = 1.5
```

The faceplate's outline lights pink during the drag, so the user
can see exactly what they have "grabbed".

## Snap to screen edges (optional)

Borderless apps often snap to screen edges for tidiness. The
framework exposes a snap distance you can set per-window:

```python
window.set_edge_snap(distance=12)  # snap when within 12px of any screen edge
```

Drag the player near the right edge of your monitor: it snaps to
within a pixel of the bezel when you release. Useful for tucking the
player out of the way.

## Multi-monitor

When the user drags the window to a second monitor with a different
DPI, the framework re-scales the surface and recomputes the hit-test
path. You do not need to handle this; the test is to drag from a
2x Retina display to a 1x external monitor and back, and verify the
faceplate stays sharp on both.

## Checkpoint

- Dragging an empty area of the faceplate moves the window.
- Clicking an orb button no longer initiates a drag.
- Dragging the scrubber thumb seeks (does not move the window).
- The faceplate outline lights pink while dragging.
- Optional: snap-to-edge works.

Continue to [chapter 7: theme and polish](stylized-music-07-theme-and-polish.md).
