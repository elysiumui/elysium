"""UI test automation — Tier-2 Qt parity (QTest).

A headless driver for simulating user input against Elysium components and
asserting on the resulting widget state — no window, GPU, or event loop. Built
on the same :class:`elysium.input.InputRouter` apps use, so what the harness
exercises is the real input path.

    h = UiHarness([name_field, age_spin, table])
    h.focus("name"); h.type("Ada")
    assert h.find("name").value == "Ada"
    h.click_widget("save")
    assert "Saved" in h.texts()

``type`` / ``key`` go through the router (focus nav, IME, clipboard, editing);
``click`` / ``scroll`` dispatch to the widget under the point the way an app's
frame loop does. ``paint`` captures the display list for visual assertions.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from elysium.input import InputRouter

# Modifier bits (mirror elysium.input).
SHIFT, CTRL, ALT, META = 1, 2, 4, 8


class FakeWindow:
    """Minimal window stand-in implementing the surface the InputRouter +
    harness read from: a key queue, IME preedit, clipboard, scroll, cursor."""

    def __init__(self) -> None:
        self._keys: list[tuple] = []
        self._scroll: list[tuple] = []
        self._preedit = ""
        self._clip = ""
        self.cursor_position: Optional[tuple[float, float]] = None

    # router reads
    def poll_key_event(self):
        return self._keys.pop(0) if self._keys else None

    def poll_scroll_delta(self):
        return self._scroll.pop(0) if self._scroll else (0.0, 0.0, False)

    def preedit(self) -> str:
        return self._preedit

    def get_clipboard_text(self) -> str:
        return self._clip

    def set_clipboard_text(self, s: str) -> None:
        self._clip = s

    def set_ime_cursor_area(self, *a) -> None:
        pass

    # harness writes
    def queue_key(self, code: str, pressed: bool, mods: int, text: str) -> None:
        self._keys.append((code, pressed, mods, text))

    def queue_scroll(self, dx: float, dy: float, precise: bool) -> None:
        self._scroll.append((dx, dy, precise))

    def set_preedit(self, s: str) -> None:
        self._preedit = s


class CaptureDL:
    """A display-list stand-in that records drawn text and tallies calls;
    every other draw method is a no-op. Use ``texts`` for visual assertions."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.calls: dict[str, int] = {}

    def draw_text(self, s: Any, *a, **k) -> None:
        self.texts.append(str(s))
        self.calls["draw_text"] = self.calls.get("draw_text", 0) + 1

    def draw_paragraph(self, s: Any, *a, **k) -> float:
        self.texts.append(str(s))
        self.calls["draw_paragraph"] = self.calls.get("draw_paragraph", 0) + 1
        return 20.0

    def __getattr__(self, name: str) -> Callable[..., None]:
        def _rec(*a, **k):
            self.calls[name] = self.calls.get(name, 0) + 1
            return None
        return _rec


def _char_code(ch: str) -> str:
    if ch.isalpha():
        return f"Key{ch.upper()}"
    if ch.isdigit():
        return f"Digit{ch}"
    return {" ": "Space", ".": "Period", ",": "Comma", "-": "Minus"}.get(ch, ch)


