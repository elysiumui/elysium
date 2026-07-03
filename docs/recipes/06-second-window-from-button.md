# How do I open a second window from a button click?

Call `app.window(...)` from inside a button handler. Hold a
reference so the new window isn't garbage-collected.

```python
import elysium as ely

app = ely.App(title="…", identifier="dev.example.app")
main = app.window(transparent=True, title_bar=False, initial_size=(480, 320))
main.load_skin("main.esk/")

side_windows = []

@main.on("open_side.click")
def open_side(event):
    w = app.window(transparent=True, title_bar=False, initial_size=(280, 480))
    w.load_skin("side.esk/")
    side_windows.append(w)
    # optional: position next to main
    main_x, main_y = main.outer_position
    w.set_outer_position(main_x + main.width + 8, main_y)

app.run()
```

Each `app.window(...)` returns a fresh window with its own skin
and hook proxy. Signals are shared if you reference them in
multiple windows' effects.

See [Windowing](../guides/windowing.md).
