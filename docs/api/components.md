# `elysium.components`

The 30 built-in components, grouped by family.

## Text (4)

| Class | Purpose |
|---|---|
| `Label` | Static text |
| `Heading` | Larger emphasis text |
| `Caption` | Small de-emphasized text |
| `Code` | Monospace inline text |

## Action (5)

| Class | Purpose |
|---|---|
| `Button` | The primary action |
| `IconButton` | Square icon-only |
| `OrbButton` | Spherical button (Stylized Music Player demo) |
| `Link` | Underlined text action |
| `Chip` | Compact pill action |

## Input (6)

| Class | Purpose |
|---|---|
| `TextInput` | Single-line |
| `TextArea` | Multi-line |
| `Slider` | Numeric range |
| `Toggle` | Boolean switch |
| `Checkbox` | Boolean + tri-state |
| `Radio` | One-of-N picker |

## Container (5)

| Class | Purpose |
|---|---|
| `Card` | Elevated surface; glass material aware |
| `Panel` | Section divider with header |
| `Group` | Visual grouping |
| `Divider` | Hairline rule |
| `Accordion` | Collapsible section list |

## Feedback (4)

| Class | Purpose |
|---|---|
| `ProgressBar` | Linear or radial fill |
| `Toast` | Brief overlay message |
| `Spinner` | Indeterminate loading |
| `Tooltip` | Hover annotation |

## Navigation (3)

| Class | Purpose |
|---|---|
| `Tabs` | Horizontal tab strip |
| `Breadcrumb` | Stacked path |
| `Pagination` | Page selector |

## Overlay (3)

| Class | Purpose |
|---|---|
| `Popover` | Floating panel anchored to a placement |
| `Menu` | Right-click + dropdown menus |
| `CommandPalette` | Fuzzy-search command launcher |

## Phase 3 — self-host primitives (5)

Shipped to support the Elysium Designer's self-host on the framework.
Every app gets them for free.

| Class | Purpose |
|---|---|
| `Tree` (+ `TreeRow`) | Virtualised hierarchical list with chevron expand + kind-coloured dot + indented label. Author pre-flattens depth; `hit_test_row(x, y)` returns `(row_id, "chevron"|"label")` so dispatch is one call. |
| `NumericField` | TextField-style numeric input with Maya-style **scrub-on-drag** (`scrub_start` / `scrub_drag` / `scrub_end`). Supports min / max clamp + custom format. |
| `FAB` | Floating Action Button. Circular hit-test (not bbox), drop-shadow lift on hover, three variants (`primary` / `accent` / `surface`). |
| `RadialPopover` | Maya-style marking-menu donut. Items are `(id, label)` pairs evenly spaced clockwise from 12 o'clock; `hit_test_item(x, y)` returns the wedge under the cursor. |
| `IconButton` (+ `GlyphAtlas` + `get_default_atlas`) | Icon-only button that resolves names through a process-wide atlas (skin loader auto-populates from `<bundle>/assets/icons/*.png`). Falls back to text rendering when no atlas entry. |

Quick wiring:

```python
import elysium as ely
from elysium import components as ui, layout

tree = ui.Tree(
    x=10, y=40, w=240, h=400,
    rows=[
        ui.TreeRow(id="r",  label="Project",  expandable=True, expanded=True),
        ui.TreeRow(id="w",  label="MainWindow", depth=1),
        ui.TreeRow(id="b",  label="butterfly",  depth=2, selected=True),
    ],
)

nf = ui.NumericField(
    label="Opacity", value=1.0,
    min_value=0.0, max_value=1.0, step=0.01,
    on_change=lambda v: print("opacity:", v),
)

fab = ui.FAB(
    x=580, y=540, w=56, h=56, icon="A", variant="primary",
    on_click=lambda: print("Aether"),
)

marking = ui.RadialPopover(
    items=[("cut", "Cut"), ("copy", "Copy"),
           ("paste", "Paste"), ("delete", "Delete")],
    visible=True,
)

ib = ui.IconButton(icon="save", variant="ghost",
                   on_click=lambda: print("save"))
```

## skin `calc(...)` preprocessor

`elysium.skin.load_skin()` resolves any `"calc(<expr>)"` string in a
numeric position before passing the document to the native loader
(spec §6.5). The expression grammar is intentionally tight:

* decimal + scientific-notation numbers
* operators `+ - * /`
* parentheses + whitespace

Anything else — identifiers, `%`, function calls — raises
`CalcExpressionError` at load time. Use it for arithmetic layout
constants:

```jsonc
{
  "root": {
    "type": "scene",
    "size": { "w": "calc(800 - 116 - 320)", "h": 480 }
  }
}
```

## Base class

| Class | Purpose |
|---|---|
| `Component` | Subclass to author custom components |

## Auto-rendered details

::: elysium.components

## See also

- [Components overview](../guides/components-overview.md)
- [Recipes: custom component](../recipes/15-custom-component.md)
