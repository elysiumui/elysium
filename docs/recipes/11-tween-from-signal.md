# How do I drive a Tween off the value of a signal?

Read the signal in an effect; when it changes, replan and restart
the tween.

```python
from elysium.reactive import signal, effect
from elysium.anim import Tween, AnimationClock, run_animation_thread

target_x = signal(0.0)

clock = AnimationClock()
run_animation_thread(clock, fps=60)

mover = Tween(
    target=lambda v: setattr(window.dot, "x", v),
    start=0.0, end=0.0,
    duration=0.4,
    easing="ease_out_cubic",
)
clock.add(mover)


@effect
def follow():
    new_x = target_x()
    mover.replan(start=window.dot.x, end=new_x)
    mover.restart()


# Trigger:
target_x.set(180)    # the tween animates dot.x from current to 180
```

The effect runs whenever `target_x` changes. `replan(start=…,
end=…)` updates the Tween's endpoints; `restart()` plays it from
t=0.

See [Reactive](../guides/reactive.md) and [Animation](../guides/animation.md).
