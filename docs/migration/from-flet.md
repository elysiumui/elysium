# From Flet

Flet is a Flutter-backed Python framework for web and desktop UI.
Moving to Elysium trades web compatibility (Flet runs in a browser
or a Flutter shell) for native borderless / shaped / GPU-composited
windows and a Designer.

## Concept map

| Flet | Elysium |
|---|---|
| `flet.app` | `ely.App` |
| `Page` | `app.window(...)` |
| Control | `Component` |
| `Text` | `Label` |
| `ElevatedButton` / `TextButton` | `Button` |
| `TextField` | `TextInput` |
| `Slider` | `Slider` |
| `Switch` | `Toggle` |
| `Checkbox` | `Checkbox` |
| `Container` | `layout.Stack` (single child) or `layout.Col` / `Row` (multi) |
| `Row` / `Column` | `layout.Row` / `layout.Col` |
| `Stack` | `layout.Stack` |
| `GridView` | `layout.Grid` |
| `ListView` | (compose with `Col` + virtualization later) |
| `Image` | `Image` placement |
| `Animation` (animate_*) | `anim.Tween` |
| `page.update()` | (not needed; signals do this) |
| `page.go(...)` | (no router in v1; build with multiple windows) |

## Reactive flow

Flet uses imperative `page.update()` after mutating controls.
Elysium uses fine-grained reactive: set a signal, effects re-run,
the canvas updates next frame. No explicit "update".

```python
# Flet
text.value = "Hello"
page.update()

# Elysium
greeting = signal("Hello")
@effect
def push():
    window.greeting.text = greeting()
greeting.set("Hi")
```

## `animate_opacity` / `animate_size`

Flet's per-property animation flags become Tweens:

```python
# Flet
container.animate_opacity = 300   # ms
container.opacity = 0.5
page.update()

# Elysium
Tween(target=lambda v: setattr(window.container, "opacity", v),
      start=1.0, end=0.5, duration=0.3, easing="ease_out_sine").start()
```

## `ft.colors` → `Color` + `Theme`

Flet's color constants (`ft.colors.PURPLE_400`) map to Elysium's
`Color` values and theme tokens. The Elysium `Theme` system
supplies named tokens (`theme.accent`, `theme.surface`) that
cascade across the UI.

## Web vs native

Flet's strength is running the same Python code in a browser
(via Flutter Web). Elysium is native-only in v1; for a web
deployment of an Elysium app you would build a web shell and
embed the framework as a [WebView](../guides/webview.md) host  
not the same value proposition.

## When Flet still wins

- Apps that need to run in a browser.
- Apps that need the Material 3 widget catalog out of the box
  (Flutter's full set is huge).
- Apps with hot reload across web + desktop targets.

## See also

- [Architecture](../guides/architecture.md)
- [Reactive](../guides/reactive.md)
- [Animation](../guides/animation.md)
