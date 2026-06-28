# Tables & Model/View

Elysium's [Model/View](../api/modelview.md) mirrors Qt's: an `ItemModel` owns
the data, a view (`TableView` / `ListView` / `TreeView`) renders the visible
window, and delegates control per-cell rendering and editing. Everything
virtualizes, so a 100k-row table stays at frame rate.

## Model + columns

```python
from elysium.modelview import ItemModel, Column

model = ItemModel(
    rows=[{"name": f"Item {i}", "qty": i % 50, "price": i * 1.5} for i in range(100_000)],
    columns=[
        Column("name", width=240),
        Column("qty", width=80, align="right"),
        Column("price", width=100, align="right"),
    ],
)
```

## Sorting & filtering

Sorting and filtering produce a derived *view* over the source rows — cheap and
non-destructive.

```python
model.toggle_sort("price")                  # cycle asc → desc → unsorted
state_key, descending = model.sort_state
model.filter(lambda r: r["qty"] > 0)        # predicate filter
model.filter(None)                          # clear
visible_count = model.row_count()           # rows after sort+filter
```

## Delegates

A delegate paints (and optionally edits) a cell. Ship-built ones cover text and
inline editing; the 3-D delegate has no Qt equivalent.

```python
from elysium.modelview import TextDelegate, EditableCellDelegate, Mesh3DDelegate, Column

cols = [
    Column("name", delegate=EditableCellDelegate()),   # double-click to edit
    Column("qty", align="right", delegate=TextDelegate(align="right")),
    Column("model", width=80, delegate=Mesh3DDelegate()),  # GPU 3-D thumbnail per row
]
```

Write a custom delegate by implementing the `Delegate` protocol
(`paint(dl, rect, value, *, selected, theme)` and `editable()`).

## Inline editing

```python
from elysium.modelview import TableView

table = TableView(x=0, y=0, w=600, h=400, model=model)
editor = table.begin_edit(0, 0)             # returns a TextField over the cell
editor.set_value("New name")
table.commit_edit()                         # or table.cancel_edit()
```

## Scale & virtualization

The view paints only the rows inside its rect — the windowing math lives in
[`elysium.components.virtual`](../api/virtual.md) (`row_window` /
`visible_window`). Pair a view with a [`ScrollBar`](../api/scroll.md), or use
`VirtualList` / `VirtualForm` directly for custom rows:

```python
from elysium.components.virtual import VirtualList

rows = VirtualList(
    x=0, y=0, w=400, h=300, item_count=100_000, item_height=28.0,
    render_item=lambda dl, i, x, y, w, h: dl.draw_text(f"Row {i}", x + 8, y + 18, 14, (0, 0, 0, 255)),
)
# paints ~11 rows regardless of item_count
```

## Trees

`TreeView` renders a `TreeNode` hierarchy with the same virtualization:

```python
from elysium.modelview import TreeView, TreeNode

root = TreeNode("r", "Root", children=[TreeNode("a", "A"), TreeNode("b", "B")], expanded=True)
tree = TreeView(x=0, y=0, w=240, h=400, nodes=[root])
```

For the full read/create/update/delete flow see [CRUD app](crud-app.md).
