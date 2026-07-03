# Migration

Move an existing Python desktop app to Elysium. Pick the guide
that matches your current framework.

| Coming from | Guide |
|---|---|
| Tkinter / Tk | [From Tkinter](from-tkinter.md) |
| PyQt6 | [From PyQt6](from-pyqt6.md) |
| PySide6 | [From PySide6](from-pyside6.md) |
| Kivy | [From Kivy](from-kivy.md) |
| Flet | [From Flet](from-flet.md) |

## Shared themes across migrations

Five things change for everyone moving to Elysium:

1. **No layout-by-callback.** Layout is declarative in skins or in
   Python `Stack` / `Row` / `Col` containers.
2. **No state in widgets.** State lives in [signals](../guides/reactive.md).
3. **Skin-vs-code split.** Visuals in `.esk` folders; behavior in
   Python. The Designer authors skins; your editor wires behavior.
4. **Borderless and animated by default.** What used to require
   custom paint code in your old framework now ships out of the
   box.
5. **PBR + brush + AI.** Capabilities most Python frameworks do
   not have are first-class here.

## "When my existing framework still wins"

A common section in every migration guide. Elysium is the right
choice for the apps it was built for (borderless, animated,
high-fidelity, GPU-accelerated). For server-rendered data tables,
classic enterprise forms, or systems that need to integrate with
Qt's vast widget ecosystem, the old framework may still be the
right call.

## See also

- [Which Python GUI?](../resources/which-python-gui.md): the
  pre-migration decision guide.
- [Comparison table](../resources/comparison.md): feature-by-
  feature matrix.
