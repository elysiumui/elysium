# Commands and undo

`elysium.commands` gives an app a real undo history and a reusable action model —
Qt's `QUndoStack` / `QUndoCommand` / `QAction`.

## The undo stack

Every reversible edit is a `Command` with `redo()` and `undo()`. The simplest is
`FunctionCommand`, which takes two callables:

```python
from elysium.commands import UndoStack, FunctionCommand

stack = UndoStack(limit=200, on_change=refresh_toolbar)

def set_price(row, new, old):
    stack.push(FunctionCommand(
        text=f"Set price to {new}",
        redo_fn=lambda: row.__setitem__("price", new),
        undo_fn=lambda: row.__setitem__("price", old),
    ))

stack.undo(); stack.redo()
stack.can_undo(); stack.can_redo()
stack.undo_text(); stack.redo_text()    # for menu labels
```

`push` runs the command's `redo()` immediately, so you describe the edit once.

## Subclassing Command

For richer edits, subclass `Command` and implement `redo` / `undo` (and
optionally `merge_with` so a run of keystrokes collapses into one undo step via a
shared `merge_id`):

```python
from elysium.commands import Command

class RenameCommand(Command):
    def __init__(self, item, new):
        super().__init__(text="Rename")
        self.item, self.new, self.old = item, new, item.name
    def redo(self): self.item.name = self.new
    def undo(self): self.item.name = self.old
```

## Macros

Group several commands so they undo together:

```python
stack.begin_macro("Bulk price change")
for row in selection:
    stack.push(SetPrice(row, row["price"] * 1.1))
stack.end_macro()
```

## Clean state

Mark the stack clean after a save so you can show an unsaved-changes indicator:

```python
stack.set_clean()
title = "Untitled *" if not stack.is_clean() else "Untitled"
```

## Actions

`Action` is a command-bus entry — `text`, `shortcut`, `icon`, `tooltip`,
`enabled`, `checkable` / `checked`, `danger`, and `on_triggered`. It can render
itself into a menu item or a tool button so one definition drives the menu, the
toolbar and the keyboard:

```python
from elysium.commands import Action

undo_action = Action(text="Undo", shortcut="Ctrl+Z",
                     enabled=stack.can_undo(), on_triggered=stack.undo)

menu_item   = undo_action.to_menu_item()
tool_button = undo_action.to_tool_button()
undo_action.trigger()
```

## See also

- API: [`elysium.commands`](../api/commands.md)
- [Documents and editing](documents.md)
