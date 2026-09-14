# `elysium.accessibility`

Read system accessibility preferences; publish accessible trees
for screen readers.

## Classes

| Class | Purpose |
|---|---|
| `A11yPrefs` | Dataclass of OS-reported a11y preferences |

## Functions

| Function | Purpose |
|---|---|
| `current()` | Return the current `A11yPrefs` |
| `subscribe(fn)` | Subscribe to changes |

## A11yPrefs fields

```python
@dataclass
class A11yPrefs:
    reduce_motion: bool
    high_contrast: bool
    invert_colors: bool
    larger_text: bool
    screen_reader_active: bool
```

## Per-window helpers

(on the `Window` class: re-listed here for discoverability)

| Method | Purpose |
|---|---|
| `window.publish_a11y_tree(root_id, nodes)` | Publish the accessible tree |
| `window.set_a11y_focus(id)` | Tell the OS which node is focused |

## Assistive actions

`window.poll_a11y_event()` returns `(node_id, action_name, value)` or `None`.
Drain it on the UI thread and route actions only to current visible controls.
Editable text fields and text areas advertise `SetValue`; its optional `value`
is the complete replacement string. Update the field draft, then use the same
validation and explicit Apply/submit behavior as keyboard input. Disabled and
read-only fields must reject replacement.

`window.poll_a11y_action()` remains available for legacy consumers and returns
only `(node_id, action_name)`. Both methods drain the same queue, so choose one
polling interface per window. The event method preserves replacement text.

## Auto-rendered details

::: elysium.accessibility

## See also

- [Accessibility](../guides/accessibility.md)
- [Recipes: respect reduce-motion](../recipes/14-respect-reduce-motion.md)
