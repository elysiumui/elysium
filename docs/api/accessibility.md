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
| `window.publish_a11y_focus(id)` | Tell the OS which node is focused |

## Auto-rendered details

::: elysium.accessibility

## See also

- [Accessibility](../guides/accessibility.md)
- [Recipes: respect reduce-motion](../recipes/14-respect-reduce-motion.md)
