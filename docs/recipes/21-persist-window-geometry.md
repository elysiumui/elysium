# How do I persist window position and size between launches?

Save geometry on close; restore on open. Use
`elysium.platform.user_data_dir` for a per-user, per-OS location.

```python
import json
from elysium import platform

geometry_path = platform.user_data_dir("myapp") / "window.json"


def save_geometry(window):
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    geometry_path.write_text(json.dumps({
        "x": window.outer_position[0],
        "y": window.outer_position[1],
        "width": window.width,
        "height": window.height,
    }))


def load_geometry(window):
    if not geometry_path.exists():
        return
    g = json.loads(geometry_path.read_text())
    window.set_outer_position(g["x"], g["y"])
    window.resize(g["width"], g["height"])


load_geometry(window)
@window.on("window.closed")
def on_close(event):
    save_geometry(window)
```

Geometry persists per OS at:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/myapp/window.json` |
| Windows | `%AppData%\myapp\window.json` |
| Linux | `~/.config/myapp/window.json` |

For multi-window apps, save one geometry per window id.

See [Windowing](../guides/windowing.md).
