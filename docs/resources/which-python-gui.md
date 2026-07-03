# Which Python GUI?

A decision guide. Picks the right Python desktop UI framework for
your project, even if it is not Elysium.

## Decision tree

1. **Mobile target needed?** → Kivy or Flet.
2. **Web target needed (same code)?** → Flet.
3. **Borderless / shaped / animated desktop app?** → Elysium.
4. **Browser-like document app (huge tables, complex forms)?** →
   PyQt6 / PySide6.
5. **Minimum-binary toy / script with a GUI?** → Tkinter.
6. **Already in Qt ecosystem?** → PyQt6 / PySide6 (stay).

## At-a-glance comparison

| Framework | Renderer | Borderless / shaped | Animation | Theming | Designer app | Mobile | Web |
|---|---|---|---|---|---|---|---|
| Tkinter | OS native | hacky | none | basic | none | no | no |
| PyQt6 | OS native (or QPainter) | partial | QPropertyAnimation | qss | Qt Designer | partial | no |
| PySide6 | same as PyQt6 | partial | same | same | same | partial | no |
| Kivy | OpenGL | yes (DIY) | Animation class | kv-driven | none | yes | partial |
| Flet | Flutter | partial | animate_* | Material | none | yes | yes |
| **Elysium** | **Skia + wgpu** | **first-class** | **Tween / Spring / Timeline / Clock** | **5 built-in + custom** | **Designer.app** | **no (v1)** | **no (v1)** |

For "what's Elysium good at," the [Comparison matrix](comparison.md)
goes deeper.

## "What's the catch?"

Three things to know before committing to Elysium:

- **Desktop-only in v1.** No mobile / web target.
- **Smaller widget catalog.** 30 components shipping; you can
  compose more, but if you need a 1M-row table view today, Qt is
  better.
- **PyInstaller bundle size.** ~80 MB on macOS, ~110 MB on Windows,
  ~95 MB on Linux. The native renderer + Skia + wgpu + brushes
  drives this. Smaller than Electron; bigger than Tkinter.

The trade is: rich GPU-composited UI, real animation, designer
tooling, AI workflows, borderless / shaped windows, brush + PBR.
For the apps Elysium is built for, the trade is the right one.

## When you genuinely should use Qt

- Heavy data-grid apps (think Bloomberg-terminal complexity).
- LTS support is non-negotiable (Qt has formal LTS branches; Elysium
  ships continuously).
- Qt-specific deep integrations (QtCharts, QtCAD, QtMaps, Qt for
  Automotive, QtIVI).

## When you genuinely should use Tkinter

- Throwaway scripts and proof-of-concept apps.
- Apps targeted at machines where you cannot install anything beyond
  the stdlib.
- Educational settings where the simplest possible API is the point.

## See also

- [Comparison](comparison.md): feature matrix in depth.
- [Migration guides](../migration/index.md): when you have decided
  to switch.
