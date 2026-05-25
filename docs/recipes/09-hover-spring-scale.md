# How do I make a hover state with a Spring scale?

Use a `Spring` and target a new value on enter / leave.

```python
from elysium.anim import Spring

scale = Spring(stiffness=220.0, damping=22.0)

@scale.on_update
def apply(v: float):
    window.btn_play.scale = v


@window.on("btn_play.hover")
def hover(event):
    scale.target(1.08 if event.entered else 1.0)
```

`Spring.target(v)` smoothly animates from the current spring value
toward `v`. `on_update` fires every animation frame.

Stiffness 200-260, damping 18-24 is a natural-feeling button
hover. Higher stiffness = snappier; lower damping = more bounce.

See [Animation](../guides/animation.md).
