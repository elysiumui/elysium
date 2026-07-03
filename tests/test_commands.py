"""Tier 6 Phase 1 — command framework: Command, UndoStack, Action."""
from __future__ import annotations

from dataclasses import dataclass

from elysium.commands import (
    Command, FunctionCommand, MacroCommand, UndoStack, Action,
)


@dataclass
class _Add(Command):
    """Append a value to a shared list; coalesce consecutive adds."""
    target: list = None
    value: int = 0

    def redo(self):
        self.target.append(self.value)

    def undo(self):
        self.target.pop()

    def merge_with(self, other):
        # Merge by absorbing the other's effect (the value stays appended).
        if isinstance(other, _Add):
            self.value = other.value
            return True
        return False


def _func_cmd(log, name):
    return FunctionCommand(
        text=name,
        redo_fn=lambda: log.append(f"do:{name}"),
        undo_fn=lambda: log.append(f"undo:{name}"))


# --- commands --------------------------------------------------------------

def test_function_command_redo_undo():
    log = []
    c = _func_cmd(log, "A")
    c.redo(); c.undo()
    assert log == ["do:A", "undo:A"]


# --- undo stack basics -----------------------------------------------------

def test_push_executes_and_records():
    data = []
    st = UndoStack()
    st.push(_Add(text="add 1", target=data, value=1))
    assert data == [1]
    assert st.can_undo() and not st.can_redo()
    assert st.undo_text() == "add 1"


def test_undo_redo_walk():
    data = []
    st = UndoStack()
    st.push(_Add(target=data, value=1))
    st.push(_Add(target=data, value=2))
    assert data == [1, 2]
    st.undo()
    assert data == [1] and st.can_redo()
    st.undo()
    assert data == [] and not st.can_undo()
    st.redo()
    assert data == [1]
    st.redo()
    assert data == [1, 2] and not st.can_redo()


def test_push_clears_redo_branch():
    data = []
    st = UndoStack()
    st.push(_Add(target=data, value=1))
    st.push(_Add(target=data, value=2))
    st.undo()                      # data == [1], a redo is available
    st.push(_Add(target=data, value=9))   # new branch discards the redo
    assert data == [1, 9]
    assert not st.can_redo()
    assert len(st.commands) == 2


# --- merging / coalescing --------------------------------------------------

def test_merge_coalesces_same_id():
    data = []
    st = UndoStack()
    st.push(_Add(text="type", target=data, value=1, merge_id=7))
    st.push(_Add(text="type", target=data, value=2, merge_id=7))
    st.push(_Add(text="type", target=data, value=3, merge_id=7))
    assert data == [1, 2, 3]
    assert len(st.commands) == 1          # all merged into one undo step
    st.undo()
    assert data == [1, 2]                  # only the last add reverts
    # different merge_id does not merge
    st2 = UndoStack()
    st2.push(_Add(target=[], value=1, merge_id=1))
    st2.push(_Add(target=[], value=2, merge_id=2))
    assert len(st2.commands) == 2


# --- macros ----------------------------------------------------------------

def test_macro_groups_into_one_step():
    data = []
    st = UndoStack()
    st.begin_macro("triple")
    st.push(_Add(target=data, value=1))
    st.push(_Add(target=data, value=2))
    st.push(_Add(target=data, value=3))
    st.end_macro()
    assert data == [1, 2, 3]
    assert len(st.commands) == 1
    st.undo()
    assert data == []                      # the whole macro reverts at once
    st.redo()
    assert data == [1, 2, 3]


def test_empty_macro_records_nothing():
    st = UndoStack()
    st.begin_macro("noop")
    st.end_macro()
    assert st.commands == []


# --- limit + clean ---------------------------------------------------------

def test_limit_drops_oldest():
    data = []
    st = UndoStack(limit=2)
    for v in (1, 2, 3):
        st.push(_Add(target=data, value=v))
    assert len(st.commands) == 2          # oldest dropped
    assert st.index == 2


def test_clean_state_tracking():
    data = []
    st = UndoStack()
    assert st.is_clean()
    st.push(_Add(target=data, value=1))
    assert not st.is_clean()
    st.set_clean()
    assert st.is_clean()
    st.push(_Add(target=data, value=2))
    assert not st.is_clean()
    st.undo()
    assert st.is_clean()                   # back at the saved index


def test_on_change_fires():
    calls = []
    st = UndoStack(on_change=lambda: calls.append(1))
    st.push(_Add(target=[], value=1))
    st.undo()
    st.redo()
    assert len(calls) == 3


# --- Action ----------------------------------------------------------------

def test_action_trigger_runs_callback():
    fired = []
    a = Action(text="Save", on_triggered=lambda: fired.append(1))
    assert a.trigger() is True
    assert fired == [1]
    a.enabled = False
    assert a.trigger() is False
    assert fired == [1]


def test_action_checkable_toggles():
    a = Action(text="Bold", checkable=True)
    assert a.checked is False
    a.trigger()
    assert a.checked is True
    a.trigger()
    assert a.checked is False


def test_action_builds_menu_item_and_tool_button():
    fired = []
    a = Action(text="Run", shortcut="Ctrl+R", tooltip="Run it",
               on_triggered=lambda: fired.append(1))
    mi = a.to_menu_item()
    assert mi.label == "Run" and mi.shortcut == "Ctrl+R"
    mi.on_click()
    assert fired == [1]
    tb = a.to_tool_button()
    assert tb.tooltip == "Run it"
    tb.on_click()
    assert fired == [1, 1]
