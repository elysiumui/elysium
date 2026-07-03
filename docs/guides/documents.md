# Documents & editing

Tier 6 adds the building blocks of an editor: **undo/redo + actions**
(`elysium.commands`), **rich text** (`elysium.text.richtext`), and **inter-widget
drag-and-drop** (`elysium.dnd`). See `examples/notes-demo/` for all three in one
app, and the [Qt porting guide](porting-from-qt.md#documents-editing-tier-6) for
the class map.

## Undo / redo + actions

A `Command` is a reversible operation; an `UndoStack` records them.

```python
from elysium.commands import UndoStack, FunctionCommand, Action

undo = UndoStack()
undo.push(FunctionCommand(text="insert", redo_fn=do_insert, undo_fn=undo_insert))
undo.undo(); undo.redo()
```

* **Merging** — give commands a shared `merge_id` and implement `merge_with` to
  coalesce a burst (e.g. one keystroke per `push`) into a single undo step.
* **Macros** — `begin_macro("rename") … end_macro()` groups several pushes into
  one step.
* **Clean state** — `set_clean()` marks the saved point; `is_clean()` drives a
  "modified ●" indicator. A `limit` caps history; `on_change` fires on every
  change (refresh your Undo/Redo buttons there).

An `Action` is one shared trigger for a menu item, a toolbar button, and a
shortcut — so they never drift:

```python
undo_action = Action(text="Undo", shortcut="Ctrl+Z", on_triggered=undo.undo)
undo.on_change = lambda: setattr(undo_action, "enabled", undo.can_undo())

toolbar.items = [undo_action.to_tool_button(), ...]   # shell.ToolBar
menu = [undo_action.to_menu_item(), ...]              # components.Menu
```

## Rich text

A `RichDocument` is a sequence of styled `Run`s, inline `Image`s, and paragraph
`Break`s; a `RichTextView` lays it out and renders it.

```python
from elysium.text.richtext import RichDocument, Run, Break, Image, RichTextView

doc = RichDocument(default_size=15)
doc.add(Run(text="Title", bold=True, size=22)).add(Break())
doc.add(Run(text="A ")).add(Run(text="link", link="https://elysiumui.com"))
doc.add(Run(text=" and ")).add(Run(text="italic", italic=True))

view = RichTextView(document=doc, x=20, y=20, w=360, on_link=open_url)
view.paint(dl)                       # word-wrapped, baseline-aligned
clicked = view.on_click(mx, my)      # follows a hyperlink if one is hit
```

Bold is real font weight and italic a slant variation axis (via the Skia
paragraph path) — not faux effects; mixed sizes on a line share a baseline.

## Drag-and-drop

In-app, widget-to-widget DnD (distinct from native file-drop in
`elysium.native`).

```python
from elysium.dnd import DragController, DropZone, MimeData

drag = DragController()
drag.add_zone(DropZone(rect=(x, y, w, h),
                       accept=lambda m: m.has_format("application/x-note"),
                       on_drop=lambda m, px, py: move_note(m.data(...), px, py)))

# from a draggable source's press:
drag.press(mx, my, MimeData.from_text("note-3"), hotspot=(10, 10))
drag.move(mx, my)       # past a small threshold → a real drag (a click is safe)
drag.release(mx, my)    # delivers to the accepting zone under the cursor
drag.paint(dl)          # highlights the target + draws the drag ghost
```

Pair it with an `UndoStack` (as the notes demo does) so a drag-reorder is itself
undoable.

## Notes

* Per-paragraph block styles (alignment, lists) and an editable
  `RichTextEdit` (caret + selection over styled runs) are tracked follow-ups;
  the document model, layout, view, and hyperlink hit-testing are available now.
