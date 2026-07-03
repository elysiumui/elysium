# Completer (autocomplete)

`elysium.components.completer.Completer` is a completion popup for text inputs —
Qt's `QCompleter`. It ranks candidates against the current query (optionally
fuzzy), shows up to `max_visible` rows, and accepts with click or keyboard.

```python
from elysium.components.completer import Completer

completer = Completer(
    candidates=["Northwind", "Crestline", "Harbor Co.", "Fernweh"],
    fuzzy=True, max_visible=6,
    on_accept=lambda value: vendor_field.set_text(value),
    x=120, y=80, w=220, h=0,
)

# as the user types in your text field:
completer.update_query(text)     # recompute matches; shows when non-empty
completer.visible                 # whether the popup is up
completer.panel_height()          # measured popup height for layout

# input routing:
completer.on_key(key)            # Up/Down/Enter/Escape
completer.on_click(mx, my)
completer.paint(dl)
```

Accepted values feed `on_accept`; recent acceptances are kept in `history` so
they can rank first. Use it behind any `TextField` / cell editor — the
[`DataGrid`](data-grid.md) vendor column and the dashboard search both use it.

## See also

- API: [`elysium.components.completer`](../api/completer.md)
- [Text input and dialogs](text-input-and-dialogs.md)
