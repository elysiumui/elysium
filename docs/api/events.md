# `elysium.events`

Event types and propagation helpers.

## Event classes

| Class | Fired by |
|---|---|
| `ClickEvent` | Press + release inside the same placement |
| `PressEvent` / `ReleaseEvent` | Pointer-down / -up |
| `HoverEvent` | Pointer enter / leave |
| `DragEvent` | Pointer drag (`delta_x`, `delta_y`, `velocity`) |
| `FocusEvent` / `BlurEvent` | Focus ring movement |
| `KeyEvent` | Keyboard (`code`, `text`, `modifiers`) |
| `ChangeEvent` | Slider / Toggle / TextInput value change |
| `WindowEvent` | Window-level events (resized, focus.gained, etc.) |

## Common fields

```python
event.x, event.y                 # canvas x / y
event.local_x, event.local_y     # local to the placement
event.button                     # 1=primary, 2=secondary, 3=middle
event.modifiers                  # 1=Shift, 2=Ctrl, 4=Alt, 8=Meta
event.target_id                  # which placement was hit
event.stop_propagation()
event.prevent_default()
```

## Auto-rendered details

::: elysium.events

## See also

- [Events](../guides/events.md)
- [Focus](../guides/focus.md)
