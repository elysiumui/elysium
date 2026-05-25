# Aurora Clock 4. Animate the arc and the glow

Time: 7 minutes.

## What we are adding

Two animations:

1. A **sweeping arc** that follows the second hand: a violet arc
   from the center to the current second's angle, repainted as the
   second value advances.
2. A **breathing glow** behind the dial: a soft radial blur that
   pulses opacity from 0.4 to 0.9 over six seconds, ping-ponging
   forever.

![Aurora Clock chapter 4: sweep arc updates each second; the aurora glow pulses gently in the background](../assets/aurora-clock-ch4.gif)

## Add the two new placements

Append two placements to `aurora_clock.esk/document.json` (inside
the `"placements"` array, after `dial`):

```json
{
  "id": "glow",
  "kind": "ellipse",
  "x": -20, "y": -20,
  "width": 400, "height": 400,
  "fill": "#7c3aedff",
  "blur": 48,
  "opacity": 0.4
},
{
  "id": "sweep_arc",
  "kind": "arc",
  "cx": 180, "cy": 180,
  "radius": 156,
  "start_angle": -90,
  "end_angle": -90,
  "stroke": "#f0abfcff",
  "stroke_width": 3.0,
  "cap": "round"
}
```

Order matters in this file: `background` first (back), `glow` next
(blurred halo), `dial` and `ticks` on top, and `sweep_arc` on top of
those, with `time_label` last so it draws above everything.

## Sweep the arc with a reactive effect

The arc's `end_angle` is what we animate. Set it from the
`now_seconds` signal you wired in chapter 3. Add this near the other
effect:

```python
@effect
def push_sweep_to_arc():
    seconds = now_seconds()
    angle = -90 + (seconds / 60.0) * 360.0
    window.sweep_arc.end_angle = angle
```

The arc starts at `-90` (12 o'clock) and sweeps clockwise to the
current second. At 20 Hz the motion looks smooth.

## Ping-pong the glow with a Tween

The glow opacity needs to interpolate between 0.4 and 0.9 with a
ping-pong loop. The `elysium.anim` package has the right primitives:

```python
from elysium.anim import Tween, AnimationClock, run_animation_thread

glow_tween = Tween(
    target=lambda value: setattr_glow_opacity(value),
    start=0.4,
    end=0.9,
    duration=3.0,
    easing="ease_in_out_sine",
    loop="ping_pong",
)


def setattr_glow_opacity(value: float) -> None:
    window.glow.opacity = value


clock = AnimationClock()
clock.add(glow_tween)
run_animation_thread(clock, fps=60)
```

`Tween` calls its `target` callable each frame with the interpolated
value. `loop="ping_pong"` reverses direction at each endpoint so the
total period is 6.0 seconds (3.0 in, 3.0 out). `AnimationClock` is
the scheduler; `run_animation_thread` runs it on its own thread so
the animation never blocks the render thread or any signal effects.

## Putting it together

Your full `aurora_clock.py` now looks like this:

```python
import threading
import time
from datetime import datetime
from pathlib import Path

import elysium as ely
from elysium.reactive import signal, effect
from elysium.anim import Tween, AnimationClock, run_animation_thread

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"
SKIN_PATH = str(Path(__file__).parent / "aurora_clock.esk")

app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(360, 360),
)
window.set_hit_test_path(ELLIPSE)
window.load_skin(SKIN_PATH)

time_signal = signal(datetime.now().strftime("%H:%M:%S"))
now_seconds = signal(0.0)

@effect
def push_time():
    window.time_label.text = time_signal()

@effect
def push_sweep():
    seconds = now_seconds()
    angle = -90 + (seconds / 60.0) * 360.0
    window.sweep_arc.end_angle = angle


def tick_forever():
    while True:
        now = datetime.now()
        time_signal.set(now.strftime("%H:%M:%S"))
        now_seconds.set(now.second + now.microsecond / 1_000_000.0)
        time.sleep(0.05)


threading.Thread(target=tick_forever, daemon=True).start()

glow_tween = Tween(
    target=lambda v: setattr(window.glow, "opacity", v),
    start=0.4, end=0.9,
    duration=3.0,
    easing="ease_in_out_sine",
    loop="ping_pong",
)
clock = AnimationClock()
clock.add(glow_tween)
run_animation_thread(clock, fps=60)

app.run()
```

Run it. The sweep arc traces the second hand and the violet halo
breathes behind the dial. The clock face is now visibly alive.

## Performance note

The two effects (`push_time`, `push_sweep`) re-run on the render
thread; the Tween updates on its own animation thread; the
`tick_forever` ticker on a third thread. All three eventually
mutate placements on the window proxy, which is thread-safe by
design. The native side batches these mutations into the next
display list flush, so even at 20 Hz signals plus 60 fps tween you
will see well under 1% CPU on a modern machine.

## Checkpoint

You should see:

- A violet arc sweeping from 12 o'clock, advancing as time passes.
- A soft halo pulsing in the background every six seconds.
- The label still ticking once per second.

Continue to [chapter 5: theme toggle + event wiring](aurora-clock-05-theme-and-events.md).
