# From Tkinter

Tkinter is the Python standard library's GUI module. It is small,
universal, and shows its age. Moving to Elysium gets you a GPU
compositor, animation primitives, theming, and borderless / shaped
windows in exchange for a slightly heavier install.

## Widget map

| Tkinter | Elysium |
|---|---|
| `Tk()` | `ely.App(...)` + `app.window(...)` |
| `Frame` | [layout.Stack / Row / Col](../guides/layout.md) |
| `Label` | `components.Label` |
| `Button(command=fn)` | `components.Button(on_click=fn)` |
| `Entry` | `components.TextInput` |
| `Text` | `components.TextArea` |
| `Checkbutton` | `components.Checkbox` |
| `Radiobutton` | `components.Radio` |
| `Scale` | `components.Slider` |
| `Canvas` | `ely.Canvas` + `DisplayList` |
| `ttk.Treeview` | (no direct equivalent in v1; compose from primitives) |
| `Toplevel` | `app.window(...)` (any window can be a child or modal) |
| `mainloop()` | `app.run()` |

## Event model

Tkinter binds events by name on widgets:

```python
btn.bind("<Button-1>", on_click)
entry.bind("<Return>", on_submit)
```

Elysium uses dotted hook names + decorators:

```python
@window.on("btn.click")
def on_click(event): ...

@window.on("entry.key")
def on_submit(event):
    if event.code == "Enter":
        ...
```

## StringVar / IntVar → signal

Tkinter's tracked variables become Elysium signals:

```python
# Tkinter
name = tk.StringVar()
name.set("Ada")
label = tk.Label(textvariable=name)

# Elysium
name = signal("Ada")
@effect
def push():
    window.name_label.text = name()
name.set("Lovelace")
```

Signals are simpler: no per-widget binding, just the one effect.

## Geometry managers

Tkinter ships three (`pack`, `grid`, `place`); Elysium ships
five containers (`Stack`, `Row`, `Col`, `Grid`, `Form`). See the
[Layout guide](../guides/layout.md).

## The borderless pitch

Tkinter on macOS / Windows / Linux always renders with system
chrome. Elysium's default is borderless transparent. If you have
been faking borderless via `overrideredirect`, you know the pain
of building per-OS workarounds; Elysium just does this natively.

## Animation

Tkinter has no animation primitive. The standard workaround is
`after(ms, fn)` with manual interpolation. Elysium:

```python
from elysium.anim import Tween
Tween(target=..., start=0, end=240, duration=0.4, easing="ease_out_cubic")
```

## When Tkinter still wins

- Apps that need to run on a tk-only machine (no extra installs
  available).
- Apps shipping the smallest possible binary.
- Apps that need to plug into a tk-based third-party ecosystem.

Otherwise, Elysium is strictly more capable.

## See also

- [Architecture](../guides/architecture.md): App / Window / Skin
  model.
- [Components overview](../guides/components-overview.md): the
  full component catalog.
- [Borderless and shaped](../guides/borderless-and-shaped.md)  
  the headline guide.
