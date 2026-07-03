# Hello world

```python
import elysium as ely

app = ely.App(title="Hello, Elysium")
win = app.window(transparent=False, title_bar=True,
                 resizable=True, initial_size=(720, 480))
win.load_skin("examples/hello/skin.esk/")

@win.on("greet.click")
def on_click():
    win["message"].text = "Hello, world!"

app.run()
```

The `examples/hello/skin.esk/` directory in the repository is a six-shape demo skin you can use as a starting point.

## What's happening
1. `App` owns the event loop and the application menu.
2. `app.window(...)` creates a shaped or rectangular OS window.
3. `load_skin(path)` reads the `.esk` bundle and registers every hook.
4. `@win.on("name.event")` wires a Python callable to an event hook.
5. `win["name"].text = ...` writes through a typed hook proxy.
