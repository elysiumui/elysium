# Layout

The `elysium.layout` package contains the five containers that
arrange components: **Stack**, **Row**, **Col**, **Grid**, and
**Form**. Use them in skins and in code.

## The five containers

| Container | Axis | Children | Used for |
|---|---|---|---|
| Stack | Z (overlay) | Anything | Layered overlays, modals |
| Row | X (horizontal) | Anything | Toolbars, button strips |
| Col | Y (vertical) | Anything | Lists, settings panels |
| Grid | XY (2D) | Anything | Galleries, calendars |
| Form | Y (label + control pairs) | Form-row components | Settings dialogs |

## Stack

```python
from elysium.layout import Stack

Stack(children=[
    background_card,
    title_label,
    close_button,
])
```

Children draw in order; the last child is on top. Great for
overlays, modals, dropdowns. Each child can position itself with
`align` and `offset` properties.

## Row and Col

```python
from elysium.layout import Row, Col

Row(spacing=12, align="center", children=[
    icon_button,
    title_label,
    Spacer(),       # consumes remaining space
    save_button,
])

Col(spacing=8, align="stretch", children=[
    name_input,
    email_input,
    submit_button,
])
```

Properties:

- **spacing**: pixels between children.
- **align**: how children align on the cross-axis (`start`,
  `center`, `end`, `stretch`).
- **justify**: how children space on the main-axis (`start`,
  `center`, `end`, `between`, `around`, `evenly`).

## Grid

```python
from elysium.layout import Grid

Grid(
    columns=3,
    spacing=8,
    children=[card_a, card_b, card_c, card_d, card_e, card_f],
)
```

Items flow into rows. For more control:

```python
Grid(
    columns="1fr 2fr 1fr",     # CSS-like sizing
    rows="auto auto",
    gap=12,
    children=[
        Grid.Cell(child=header, column_span=3),
        Grid.Cell(child=sidebar, row=2, column=1),
        Grid.Cell(child=main,    row=2, column=2),
        Grid.Cell(child=aux,     row=2, column=3),
    ],
)
```

The `1fr` / `2fr` syntax expresses fractional widths;
`Grid.Cell(...)` declares span.

## Form

```python
from elysium.layout import Form

Form(label_width=120, children=[
    Form.Row("Name",  TextInput(id="name_input")),
    Form.Row("Email", TextInput(id="email_input")),
    Form.Row("Notify me",  Toggle(id="notify_toggle")),
])
```

`Form.Row(label, control)` adds a labeled row. The Form lays out
label + control pairs consistently, with the labels right-aligned
(default).

## Alignment constants

A few useful constants for align / justify properties:

```python
from elysium.layout import START, CENTER, END, STRETCH, BETWEEN

Row(align=CENTER, justify=BETWEEN, children=[...])
```

Same semantics as flexbox. Strings ("center", "between") and
constants are interchangeable.

## Spacing and padding

| Property | Where |
|---|---|
| `spacing` | Between children (gap) |
| `padding` | Around the container's inner edge |
| `margin` | Around the container's outer edge (in its parent's layout) |

Numeric (uniform) or per-side: `padding={"top": 12, "x": 16}`.

## Reactive layouts

Container properties can be signals:

```python
spacing = signal(8)
Row(spacing=spacing, children=[...])
```

Setting `spacing.set(16)` re-lays-out the row immediately.

## Layout vs skin

Containers can be expressed in two ways:

1. **In code** (the examples above): for dynamic UIs that compose
   different children based on state.
2. **In the skin's `document.json`**: declared statically alongside
   shapes and text. The Designer authors layouts this way.

A typical app uses both: the skin defines the broad structure, the
code injects dynamic lists.

## Performance

Layout runs on the Python thread; computed lazily when any
property changes. Budget: ~50 µs for a moderate hierarchy (50
children). Deep nesting (10+ levels) is fine.

## See also

- [Components overview](components-overview.md): the children
  you put in containers.
- [Reactive](reactive.md): signal-driven layout.
- [Theming](theming.md): spacing tokens.
