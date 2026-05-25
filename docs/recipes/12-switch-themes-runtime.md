# How do I switch themes at runtime?

Call `set_theme(theme)`. Components and `{theme.…}`-bound skin
fields update in one frame.

```python
from elysium.theme import set_theme, midnight_glass, frost

set_theme(midnight_glass())   # initially

@window.on("theme_toggle.click")
def cycle(event):
    set_theme(frost() if event.target_label == "Frost" else midnight_glass())
```

Skin fields written as `"fill": "{theme.surface}"` re-resolve.
Components reading `theme.accent` and friends rerender.

For non-theme-bound color literals in your skin, override them
manually in the handler:

```python
window.background.fill = theme.background
window.title.fill = theme.on_background
```

See [Theming](../guides/theming.md).
