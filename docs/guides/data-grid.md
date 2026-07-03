# The data grid

`elysium.modelview.grid.DataGrid` is an Excel-grade editable spreadsheet built
over an [`ItemModel`](../api/modelview.md). It is the widget a bulk editor is
built around — think Google Sheets / the Shopify bulk editor: frozen columns,
rectangular selection, copy/paste from Excel, fill-down, per-cell validation and
pending-edit highlighting, over a virtualized 100k-row body.

It complements the read-oriented `TableView` in `elysium.modelview`; reach for
`DataGrid` when cells are **editable in bulk**.

The runnable reference app is
[`examples/variantproof-grid/`](https://github.com/).

## A minimal grid

`DataGrid` wraps a model and a column list. `formatter(value, column)` controls
display text; `frozen_cols` pins the leading columns.

```python
from elysium.modelview import ItemModel, Column
from elysium.modelview.grid import DataGrid

cols = [Column(key="handle", width=160), Column(key="title", width=180),
        Column(key="sku", width=120),
        Column(key="price", width=90, align="right")]
rows = [{"handle": "aurora-merino-crew", "title": "Aurora Merino Crew",
         "sku": "AMC-NVY-S", "price": 128.0}, ...]

grid = DataGrid(
    model=ItemModel(rows=rows, columns=cols),
    frozen_cols=2,                                  # pin handle + title
    formatter=lambda v, c: (f"${v:,.2f}" if c.key == "price" else str(v)),
    x=0, y=0, w=900, h=600,
)
grid.paint(dl)
```

The frozen columns paint in their own band; the remaining columns scroll
horizontally (`scroll_x`) under a clip, with a divider between the two bands.
Rows are virtualized — only the visible window (`visible_rows()`) is drawn.

## Selection

`select(row, col, extend=False)` sets the active cell; `extend=True` grows a
rectangular selection from the anchor (this is what Shift-click / drag do).
`selected_range()` returns `(r0, c0, r1, c1)` in view coordinates.

```python
grid.select(1, 3)                 # active cell
grid.select(4, 5, extend=True)    # rectangle (1,3)..(4,5)
r0, c0, r1, c1 = grid.selected_range()
```

Wire pointer events through `on_press` / `on_drag` / `on_release` — they handle
both range-select and column-resize (dragging a header border).

## Editing, validation and pending state

`set_cell(view_row, col_index, value)` writes through to the model and marks the
cell **dirty**. Register a per-column validator (`key → fn(value) -> error|None`)
and failed cells get a red badge.

```python
grid.validators["sku"] = lambda v: "duplicate SKU" if is_dup(v) else None

grid.set_cell(0, 3, 132.0)        # green pending-edit highlight
grid.set_cell(2, 2, "CLS-WHT-M")  # runs the sku validator

grid.dirty_count()                # how many edits are pending
grid.error_count()                # how many failed validation
grid.is_dirty(view_row, col)      # per-cell
grid.cell_error(view_row, col)    # the error string, or None
```

Cell state is keyed by **row identity**, not row index, so a pending edit or
error stays attached to its row across sorting and filtering. `clear_pending()`
resets after a successful save/sync.

## Copy, paste and fill-down

These mirror a spreadsheet and use the native clipboard:

```python
tsv = grid.copy()           # selection → tab-separated text
grid.copy_to_clipboard()    # …straight to the OS clipboard

grid.paste(tsv)             # parse a TSV block into the target range
grid.fill_down()            # copy the top row of the selection down
```

`paste` parses a rectangular TSV block (as produced by Excel / Sheets) and writes
it cell-by-cell from the active cell, running each column's validator as it goes.

## Columns: resize, reorder, show/hide

```python
grid.resize_col("price", 120)       # also via header-border drag
grid.move_col("vendor", 1)          # reorder
grid.set_col_visible("type", False) # hide (column chooser)
grid.visible_cols()                 # the live, ordered, visible columns
```

## Sorting

Sorting is on by default (`DataGrid(sortable=True)`) and delegates to the model.
Clicking a column header cycles **ascending → descending → unsorted**; the active
column shows a ▴ / ▾ caret. It's configurable per column — set
`Column(sortable=False)` to make a column unsortable, or `DataGrid(sortable=False)`
to turn header-click sorting off entirely.

```python
grid = DataGrid(model=model, sortable=True)   # default
grid.sort_by("price")                          # programmatic: asc → desc → off
```

Sorting changes the view order (cell state stays attached to its row, since it's
keyed by row identity), so a pending edit follows its row as it moves.

## Filtering

A per-column filter row is optional — opt in with `DataGrid(filterable=True)` and
a search box appears under each header. Typing narrows the body live (matching
columns are AND-combined); a column opts out with `Column(filterable=False)`.

```python
grid = DataGrid(model=model, filterable=True)

# programmatic (fully testable):
grid.set_filter("vendor", "Crestline")    # case-insensitive substring by default
grid.set_filter("type", "shirt")          # combine — rows must match both
grid.active_filters()                      # {"vendor": "Crestline", "type": "shirt"}
grid.clear_filters()

# interactive: route input to the focused filter box
grid.focus_filter("vendor")    # or set on a filter-box click via on_press
grid.on_text("Crest")          # append typed text
grid.on_backspace()            # delete a character
```

Pass a custom matcher to change the search semantics (exact, prefix, numeric
range, …):

```python
grid = DataGrid(model=model, filterable=True,
                filter_match=lambda value, query: str(value).startswith(query))
```

Filtering uses the model's `view()`, so `row_count()`, `visible_rows()` and
`cell_at` all see the narrowed set automatically and virtualization still holds.

## Chrome around the grid

`DataGrid` is just the grid surface. The reference app frames it with a
[`ToolBar`](app-shell.md) of transforms, a saved-views rail, and a bottom
pending-changes tray driven by `dirty_count()` / `error_count()`:

```python
pending, errors = grid.dirty_count(), grid.error_count()
dl.draw_text(f"{pending} pending edits · {errors} need attention", 30, ty, 12, muted)
```

## See also

- API: [`elysium.modelview.grid`](../api/grid.md),
  [`elysium.modelview`](../api/modelview.md)
- Pattern: [Tables and Model/View](../patterns/tables-and-modelview.md)
- [Build a Shopify-style desktop app](../tutorials/shopify-style-desktop-app.md)
