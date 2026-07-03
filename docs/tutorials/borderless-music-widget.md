# Borderless music widget

Time: 25 minutes. Difficulty: Beginner.

A star-shaped borderless widget with Play / Pause / Next /
Previous controls. Smaller and simpler than the [Stylized Music
Player](../getting-started/stylized-music-01-the-faceplate.md): no
equalizer visualizer, no scrubber, no album art. Just a compact
player that lives in the corner of your desktop.

## Prerequisites

- Walked through [Aurora Clock](../getting-started/aurora-clock-01-window.md)
  at least once.
- `pip install elysium-ui`.

## Star-shaped window

```python
import elysium as ely

# 5-point star inscribed in 200 x 200
STAR = (
    "M 100,10 L 120,75 L 190,75 L 135,115 "
    "L 155,180 L 100,140 L 45,180 L 65,115 "
    "L 10,75 L 80,75 Z"
)

app = ely.App(title="Music widget", identifier="dev.example.music-widget")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(200, 200),
    level=3,    # floating above other windows
)
window.set_hit_test_path(STAR)
```

## Skin

Create `widget.esk/manifest.json` and `widget.esk/document.json`:

```json
// manifest.json
{ "schema_version": "1.0",
  "id": "dev.example.music-widget", "name": "Music Widget",
  "version": "0.1.0", "color_space": "srgb",
  "window": { "shape": { "kind": "path",
    "path_d": "M 100,10 L 120,75 L 190,75 L 135,115 L 155,180 L 100,140 L 45,180 L 65,115 L 10,75 L 80,75 Z" } }
}
```

```json
// document.json
{
  "placements": [
    { "id": "back", "kind": "path",
      "path_d": "M 100,10 L 120,75 L 190,75 L 135,115 L 155,180 L 100,140 L 45,180 L 65,115 L 10,75 L 80,75 Z",
      "fill": "linear-gradient(135deg, #18113c 0%, #2a1a5a 100%)",
      "stroke": "#a78bfa66", "stroke_width": 1.5 },
    { "id": "btn_prev", "kind": "orb_button",
      "cx": 65, "cy": 105, "radius": 14, "glyph": "prev",
      "fill": "radial-gradient(circle at 35% 30%, #ec4899, #6b21a8)" },
    { "id": "btn_play", "kind": "orb_button",
      "cx": 100, "cy": 100, "radius": 20, "glyph": "play",
      "fill": "radial-gradient(circle at 35% 30%, #fde68a, #a78bfa)" },
    { "id": "btn_next", "kind": "orb_button",
      "cx": 135, "cy": 105, "radius": 14, "glyph": "next",
      "fill": "radial-gradient(circle at 35% 30%, #ec4899, #6b21a8)" }
  ]
}
```

Load:

```python
from pathlib import Path
window.load_skin(str(Path(__file__).parent / "widget.esk"))
```

## Wire the buttons

```python
from elysium.reactive import signal, effect

is_playing = signal(False)


@effect
def push_play_glyph():
    window.btn_play.glyph = "pause" if is_playing() else "play"


@window.on("btn_play.click")
def toggle(event):
    is_playing.set(not is_playing())


skip = signal(0)

@window.on("btn_prev.click")
def prev(event):
    skip.set(skip() - 1)


@window.on("btn_next.click")
def nxt(event):
    skip.set(skip() + 1)
```

## Hover spring

```python
from elysium.anim import Spring

for bid in ("btn_prev", "btn_play", "btn_next"):
    s = Spring(stiffness=220.0, damping=22.0)
    s.on_update(lambda v, b=bid: setattr(window[b], "scale", v))
    window.subscribe(f"{bid}.hover",
                     lambda e, s=s: s.target(1.08 if e.entered else 1.0))
```

## Persist position

The widget should remember where you dragged it:

```python
import json
from elysium import platform

geom = platform.user_data_dir("music-widget") / "geom.json"

if geom.exists():
    g = json.loads(geom.read_text())
    window.set_outer_position(g["x"], g["y"])


@window.on("window.closed")
def save_geom(event):
    geom.parent.mkdir(parents=True, exist_ok=True)
    geom.write_text(json.dumps({
        "x": window.outer_position[0],
        "y": window.outer_position[1],
    }))
```

## Pack

```sh
elysium pack widget.py --name "Music Widget" \
  --identifier dev.example.music-widget \
  --include widget.esk
```

A signed standalone bundle per OS.

## What you built

A 200x200 star-shaped widget that floats above other windows,
controls playback, persists position, and ships as a real app.
Roughly 60 lines of Python.

## See also

- [Stylized Music Player](../getting-started/stylized-music-01-the-faceplate.md)
 : the full demo this riffs on.
- [Recipes: star-shaped hit region](../recipes/02-star-shaped-hit-region.md)
- [Recipes: persist window geometry](../recipes/21-persist-window-geometry.md)
