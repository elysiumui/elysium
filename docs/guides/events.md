# Events

Input events (click, hover, drag, focus, key) flow from the OS
into the framework's hit-tester, then into the Skin's hook bus.
Python wires handlers with the `@window.on(...)` decorator.

## Bind a handler

```python
@window.on("save.click")
def on_save(event):
    print("save pressed", event)
```

`save.click` is the hook name; events are dispatched by name. The
hook name has two parts: the placement's `id` and the event kind.

## Event kinds

| Kind | Fired by |
|---|---|
| `click` | Press + release inside the same placement |
| `press` | Pointer-down |
| `release` | Pointer-up |
| `hover` | Pointer enter / leave (`event.entered` bool) |
| `drag` | Pointer drag (`event.delta_x`, `delta_y`) |
| `drag.start` / `drag.end` | Drag begin / end |
| `focus` / `blur` | Focus ring movement |
| `change` | Slider, Toggle, TextInput value change |
| `key` | Keyboard event (`event.code`, `event.modifiers`) |

Components define richer event kinds; the [Components overview](components-overview.md)
lists per-component hooks.

## ClickEvent

The event passed to a `click` handler:

```python
event.x              # canvas x relative to window
event.y              # canvas y relative to window
event.local_x        # x relative to the placement
event.local_y        # y relative to the placement
event.button         # 1=primary, 2=secondary, 3=middle
event.modifiers      # bitmask: 1=Shift, 2=Ctrl, 4=Alt, 8=Meta
event.target_id      # which placement was hit
event.stop_propagation()
event.prevent_default()
```

Drag events add `delta_x`, `delta_y`, and `velocity_x/y`. Key
events add `code` (string like "ArrowUp") and `text` (the
character if any).

## Propagation

Events propagate from the deepest hit placement up through its
parents in the layout tree. Call `event.stop_propagation()` to
halt; otherwise the framework continues bubbling.

```python
@window.on("button.click")
def on_button(event):
    if some_condition:
        event.stop_propagation()
    # otherwise the click also reaches button's parent panel
```

## Default behavior

A few events have framework default behavior (a click on a window-
drag-enabled placement starts a drag; a key on a focused input
inserts text). Call `event.prevent_default()` to suppress:

```python
@window.on("name_input.key")
def filter_input(event):
    if event.text and not event.text.isalpha():
        event.prevent_default()    # block non-letter input
```

## Imperative subscription

For dynamic handlers (subscribe and later unsubscribe), use
`subscribe`:

```python
def on_click(event):
    print("clicked")

unsubscribe = window.subscribe("save.click", on_click)
# later …
unsubscribe()
```

`@window.on(...)` is sugar over `subscribe`; both work fine.

## Firing manually

For testing or programmatic dispatch:

```python
window.fire("save.click", event=None)
```

Returns the number of handlers invoked. Exceptions inside handlers
are caught and logged (never propagate into the render or input
thread).

## Window-level events

Hooks that aren't placement-specific:

| Hook | Fired by |
|---|---|
| `window.opened` | First frame after `app.window(...)` |
| `window.closed` | After `window.close()` |
| `window.focus.gained` / `window.focus.lost` | OS focus change |
| `window.resized` | `(w, h)` payload |
| `window.dpi.changed` | After a multi-monitor DPI change |
| `window.drag.start` / `window.drag.end` | Window-drag gesture |

## Keyboard

A focused window receives every key event. The framework's
focus navigation (Tab / arrows) is layered on top; see [Focus](focus.md).

```python
@window.on("window.key")
def handle(event):
    if event.code == "Escape":
        window.close()
```

## Performance

Event dispatch budget: <100 µs per event end-to-end (OS → handler
→ return). Exceptions inside handlers are caught with a printed
traceback; never crash the app.

## See also

- [Focus](focus.md): keyboard focus model.
- [Components overview](components-overview.md): per-component
  hook names.
- [Recipes: animate opacity on press](../recipes/08-animate-opacity-on-press.md)
