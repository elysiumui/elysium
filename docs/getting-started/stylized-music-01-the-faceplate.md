# Stylized Music Player 1. The faceplate

Time: 12 minutes.

## What you are building

Eight chapters that build a custom-shaped, animated music player skin
in the lineage of late-1990s desktop music-player skin culture:
irregular faceplate outline, glowing equalizer bars, gradient album-
art frame, spherical hit zones. Demonstrates that the Framework can
deliver the elaborate borderless aesthetic of that era in modern
Python.

This chapter ships the faceplate path: an irregular asymmetric SVG
outline that becomes the window shape and hit region.

![Stylized Music Player chapter 1: the faceplate outline rendered on a transparent window with debug grid](../assets/stylized-music-ch1.png)

## Project layout

Create a fresh folder `stylized_music_player/` and inside it:

```
stylized_music_player/
  player.py
  player.esk/
    manifest.json
    document.json
```

The skin folder will grow over the next seven chapters. Treat it as
the source of visual truth; the Python file wires interaction and
animation.

## Author the faceplate path

The faceplate is an asymmetric blob about 520 wide and 220 tall.
Use this SVG path; the coordinates assume an origin at the window's
top-left:

```
M 24,40
C 12,28 28,4 48,8
L 220,16
C 244,18 268,8 296,12
L 480,28
C 504,32 516,52 510,76
L 502,156
C 498,180 484,200 460,206
L 96,212
C 68,216 44,202 36,180
L 28,96
C 24,80 16,60 24,40 Z
```

Save it in your Python file as a constant; we will reference it in
two places (window shape + visible fill).

## Open the shaped window

In `player.py`:

```python
import elysium as ely

FACEPLATE = (
    "M 24,40 "
    "C 12,28 28,4 48,8 "
    "L 220,16 "
    "C 244,18 268,8 296,12 "
    "L 480,28 "
    "C 504,32 516,52 510,76 "
    "L 502,156 "
    "C 498,180 484,200 460,206 "
    "L 96,212 "
    "C 68,216 44,202 36,180 "
    "L 28,96 "
    "C 24,80 16,60 24,40 Z"
)

app = ely.App(title="Stylized Music Player", identifier="dev.elysium.stylized-music")
window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(530, 220),
)
window.set_hit_test_path(FACEPLATE)

app.run()
```

Run with `python player.py`. The OS allocates a 530x220 transparent
window, but only the faceplate-shaped region inside it accepts
clicks.

## Paint the faceplate

Author the skin so the visible pixels match the hit region. Edit
`player.esk/manifest.json`:

```json
{
  "schema_version": "1.0",
  "id": "dev.elysium.stylized-music",
  "name": "Stylized Music Player",
  "version": "0.1.0",
  "color_space": "srgb"
}
```

And `player.esk/document.json`:

```json
{
  "placements": [
    {
      "id": "faceplate_back",
      "kind": "path",
      "path_d": "M 24,40 C 12,28 28,4 48,8 L 220,16 C 244,18 268,8 296,12 L 480,28 C 504,32 516,52 510,76 L 502,156 C 498,180 484,200 460,206 L 96,212 C 68,216 44,202 36,180 L 28,96 C 24,80 16,60 24,40 Z",
      "fill": "linear-gradient(135deg, #18113c 0%, #2a1a5a 60%, #0a0820 100%)",
      "stroke": "#3b2a78ff",
      "stroke_width": 1.5
    },
    {
      "id": "faceplate_highlight",
      "kind": "path",
      "path_d": "M 36,28 C 28,18 44,10 60,12 L 260,18 C 280,18 300,12 320,16 L 460,30",
      "fill": "transparent",
      "stroke": "#c4b5fd66",
      "stroke_width": 1.0
    }
  ]
}
```

Load the skin from Python:

```python
from pathlib import Path
window.load_skin(str(Path(__file__).parent / "player.esk"))
```

Run again. The faceplate's gradient fills the irregular outline,
with a thin violet stroke around the perimeter and a hairline
highlight along the top edge.

## Make it draggable

The whole faceplate should drag the window when pressed and held
(no title bar = nowhere to grab). Add a hit hint:

```python
window.faceplate_back.drag_window = True
```

Drag the player around your desktop with the primary mouse button.
The hit region tracks the SVG path exactly: corners and curves drag
when grabbed; nothing outside the shape responds.

## Why this matters

The late-1990s skin aesthetic depended on three things you cannot
get from a stock toolkit:

1. **Non-rectangular windows**: this chapter.
2. **Custom painted controls**: chapter 3.
3. **Composited animation that does not block the UI**: chapter 5.

The Framework gives you all three at first-class quality. The
remaining chapters layer them up.

## Checkpoint

- Asymmetric faceplate outline visible against the desktop.
- Clicks outside the shape pass through.
- Drag-anywhere window movement works.

Continue to [chapter 2: album art frame](stylized-music-02-album-art-frame.md).
