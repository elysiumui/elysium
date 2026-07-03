# Text input, dialogs & data widgets

Tier-1 brings real editable text, model/view data tables, standard dialogs, and
data-entry widgets to Elysium. This guide is the practical reference; for a Qt
class-by-class map see [Porting from PySide6/Qt](porting-from-qt.md).

## The input router

Editable widgets don't poll the keyboard themselves — a per-window
`InputRouter` does it once and routes to the focused widget.

```python
router = win.input_router()
router.set_widgets([name, age, combo])   # any objects with focus_id + focus_rect
router.focus_widget("name")
# each frame, after the window has polled:
router.tick()
```

`tick()` drains key events + IME preedit and:

* sends control keys (arrows, Backspace, Home/End, Ctrl+A/Z) to the focused
  widget's `on_key`, and printable text to `on_text`;
* moves focus on unclaimed Tab/arrows;
* orchestrates **Cmd/Ctrl + C/X/V** against the system clipboard;
* parks the OS **IME** candidate popup at the caret.

A widget participates by implementing the `Editable` protocol (TextField,
SpinBox, DateEdit, EditableComboBox already do).

## Text editing

`TextField` (single-line) and `TextArea` (multi-line) embed an
`EditableText` model: caret, selection (Shift+arrows / click-drag), word jump
(Ctrl/Opt+arrow), Home/End, undo/redo (Cmd/Ctrl+Z, coalesced typing),
cut/copy/paste, IME, password mode, and validators / masks.

```python
from elysium.components import TextField
from elysium.text import IntValidator, Mask

qty   = TextField(label="Qty", validator=IntValidator(1, 999).validate, focus_id="qty")
phone = TextField(label="Phone", mask=Mask("000-000-0000"), focus_id="phone")
```

Clipboard directly: `win.set_clipboard_text(s)` / `win.get_clipboard_text()`.

## Standard dialogs

Native file dialogs (real OS picker on macOS/Windows/Linux):

```python
from elysium import dialogs as D
path = D.open_file(title="Open", filter_label="Images", filter_patterns=["*.png", "*.jpg"])
out  = D.save_file(default_name="export.png")
folder = D.pick_folder()
```

Elysium-rendered modals via a `DialogHost` (borderless, themed, non-blocking):

```python
host = D.DialogHost(win)
dlg = host.message("Delete?", "This can't be undone.", buttons=["Cancel", "Delete"])
dlg.on_result = lambda label: ... if label == "Delete" else None
# also: host.input(...), host.progress(...), host.color(...), host.font(...)
# each frame: host.update(dt); host.paint(dl); host.on_mouse_press(...)/on_key(...)
```

## Model/View tables

```python
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate

model = ItemModel(
    rows=[{"name": "Ada", "age": 36}, {"name": "Alan", "age": 41}],
    columns=[Column("name", editable=True, delegate=EditableCellDelegate()),
             Column("age", align="right")],
)
table = TableView(x=0, y=0, w=600, h=400, model=model)
model.toggle_sort("age")                 # asc → desc → unsorted on repeat
model.filter(lambda r: r["age"] >= 40)   # live filter
# header click sorts; double-click an editable cell edits it; views virtualize.
```

A `QtItemModelAdapter(model)` exposes `rowCount`/`columnCount`/`data`/`setData`
for code ported from `QAbstractItemModel`. `TreeView` + `TreeNode` cover
hierarchies; `Mesh3DDelegate` renders a GPU 3-D thumbnail per cell.

## Data-entry widgets

```python
from elysium.components.dataentry import SpinBox, DoubleSpinBox, DateEdit, TimeEdit, CalendarWidget, EditableComboBox
import datetime as dt

n   = SpinBox(value=3, minimum=0, maximum=10, step=1, wrap=True, focus_id="n")
amt = DoubleSpinBox(value=1.50, minimum=0, maximum=100, decimals=2, focus_id="amt")
day = DateEdit(date=dt.date.today(), focus_id="day")        # segmented Y/M/D
cal = CalendarWidget(selected=dt.date.today(), focus_id="cal")
who = EditableComboBox(items=["Ada", "Alan", "Grace"], focus_id="who")  # filter-as-you-type
```

All are keyboard-editable through the same `InputRouter`.
