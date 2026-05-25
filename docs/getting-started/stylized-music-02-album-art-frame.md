# Stylized Music Player 2. Album art frame

Time: 9 minutes.

## What we are adding

A 140 by 140 album art slot on the left side of the faceplate,
wrapped in a violet-to-pink gradient frame with an inner glow and a
subtle drop shadow. The frame is itself a `Card` placement using the
glass material.

![Stylized Music Player chapter 2: gradient-framed album art on the left of the faceplate](../assets/stylized-music-ch2.png)

## Add the album art placements

Append three placements to `player.esk/document.json` (inside
`placements`, after `faceplate_highlight`):

```json
{
  "id": "art_glow",
  "kind": "rounded_rect",
  "x": 28, "y": 36,
  "width": 152, "height": 152,
  "radius": 12,
  "fill": "transparent",
  "stroke": "linear-gradient(135deg, #ec4899 0%, #a78bfa 100%)",
  "stroke_width": 3.0,
  "shadow": { "color": "#a78bfa66", "blur": 18, "y": 0 }
},
{
  "id": "art_card",
  "kind": "card",
  "x": 34, "y": 42,
  "width": 140, "height": 140,
  "radius": 8,
  "material": "glass-dark",
  "background_image": "assets/art_placeholder.png"
},
{
  "id": "art_label",
  "kind": "label",
  "x": 34, "y": 184,
  "width": 140, "height": 14,
  "text": "No track loaded",
  "font_size": 10,
  "fill": "#c4b5fdff",
  "align": "center"
}
```

The `Card` component uses the `glass-dark` material: the same blurred
translucent surface that backs the dark theme: so even when no
album art is loaded, the slot looks intentional.

## Drop in a placeholder image

Create `player.esk/assets/art_placeholder.png` (any 140x140 PNG works
for testing; for the official tutorial we ship a stylized treble-
clef SVG rasterized to 140x140).

If you do not have one handy, draw a quick gradient PNG with:

```python no-check
from PIL import Image, ImageDraw
im = Image.new("RGB", (140, 140), "#1a0f3c")
ImageDraw.Draw(im).ellipse((20, 20, 120, 120), fill="#a78bfa")
im.save("player.esk/assets/art_placeholder.png")
```

Run the player. The album art slot appears with the violet-pink
gradient frame around the placeholder image.

## Swap art at runtime

When the user loads a real track, we need to swap the placeholder
for the actual artwork. Hold the current path in a reactive signal:

```python
from elysium.reactive import signal, effect

album_art_path = signal("assets/art_placeholder.png")
track_title = signal("No track loaded")


@effect
def push_art():
    window.art_card.background_image = album_art_path()


@effect
def push_title():
    window.art_label.text = track_title()
```

Now from a future "load track" handler:

```python
album_art_path.set("/Users/you/Music/MyAlbum/cover.jpg")
track_title.set("Track 04 - Drift")
```

The frame and label update inside one render frame.

## A note on materials

The framework ships eight materials usable on `card` and `panel`
placements: `solid`, `glass-light`, `glass-dark`, `vibrancy-light`,
`vibrancy-dark`, `frosted`, `holographic`, and `aurora`. They are
documented under [Theming](../guides/theming.md). For this player
the dark glass is the right call; chapter 7 lets you experiment.

## Checkpoint

- Album art frame visible to the left of (empty) center of the
  faceplate.
- The frame has a violet-to-pink gradient stroke + soft drop shadow.
- A label below the art shows the (placeholder) track title.

Continue to [chapter 3: playback controls](stylized-music-03-playback-controls.md).
