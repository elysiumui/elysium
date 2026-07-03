# `elysium.anim`

Tweens, Timelines, StateMachines, Springs, the AnimationClock,
and easings.

## Animation classes

| Class | Purpose |
|---|---|
| `Animation` | Base for Tween / Timeline |
| `Tween` | Single value interpolation |
| `Timeline` | Sequenced + parallel animations |
| `StateMachine` | Named-state value interpolation |
| `Spring` | Critically-damped natural motion |
| `SpringValue` | Spring as an animation (drives one value) |
| `AnimationClock` | Scheduler for animations |

## Easings

String aliases accepted everywhere `easing=` appears:

`linear`, `ease_in_quad`, `ease_out_quad`, `ease_in_out_quad`,
`ease_in_cubic`, `ease_out_cubic`, `ease_in_out_cubic`,
`ease_out_expo`, `ease_in_sine`, `ease_out_sine`,
`ease_in_out_sine`.

| Function | Purpose |
|---|---|
| `cubic_bezier(p1x, p1y, p2x, p2y)` | Custom cubic-bezier easing |
| `spring(stiffness, damping, mass=1.0)` | Spring as an easing function |
| `easing(name_or_fn)` | Resolve a name or pass through a callable |

## Loop modes

`Tween(..., loop="once" | "loop" | "ping_pong")`.

## Threading

| Function | Purpose |
|---|---|
| `run_animation_thread(clock, fps=60)` | Spawn a daemon thread that ticks the clock |

## Auto-rendered details

::: elysium.anim

## See also

- [Animation](../guides/animation.md)
- [Recipes: tween + spring patterns](../recipes/index.md#animation)
