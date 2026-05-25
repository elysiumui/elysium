# `elysium.reactive`

Fine-grained reactive primitives, modeled on Solid.js.

## Primitives

| Function | Purpose |
|---|---|
| `signal(value)` | Create a mutable reactive cell |
| `computed(fn)` | Lazy derived read |
| `effect(fn)` | Side-effecting callback that re-runs on signal changes |

## Class

| Class | Purpose |
|---|---|
| `Signal` | Type of values returned by `signal(...)` |

## Helpers

| Function | Purpose |
|---|---|
| `batch(fn)` | Run `fn` and defer effect re-runs to its end |
| `untrack(fn)` | Read signals without registering dependencies |
| `on_cleanup(fn)` | Register a cleanup inside an effect |

## Auto-rendered details

::: elysium.reactive

## See also

- [Reactive](../guides/reactive.md)
- [Recipes: signal + computed](../recipes/22-signal-computed-derived-label.md)
