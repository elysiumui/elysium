# From PyQt6

PyQt6 wraps the C++ Qt library: the most capable GUI toolkit
available for Python. Moving to Elysium trades Qt's vast widget
catalog for a smaller, opinionated framework that ships borderless,
animated, GPU-accelerated rendering and a Designer.

## Widget map

| PyQt6 | Elysium |
|---|---|
| `QApplication` | `ely.App(...)` |
| `QMainWindow` | `app.window(...)` |
| `QWidget` (custom subclass) | `components.Component` subclass |
| `QLabel` | `components.Label` |
| `QPushButton` | `components.Button` |
| `QLineEdit` | `components.TextInput` |
| `QTextEdit` | `components.TextArea` |
| `QCheckBox` | `components.Checkbox` |
| `QRadioButton` | `components.Radio` |
| `QSlider` | `components.Slider` |
| `QComboBox` | (compose from `Popover` + `Button`) |
| `QListView` / `QTableView` | (no direct equivalent in v1) |
| `QGraphicsView` | `ely.Canvas` + `DisplayList` |
| `QML` | `.esk` skin |
| `QPropertyAnimation` | `anim.Tween` |
| `app.exec()` | `app.run()` |

## Signals and slots → @win.on + signals

PyQt6:

```python
btn.clicked.connect(on_click)
```

Elysium:

```python
@window.on("btn.click")
def on_click(event): ...
```

Cross-component data flow uses Elysium signals (reactive cells)
where Qt would use signals (Qt sense = events):

```python
name = signal("Ada")     # cross-window value
window.greeting.text = ... # auto-updated via effect
```

## qss vs Theme

Qt Style Sheets (qss) is CSS-like text styling per widget.
Elysium uses a structured `Theme` dataclass and `{theme.…}` token
references in skins. The result is similar (theme-able UI) but
typed and authorable in the Designer.

## QML vs `.esk`

Qt's QML files describe declarative UI. `.esk` folders play the
same role for Elysium:

```qml
// PyQt6 QML
Rectangle { color: "#1e1b4b"; radius: 28; width: 320; height: 200 }
```

```json
// Elysium .esk document
{ "kind": "rounded_rect", "fill": "#1e1b4b", "radius": 28,
  "x": 0, "y": 0, "width": 320, "height": 200 }
```

The `.esk` is authored in the Designer rather than text-edited
directly (though you can; the JSON is human-readable).

## QPropertyAnimation → Tween

```python
# PyQt6
anim = QPropertyAnimation(widget, b"geometry")
anim.setDuration(400)
anim.setEndValue(QRect(10, 10, 200, 100))
anim.start()

# Elysium
Tween(target=lambda r: setattr(widget, "rect", r),
      start=...,
      end=(10, 10, 200, 100),
      duration=0.4,
      easing="ease_out_cubic").start()
```

## Licensing

PyQt6 is GPL/commercial; Elysium is permissively licensed (see
[License](../resources/contributing.md)). Often a deciding factor
for closed-source desktop apps.

## When PyQt6 still wins

- Apps needing a `QTableView` with 1M rows.
- Apps shipping inside an existing Qt-based product line.
- Apps that must integrate with Qt-only third-party libs (Qt Quick
  3D, Qt Charts, Qt Maps).

## See also

- [From PySide6](from-pyside6.md): sister wrapper of Qt.
- [Architecture](../guides/architecture.md)
- [Skins](../guides/skins.md)
