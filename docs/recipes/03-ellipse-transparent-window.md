# How do I open an ellipse-shaped transparent window?

Use the two-arc SVG path for an ellipse fitting the window's
bounds, then pass it to `set_hit_test_path`.

```python
import elysium as ely

ELLIPSE = "M 0,180 A 180,180 0 1 0 360,180 A 180,180 0 1 0 0,180 Z"

app = ely.App(title="Aurora Clock", identifier="dev.example.aurora")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(360, 360),
)
window.set_hit_test_path(ELLIPSE)
app.run()
```

For a 360x360 window the ellipse is centered at (180, 180) with
radii 180/180. For a different size, rewrite the arc parameters
(`A r1,r2 0 1 0 …`) to match.

This is the Aurora Clock pattern from
[chapter 1 of its tutorial](../getting-started/aurora-clock-01-window.md).
