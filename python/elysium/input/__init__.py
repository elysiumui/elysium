"""Framework-level input routing + focus management.

Until now every Elysium app hand-rolled its own ``poll_key_event`` loop and
mutated widget state directly (see ``examples/*/main.py``). Editable widgets
(text fields, spin boxes, editable table cells) need a *central* router that
delivers keystrokes, typed text, IME composition, and clipboard actions to
whichever widget currently holds focus — the retained-interaction layer Qt
gets from ``QApplication`` event dispatch + ``QWidget.setFocus``.

This module provides three pieces:

* :class:`Focusable` / :class:`Editable` — duck-typed protocols a widget
  implements to participate. A widget is *focusable* if it has a stable
  ``focus_id`` and a ``focus_rect``; *editable* if it additionally accepts
  keys / text / IME.
* :class:`FocusManager` — owns the current focused id and moves focus via
  Tab / Shift-Tab / arrows, reusing :func:`elysium.focus.next_focus`.
* :class:`InputRouter` — bound to a window; each frame it drains the native
  key queue + IME preedit and routes them to the focused editable, handles
  focus-navigation keys the widget didn't consume, orchestrates
  cut/copy/paste against the system clipboard, and keeps the OS IME
  candidate popup parked at the caret.

The router never owns *rendering* — widgets still paint themselves each
frame. It owns *interaction*: turning raw OS input into method calls on the
focused widget.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Protocol, runtime_checkable

from elysium.focus import FocusNode, next_focus

# Printable-text key-down events arrive with a non-empty ``text`` field; we
# forward those to ``on_text``. Control keys (arrows, Tab, Backspace, …) have
# empty ``text`` and go through ``on_key``. The committed string of an IME
# composition arrives as a synthetic event whose ``code`` is this sentinel.
_IME_COMMIT_CODE = "ImeCommit"

# Modifier bitmask (matches the native ``modifiers`` getter):
MOD_SHIFT = 1
MOD_CTRL = 2
MOD_ALT = 4
MOD_META = 8

# The "command" modifier is Cmd on macOS, Ctrl elsewhere. We accept either so
# clipboard shortcuts work cross-platform without the router knowing the OS.
_CMD_MASK = MOD_CTRL | MOD_META


@runtime_checkable
class Focusable(Protocol):
    """A widget that can hold keyboard focus."""

    #: Stable identifier, unique within a window's focusable set.
    focus_id: str

    def focus_rect(self) -> tuple[float, float, float, float]:
        """Bounding rect ``(x, y, w, h)`` in window coords, used for
        spatial (arrow-key) focus navigation and the focus ring."""
        ...


@runtime_checkable
class Editable(Protocol):
    """A focusable widget that consumes text input.

    All methods are optional in practice — the router guards each call —
    but a real text widget implements at least ``on_key`` + ``on_text``.
    """

    focus_id: str

    def focus_rect(self) -> tuple[float, float, float, float]: ...

    def wants_keys(self) -> bool:
        """Return True while this widget should receive key/text input
        (e.g. it's enabled and in an editable mode)."""

    def on_key(self, code: str, mods: int) -> bool:
        """Handle a control key (arrows, Backspace, Home, Ctrl+A, …).
        Return True if consumed; False lets the router try focus
        navigation (so e.g. an unhandled Tab still moves focus)."""

    def on_text(self, text: str) -> None:
        """Insert typed text at the caret (a single grapheme, usually)."""

    def on_ime_preedit(self, text: str) -> None:
        """Update the in-flight IME composition string (rendered with an
        underline); empty string clears it."""

    def on_ime_commit(self, text: str) -> None:
        """Commit a finished IME composition as inserted text."""

    def caret_rect(self) -> Optional[tuple[float, float, float, float]]:
        """Caret rect ``(x, y, w, h)`` in window coords for IME popup
        placement, or None if unavailable."""

    # Clipboard hooks — the router calls these for Cmd/Ctrl+C/X/V so each
    # widget controls its own selection semantics.
    def selected_text(self) -> str: ...
    def delete_selection(self) -> None: ...


def _has(obj: Any, name: str) -> bool:
    return callable(getattr(obj, name, None))


class FocusManager:
    """Owns the focused-widget id and moves focus between focusables.

    Focus navigation reuses :func:`elysium.focus.next_focus` (document-order
    Tab, spatial arrows) over the live focusable rects.
    """

    def __init__(self) -> None:
        self._focused: str | None = None
        self._on_change: list[Any] = []

    @property
    def focused_id(self) -> str | None:
        return self._focused

    def on_change(self, fn) -> None:
        """Register ``fn(new_id | None)`` fired whenever focus moves."""
        self._on_change.append(fn)

    def _emit(self, new_id: str | None, focusables: dict[str, Any]) -> None:
        if new_id == self._focused:
            return
        old = self._focused
        if old is not None and old in focusables and _has(focusables[old], "on_focus_out"):
            try: focusables[old].on_focus_out()
            except Exception: pass
        self._focused = new_id
        if new_id is not None and new_id in focusables and _has(focusables[new_id], "on_focus_in"):
            try: focusables[new_id].on_focus_in()
            except Exception: pass
        for cb in self._on_change:
            try: cb(new_id)
            except Exception: pass

    def focus(self, widget_id: str | None, focusables: dict[str, Any]) -> None:
        self._emit(widget_id, focusables)

    def blur(self, focusables: dict[str, Any]) -> None:
        self._emit(None, focusables)

    def move(self, direction: str, widgets: list[Any]) -> str | None:
        """Move focus in ``direction`` ("next"/"prev"/"up"/"down"/
        "left"/"right"). Returns the new focused id (or None)."""
        focusables = {w.focus_id: w for w in widgets}
        nodes = [FocusNode(id=w.focus_id, bounds=tuple(w.focus_rect())) for w in widgets]
        new_id = next_focus(nodes, self._focused, direction)  # type: ignore[arg-type]
        if new_id is not None:
            self._emit(new_id, focusables)
        return self._focused


# Control-key codes that drive focus navigation when the focused widget
# doesn't consume them.
_NAV_KEYS = {
    "Tab": None,  # resolved to next/prev by shift state
    "ArrowUp": "up",
    "ArrowDown": "down",
    "ArrowLeft": "left",
    "ArrowRight": "right",
}


class InputRouter:
    """Per-window input dispatcher. Call :meth:`set_widgets` each frame (or
    whenever the focusable set changes) and :meth:`tick` once per frame
    after the window has polled — it drains the native key queue + IME
    preedit and routes everything to the focused widget.
    """

    def __init__(self, window: Any) -> None:
        self.window = window
        self.focus = FocusManager()
        self._widgets: list[Any] = []
        self._by_id: dict[str, Any] = {}
        self._scrollables: list[Any] = []

    # -- registration -------------------------------------------------------

    def set_widgets(self, widgets: Iterable[Any]) -> None:
        """Replace the focusable widget set. Widgets must expose
        ``focus_id`` + ``focus_rect``; editables additionally implement the
        :class:`Editable` methods. Safe to call every frame."""
        self._widgets = [w for w in widgets if getattr(w, "focus_id", None)]
        self._by_id = {w.focus_id: w for w in self._widgets}
        # If the focused widget vanished, drop focus.
        if self.focus.focused_id is not None and self.focus.focused_id not in self._by_id:
            self.focus.focus(None, self._by_id)

    @property
    def focused(self) -> Any | None:
        fid = self.focus.focused_id
        return self._by_id.get(fid) if fid is not None else None

    def focus_widget(self, widget_id: str | None) -> None:
        self.focus.focus(widget_id, self._by_id)

    def set_scrollables(self, scrollables: Iterable[Any]) -> None:
        """Register the scrollable widgets (``scroll_rect`` + ``on_scroll``).
        Mouse-wheel deltas are routed to whichever one is under the cursor.
        Listed back-to-front; the last (topmost) match wins. Safe per frame."""
        self._scrollables = [s for s in scrollables
                             if _has(s, "on_scroll") and _has(s, "scroll_rect")]

    def _hovered_scrollable(self, cur: tuple[float, float]) -> Any | None:
        mx, my = cur
        for s in reversed(self._scrollables):
            try:
                x, y, w, h = s.scroll_rect()
            except Exception:
                continue
            if x <= mx <= x + w and y <= my <= y + h:
                return s
        return None

    # -- per-frame routing --------------------------------------------------

    def tick(self) -> None:
        """Drain input and route it. Call once per frame."""
        focused = self.focused

        # 1) IME preedit → focused editable (rendered as underlined candidate).
        try:
            preedit = self.window.preedit()
        except Exception:
            preedit = ""
        if focused is not None and _has(focused, "on_ime_preedit"):
            try: focused.on_ime_preedit(preedit)
            except Exception: pass

        # 2) Drain key events.
        while True:
            ev = self.window.poll_key_event()
            if ev is None:
                break
            code, pressed, mods, text = ev
            self._route_key(code, pressed, mods, text)

        # 2b) Drain mouse-wheel scroll → hovered scrollable.
        if self._scrollables and _has(self.window, "poll_scroll_delta"):
            try:
                sx, sy, precise = self.window.poll_scroll_delta()
            except Exception:
                sx = sy = 0.0
                precise = False
            if sx or sy:
                cur = getattr(self.window, "cursor_position", None)
                target = self._hovered_scrollable(cur) if cur is not None else None
                if target is not None:
                    try: target.on_scroll(sx, sy, precise)
                    except Exception: pass

        # 3) Park the OS IME candidate popup at the caret.
        focused = self.focused
        if focused is not None and _has(focused, "caret_rect"):
            try:
                rect = focused.caret_rect()
            except Exception:
                rect = None
            if rect is not None and _has(self.window, "set_ime_cursor_area"):
                try: self.window.set_ime_cursor_area(*rect)
                except Exception: pass

    def _route_key(self, code: str, pressed: bool, mods: int, text: str) -> None:
        focused = self.focused

        # Committed IME text is always inserted, regardless of pressed state.
        if code == _IME_COMMIT_CODE:
            if focused is not None and _has(focused, "on_ime_commit"):
                try: focused.on_ime_commit(text)
                except Exception: pass
            return

        # We act on key-down only (text editing doesn't care about key-up).
        if not pressed:
            return

        editable = focused if (focused is not None
                               and _has(focused, "on_key")
                               and (not _has(focused, "wants_keys") or focused.wants_keys())) else None

        # Clipboard shortcuts (Cmd/Ctrl + C/X/V) are orchestrated centrally so
        # every editable gets identical behaviour.
        if editable is not None and (mods & _CMD_MASK) and not (mods & MOD_ALT):
            if code == "KeyC":
                self._copy(editable); return
            if code == "KeyX":
                self._cut(editable); return
            if code == "KeyV":
                self._paste(editable); return

        # Let the focused editable consume the key first.
        if editable is not None:
            try:
                consumed = bool(editable.on_key(code, mods))
            except Exception:
                consumed = False
            if consumed:
                return
            # Printable text the widget didn't claim as a control key.
            if text and _has(editable, "on_text"):
                try: editable.on_text(text)
                except Exception: pass
                return

        # Not consumed → focus navigation for Tab / arrows.
        direction = _nav_direction(code, mods)
        if direction is not None and self._widgets:
            self.focus.move(direction, self._widgets)

    # -- clipboard ----------------------------------------------------------

    def _clip_get(self) -> str:
        try:
            return self.window.get_clipboard_text() or ""
        except Exception:
            return ""

    def _clip_set(self, s: str) -> None:
        try:
            self.window.set_clipboard_text(s)
        except Exception:
            pass

    def _copy(self, editable: Any) -> None:
        if _has(editable, "selected_text"):
            sel = editable.selected_text()
            if sel:
                self._clip_set(sel)

    def _cut(self, editable: Any) -> None:
        if _has(editable, "selected_text"):
            sel = editable.selected_text()
            if sel:
                self._clip_set(sel)
                if _has(editable, "delete_selection"):
                    try: editable.delete_selection()
                    except Exception: pass

    def _paste(self, editable: Any) -> None:
        text = self._clip_get()
        if not text:
            return
        # Prefer a dedicated paste hook; fall back to per-grapheme on_text.
        if _has(editable, "on_paste"):
            try: editable.on_paste(text); return
            except Exception: pass
        if _has(editable, "on_text"):
            try: editable.on_text(text)
            except Exception: pass


def _nav_direction(code: str, mods: int) -> str | None:
    if code == "Tab":
        return "prev" if (mods & MOD_SHIFT) else "next"
    return _NAV_KEYS.get(code)


__all__ = [
    "Focusable",
    "Editable",
    "FocusManager",
    "InputRouter",
    "MOD_SHIFT",
    "MOD_CTRL",
    "MOD_ALT",
    "MOD_META",
]
