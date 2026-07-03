# Butterfly Banner 2. Flight animation

Time: 8 minutes.

## What we are adding

The butterfly starts above the screen, descends in a curved path
to the center, and idles there with a gentle hover. The path uses
`Tween` for the descent and `Spring` for the idle hover.

![Butterfly Banner chapter 2: butterfly descending from offscreen and settling at the center](../assets/butterfly-banner-ch2.gif)

## Position the window above the screen

We will move the OS window itself (not the butterfly inside it).
Center horizontally on the user's screen and place the top edge
above the visible area:

```python
import elysium as ely

screens = ely.platform.screens()
primary = screens.primary

start_x = (primary.width - 960) // 2
start_y = -540   # entirely off the top of the screen
end_y = (primary.height - 540) // 2

window.set_outer_position(start_x, start_y)
```

`set_outer_position` works on borderless windows and uses the
screen's coordinate space directly. The butterfly is now invisible
because it sits above the top edge.

## Tween the descent

```python
from elysium.anim import Tween, Timeline, AnimationClock, run_animation_thread, cubic_bezier

descent = Tween(
    target=lambda y: window.set_outer_position(start_x, int(y)),
    start=start_y,
    end=end_y,
    duration=2.4,
    easing=cubic_bezier(0.22, 1.0, 0.36, 1.0),  # gentle ease-out
)


clock = AnimationClock()
clock.add(descent)
run_animation_thread(clock, fps=60)
descent.start()
```

The cubic-bezier curve gives a slightly springy ease-out that feels
intentional rather than mechanical. The butterfly slides into view
over 2.4 seconds.

## Add the idle hover

Once the descent finishes, we want the butterfly to hover with a
gentle vertical oscillation (a 4-pixel wave, 2.5 second period).
A `Spring` driven by a slow time-based input does this:

```python
import math
import time

class Hover:
    def __init__(self, base_y: int, amplitude: float = 4.0, period: float = 2.5):
        self.base = base_y
        self.amplitude = amplitude
        self.period = period
        self.t_start = None

    def __call__(self) -> int:
        if self.t_start is None:
            self.t_start = time.monotonic()
        elapsed = time.monotonic() - self.t_start
        offset = math.sin(elapsed * 2.0 * math.pi / self.period) * self.amplitude
        return int(self.base + offset)


hover = Hover(end_y)


def hover_thread():
    while True:
        time.sleep(1.0 / 60.0)
        window.set_outer_position(start_x, hover())
```

After the descent finishes, switch from the Tween's `set_outer_position`
to the hover thread. Wire the handoff with the Tween's `on_complete`:

```python
import threading

def start_hover():
    threading.Thread(target=hover_thread, daemon=True).start()


descent.on_complete(start_hover)
```

The butterfly slides in, settles, and breathes.

## Compose with a Timeline

If you want more complex choreography (descent → pause → flap
faster → unfurl banner, etc.) reach for a Timeline:

```python
timeline = Timeline([
    (0.0, descent),
    (2.6, banner_unfurl),   # placeholder; chapter 3 defines this
])
clock.add(timeline)
timeline.start()
```

`Timeline` plays each child animation at the specified offset
(seconds from start). It also accepts callable hooks so you can fire
arbitrary code at named moments (e.g. play a sound, log telemetry).

## Adjust the wing flap during descent

The default 1-second flap cadence is too slow while the butterfly
is in motion. Speed it up briefly:

```python
window.skin.animations["wing_flap"].set_rate(2.0)  # twice as fast


def restore_flap_rate():
    window.skin.animations["wing_flap"].set_rate(1.0)


descent.on_complete(restore_flap_rate)
```

Now the wings flap twice as fast during the descent, then return to
the normal rate for the idle hover. Subtle, but it sells the motion.

## Respect reduced-motion

Some users have system "Reduce Motion" turned on. The framework
exposes a single read for this:

```python
from elysium import accessibility

if accessibility.current().reduce_motion:
    descent.duration = 0.4
    hover.amplitude = 0.0
```

Honoring reduce-motion is a small change with a big quality-of-life
upside.

## Checkpoint

- Butterfly enters from above and settles at the screen center.
- Wing-flap rate doubles during descent, returns to 1 Hz on idle.
- Idle hover oscillates 4 pixels vertically.
- Reduce-Motion shortens the descent and disables the oscillation.

Continue to [chapter 3: banner unfurl + logo](butterfly-banner-03-banner-unfurl-and-logo.md).
