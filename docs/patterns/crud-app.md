# CRUD app

A create / read / update / delete screen is the canonical line-of-business UI.
This pattern wires an [`ItemModel`](../api/modelview.md) to a virtualized
[`TableView`](../api/modelview.md), edits rows in place, and persists with
[`Settings`](../api/settings.md). The runnable version is
[`examples/qt-parity-demo`](https://github.com/elysiumui/elysium/tree/main/examples/qt-parity-demo).

## The model

`ItemModel` holds the rows (dicts or objects) and derives a sorted/filtered
*view*; the `TableView` only paints the visible window, so it scales.

```python
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate

model = ItemModel(
    rows=[
        {"name": "Ada Lovelace", "role": "Engineer", "age": 36},
        {"name": "Alan Turing", "role": "Researcher", "age": 41},
    ],
    columns=[
        Column("name", width=200, editable=True, delegate=EditableCellDelegate()),
        Column("role", width=160, editable=True, delegate=EditableCellDelegate()),
        Column("age", width=70, align="right"),
    ],
)
table = TableView(x=20, y=80, w=520, h=360, model=model)
```

## Create

Append a row from the form fields; the view updates on the next frame.

```python
def add_person(name_field, role_field, age_spin, model):
    model.append({
        "name": name_field.value or "Unnamed",
        "role": role_field.value or "—",
        "age": age_spin.value,
    })
```

## Read — sort & filter

Header clicks sort; a search box filters. Both operate on the derived view, so
the source rows are untouched.

```python
model.toggle_sort("age")                      # asc → desc → unsorted
model.filter(lambda r: r["age"] >= 40)        # live filter
model.filter(None)                            # clear
```

## Update — inline edit

A `TableView` over editable columns edits in place: double-click a cell (or call
`begin_edit`) to get a `TextField` editor, then commit back to the model.

```python
editor = table.begin_edit(0, 0)               # row 0, column 0
editor.set_value("Augusta Ada King")
table.commit_edit()                           # writes to the model
```

## Delete

Remove the selected row.

```python
def delete_selected(table, model):
    row = table.selected_row
    if row >= 0:
        model.remove(model.view()[row])
```

## Persist

Save the table state (and window geometry) with `Settings`; it writes atomically
to the per-user config dir.

```python
from elysium.settings import Settings

settings = Settings("contacts", autosave=True)
settings.set("rows", model.rows())            # JSON-serializable rows
# On next launch:
rows = settings.get("rows", [])
```

## Driving it

Register the form fields with the window's `InputRouter` and dispatch clicks to
the table from your frame loop; see [Forms & validation](forms-and-validation.md)
for the input wiring and [Tables & Model/View](tables-and-modelview.md) for
delegates and virtualization. To test the whole flow headlessly, drive it with
[`UiHarness`](../api/testing.md).
