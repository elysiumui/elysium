# Comparison matrix

Feature-by-feature comparison against the major Python desktop
UI frameworks. Use alongside [Which Python GUI?](which-python-gui.md)
for a higher-level decision guide.

## Capability matrix

Legend: ✓ first-class · △ partial / via plugin · ✗ not supported

| Capability | Elysium | Tkinter | PyQt6 | PySide6 | Kivy | Toga | Flet | dearpygui | wxPython | customtkinter |
|---|---|---|---|---|---|---|---|---|---|---|
| Borderless / shaped windows | ✓ | △ | △ | △ | ✓ | △ | △ | △ | △ | △ |
| Hit-test path (SVG) | ✓ | ✗ | ✗ | ✗ | △ | ✗ | ✗ | ✗ | ✗ | ✗ |
| GPU-composited rendering | ✓ | ✗ | △ | △ | ✓ | △ | ✓ | △ | ✗ | ✗ |
| PBR 3D embedded | ✓ | ✗ | △ | △ | △ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Animation primitives | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✓ | △ | △ | △ |
| Spring / Timeline | ✓ | ✗ | △ | △ | △ | ✗ | △ | ✗ | ✗ | ✗ |
| Reactive signals | ✓ | ✗ | ✗ | ✗ | △ | ✗ | △ | ✗ | ✗ | ✗ |
| Theming system | ✓ (5 + custom) | △ | qss | qss | kv | △ | Material | △ | △ | ✓ |
| Designer app | ✓ (Elysium Designer) | ✗ | △ (Qt Designer) | △ | ✗ | ✗ | ✗ | ✗ | △ | ✗ |
| Hot reload | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | △ | ✗ | ✗ | ✗ |
| Brush / paint system | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| In-app AI agent | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Accessibility | ✓ | ✓ | ✓ | ✓ | △ | △ | △ | △ | ✓ | △ |
| Tablet / pen input | ✓ | ✗ | △ | △ | ✓ | ✗ | ✗ | ✗ | △ | ✗ |
| WebView integration | ✓ | ✗ | ✓ | ✓ | △ | ✗ | ✓ | ✗ | ✓ | ✗ |
| Code Link (Designer↔editor) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Mobile target | ✗ | ✗ | △ | △ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Web target | ✗ | ✗ | ✗ | ✗ | △ | △ | ✓ | ✗ | ✗ | ✗ |
| Skin marketplace | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

## Library size and distribution

| Framework | wheel size | typical PyInstaller bundle |
|---|---|---|
| Tkinter | (stdlib) | 12 MB |
| PyQt6 | 70 MB | ~85 MB |
| PySide6 | 90 MB | ~110 MB |
| Kivy | 12 MB | ~40 MB |
| Toga | 4 MB | ~25 MB |
| Flet | 30 MB | ~90 MB |
| dearpygui | 18 MB | ~30 MB |
| wxPython | 50 MB | ~65 MB |
| customtkinter | 1 MB | ~14 MB |
| **Elysium** | **35 MB** | **~80-110 MB per OS** |

## License

| Framework | License |
|---|---|
| Tkinter | PSF |
| PyQt6 | GPL or commercial |
| PySide6 | LGPL |
| Kivy | MIT |
| Toga | BSD |
| Flet | Apache 2.0 |
| dearpygui | MIT |
| wxPython | wxWindows (LGPL-like) |
| customtkinter | MIT |
| Elysium | Permissive (see [Contributing](contributing.md)) |

## See also

- [Which Python GUI?](which-python-gui.md)
- [Migration guides](../migration/index.md)
