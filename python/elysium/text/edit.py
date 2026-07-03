"""`EditableText` — a pure, geometry-agnostic text-editing model.

All indices are Unicode codepoints (Python ``str`` indexing), matching the
native shaping primitives (`elysium._native.text_caret_x` /
`text_hit_index`). The model knows nothing about pixels or painting: a widget
owns geometry (mapping clicks → caret via the native hit-test, drawing the
caret/selection at the native caret-x), while this class owns the *text*:
caret, selection, undo/redo, word navigation, validation, and IME state.

Supports both single-line (`multiline=False`) and multi-line
(`multiline=True`, hard ``\\n`` breaks) editing — vertical caret movement
operates over newline-delimited logical lines, preserving the target column.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from elysium.text.validate import Invalid

# A "word" character for word-jump (Ctrl/Opt+Arrow, Ctrl+Backspace). Runs of
# these form a word; everything else is a separator.
_WORD = re.compile(r"\w", re.UNICODE)


@dataclass
class _Snapshot:
    text: str
    caret: int
    anchor: int


@dataclass
class EditableText:
    text: str = ""
    caret: int = 0
    # Selection runs between anchor and caret. Defaults to None so that
    # constructing with an explicit caret doesn't create a phantom
    # selection back to 0 — post_init collapses anchor onto caret unless
    # the caller passed an explicit anchor.
    anchor: int | None = None
    multiline: bool = False
    max_length: int | None = None
    # `validator(proposed_text) -> Invalid|Intermediate|Acceptable`; edits
    # that would make the value Invalid are rejected.
    validator: Optional[Callable[[str], int]] = None
    # `mask.apply(raw) -> formatted`; when set, the field is reformatted
    # through the mask after each edit and the caret clamped.
    mask: object | None = None
    on_change: Optional[Callable[[str], None]] = None

    # IME composition (rendered by the widget as underlined; not committed).
    preedit: str = ""

    _undo: list[_Snapshot] = field(default_factory=list)
    _redo: list[_Snapshot] = field(default_factory=list)
    _coalescing: bool = False  # True while a run of single-char inserts merges

    def __post_init__(self) -> None:
        self.caret = self._clamp(self.caret)
        # Collapse anchor onto the caret unless an explicit selection was
        # requested at construction.
        self.anchor = self.caret if self.anchor is None else self._clamp(self.anchor)

    # -- basic queries ------------------------------------------------------

    def __len__(self) -> int:
        return len(self.text)

    def _clamp(self, i: int) -> int:
        return max(0, min(i, len(self.text)))

    @property
    def has_selection(self) -> bool:
        return self.caret != self.anchor

    def selection(self) -> tuple[int, int]:
        return (min(self.caret, self.anchor), max(self.caret, self.anchor))

    def selected_text(self) -> str:
        lo, hi = self.selection()
        return self.text[lo:hi]

    # -- undo plumbing ------------------------------------------------------

    def _snapshot(self) -> _Snapshot:
        return _Snapshot(self.text, self.caret, self.anchor)

    def _push_undo(self, *, coalesce: bool = False) -> None:
        if coalesce and self._coalescing and self._undo:
            return  # merge into the in-progress group
        self._undo.append(self._snapshot())
        self._redo.clear()
        self._coalescing = coalesce
        # Cap history so a long session doesn't grow unbounded.
        if len(self._undo) > 256:
            self._undo.pop(0)

    def _break_coalesce(self) -> None:
        self._coalescing = False

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        s = self._undo.pop()
        self.text, self.caret, self.anchor = s.text, s.caret, s.anchor
        self._coalescing = False
        self._fire()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        s = self._redo.pop()
        self.text, self.caret, self.anchor = s.text, s.caret, s.anchor
        self._coalescing = False
        self._fire()
        return True

    # -- mutation -----------------------------------------------------------

    def _fire(self) -> None:
        if self.on_change is not None:
            try: self.on_change(self.text)
            except Exception: pass

    def _accept(self, proposed: str) -> bool:
        if self.max_length is not None and len(proposed) > self.max_length:
            return False
        if self.validator is not None and self.validator(proposed) == Invalid:
            return False
        return True

    def set_text(self, value: str, *, keep_caret: bool = False) -> None:
        """Programmatically replace the whole value (clears undo)."""
        self.text = value
        self._undo.clear(); self._redo.clear(); self._coalescing = False
        if not keep_caret:
            self.caret = self.anchor = len(value)
        else:
            self.caret = self._clamp(self.caret); self.anchor = self.caret
        self._fire()

    def insert(self, s: str, *, coalesce: bool = False) -> bool:
        """Replace any selection with ``s`` and place the caret after it.
        Rejected (returns False) if the validator/length would forbid it."""
        if not s:
            return False
        lo, hi = self.selection()
        proposed = self.text[:lo] + s + self.text[hi:]
        if self.mask is not None:
            proposed = self.mask.apply(_strip_to_input(proposed))
        if not self._accept(proposed):
            return False
        self._push_undo(coalesce=coalesce)
        self.text = proposed
        if self.mask is not None:
            # Masked input is forward-typed; literals the mask auto-inserts
            # shift positions, so park the caret at the end of the filled
            # content rather than trying to track an in-string offset.
            self.caret = self.anchor = len(proposed)
        else:
            self.caret = self.anchor = lo + len(s)
        self._fire()
        return True

    def backspace(self) -> bool:
        if self.has_selection:
            return self._delete_selection()
        if self.caret == 0:
            return False
        self._break_coalesce()
        self._push_undo()
        self.text = self.text[: self.caret - 1] + self.text[self.caret:]
        self.caret = self.anchor = self.caret - 1
        self._fire()
        return True

    def delete_forward(self) -> bool:
        if self.has_selection:
            return self._delete_selection()
        if self.caret >= len(self.text):
            return False
        self._break_coalesce()
        self._push_undo()
        self.text = self.text[: self.caret] + self.text[self.caret + 1:]
        self.caret = self.anchor = self.caret
        self._fire()
        return True

    def delete_selection(self) -> bool:
        return self._delete_selection()

    def _delete_selection(self) -> bool:
        if not self.has_selection:
            return False
        lo, hi = self.selection()
        self._break_coalesce()
        self._push_undo()
        self.text = self.text[:lo] + self.text[hi:]
        self.caret = self.anchor = lo
        self._fire()
        return True

    def delete_word_back(self) -> bool:
        if self.has_selection:
            return self._delete_selection()
        if self.caret == 0:
            return False
        target = self._word_left(self.caret)
        self._break_coalesce()
        self._push_undo()
        self.text = self.text[:target] + self.text[self.caret:]
        self.caret = self.anchor = target
        self._fire()
        return True

    # -- caret movement (select=True extends the selection) -----------------

    def _set_caret(self, i: int, select: bool) -> None:
        self.caret = self._clamp(i)
        if not select:
            self.anchor = self.caret
        self._break_coalesce()

    def move_left(self, select: bool = False) -> None:
        if self.has_selection and not select:
            self._set_caret(self.selection()[0], False)
        else:
            self._set_caret(self.caret - 1, select)

    def move_right(self, select: bool = False) -> None:
        if self.has_selection and not select:
            self._set_caret(self.selection()[1], False)
        else:
            self._set_caret(self.caret + 1, select)

    def move_word_left(self, select: bool = False) -> None:
        self._set_caret(self._word_left(self.caret), select)

    def move_word_right(self, select: bool = False) -> None:
        self._set_caret(self._word_right(self.caret), select)

    def move_home(self, select: bool = False) -> None:
        self._set_caret(self._line_start(self.caret), select)

    def move_end(self, select: bool = False) -> None:
        self._set_caret(self._line_end(self.caret), select)

    def move_doc_start(self, select: bool = False) -> None:
        self._set_caret(0, select)

    def move_doc_end(self, select: bool = False) -> None:
        self._set_caret(len(self.text), select)

    def move_up(self, select: bool = False) -> None:
        if not self.multiline:
            return self.move_home(select)
        self._vertical(-1, select)

    def move_down(self, select: bool = False) -> None:
        if not self.multiline:
            return self.move_end(select)
        self._vertical(+1, select)

    def select_all(self) -> None:
        self.anchor = 0
        self.caret = len(self.text)
        self._break_coalesce()

    def set_caret(self, i: int, select: bool = False) -> None:
        """Public caret set — used by widgets after a click hit-test."""
        self._set_caret(i, select)

    # -- IME ----------------------------------------------------------------

    def set_preedit(self, s: str) -> None:
        self.preedit = s or ""

    def commit_preedit(self, s: str) -> None:
        self.preedit = ""
        self.insert(s)

    # -- word / line helpers ------------------------------------------------

    def _is_word(self, i: int) -> bool:
        return 0 <= i < len(self.text) and bool(_WORD.match(self.text[i]))

    def _word_left(self, i: int) -> int:
        i = self._clamp(i)
        # Skip separators immediately left, then the word run.
        while i > 0 and not self._is_word(i - 1):
            i -= 1
        while i > 0 and self._is_word(i - 1):
            i -= 1
        return i

    def _word_right(self, i: int) -> int:
        i = self._clamp(i)
        n = len(self.text)
        while i < n and not self._is_word(i):
            i += 1
        while i < n and self._is_word(i):
            i += 1
        return i

    def _line_start(self, i: int) -> int:
        if not self.multiline:
            return 0
        nl = self.text.rfind("\n", 0, i)
        return nl + 1

    def _line_end(self, i: int) -> int:
        if not self.multiline:
            return len(self.text)
        nl = self.text.find("\n", i)
        return len(self.text) if nl < 0 else nl

    def _vertical(self, dir_: int, select: bool) -> None:
        start = self._line_start(self.caret)
        col = self.caret - start
        if dir_ < 0:
            if start == 0:
                self._set_caret(0, select); return
            prev_start = self._line_start(start - 1)
            prev_end = start - 1
            self._set_caret(min(prev_start + col, prev_end), select)
        else:
            end = self._line_end(self.caret)
            if end >= len(self.text):
                self._set_caret(len(self.text), select); return
            next_start = end + 1
            next_end = self._line_end(next_start)
            self._set_caret(min(next_start + col, next_end), select)

    # -- key interpretation (called by the InputRouter via the widget) ------

    def on_key(self, code: str, mods: int) -> bool:
        """Interpret a control key. Returns True if consumed. Printable
        characters are NOT handled here — they arrive via `on_text`."""
        shift = bool(mods & 1)
        # word-jump modifier: Ctrl on Win/Linux, Alt(Option) on macOS. We
        # accept either so the same widget works everywhere.
        word = bool(mods & (2 | 4))
        cmd = bool(mods & (2 | 8))  # Ctrl or Cmd

        if code == "ArrowLeft":
            (self.move_word_left if word else self.move_left)(shift); return True
        if code == "ArrowRight":
            (self.move_word_right if word else self.move_right)(shift); return True
        if code == "ArrowUp":
            if self.multiline:
                self.move_up(shift); return True
            return False  # single-line: let it bubble (e.g. spinbox increment)
        if code == "ArrowDown":
            if self.multiline:
                self.move_down(shift); return True
            return False
        if code == "Home":
            (self.move_doc_start if cmd else self.move_home)(shift); return True
        if code == "End":
            (self.move_doc_end if cmd else self.move_end)(shift); return True
        if code == "Backspace":
            return self.delete_word_back() if word else self.backspace()
        if code == "Delete":
            return self.delete_forward()
        if code == "Enter" or code == "NumpadEnter":
            if self.multiline:
                self.insert("\n"); return True
            return False  # single-line: submit is the app's concern
        if cmd and code == "KeyA":
            self.select_all(); return True
        if cmd and code == "KeyZ":
            return (self.redo() if shift else self.undo())
        if cmd and code == "KeyY":
            return self.redo()
        return False

    def on_text(self, s: str) -> None:
        """Insert printable typed text (coalesced into one undo group while
        the user types a run)."""
        # Filter out control chars that slip through as text.
        s = "".join(ch for ch in s if ch == "\n" or ch.isprintable())
        if not s:
            return
        self.insert(s, coalesce=True)


def _strip_to_input(s: str) -> str:
    """For masked fields, recover the user-meaningful characters from a
    formatted string so re-applying the mask is idempotent. We simply hand
    the whole string back to Mask.apply, which skips literals it re-inserts.
    """
    return s


__all__ = ["EditableText"]
