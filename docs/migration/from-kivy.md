# From Kivy

Kivy is the OpenGL-backed cross-platform Python toolkit known for
its touch-first design and `.kv` declarative UI files. Elysium
borrows the declarative-skin idea (under a different format and
with a dedicated authoring app); the rest of the model differs.

## Widget map

| Kivy | Elysium |
|---|---|
| `App` | `ely.App` |
| `Window` | `app.window(...)` |
| `Widget` | `components.Component` |
| `Label` | `components.Label` |
| `Button` | `components.Button` |
| `TextInput` | `components.TextInput` |
| `Slider` | `components.Slider` |
| `Switch` | `components.Toggle` |
| `BoxLayout` (horizontal) | `layout.Row` |
| `BoxLayout` (vertical) | `layout.Col` |
| `StackLayout` | `layout.Stack` |
| `GridLayout` | `layout.Grid` |
| `RelativeLayout` | (compose with absolute coords on `Stack`) |
| `ScrollView` | `components.ScrollView` |
| `Canvas` | `ely.Canvas` |
| `Image` | `ely.Image` |

## `.kv` vs `.esk`

Kivy's `.kv` is a declarative DSL parsed at runtime:

```kv
BoxLayout:
    orientation: 'vertical'
    Label:
        text: "Hello"
    Button:
        text: "OK"
        on_press: app.do_thing()
```

Elysium's `.esk` is a JSON folder, authored in the Designer:

```json
{ "placements": [
  { "id": "title", "kind": "label", "text": "Hello", "x": 0, "y": 10, "width": 320, "height": 40, "font_size": 16 },
  { "id": "ok",    "kind": "button","label": "OK",  "x": 100, "y": 60, "width": 120, "height": 36 }
]}
```

```python
@window.on("ok.click")
def do_thing(event):
    ...
```

The two roles map: visual definition (kv / `.esk`) and event
wiring (Python).

## `Property` → `signal`

```python
# Kivy
class MyWidget(Widget):
    name = StringProperty("Ada")

# Elysium
name = signal("Ada")
```

Kivy's properties are bound to widgets; Elysium's signals are
free-standing and can drive any number of effects.

## `on_touch_down` → `ClickEvent` + drag

Kivy's `on_touch_down` is essentially a ClickEvent. Elysium splits:

- `@window.on("foo.click")` for press + release at the same target.
- `@window.on("foo.press")` for pointer-down only.
- `@window.on("foo.drag")` for drag with `delta_x`, `delta_y`.

## Animation

Kivy's `Animation` class becomes Elysium's `Tween`:

```python
# Kivy
Animation(x=200, duration=0.4, t="out_cubic").start(widget)

# Elysium
Tween(target=lambda v: setattr(widget, "x", v),
      start=widget.x, end=200,
      duration=0.4, easing="ease_out_cubic").start()
```

## Borderless / shaped

Kivy can do borderless via `Window.borderless = True` and roll-
your-own hit testing. Elysium ships borderless + SVG hit-test
paths first-class.

## Touch and tablet

Both frameworks handle multi-touch. Elysium's
[Touch and dynamics](https://designer.elysiumui.com/brush/touch-and-dynamics/)
documents the brush-side pipeline; for general gestures, the
event model in Elysium is single-pointer with multi-pointer support
via the `secondary_pointers` field on drag events.

## When Kivy still wins

- Mobile (Android, iOS): Elysium is desktop-only in v1.
- Multi-touch-heavy apps with custom gesture recognizers.
- Existing Kivy-based product line you do not want to disturb.

## See also

- [Architecture](../guides/architecture.md)
- [Skins](../guides/skins.md)
- [Animation](../guides/animation.md)
