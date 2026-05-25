# Components overview

The 30 components ship in `elysium.components`. They are
opinionated, pre-styled, and theme-aware. Each one paints into
the skin's display list; each one wires up standard hook names
(`button_id.click`, `slider_id.change`, etc.).

## Reach the components

```python
from elysium.components import Button, Slider, Toggle, Popover  # etc.
```

Components are Python classes you instantiate and attach. They
read from the active [Theme](theming.md) for colors, motion, and
materials.

## The seven families

### Text (4)

| Component | Purpose |
|---|---|
| Label | Static text |
| Heading | Larger emphasis text with weight + tracking |
| Caption | Small de-emphasized text (footnotes, hints) |
| Code | Monospace inline text |

### Action (5)

| Component | Purpose |
|---|---|
| Button | The primary action |
| IconButton | Square icon-only button |
| OrbButton | Spherical button (stylized music player demo) |
| Link | Underlined text action |
| Chip | Compact pill action (often used in tag lists) |

### Input (6)

| Component | Purpose |
|---|---|
| TextInput | Single-line text |
| TextArea | Multi-line text |
| Slider | Numeric range |
| Toggle | Boolean switch |
| Checkbox | Boolean with tri-state option |
| Radio | One-of-N picker |

### Container (5)

| Component | Purpose |
|---|---|
| Card | Surface with elevation; supports glass materials |
| Panel | Section divider with header |
| Group | Visual grouping without surface change |
| Divider | Hairline rule |
| Accordion | Collapsible section list |

### Feedback (4)

| Component | Purpose |
|---|---|
| ProgressBar | Linear or radial fill |
| Toast | Brief overlay message (Pomodoro tutorial) |
| Spinner | Indeterminate loading |
| Tooltip | Hover-triggered annotation |

### Navigation (3)

| Component | Purpose |
|---|---|
| Tabs | Horizontal tab strip |
| Breadcrumb | Stacked path |
| Pagination | Page selector |

### Overlay (3)

| Component | Purpose |
|---|---|
| Popover | Floating panel anchored to a placement |
| Menu | Right-click and dropdown menus |
| CommandPalette | Cmd+K-style fuzzy command launcher |

## Component shape

Every component takes:

- **id**: hook prefix. Determines event names (`btn.click` etc.).
- **bindings**: signals or values for each reactive property.
- **style overrides**: optional theme token replacements.

Example:

```python
from elysium.components import Button
from elysium.reactive import signal

label = signal("Click me")

Button(
    id="primary",
    label=label,           # reactive: re-renders on signal.set
    on_click=lambda e: label.set("Clicked!"),
    style={"radius": 12, "fill": "{theme.accent}"},
)
```

Properties can be plain values or signals. Signals re-render on
change automatically.

## Hook names

A component with id "save" emits:

- `save.click`: primary action.
- `save.hover`: pointer enter / leave.
- `save.press`: pointer-down.
- `save.focus` / `save.blur`: focus ring.
- `save.disabled.click`: fires even when disabled (for analytics).

Slider, Toggle, Checkbox add `save.change` with the new value.

## Theme awareness

Components read tokens from the active theme:

- `theme.accent` for primary fill.
- `theme.on_accent` for text over the accent.
- `theme.surface` for cards / panels.
- `theme.motion` for animation durations.

Switching themes at runtime (`theme.set_theme(new_theme)`) updates
every component in one frame.

## Custom components

For one-off shapes, drop down to Canvas + DisplayList. For a
slightly-customized version of an existing component, override
specific style tokens:

```python
Button(
    id="ghost",
    label="Ghost",
    style={
        "fill": "transparent",
        "stroke": "{theme.accent}",
        "text_fill": "{theme.accent}",
    },
)
```

For a structurally different component, compose from primitives;
see [Recipes: build a custom component](../recipes/15-custom-component.md).

## See also

- [Layout](layout.md): arrange the components.
- [Theming](theming.md): tokens components read from.
- [Events](events.md): handlers for component hooks.
