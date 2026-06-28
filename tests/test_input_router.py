"""Tier-1 Phase-1: framework input routing + focus management.

These run fully headless — a fake window feeds synthetic key/IME/clipboard
events into the InputRouter, and a fake editable widget records the method
calls — so we assert routing behaviour without a live event loop or the
native extension.
"""
from __future__ import annotations

from elysium.input import (
    InputRouter,
    FocusManager,
    MOD_SHIFT,
    MOD_CTRL,
    MOD_META,
)


class FakeWindow:
    """Minimal stand-in exposing the surface the router pulls from."""

    def __init__(self):
        self._queue: list[tuple] = []
        self._preedit = ""
        self._clip = ""
        self.ime_cursor_calls: list[tuple] = []

    # input the router reads
    def poll_key_event(self):
        return self._queue.pop(0) if self._queue else None

    def preedit(self):
        return self._preedit

    def get_clipboard_text(self):
        return self._clip

    def set_clipboard_text(self, s):
        self._clip = s

    def set_ime_cursor_area(self, x, y, w, h):
        self.ime_cursor_calls.append((x, y, w, h))

    # test helpers
    def key(self, code, mods=0, text="", pressed=True):
        self._queue.append((code, pressed, mods, text))

    def type_text(self, code, ch):
        self._queue.append((code, True, 0, ch))


class FakeEditable:
    def __init__(self, focus_id, rect=(0, 0, 100, 20), wants=True):
        self.focus_id = focus_id
        self._rect = rect
        self._wants = wants
        self.text = ""
        self.sel = ""
        self.keys: list[tuple] = []
        self.preedits: list[str] = []
        self.commits: list[str] = []
        self.focus_in = 0
        self.focus_out = 0
        # which control codes this widget claims (consumes)
        self.consume = {"ArrowLeft", "ArrowRight", "Home", "End", "Backspace", "KeyA"}

    def focus_rect(self):
        return self._rect

    def wants_keys(self):
        return self._wants

    def on_key(self, code, mods):
        self.keys.append((code, mods))
        if code == "KeyA" and mods & (MOD_CTRL | MOD_META):
            self.sel = self.text  # select-all
            return True
        return code in self.consume

    def on_text(self, s):
        self.text += s

    def on_paste(self, s):
        self.text += s

    def on_ime_preedit(self, s):
        self.preedits.append(s)

    def on_ime_commit(self, s):
        self.text += s
        self.commits.append(s)

    def caret_rect(self):
        return (len(self.text) * 8.0, 0.0, 2.0, 18.0)

    def selected_text(self):
        return self.sel

    def delete_selection(self):
        if self.sel:
            self.text = self.text.replace(self.sel, "", 1)
            self.sel = ""

    # focus lifecycle
    def on_focus_in(self):
        self.focus_in += 1

    def on_focus_out(self):
        self.focus_out += 1


def _router_with(widgets):
    win = FakeWindow()
    r = InputRouter(win)
    r.set_widgets(widgets)
    return win, r


def test_typed_text_routes_to_focused_widget():
    a = FakeEditable("a")
    b = FakeEditable("b", rect=(0, 30, 100, 20))
    win, r = _router_with([a, b])
    r.focus_widget("a")
    for ch in "héllo":
        win.type_text(f"Key{ch.upper()}", ch)
    r.tick()
    assert a.text == "héllo"
    assert b.text == ""


def test_unfocused_widgets_get_nothing():
    a = FakeEditable("a")
    win, r = _router_with([a])
    # No focus set.
    win.type_text("KeyX", "x")
    r.tick()
    assert a.text == ""


def test_tab_moves_focus_when_widget_does_not_consume():
    a = FakeEditable("a")
    b = FakeEditable("b", rect=(0, 30, 100, 20))
    win, r = _router_with([a, b])
    r.focus_widget("a")
    assert a.focus_in == 1
    win.key("Tab")
    r.tick()
    assert r.focus.focused_id == "b"
    assert a.focus_out == 1 and b.focus_in == 1
    # Shift+Tab goes back.
    win.key("Tab", mods=MOD_SHIFT)
    r.tick()
    assert r.focus.focused_id == "a"


def test_arrow_consumed_by_widget_does_not_move_focus():
    a = FakeEditable("a")
    b = FakeEditable("b", rect=(200, 0, 100, 20))  # to the right
    win, r = _router_with([a, b])
    r.focus_widget("a")
    win.key("ArrowRight")  # widget consumes (caret move), not focus nav
    r.tick()
    assert r.focus.focused_id == "a"
    assert ("ArrowRight", 0) in a.keys


def test_arrow_not_consumed_moves_focus_spatially():
    a = FakeEditable("a", wants=True)
    a.consume = set()  # consumes nothing
    b = FakeEditable("b", rect=(200, 0, 100, 20))  # to the right
    win, r = _router_with([a, b])
    r.focus_widget("a")
    win.key("ArrowRight")
    r.tick()
    assert r.focus.focused_id == "b"


def test_clipboard_copy_cut_paste():
    a = FakeEditable("a")
    a.text = "hello world"
    win, r = _router_with([a])
    r.focus_widget("a")
    # Select-all then copy.
    win.key("KeyA", mods=MOD_CTRL)
    win.key("KeyC", mods=MOD_CTRL)
    r.tick()
    assert win.get_clipboard_text() == "hello world"
    # Cut clears selection.
    win.key("KeyA", mods=MOD_CTRL)
    win.key("KeyX", mods=MOD_CTRL)
    r.tick()
    assert a.text == ""
    assert win.get_clipboard_text() == "hello world"
    # Paste re-inserts.
    win.key("KeyV", mods=MOD_META)  # Cmd on macOS also works
    r.tick()
    assert a.text == "hello world"


def test_ime_preedit_and_commit():
    a = FakeEditable("a")
    win, r = _router_with([a])
    r.focus_widget("a")
    # Composition in progress.
    win._preedit = "に"
    r.tick()
    assert a.preedits[-1] == "に"
    # Commit delivers via the synthetic ImeCommit event.
    win._preedit = ""
    win._queue.append(("ImeCommit", True, 0, "日本"))
    r.tick()
    assert "日本" in a.text
    assert a.commits == ["日本"]


def test_ime_cursor_area_parked_at_caret():
    a = FakeEditable("a")
    a.text = "abc"
    win, r = _router_with([a])
    r.focus_widget("a")
    r.tick()
    assert win.ime_cursor_calls  # caret_rect() forwarded to the window
    assert win.ime_cursor_calls[-1][0] == 24.0  # 3 chars * 8px


def test_focused_widget_removed_drops_focus():
    a = FakeEditable("a")
    win, r = _router_with([a])
    r.focus_widget("a")
    assert r.focus.focused_id == "a"
    r.set_widgets([])  # widget gone
    assert r.focus.focused_id is None


def test_focus_manager_change_callback():
    a = FakeEditable("a")
    b = FakeEditable("b", rect=(0, 30, 100, 20))
    fm = FocusManager()
    seen = []
    fm.on_change(seen.append)
    fm.focus("a", {"a": a, "b": b})
    fm.move("next", [a, b])
    assert seen == ["a", "b"]
