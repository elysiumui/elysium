# How do I add a global hotkey to open a CommandPalette?

Register a global accelerator via `elysium.platform.register_hotkey`,
and open a transient borderless window in the handler.

```python
from elysium import platform
from elysium.components import CommandPalette


def open_palette():
    win = app.window(
        transparent=True, title_bar=False, resizable=False,
        initial_size=(560, 320),
        level=3,                # floating; above other windows
    )
    win.load_skin("palette.esk/")

    palette = CommandPalette(
        id="palette",
        commands=[
            {"id": "new",      "label": "New project",       "shortcut": "N"},
            {"id": "open",     "label": "Open …",            "shortcut": "O"},
            {"id": "settings", "label": "Open settings",     "shortcut": ","},
        ],
        on_choose=lambda cmd: (do(cmd["id"]), win.close()),
    )
    win.add(palette)
    win.focus_first()


platform.register_hotkey("Cmd+K", open_palette)    # macOS
platform.register_hotkey("Ctrl+K", open_palette)   # Win / Linux
```

`register_hotkey` registers a system-wide accelerator. On macOS
this requires `NSApplication.shared.registerForRemoteNotifications`
permission; the framework prompts the first time.

The transient palette window auto-closes on Esc or outside-click
(both built into the `CommandPalette` component's defaults).

See [Components overview](../guides/components-overview.md).
