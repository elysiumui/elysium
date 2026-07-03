# App shell

`elysium.shell` provides the structural, `QMainWindow`-class widgets a desktop
app frames itself with — menu bar, tool bars, dockable panels, splitters, tabs,
a status bar, and group boxes. They are ordinary immediate-mode
[`Component`](components-overview.md)s: each reads `current_theme()` at paint
time (so it recolours with the theme — including [Studio](theming.md)) and
exposes plain methods the host calls to dispatch input.

See [`examples/app-shell-demo/`](https://github.com/elysiumui/elysium/tree/main/examples/app-shell-demo)
for a docking IDE that wires all of them together, and the
[Qt porting guide](porting-from-qt.md#app-shell-tier-4) for the class map.

## Widgets

| Widget | Role |
| --- | --- |
| `MenuBar` | A persistent strip of menu titles; each opens a dropdown `Menu` of `MenuItem`s (labels, shortcuts, `danger`). |
| `ToolBar` / `ToolButton` | An icon/text tool strip. Items are `ToolButton`s, `"separator"`, or a flexible `"spacer"` that pushes the rest to the far edge. `ToolButton.icon` is a painter `(dl, cx, cy, size, color)`, so any glyph source works. |
| `TabWidget` | Content-width tabs (optionally `closable`) that route to the active tab's content. |
| `Splitter` | A draggable divider giving two resizable panes (`"horizontal"` or `"vertical"`), min-size clamped. |
| `StatusBar` | A thin bar: a transient `message` + right-aligned permanent `sections`. |
| `GroupBox` | A titled, bordered container; lay children inside `content_rect()`. |
| `DockWidget` / `DockManager` | Dockable, tabbed panels around a central area. |

## Docking

`DockManager` arranges `DockWidget`s into four areas — `left`, `right`,
`bottom`, and `center`:

```python
from elysium.shell import DockManager, DockWidget

docks = DockManager(x=0, y=0, w=1280, h=720)
docks.add(DockWidget(id="explorer", title="Explorer", content=tree), "left")
docks.add(DockWidget(id="outline",  title="Outline",  content=outl), "left")
docks.add(DockWidget(id="props",    title="Properties", content=props), "right")
docks.add(DockWidget(id="editor",   title="main.py",  content=editor), "center")
docks.add(DockWidget(id="console",  title="Console",  content=log),    "bottom")
```

* **Tabbing** — multiple widgets in the same area share it via a tab strip
  (active tab gets an accent bar; `closable` tabs get an ✕).
* **Resizing** — a `Splitter`-style handle sits between each docked area and the
  centre; drag it to resize (the size is clamped to `min_area`).
* **Re-docking** — drag a tab: drop-zone overlays (left / right / bottom /
  centre) highlight, and releasing moves the widget to that area. A small move
  threshold keeps a plain click as a tab-select.
* **Persistence** — `serialize()` returns a plain dict (areas → widget ids,
  active tabs, sizes); `restore(blob, registry)` rebuilds from it, where
  `registry` maps `id → DockWidget`. Wire these to
  [`elysium.settings.Settings`](threading-and-services.md) to remember a user's
  layout across runs.

### Input dispatch

`DockManager` is immediate-mode, so the host routes pointer events:

```python
# mouse down
if docks.on_press(mx, my):
    ...           # consumed: a tab select, close, or a resize/drag began
# mouse move (while a button is held)
docks.on_drag(mx, my)
# mouse up
docks.on_release()
# each frame
docks.paint(dl)
```

`hit(mx, my)` returns `("tab" | "close" | "handle", area, index)` (or `None`) if
you need to inspect a point without mutating state.

## Notes

* Detaching a dock into a separate floating OS window is a tracked follow-up;
  docked + tabbed + drag-to-redock + persisted layouts are available now.
* These widgets compose the existing primitives (`Menu`, `Button`, `Label`,
  `Tabs`) — drop them into any window's per-frame paint alongside your own
  content.
