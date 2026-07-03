# How do I open a borderless window?

Pass `title_bar=False` (and usually `transparent=True`) to
`app.window(...)`.

```python
import elysium as ely

app = ely.App(title="Borderless demo", identifier="dev.example.borderless")
window = app.window(
    transparent=True,
    title_bar=False,
    resizable=False,
    initial_size=(360, 240),
)
app.run()
```

You get a 360 by 240 transparent window with no chrome. Add a
hit-test path to shape it; see
[recipe 03](03-ellipse-transparent-window.md) or [recipe 02](02-star-shaped-hit-region.md).

See [Borderless and shaped](../guides/borderless-and-shaped.md).
