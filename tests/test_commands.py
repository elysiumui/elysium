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


# --- macro safety + clean-state parity (QA report, item 12) ---------------

def test_end_macro_invalidates_a_clean_marker_like_push_does():
    """The related defect: end_macro() discarded the redo branch but skipped
    the `_clean_index` fix-up push() performs, so `is_clean()` reported "no
    unsaved changes" for a document that HAD diverged from what was saved.
    A user trusting that indicator closes the app and loses the work.

    Both routes must agree — the documents are identical.
    """
    results = {}
    for label in ("push", "macro"):
        data = []
        st = UndoStack()
        st.push(_Add(target=data, value=1))
        st.push(_Add(target=data, value=2))
        st.set_clean()                    # saved at index 2
        st.undo()                         # step back
        if label == "macro":              # a new edit discards the branch
            st.begin_macro("m")           # that holds the clean point
            st.push(_Add(target=data, value=3))
            st.end_macro()
        else:
            st.push(_Add(target=data, value=3))
        results[label] = (list(data), st.is_clean())
    assert results["push"][0] == results["macro"][0]     # same document
    assert results["macro"][1] is False                  # ...so same verdict
    assert results["push"][1] is False


def test_macro_context_manager_records_one_step():
    data = []
    st = UndoStack()
    with st.macro("triple"):
        st.push(_Add(target=data, value=1))
        st.push(_Add(target=data, value=2))
        st.push(_Add(target=data, value=3))
    assert data == [1, 2, 3]
    assert len(st.commands) == 1
    st.undo()
    assert data == []


def test_macro_context_manager_closes_on_the_exception_path():
    """Item 12's root cause: a missed end_macro() — an early return, a raise
    between the calls, a branch that forgets it — left the stack believing a
    macro was open forever. Every subsequent command then executed against
    the document while being recorded nowhere: Ctrl-Z silently did nothing,
    permanently, with no error and no visible state change.
    """
    data = []
    st = UndoStack()
    try:
        with st.macro("boom"):
            st.push(_Add(target=data, value=1))
            raise RuntimeError("early exit")
    except RuntimeError:
        pass
    assert st._macro == []                # the macro was closed
    assert st.can_undo() and len(st.commands) == 1
    st.undo()
    assert data == []                     # ...and the edit that ran is undoable

    # The stack is still usable afterwards — the old failure mode swallowed
    # everything pushed from here on.
    st.push(_Add(target=data, value=9))
    assert data == [9] and st.can_undo()


def test_push_inside_a_macro_notifies_observers():
    """The document changes on push, so a 'modified' indicator or an autosave
    trigger keyed off on_change must fire — previously push() returned before
    _notify() on the macro path, so nothing fired until end_macro()."""
    seen = []
    st = UndoStack(on_change=lambda: seen.append(1))
    st.begin_macro("m")
    st.push(_Add(target=[], value=1))
    assert seen                            # fired during the macro