class UiHarness:
    """Drives synthetic input against a set of components and exposes their
    state for assertions. Immediate-mode: it holds widget references (no
    retained tree) and resolves ``find`` by ``focus_id`` or predicate."""

    def __init__(self, widgets: Optional[Iterable[Any]] = None) -> None:
        self.window = FakeWindow()
        self.router = InputRouter(self.window)
        self._widgets: list[Any] = []
        self._last_dl: Optional[CaptureDL] = None
        if widgets:
            self.set_widgets(widgets)

    # -- registration / queries --------------------------------------------

    def set_widgets(self, widgets: Iterable[Any]) -> "UiHarness":
        self._widgets = list(widgets)
        focusables = [w for w in self._widgets if getattr(w, "focus_id", None)]
        self.router.set_widgets(focusables)
        scrollables = [w for w in self._widgets
                       if callable(getattr(w, "on_scroll", None))
                       and callable(getattr(w, "scroll_rect", None))]
        self.router.set_scrollables(scrollables)
        return self

    def register(self, widget: Any) -> Any:
        self._widgets.append(widget)
        self.set_widgets(self._widgets)
        return widget

    def find(self, focus_id: str) -> Any:
        for w in self._widgets:
            if getattr(w, "focus_id", None) == focus_id:
                return w
        raise KeyError(f"no widget with focus_id={focus_id!r}")

    def find_by(self, predicate: Callable[[Any], bool]) -> Any:
        for w in self._widgets:
            if predicate(w):
                return w
        raise KeyError("no widget matched predicate")

    # -- focus + keyboard ---------------------------------------------------

    def focus(self, focus_id: Optional[str]) -> "UiHarness":
        self.router.focus_widget(focus_id)
        return self

    @property
    def focused_id(self) -> Optional[str]:
        return self.router.focus.focused_id

    def key(self, code: str, mods: int = 0, text: str = "") -> "UiHarness":
        self.window.queue_key(code, True, mods, text)
        self.router.tick()
        return self

    def type(self, text: str) -> "UiHarness":
        for ch in text:
            self.window.queue_key(_char_code(ch), True, 0, ch)
        self.router.tick()
        return self

    def ime(self, preedit: str = "", commit: Optional[str] = None) -> "UiHarness":
        self.window.set_preedit(preedit)
        if commit is not None:
            self.window.queue_key("ImeCommit", True, 0, commit)
        self.router.tick()
        return self

    # -- mouse --------------------------------------------------------------

    def _widget_at(self, x: float, y: float) -> Optional[Any]:
        for w in reversed(self._widgets):
            if not callable(getattr(w, "on_mouse_press", None)):
                continue
            rect = None
            if callable(getattr(w, "focus_rect", None)):
                rect = w.focus_rect()
            elif all(hasattr(w, k) for k in ("x", "y", "w", "h")):
                rect = (w.x, w.y, w.w, w.h)
            if rect is None:
                continue
            rx, ry, rw, rh = rect
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return w
        return None

    def hover(self, x: float, y: float) -> "UiHarness":
        self.window.cursor_position = (x, y)
        return self

    def click(self, x: float, y: float, *, double: bool = False) -> Optional[Any]:
        self.window.cursor_position = (x, y)
        w = self._widget_at(x, y)
        if w is None:
            return None
        if getattr(w, "focus_id", None):
            self.router.focus_widget(w.focus_id)
        try:
            w.on_mouse_press(x, y, double=double)
        except TypeError:
            w.on_mouse_press(x, y)
            if double:
                w.on_mouse_press(x, y)
        return w

    def double_click(self, x: float, y: float) -> Optional[Any]:
        return self.click(x, y, double=True)

    def click_widget(self, focus_id: str, *, double: bool = False) -> Any:
        w = self.find(focus_id)
        rx, ry, rw, rh = w.focus_rect()
        return self.click(rx + rw / 2.0, ry + rh / 2.0, double=double)

    def scroll(self, dx: float, dy: float, *, at: Optional[tuple[float, float]] = None,
               precise: bool = False) -> "UiHarness":
        if at is not None:
            self.window.cursor_position = at
        self.window.queue_scroll(dx, dy, precise)
        self.router.tick()
        return self

    # -- rendering / assertions --------------------------------------------

    def paint(self) -> CaptureDL:
        dl = CaptureDL()
        for w in self._widgets:
            if callable(getattr(w, "paint", None)):
                try:
                    w.paint(dl)
                except TypeError:
                    # Containers whose paint takes a content callback.
                    w.paint(dl, lambda d: None)
        self._last_dl = dl
        return dl

    def texts(self) -> list[str]:
        return self.paint().texts

    # -- record / playback --------------------------------------------------

    def play(self, script: list[tuple]) -> "UiHarness":
        """Replay a list of ``(method_name, *args)`` / ``(method, args, kwargs)``
        actions, e.g. ``[("focus", "name"), ("type", "Ada"), ("key", "Enter")]``."""
        for step in script:
            name, rest = step[0], step[1:]
            args, kwargs = (), {}
            if len(rest) == 2 and isinstance(rest[0], (list, tuple)) and isinstance(rest[1], dict):
                args, kwargs = tuple(rest[0]), rest[1]
            else:
                args = rest
            getattr(self, name)(*args, **kwargs)
        return self


__all__ = ["UiHarness", "FakeWindow", "CaptureDL", "SHIFT", "CTRL", "ALT", "META"]
