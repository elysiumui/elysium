# Designer → code → ship

Elysium is two products that are really one: the **framework** (this site) and
the **Designer** (a visual authoring tool, documented at
[designer.elysiumui.com](https://designer.elysiumui.com)). This guide is the bridge —
the end-to-end path from a design in the Designer to a running, shipped app.

## The contract: the `.esk` skin

The Designer and the framework meet at the `.esk` skin bundle. The Designer
*authors* skins; the framework *loads* them. A skin is portable, version-
controlled, and hot-reloadable.

```python
import elysium as ely

app = ely.App(title="My App", identifier="dev.example.myapp")
win = app.window(transparent=True, title_bar=False)
win.load_skin("designs/dashboard.esk")
app.run()
```

See [Skins](skins.md) for the bundle format and the designer↔developer contract.

## 1. Design

Build the visual in the Designer — shapes, gradients, 3-D, brushes, themes — and
mark the interactive parts with **hooks** (named slots the code binds to). The
Designer's [getting-started tutorial](https://designer.elysiumui.com) walks the
authoring flow.

## 2. Wire it in code

Bind behavior to the hooks the design exposes. Dotted access and the `@on`
decorator connect events; component widgets from this framework fill dynamic
regions.

```python
@win.on("play_button.click")
def play(event):
    ...

win.cover.text = "Now playing"      # set a named text hook
```

## 3. Iterate with hot reload

Run with hot reload and edit the design live — saves in the Designer push to the
running app over IPC, no restart.

```python
win.enable_hot_reload()             # listens on the default session socket
```

See [Hot reload](hot-reload.md) and [Code Link](code-link.md) (the
Designer↔editor pairing that scaffolds and jumps to handlers).

## 4. Ship

Package a signed, single-file app for macOS / Windows / Linux with the CLI:

```bash
elysium pack
```

See [Packaging](packaging.md) and [Auto-update](auto-update.md).

## Which docs, when

- **This site** (`docs.elysiumui.com`) — the Python framework: API, components,
  patterns, rendering, packaging.
- **[Designer docs](https://designer.elysiumui.com)** — the visual tool: modeling,
  sculpting, rigging, rendering, themes, and the Aether AI assistant.

They cross-link throughout; treat them as one manual with two halves.
