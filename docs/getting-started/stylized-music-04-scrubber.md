# Stylized Music Player 4. Custom scrubber

Time: 8 minutes.

## What we are adding

A horizontal scrubber under the album art and buttons, with a
violet-to-pink glowing trail behind the thumb, time elapsed / total
labels at each end, and click-and-drag seek behavior.

![Stylized Music Player chapter 4: scrubber with a glowing trail underneath the play controls](../assets/stylized-music-ch4.png)

## Add the scrubber placements

Append to `player.esk/document.json`:

```json
{
  "id": "scrub_track",
  "kind": "rounded_rect",
  "x": 200, "y": 152,
  "width": 280, "height": 4,
  "radius": 2,
  "fill": "#3b2a78ff"
},
{
  "id": "scrub_trail",
  "kind": "rounded_rect",
  "x": 200, "y": 152,
  "width": 0, "height": 4,
  "radius": 2,
  "fill": "linear-gradient(90deg, #a78bfa 0%, #ec4899 100%)",
  "shadow": { "color": "#ec489966", "blur": 8 }
},
{
  "id": "scrub_thumb",
  "kind": "ellipse",
  "x": 196, "y": 148,
  "width": 12, "height": 12,
  "fill": "radial-gradient(circle at 35% 30%, #ffffff 0%, #a78bfa 70%, #6b21a8 100%)",
  "stroke": "#ffffffcc",
  "stroke_width": 1.0
},
{
  "id": "time_elapsed",
  "kind": "label",
  "x": 200, "y": 168,
  "width": 40, "height": 12,
  "text": "0:00",
  "font_size": 9,
  "fill": "#c4b5fdcc",
  "align": "left"
},
{
  "id": "time_total",
  "kind": "label",
  "x": 440, "y": 168,
  "width": 40, "height": 12,
  "text": "0:00",
  "font_size": 9,
  "fill": "#c4b5fdcc",
  "align": "right"
}
```

## Bind the scrubber to a signal

The scrubber position is a float in `[0.0, 1.0]`. A signal holds it
and three effects update the trail width, the thumb x, and the
elapsed-time label.

```python
from elysium.reactive import signal, effect

duration_s = signal(214.0)         # track length in seconds
position_s = signal(0.0)           # current playback position


@effect
def push_trail_width():
    pos = position_s() / max(duration_s(), 1.0)
    window.scrub_trail.width = pos * 280.0


@effect
def push_thumb_x():
    pos = position_s() / max(duration_s(), 1.0)
    window.scrub_thumb.x = 196 + pos * 280.0


def format_time(s: float) -> str:
    m, s = divmod(int(s), 60)
    return f"{m}:{s:02d}"


@effect
def push_elapsed_label():
    window.time_elapsed.text = format_time(position_s())


@effect
def push_total_label():
    window.time_total.text = format_time(duration_s())
```

## Drag-to-seek

The scrubber needs to react to a click anywhere on the track and to
drag along it. The framework's `pointer.drag` hook gives you the
relative motion deltas for free.

```python
@window.on("scrub_track.click")
def seek_click(event):
    x = event.local_x  # x relative to the placement
    fraction = max(0.0, min(1.0, x / 280.0))
    position_s.set(fraction * duration_s())


@window.on("scrub_thumb.drag")
def seek_drag(event):
    new_x = window.scrub_thumb.x + event.delta_x
    new_x = max(196.0, min(196.0 + 280.0, new_x))
    fraction = (new_x - 196.0) / 280.0
    position_s.set(fraction * duration_s())
```

`event.local_x` is the click position inside the placement; `event.delta_x`
is the per-frame mouse motion during a drag. Both come from the
input pipeline and feed directly into the signal.

## Advance the position when playing

Combine `is_playing` from chapter 3 with the position signal:

```python
import threading
import time

def position_thread():
    while True:
        time.sleep(0.1)
        if not is_playing():
            continue
        if position_s() >= duration_s():
            is_playing.set(False)
            continue
        position_s.set(position_s() + 0.1)

threading.Thread(target=position_thread, daemon=True).start()
```

10 Hz is enough for a smooth-looking scrubber. The actual audio
backend in chapter 5 will replace this with the real track position.

## Hover hint

When the user hovers the track, show a faint preview of where they
would seek to. Append a thin vertical line placement and update it
on hover:

```python
@window.on("scrub_track.hover")
def hover(event):
    if event.entered:
        window.scrub_track.height = 6.0
    else:
        window.scrub_track.height = 4.0
```

The track thickens slightly on hover. Subtle, but it tells the user
the bar is interactive.

## Checkpoint

- Scrubber below the orb buttons with a violet-pink trail.
- The thumb tracks the trail's right edge as time advances.
- Click anywhere on the track: position jumps there.
- Drag the thumb: position follows.
- Track thickens on hover.

Continue to [chapter 5: equalizer visualizer](stylized-music-05-equalizer-visualizer.md).
