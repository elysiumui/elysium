# Stylized Music Player 5. Equalizer visualizer

Time: 12 minutes.

## What we are adding

Sixteen vertical bars under the orb buttons that bounce in time with
the audio. The bars draw on a `Canvas` and animate via a `Timeline`
that interpolates each bar's height from a frequency-spectrum
sample. A mocked spectrum drives the bars in the tutorial; the
audio-backend appendix at the end shows how to plug in a real source.

![Stylized Music Player chapter 5: sixteen glowing equalizer bars under the controls, animating to a beat](../assets/stylized-music-ch5.gif)

## Add the bars to the skin

Append a single Canvas placement to `player.esk/document.json`:

```json
{
  "id": "eq_canvas",
  "kind": "canvas",
  "x": 200, "y": 60,
  "width": 280, "height": 80
}
```

The Canvas is an empty surface that we paint to from Python via a
`DisplayList`. Bars live as line segments inside that list, so we
get GPU-accelerated rendering with minimal overhead.

## Build a DisplayList of bars

Wire a small helper that builds a fresh display list from a list of
16 heights (each `0.0` to `1.0`):

```python
import elysium as ely


BAR_COUNT = 16
BAR_GAP = 4
BAR_WIDTH = (280 - (BAR_COUNT - 1) * BAR_GAP) / BAR_COUNT  # ~13


def build_eq_display_list(heights):
    dl = ely.DisplayList()
    base_y = 80  # canvas height; bars grow upward from here
    for i, h in enumerate(heights):
        x = i * (BAR_WIDTH + BAR_GAP)
        bar_h = max(2.0, h * 76.0)
        bar = ely.Path()
        bar.rect(x, base_y - bar_h, BAR_WIDTH, bar_h, radius=2)
        # Color top-to-bottom: pink at top, violet at base.
        dl.fill_path(bar, gradient=(
            (0.0, "#ec4899ff"),
            (1.0, "#a78bfaff"),
        ))
        # Soft glow underneath.
        dl.shadow(bar, color="#ec489966", blur=6)
    return dl
```

## Mock a spectrum

A real frequency analyzer would call into `librosa`, `numpy`, or a
platform audio API. For the tutorial we mock a beat-following
spectrum so the chapter stands alone:

```python
import math
import random
import time
import threading

eq_heights = [0.0] * BAR_COUNT


def mock_spectrum_thread():
    t = 0.0
    while True:
        time.sleep(1.0 / 30.0)
        if not is_playing():
            for i in range(BAR_COUNT):
                eq_heights[i] *= 0.7  # decay when paused
            window.eq_canvas.publish_display_list(build_eq_display_list(eq_heights))
            continue
        t += 1.0 / 30.0
        beat = abs(math.sin(t * 4.0 * math.pi)) ** 2
        for i in range(BAR_COUNT):
            target = beat * (0.6 + 0.4 * random.random())
            # Smooth ramp toward the target.
            eq_heights[i] = eq_heights[i] * 0.6 + target * 0.4
        window.eq_canvas.publish_display_list(build_eq_display_list(eq_heights))


threading.Thread(target=mock_spectrum_thread, daemon=True).start()
```

The thread runs at 30 Hz. The bars rise on a synthetic 4 Hz "beat",
each with a small random offset so the visual reads as a band of
energy moving across the spectrum. When `is_playing` is false, the
heights decay smoothly toward zero.

## Why a DisplayList + Canvas

A Canvas placement reserves a GPU surface in the skin; publishing a
DisplayList to it tells the renderer to compose that list on top of
the rest of the skin in one draw pass. Compared to mutating 16
individual placements each frame, this is roughly an order of
magnitude faster on a mid-range GPU.

The same pattern powers the framework's gauges, sparklines, and any
custom-painted control.

## Add a per-bar Tween for the attack

The mock spectrum already smooths each bar with linear interpolation
(`* 0.6 + target * 0.4`). To get the snappy attack and slow decay of
1990s skins, swap to a Tween per bar:

```python
from elysium.anim import Tween

bar_tweens = [
    Tween(target=lambda v, i=i: eq_heights.__setitem__(i, v),
          start=0.0, end=0.0,
          duration=0.18, easing="ease_out_expo")
    for i in range(BAR_COUNT)
]


def push_target(i: int, target_h: float):
    t = bar_tweens[i]
    t.replan(start=eq_heights[i], end=target_h)
    t.restart()
```

In the spectrum thread:

```python
push_target(i, target)
```

(Replacing the manual smoothing.) Each bar now snaps up quickly on a
beat and falls back with the easing curve.

## Plug in a real audio source

The full real-audio appendix is in
[Recipes: stream audio into an equalizer](../recipes/index.md), but
the short version: replace `mock_spectrum_thread` with a callback
from a platform audio API (`pyaudio`, `sounddevice`, or the
framework's `elysium.webview` bridge if you are streaming through a
browser embed), FFT the samples, normalize to 16 bins, and feed each
bin into `push_target(i, height)`.

The Canvas + DisplayList path makes zero assumptions about where the
heights come from. Anything that updates a 16-element list at ~30 Hz
will look great.

## Checkpoint

- Sixteen bars visible above the scrubber.
- Bars bounce on the synthetic beat while playing.
- Bars decay smoothly when paused.
- Optional: swap to per-bar Tweens for a snappier attack curve.

Continue to [chapter 6: drag + hit test refinement](stylized-music-06-drag-and-hit-test.md).
