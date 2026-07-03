# How do I build a custom component from primitives?

Subclass `elysium.components.Component`. Override `paint(dl)` to
emit a DisplayList describing what the component should look like.

```python
import elysium as ely
from elysium.components import Component

class Sparkline(Component):
    """Plot a list of floats as a polyline."""

    def __init__(self, id: str, values, color="#a78bfa", width=200, height=40):
        super().__init__(id=id, width=width, height=height)
        self.values = values
        self.color = color

    def paint(self, dl: ely.DisplayList):
        dl.stroke_color(self.color)
        dl.stroke_width(2.0)
        n = len(self.values)
        if n < 2:
            return
        path = ely.Path()
        vmax = max(self.values)
        vmin = min(self.values)
        rng = vmax - vmin or 1
        for i, v in enumerate(self.values):
            x = i / (n - 1) * self.width
            y = self.height - (v - vmin) / rng * self.height
            (path.move_to if i == 0 else path.line_to)(x, y)
        dl.stroke_path(path)


# Use it:
spark = Sparkline(id="cpu", values=[0.1, 0.4, 0.2, 0.6, 0.5, 0.7])
window.add_placement(spark)
```

The framework calls `paint(dl)` when the component is dirty (a
property changed or a parent recomposed). Mutate state via signals
to trigger re-paint:

```python
self.values = new_values
self.invalidate()
```

For a more complex layout, compose existing components inside
your custom component's `compose()` method.

See [Components overview](../guides/components-overview.md) and
[Rendering](../guides/rendering.md).
