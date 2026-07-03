# Styling & accessibility

Tier 7 adds the polish layer: declarative per-widget **styling**
(`elysium.styling`), **autocomplete** (`elysium.components.completer`), a
semantic **accessibility** layer (`elysium.accessibility`), and **per-widget
fonts**.

## Declarative styling (QSS-like)

A `StyleSheet` maps selectors to property overrides and resolves them per widget
by type, `#id`, `.class`, and `:state`.

```python
from elysium.styling import StyleSheet

sheet = StyleSheet({
    "Button":            {"radius": 6},
    "Button.primary":    {"radius": 10},
    "Button:hover":      {"radius": 12},
    "#save":             {"radius": 14},
})

# merge every matching rule in CSS specificity order (id ≫ class/state ≫ type):
props = sheet.resolve("Button", id="save", classes=["primary"], states=["hover"])
sheet.apply(button, states=["hover"] if hovered else [])   # writes onto the widget
```

States: `hover` · `focus` · `pressed` · `disabled` · `checked` · `active`. A
rule matches only when **all** its classes and states are active. It's a
resolver layered over the token reads — widgets stay theme-driven and take
overrides only where a rule matches.

## Autocomplete

```python
from elysium.components.completer import Completer

comp = Completer(candidates=cities, fuzzy=True, x=field.x, y=field.bottom,
                 w=field.w, on_accept=field.set_text)
comp.update_query(field.text)     # prefix, then contains, then fuzzy; history first
comp.on_key("down")               # Up/Down wrap · Enter accept · Esc close
comp.paint(dl)                    # popover under the field, prefix highlighted
```

## Accessibility

Each component reports a semantic `AccessibleNode` (a `Role` + label/value/state)
for the accessibility tree:

```python
from elysium.accessibility import Role, AccessibleNode, announce, paint_focus_ring

node = AccessibleNode(role=Role.CHECK_BOX, label="Word wrap",
                      checked=editor.wrap, focusable=True, focused=is_focused)
tree = node.to_dict()             # the accesskit-bridge shape

announce("Saved")                 # live region (polite); announce(..., assertive=True) interrupts
paint_focus_ring(dl, x, y, w, h, theme.primary)   # honours high-contrast prefs
```

`Announcer` (and the module-level `announce`) queue live-region messages; wire
`announcer().set_sink(...)` to the accesskit bridge. `paint_focus_ring`
thickens and goes fully opaque under high-contrast. Table cells carry
`row_index` / `col_index` / `col_header` so a screen reader can read "row 3,
Age, 42".

## Per-widget fonts

`Label` takes an opt-in `font_family` / `weight`:

```python
from elysium.components import Label
Label(text="Heading", size=20, font_family="Inter", weight=700)
```

With an override the label renders through the Skia paragraph path (real family
+ weight); without one it keeps the default single-line path unchanged (so
existing golden snapshots don't move). Combine with the app-wide
[`set_ui_font`](theming.md) for a base font plus per-widget exceptions.
