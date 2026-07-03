# How do I detect and react to system dark mode?

Use `elysium.platform.system_is_dark()` and `on_system_theme_change`.

```python
from elysium import platform
from elysium.theme import set_theme, midnight_glass, frost


def apply_for(is_dark: bool):
    set_theme(midnight_glass() if is_dark else frost())


# At startup
apply_for(platform.system_is_dark())

# Listen for runtime changes
platform.on_system_theme_change(apply_for)
```

The framework subscribes to the OS notification:

| OS | Source |
|---|---|
| macOS | `NSDistributedNotificationCenter.AppleInterfaceThemeChangedNotification` |
| Windows | `WM_SETTINGCHANGE / ImmersiveColorSet` |
| Linux | `org.freedesktop.appearance.color-scheme` (XDG portal); falls back to GNOME / KDE settings |

The callback runs on the Python thread, so it is safe to mutate
skin state and call `set_theme` directly.

See [Theming](../guides/theming.md).
