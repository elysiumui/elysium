# How do I open a window with a star-shaped hit region?

Author an SVG path and pass it to `set_hit_test_path`.

```python
import elysium as ely

# 5-point star inscribed in 240 x 240.
STAR = (
    "M 120,12 L 145,90 L 228,90 L 161,138 "
    "L 187,216 L 120,168 L 53,216 L 79,138 "
    "L 12,90 L 95,90 Z"
)

app = ely.App(title="Star", identifier="dev.example.star")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(240, 240),
)
window.set_hit_test_path(STAR)
app.run()
```

The OS still allocates a 240x240 rectangle, but only clicks inside
the star register. The rest pass through.

For a window that **looks** like a star too, paint the same path
in the skin's `document.json` (`kind: "path"`, `path_d: STAR`).

See [Borderless and shaped](../guides/borderless-and-shaped.md).
