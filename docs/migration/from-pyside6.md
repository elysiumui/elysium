# From PySide6

PySide6 is Qt for Python's "official" wrapper, maintained by The
Qt Company. The technical surface mirrors PyQt6; the differences
are import paths, licensing, and a few API edges.

For the bulk of the migration story, see [From PyQt6](from-pyqt6.md);
this page covers PySide6-specific notes.

## Import map

| PyQt6 | PySide6 |
|---|---|
| `from PyQt6.QtCore import …` | `from PySide6.QtCore import …` |
| `pyqtSignal` | `Signal` |
| `pyqtSlot` | `Slot` |
| `pyqtProperty` | `Property` |
| `QObject.connect(...)` | `obj.signal.connect(...)` (same) |

Elysium does not have a one-to-one signal-and-slot system. Use
`@window.on(...)` for events and `signal()` for reactive state;
see the [PyQt6 guide](from-pyqt6.md) for full mapping.

## Licensing

PySide6 is LGPL; PyQt6 is GPL/commercial. Elysium ships under a
permissive license. If your app needs proprietary distribution
without LGPL dynamic linking or PyQt6's commercial license, Elysium
removes that constraint.

## Deployment

PySide6 apps typically ship via PyInstaller or `briefcase` with the
Qt runtime bundled. Elysium ships via `elysium pack` (PyInstaller
under the hood, signed bundle per OS). The frameworks' deployment
stories are similar: same per-OS bundle sizes, similar startup
times.

## What is the same

- Widget-to-component mapping (Label, Button, TextInput, Slider, etc.).
- `QPropertyAnimation` → `Tween`.
- QML → `.esk`.
- The general "build a widget tree" mental model.

## What differs from PyQt6 specifically

- PySide6 plays slightly more nicely with `dataclasses` and modern
  Python type hints; Elysium leans into both first-class.
- PySide6 has `QtCharts`, `QtDataVisualization`, `QtMaps`; Elysium
  v1 ships none of these. Embed via [WebView](../guides/webview.md)
  or write thin wrappers using Canvas + DisplayList.

## When PySide6 still wins

Same answers as the PyQt6 guide. If you specifically need the Qt
Quick 3D scene graph or QtCharts, stay on PySide6.

## See also

- [From PyQt6](from-pyqt6.md): the full migration mapping.
- [Architecture](../guides/architecture.md)
