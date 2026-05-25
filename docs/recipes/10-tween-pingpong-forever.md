# How do I run a Tween on a ping-pong loop forever?

Pass `loop="ping_pong"` and never call `pause()`.

```python
from elysium.anim import Tween, AnimationClock, run_animation_thread

glow = Tween(
    target=lambda v: setattr(window.glow, "opacity", v),
    start=0.4, end=0.9,
    duration=3.0,
    easing="ease_in_out_sine",
    loop="ping_pong",
)

clock = AnimationClock()
clock.add(glow)
run_animation_thread(clock, fps=60)
glow.start()
```

Total cycle is 6.0 seconds (3 in, 3 out). The Tween auto-reverses
at each endpoint and continues forever until you call `.pause()`
or `.stop()`.

This is the Aurora Clock's breathing glow from
[chapter 4](../getting-started/aurora-clock-04-animation.md).

See [Animation](../guides/animation.md).
