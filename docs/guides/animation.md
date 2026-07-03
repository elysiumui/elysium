# Animation

Elysium's animation engine has four primitive types, all in
[`elysium.anim`](../api/anim.md): **Tween**, **Timeline**,
**StateMachine**, and **Spring**. Plus `AnimationClock` (the
scheduler) and `run_animation_thread` (run it on its own thread).

## Tween: single value over time

```python
from elysium import anim

t = anim.Tween(
    target=lambda v: setattr(window.panel, "x", v),
    start=0.0, end=240.0,
    duration=0.4,
    easing="ease_out_cubic",
)
```

Each frame the Tween calls its `target` with the interpolated
value. `easing` accepts string names (see Easings below) or
custom callables.

### Loop modes

```python
anim.Tween(..., loop="ping_pong")     # forward, reverse, repeat
anim.Tween(..., loop="loop")          # restart at start each time
anim.Tween(..., loop="once")          # default; stops at end
```

### Control

```python
t.start()        # begin
t.pause()
t.resume()
t.restart()      # back to t=0
t.replan(start=10.0, end=20.0)    # change endpoints mid-run
t.on_complete(fn)                  # callback when finished
```

## Timeline: sequenced and parallel tweens

```python
tl = anim.Timeline([
    (0.0, fade_in),
    (0.2, slide_in),
    (0.6, overshoot),
])
tl.start()
```

Each `(offset, animation)` pair schedules the animation at the
given offset (seconds from timeline start). Animations may
overlap: the Timeline plays them in parallel where they do.

`tl.parallel([a, b, c])` schedules three animations to start at
the same time.

## StateMachine: interpolate between named states

```python
sm = anim.StateMachine(
    states={
        "rest":  {"x": 0,   "scale": 1.0, "alpha": 1.0},
        "press": {"x": 0,   "scale": 0.96, "alpha": 0.85},
        "hover": {"x": 4,   "scale": 1.02, "alpha": 1.0},
    },
    initial="rest",
)

@sm.on_update
def apply(values):
    window.panel.x = values["x"]
    window.panel.scale = values["scale"]
    window.panel.opacity = values["alpha"]

sm.transition_to("hover", duration=0.2, easing="ease_in_out_sine")
```

Each state is a dict of values. The machine interpolates between
the current state and the target on `transition_to`.

## Spring: natural damped motion

```python
s = anim.Spring(stiffness=180.0, damping=26.0, mass=1.0)

@s.on_update
def apply(value):
    window.panel.scale = value

s.target(1.05)   # animate toward 1.05 with the configured stiffness
s.pulse(from_value=0.96, to_value=1.0)   # snap to from, animate to to
```

Springs are critically-damped by default; great for hover,
press, and bounce feedback. The Pomodoro tutorial's tap-to-start
uses this pattern.

## AnimationClock

The scheduler:

```python
clock = anim.AnimationClock()
clock.add(tween_a)
clock.add(tween_b)
clock.add(timeline)
```

Add every animation you want driven. `clock.tick(dt)` advances
the clock by `dt` seconds and updates every active animation.

For most apps wire the clock to its own thread:

```python
anim.run_animation_thread(clock, fps=60)
```

`run_animation_thread(clock, fps=60)` spawns a daemon thread that
calls `clock.tick(1/60)` at 60 Hz. Animations run independently
of signal effects and event handlers, never blocking the render
thread or your Python event handlers.

## Easings

Built-in easing names accepted by `easing="…"`:

| Name | Curve |
|---|---|
| `linear` | y = t |
| `ease_in_quad` / `ease_out_quad` / `ease_in_out_quad` | t² |
| `ease_in_cubic` / `ease_out_cubic` / `ease_in_out_cubic` | t³ |
| `ease_out_expo` | (sharp ease out) |
| `ease_in_sine` / `ease_out_sine` / `ease_in_out_sine` | sine |

For custom curves:

```python
ease = anim.cubic_bezier(0.16, 1.0, 0.3, 1.0)    # Material standard easing
ease = anim.spring(stiffness=200, damping=20)    # spring as an easing fn
```

Both return a callable `(t: float) -> float` accepted as `easing`.

## Render-thread evaluator

For animations that should not pay any per-frame Python cost,
push the target into a **render-thread anim slot** and the GPU
thread interpolates with no GIL:

```python
window.anim_set_target(
    slot=42,
    tx=200, ty=0, scale=1.05, rotation=0.05, alpha=1.0,
    duration=0.4, easing="ease_out",
)
```

In your `DisplayList` reference the same slot:

```python
dl.push_transform(0, 0, anim_slot=42)
dl.draw_text(...)
dl.pop_transform()
```

The render thread blends the live tween value into the transform
matrix before paint. Cost in Python: one `set_target` call, then
nothing per frame.

Use for hot paths only; the Tween API is cleaner for most cases.

## 1-ms rule

Per spec §11.1 every `on_frame` handler is expected to complete
within 1 ms. The debug overlay surfaces handler-time histograms
so you can spot offenders. If you blow the budget, push to the
render-thread evaluator or move work off the render path entirely.

## See also

- [Reactive](reactive.md): drive animations from signals.
- [Recipes: tween from a signal](../recipes/11-tween-from-signal.md)
- [Recipes: animate opacity on press](../recipes/08-animate-opacity-on-press.md)
- [Recipes: hover with a Spring scale](../recipes/09-hover-spring-scale.md)
- [Recipes: tween on ping-pong loop](../recipes/10-tween-pingpong-forever.md)
