# How do I make a window draggable without a title bar?

Borderless windows are draggable by default: pressing and dragging
anywhere on the hit region moves the window. Refine which
placements opt in or out with the `drag_window` property.

```python
import elysium as ely

app = ely.App(title="…", identifier="dev.example.app")
window = app.window(transparent=True, title_bar=False,
                    resizable=False, initial_size=(360, 240))
window.load_skin("myapp.esk/")

# Opt the background out; opt the title strip in.
window.background.drag_window = False
window.title_strip.drag_window = True

# Set a drag threshold so clicks aren't mistaken for drags.
window.set_drag_threshold(4)

app.run()
```

Per-placement `drag_window` overrides the default. For interactive
controls (buttons, sliders, scrubbers), set `drag_window = False`
so dragging them does not move the window.

See [Borderless and shaped](../guides/borderless-and-shaped.md).
