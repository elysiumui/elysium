# Elysium UI

Python UI without the rectangles.

Elysium UI is a Python desktop framework for building **borderless, shaped,
GPU-accelerated, animated apps**. Skia for paths and text, wgpu for compositing
and shaders, native shaped windows on macOS, Windows, and Linux. First-class
animation. Designer-to-developer wiring via paired `.esk` skin bundles. AI
authoring through the Aether agent.

```python
import elysium as ely

app = ely.App(title="Aurora Clock", identifier="dev.elysium.clock")
win = app.window(transparent=True, title_bar=False,
                 resizable=False, initial_size=(360, 360))
win.set_hit_test_path("M 180 0 A 180 180 0 1 0 180 360 A 180 180 0 1 0 180 0 Z")
win.load_skin("clock.esk/")
app.run()
```

## Start with a demo

Four flagship tutorials live in [Getting Started](getting-started/index.md). Each
ships an app you can run, screenshot, and modify on day one.

- [Aurora Clock](getting-started/aurora-clock-01-window.md): a transparent
  ellipse clock with an animated arc and breathing aurora glow. Five chapters,
  30 minutes.
- [Pomodoro Timer](getting-started/pomodoro-01-shape-and-modes.md): a
  rounded-rectangle timer with three modes and a radial progress ring. Four
  chapters, 25 minutes.
- [Stylized Music Player](getting-started/stylized-music-01-the-faceplate.md)  
  an elaborate borderless music player in the lineage of late-1990s desktop
  player skin culture. Eight chapters, 90 minutes.
- [Butterfly Banner](getting-started/butterfly-banner-01-load-the-skin.md): the
  official Elysium logo treatment. A hybrid Monarch and Blue Morpho butterfly
  glides down and unfurls the Elysium wordmark. Three chapters, 20 minutes.

## At a glance

| What | Where |
|------|-------|
| `App`, `Window`, `Skin` | [api/elysium.md](api/elysium.md) |
| Components | [guides/components-overview.md](guides/components-overview.md) |
| Layout | [guides/layout.md](guides/layout.md) |
| Animation | [guides/animation.md](guides/animation.md) |
| Reactive | [guides/reactive.md](guides/reactive.md) |
| Borderless and shaped windows | [guides/borderless-and-shaped.md](guides/borderless-and-shaped.md) |
| Theming | [guides/theming.md](guides/theming.md) |
| PBR materials | [guides/pbr.md](guides/pbr.md) |
| Brush system | [guides/brush.md](guides/brush.md) |
| AI and Aether | [guides/aether.md](guides/aether.md) |
| Code Link | [guides/code-link.md](guides/code-link.md) |
| Packaging | [guides/packaging.md](guides/packaging.md) |

## Install

```bash
pip install elysium-ui
```

Pre-built wheels for CPython 3.10 / 3.11 / 3.12 / 3.13 on macOS (arm64 +
x86_64), Windows (x64), and Linux (manylinux x86_64 + aarch64). See
[Getting Started > Install](getting-started/install.md) for the alternate
distribution paths (uv, conda-forge, Homebrew, GitHub Releases, Docker).

## Compare and migrate

- [Which Python GUI?](resources/which-python-gui.md): decision guide across
  Tkinter, PyQt6, PySide6, Kivy, Toga, Flet, Streamlit, dearpygui, wxPython,
  and customtkinter.
- [Migration guides](migration/index.md): coming from Tkinter, PyQt6,
  PySide6, Kivy, or Flet.

## The Designer

Authoring of `.esk` skin bundles happens in the standalone **Elysium Designer**
app, which ships as a `.app` on macOS, `.exe` on Windows, and AppImage on
Linux. The Designer's own documentation lives at
[designer.elysiumui.com](https://designer.elysiumui.com/). Start with the
[Blue Morpho to Monarch butterfly tutorial](https://designer.elysiumui.com/getting-started/butterfly/)
to learn the texture-transfer pipeline that produces the Elysium logo skin.
