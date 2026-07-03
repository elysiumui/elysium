# Stylized Music Player 3. Playback controls

Time: 9 minutes.

## What we are adding

Three custom-painted spherical buttons in the right half of the
faceplate: Previous, Play/Pause, Next. Each is a glowing orb with
an embossed glyph. The Play button morphs to a Pause glyph while
playing.

![Stylized Music Player chapter 3: three glowing spherical buttons (previous, play, next) lit on the faceplate](../assets/stylized-music-ch3.png)

## Add the buttons to the skin

Append to `player.esk/document.json`:

```json
{
  "id": "btn_prev",
  "kind": "orb_button",
  "cx": 240, "cy": 110,
  "radius": 22,
  "glyph": "prev",
  "fill": "radial-gradient(circle at 35% 30%, #ec4899 0%, #6b21a8 70%, #1a0f3c 100%)",
  "stroke": "#fbcfe8aa",
  "stroke_width": 1.0,
  "shadow": { "color": "#a78bfa66", "blur": 14 }
},
{
  "id": "btn_play",
  "kind": "orb_button",
  "cx": 305, "cy": 110,
  "radius": 30,
  "glyph": "play",
  "fill": "radial-gradient(circle at 35% 30%, #fde68a 0%, #a78bfa 50%, #6b21a8 90%)",
  "stroke": "#ffffffaa",
  "stroke_width": 1.2,
  "shadow": { "color": "#f0abfc99", "blur": 22 }
},
{
  "id": "btn_next",
  "kind": "orb_button",
  "cx": 370, "cy": 110,
  "radius": 22,
  "glyph": "next",
  "fill": "radial-gradient(circle at 35% 30%, #ec4899 0%, #6b21a8 70%, #1a0f3c 100%)",
  "stroke": "#fbcfe8aa",
  "stroke_width": 1.0,
  "shadow": { "color": "#a78bfa66", "blur": 14 }
}
```

`kind: "orb_button"` is the framework's spherical button placement
  a circle with a radial gradient fill, an embossed glyph from the
built-in catalog (`play`, `pause`, `prev`, `next`, `stop`, `eject`,
`shuffle`, `repeat`), and a circular click region.

## Hover glow with a Spring

Each orb should subtly grow on hover. Bind once at startup:

```python
from elysium.anim import Spring

hover_springs = {
    "btn_prev": Spring(stiffness=220.0, damping=22.0),
    "btn_play": Spring(stiffness=220.0, damping=22.0),
    "btn_next": Spring(stiffness=220.0, damping=22.0),
}


def make_hover_handler(btn_id: str):
    @hover_springs[btn_id].on_update
    def apply(value: float):
        setattr(window[btn_id], "scale", value)

    @window.on(f"{btn_id}.hover")
    def hover(event):
        hover_springs[btn_id].target(1.08 if event.entered else 1.0)


for bid in ("btn_prev", "btn_play", "btn_next"):
    make_hover_handler(bid)
```

`Spring.target(value)` smoothly animates the spring toward `value`
with the configured stiffness and damping. `Spring.on_update` fires
on every animation frame with the current spring value.

## Play / pause toggle

The play button morphs its glyph and triggers playback. We do not
yet have audio (chapter 5 wires that); for now toggle a signal and
swap the glyph:

```python
from elysium.reactive import signal, effect

is_playing = signal(False)


@window.on("btn_play.click")
def toggle_play(event):
    is_playing.set(not is_playing())


@effect
def push_play_glyph():
    window.btn_play.glyph = "pause" if is_playing() else "play"
```

## Previous / Next

The skip buttons fire signals that whichever audio backend you wire
in chapter 5 will subscribe to:

```python
from elysium.reactive import signal

skip_event = signal(0)  # tick this to nudge subscribers


@window.on("btn_prev.click")
def prev(event):
    skip_event.set(skip_event() - 1)


@window.on("btn_next.click")
def nxt(event):
    skip_event.set(skip_event() + 1)
```

Reading `skip_event()` shows a running net "skip count" the audio
backend can compare against to know whether to seek.

## Click feedback

Add a quick pulse on press so the user feels the click:

```python
press_springs = {bid: Spring(stiffness=280.0, damping=20.0)
                 for bid in ("btn_prev", "btn_play", "btn_next")}


def wire_press_feedback(btn_id: str):
    press_springs[btn_id].pulse(from_value=1.0, to_value=1.0)  # arm

    @window.on(f"{btn_id}.press")
    def on_press(event):
        press_springs[btn_id].pulse(from_value=0.92, to_value=1.0)

    @press_springs[btn_id].on_update
    def apply(v: float):
        setattr(window[btn_id], "scale", v)


for bid in press_springs:
    wire_press_feedback(bid)
```

Now mouse-down on any button briefly compresses it, then it springs
back. Combined with the hover glow you get the satisfying "tactile
button" feel.

## Checkpoint

- Three orb buttons on the right of the faceplate.
- Hovering an orb grows it slightly.
- Clicking Play swaps its glyph to Pause.
- Mouse-down briefly compresses any button.

Continue to [chapter 4: custom scrubber](stylized-music-04-scrubber.md).
