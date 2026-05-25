# How do I animate opacity in response to a button press?

Trigger a `Tween` on `press` and a reverse `Tween` on `release`.

```python
from elysium.anim import Tween, AnimationClock, run_animation_thread

clock = AnimationClock()
run_animation_thread(clock, fps=60)

press_in = Tween(
    target=lambda v: setattr(window.btn_play, "opacity", v),
    start=1.0, end=0.4, duration=0.08, easing="ease_out_sine",
)
press_out = Tween(
    target=lambda v: setattr(window.btn_play, "opacity", v),
    start=0.4, end=1.0, duration=0.16, easing="ease_in_out_sine",
)

clock.add(press_in)
clock.add(press_out)

@window.on("btn_play.press")
def on_press(event):
    press_in.replan(start=window.btn_play.opacity, end=0.4)
    press_in.restart()

@window.on("btn_play.release")
def on_release(event):
    press_out.replan(start=window.btn_play.opacity, end=1.0)
    press_out.restart()
```

`replan(start=…, end=…)` mid-stream avoids snapping to the new
start when the user releases before press_in finished.

See [Animation](../guides/animation.md).
