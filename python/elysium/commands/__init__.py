"""App-level undo/redo + actions — Qt's ``QUndoStack`` / ``QUndoCommand`` /
``QAction``.

A :class:`Command` is a reversible operation (``redo`` applies it, ``undo``
reverts it). An :class:`UndoStack` records executed commands and walks them back
and forth, with optional **merging** (coalescing consecutive edits — e.g. typing
into one undo step), **macros** (grouping several commands into one), a command
**limit**, and a **clean** marker (the saved-state index, for a "modified ●"
indicator).

An :class:`Action` is a single trigger — text + shortcut + enabled/checked
state + a callback — that a menu item, a toolbar button, and a keyboard shortcut
all share, so they never drift out of sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "Command",
    "FunctionCommand",
    "MacroCommand",
    "UndoStack",
    "Action",
]


# ---------------------------------------------------------------------------
# Commands.
# ---------------------------------------------------------------------------

@dataclass
class Command:
    """A reversible operation. ``redo()`` applies it (also called the first time,
    when pushed); ``undo()`` reverts it. Override both. For commands that should
    coalesce (e.g. successive keystrokes), give them a non-negative
    :attr:`merge_id` and implement :meth:`merge_with`."""

    text: str = ""
    merge_id: int = -1

    def redo(self) -> None:  # pragma: no cover - overridden
        pass

    def undo(self) -> None:  # pragma: no cover - overridden
        pass

    def merge_with(self, other: "Command") -> bool:
        """Fold ``other`` into ``self`` (both already executed). Return ``True``
        if merged — the stack then drops ``other``. Default: no merging."""
        return False


@dataclass
class FunctionCommand(Command):
    """A command from two callables — the quick way to make an undoable edit."""

    redo_fn: Callable[[], None] | None = None
    undo_fn: Callable[[], None] | None = None

    def redo(self) -> None:
        if self.redo_fn is not None:
            self.redo_fn()

    def undo(self) -> None:
        if self.undo_fn is not None:
            self.undo_fn()


@dataclass
class MacroCommand(Command):
    """A composite of child commands applied/reverted as one undo step."""

    children: list[Command] = field(default_factory=list)

    def redo(self) -> None:
        for c in self.children:
            c.redo()

    def undo(self) -> None:
        for c in reversed(self.children):
            c.undo()


# ---------------------------------------------------------------------------
# UndoStack.
# ---------------------------------------------------------------------------

@dataclass
class UndoStack:
    """Records commands and undoes/redoes them. ``index`` is the number of
    applied commands (``commands[:index]`` are applied)."""

    limit: int = 0  # 0 = unlimited
    commands: list[Command] = field(default_factory=list, init=False)
    index: int = field(default=0, init=False)
    _clean_index: int = field(default=0, init=False)
    _macro: list[MacroCommand] = field(default_factory=list, init=False)
    on_change: Callable[[], None] | None = None

    # --- push / undo / redo ----------------------------------------------

    def push(self, command: Command) -> None:
        """Execute ``command`` (its ``redo``) and record it. Inside a macro it
        joins the macro instead of the main stack. Clears the redo branch and
        may merge into the previous command."""
        command.redo()
        if self._macro:
            self._macro[-1].children.append(command)
            return
        # Drop any redo branch.
        if self.index < len(self.commands):
            del self.commands[self.index:]
            if self._clean_index > self.index:
                self._clean_index = -1  # clean state was on a discarded branch
        # Try to merge into the top command.
        if (self.commands and command.merge_id >= 0
                and self.commands[-1].merge_id == command.merge_id
                and self.commands[-1].merge_with(command)):
            self._notify()
            return
        self.commands.append(command)
        self.index = len(self.commands)
        self._enforce_limit()
        self._notify()

    def can_undo(self) -> bool:
        return self.index > 0

    def can_redo(self) -> bool:
        return self.index < len(self.commands)

    def undo(self) -> None:
        if not self.can_undo():
            return
        self.index -= 1
        self.commands[self.index].undo()
        self._notify()

    def redo(self) -> None:
        if not self.can_redo():
            return
        self.commands[self.index].redo()
        self.index += 1
        self._notify()

    def undo_text(self) -> str:
        return self.commands[self.index - 1].text if self.can_undo() else ""

    def redo_text(self) -> str:
        return self.commands[self.index].text if self.can_redo() else ""

    # --- macros -----------------------------------------------------------

    def begin_macro(self, text: str = "") -> None:
        self._macro.append(MacroCommand(text=text))

    def end_macro(self) -> None:
        if not self._macro:
            return
        macro = self._macro.pop()
        if not macro.children:
            return
        # The children already executed on push; record the macro without
        # re-running it.
        if self._macro:
            self._macro[-1].children.append(macro)
            return
        if self.index < len(self.commands):
            del self.commands[self.index:]
        self.commands.append(macro)
        self.index = len(self.commands)
        self._enforce_limit()
        self._notify()

    # --- clean state ------------------------------------------------------

    def set_clean(self) -> None:
        """Mark the current state as saved."""
        self._clean_index = self.index
        self._notify()

    def is_clean(self) -> bool:
        return self.index == self._clean_index

    def clear(self) -> None:
        self.commands.clear()
        self.index = 0
        self._clean_index = 0
        self._macro.clear()
        self._notify()

    # --- internals --------------------------------------------------------

    def _enforce_limit(self) -> None:
        if self.limit and len(self.commands) > self.limit:
            drop = len(self.commands) - self.limit
            del self.commands[:drop]
            self.index -= drop
            self._clean_index -= drop  # may go negative → "never clean"

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()


# ---------------------------------------------------------------------------
# Action.
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """A shared trigger for a menu item, a toolbar button, and a shortcut. Keeps
    one source of truth for text / enabled / checked so the surfaces can't
    drift apart."""

    text: str = ""
    shortcut: str | None = None
    icon: Callable[[Any, float, float, float, Any], None] | None = None
    tooltip: str = ""
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    danger: bool = False
    on_triggered: Callable[[], None] | None = None

    def trigger(self) -> bool:
        """Fire the action. Toggles ``checked`` if checkable. Returns ``True``
        if it ran (``False`` when disabled)."""
        if not self.enabled:
            return False
        if self.checkable:
            self.checked = not self.checked
        if self.on_triggered is not None:
            self.on_triggered()
        return True

    def to_menu_item(self):
        """A ``components.MenuItem`` wired to this action."""
        from elysium.components import MenuItem
        return MenuItem(label=self.text, shortcut=self.shortcut,
                        danger=self.danger,
                        on_click=(self.trigger if self.enabled else None))

    def to_tool_button(self):
        """A ``shell.ToolButton`` wired to this action."""
        from elysium.shell import ToolButton
        return ToolButton(label="" if self.icon else self.text, icon=self.icon,
                          tooltip=self.tooltip or self.text,
                          enabled=self.enabled, checked=self.checked,
                          on_click=self.trigger)
