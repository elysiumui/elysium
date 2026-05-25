# `elysium.layout`

The five layout containers plus alignment constants.

## Containers

| Class | Axis | Children |
|---|---|---|
| `Stack` | Z (overlay) | Anything |
| `Row` | X (horizontal) | Anything |
| `Col` | Y (vertical) | Anything |
| `Grid` | XY | Anything; `Grid.Cell` for span control |
| `Form` | Y (label + control pairs) | `Form.Row(label, control)` |

## Helpers

| Class / fn | Purpose |
|---|---|
| `Spacer` | Consumes remaining space in a Row / Col |
| `Grid.Cell(child, row=, column=, row_span=, column_span=)` | Explicit grid placement |
| `Form.Row(label, control)` | Labeled form row |

## Alignment constants

`START`, `CENTER`, `END`, `STRETCH`, `BETWEEN`, `AROUND`, `EVENLY`.

Both string ("center") and constant (`CENTER`) forms are accepted.

## Auto-rendered details

::: elysium.layout

## See also

- [Layout](../guides/layout.md)
- [Components overview](../guides/components-overview.md)
