"""Tier-1 Phase-3: standard dialogs (native wrappers + Elysium-rendered modals)."""
from __future__ import annotations

import pytest

from elysium import dialogs as D


class FakeDL:
    def __init__(self):
        self.texts: list[str] = []
        self.fills = 0
        self.para_calls: list[tuple] = []  # (text, max_width, size)

    def fill_path(self, *a):
        self.fills += 1

    def stroke_path(self, *a):
        pass

    def gradient_card(self, *a):
        pass

    def fill_path_linear_gradient(self, *a):
        self.fills += 1

    def draw_text(self, s, *a):
        self.texts.append(s)

    def draw_paragraph(self, s, *a):
        self.texts.append(s)
        # signature: (x, y, max_width, size, rgba, align, family, weight, feats)
        if len(a) >= 4:
            self.para_calls.append((s, a[2], a[3]))
        return 20.0


def _shown(dlg):
    dlg.w = dlg.h = 600.0
    dlg._vis_t = 1.0
    return dlg


# --- native file wrappers ---------------------------------------------------

def test_native_wrappers_forward_to_native(monkeypatch):
    calls = {}

    class FakeNative:
        def open_file_dialog(self, *a):
            calls["open"] = a; return "/tmp/x.txt"

        def save_file_dialog(self, *a):
            calls["save"] = a; return "/tmp/y.txt"

        def pick_folder(self, *a):
            calls["folder"] = a; return "/tmp/dir"

    monkeypatch.setattr(D, "_native", lambda: FakeNative())
    assert D.open_file(title="Open", filter_patterns=["*.txt"]) == "/tmp/x.txt"
    assert D.save_file(default_name="y.txt") == "/tmp/y.txt"
    assert D.pick_folder() == "/tmp/dir"
    assert calls["open"][0] == "Open"
    assert calls["open"][3] == ["*.txt"]


def test_native_wrappers_graceful_without_native(monkeypatch):
    monkeypatch.setattr(D, "_native", lambda: None)
    assert D.open_file() is None
    assert D.save_file() is None
    assert D.pick_folder() is None


# --- MessageDialog ----------------------------------------------------------

def test_message_dialog_resolves_on_button():
    res = []
    m = _shown(D.MessageDialog(title="Delete?", body="Sure?",
                               buttons=["Cancel", "Delete"], on_result=res.append))
    m.paint(FakeDL())
    m.click_button(1)
    assert m.result == "Delete" and m.done and res == ["Delete"]


def test_message_dialog_enter_is_primary_esc_is_cancel():
    m = _shown(D.MessageDialog(title="t", buttons=["No", "Yes"]))  # Yes primary (last)
    m.on_key("Enter", 0)
    assert m.result == "Yes"
    m2 = _shown(D.MessageDialog(title="t", buttons=["No", "Yes"]))
    m2.on_key("Escape", 0)
    assert m2.result == "No"  # last button is the cancel default


def test_message_dialog_paints_title_body_buttons():
    m = _shown(D.MessageDialog(title="Title", body="Body", buttons=["OK"]))
    dl = FakeDL()
    m.paint(dl)
    assert {"Title", "Body", "OK"} <= set(dl.texts)


def test_message_dialog_body_wraps_within_card():
    # Regression: a long body must be drawn with draw_paragraph, wrapped to a
    # width bounded by the card, instead of draw_text running off the modal.
    long_body = ("Credentials and the remote link are removed. The local "
                 "catalog snapshot, pending edits, snapshots and job history "
                 "all stay on this machine.")
    m = _shown(D.MessageDialog(title="Disconnect store?", body=long_body,
                               buttons=["Cancel", "Disconnect"]))
    dl = FakeDL()
    m.paint(dl)
    body_paras = [c for c in dl.para_calls if c[0] == long_body]
    assert body_paras, "body was not wrapped via draw_paragraph (would overflow)"
    _text, max_width, _size = body_paras[0]
    assert 0 < max_width <= m.card_w, (
        f"wrap width {max_width} not bounded by the card ({m.card_w})")


def test_input_and_progress_body_text_wraps():
    # The same fix applies to the InputDialog prompt and ProgressDialog label.
    prompt = "Enter a new, sufficiently descriptive name for the connected store"
    inp = _shown(D.InputDialog(title="Rename", prompt=prompt))
    dl = FakeDL()
    inp.paint(dl)
    assert any(c[0] == prompt and 0 < c[1] <= inp.card_w for c in dl.para_calls)

    label = "Uploading the full catalog snapshot and reconciling pending edits…"
    prog = _shown(D.ProgressDialog(title="Sync", label=label))
    dl2 = FakeDL()
    prog.paint(dl2)
    assert any(c[0] == label and 0 < c[1] <= prog.card_w for c in dl2.para_calls)


# --- InputDialog ------------------------------------------------------------

def test_input_dialog_returns_text_on_ok():
    i = _shown(D.InputDialog(title="Name", prompt="Enter:", default="Ada"))
    i.paint(FakeDL())
    i.on_text("!")
    assert i.text_field.value == "Ada!"
    i.on_key("Enter", 0)
    assert i.result == "Ada!"


def test_input_dialog_cancel_returns_none():
    i = _shown(D.InputDialog(title="Name", default="x"))
    i.on_key("Escape", 0)
    assert i.result is None and i.done


# --- ProgressDialog ---------------------------------------------------------

def test_progress_dialog_determinate_and_close():
    p = _shown(D.ProgressDialog(title="Working", label="Step 1"))
    p.set_progress(0.5)
    p.paint(FakeDL())
    assert p.bar.value == 0.5 and not p.bar.indeterminate
    p.close()
    assert p.result is True and p.done


def test_progress_dialog_indeterminate_default():
    p = _shown(D.ProgressDialog(title="Working"))
    p.paint(FakeDL())
    assert p.bar.indeterminate


# --- ColorDialog ------------------------------------------------------------

def test_color_dialog_initial_and_swatch_pick():
    c = _shown(D.ColorDialog(initial=(10, 20, 30, 128)))
    c.paint(FakeDL())
    assert c.color == (10, 20, 30, 128)
    _, (x, y, w, h) = c._swatch_rects[0]
    c.on_mouse_press(x + 1, y + 1)
    assert c.color[:3] == c.PALETTE[0]


def test_color_dialog_alpha_slider():
    c = _shown(D.ColorDialog(initial=(0, 0, 0, 255)))
    c.paint(FakeDL())
    ax, ay, aw, ah = c._alpha_track
    c.on_mouse_press(ax + aw / 2.0, ay + ah / 2.0)
    assert 120 <= c.color[3] <= 135  # ~midpoint


def test_color_dialog_hex_typing_updates_rgb():
    c = _shown(D.ColorDialog(initial=(0, 0, 0, 255)))
    c.paint(FakeDL())
    c.hex_field.set_value("#FF8800")
    assert c.color[:3] == (255, 136, 0)


def test_color_dialog_ok_returns_color():
    c = _shown(D.ColorDialog(initial=(1, 2, 3, 4)))
    c.paint(FakeDL())
    # OK is the primary (second) button.
    c._on_button(c._buttons[1])
    assert c.result == (1, 2, 3, 4)


# --- FontDialog -------------------------------------------------------------

def test_font_dialog_family_and_size():
    f = _shown(D.FontDialog())
    f.paint(FakeDL())
    fam, (x, y, w, h) = f._family_rects[2]
    f.on_mouse_press(x + 1, y + 1)
    assert f.family == fam
    f.on_mouse_press(f._size_plus[0] + 1, f._size_plus[1] + 1)
    assert f.size == 17.0
    f.on_mouse_press(f._size_minus[0] + 1, f._size_minus[1] + 1)
    assert f.size == 16.0
    f._on_button(f._buttons[1])
    assert f.result == (fam, 16.0)


# --- DialogHost -------------------------------------------------------------

def test_host_modality_and_dismissal():
    host = D.DialogHost()
    host.set_size(800, 600)
    m = host.message("t", "b", buttons=["OK"])
    assert host.is_modal and host.active is m
    # Press routes to the active dialog and is swallowed.
    assert host.on_mouse_press(5, 5) is True
    m.click_button(0)
    # Tick the close animation to completion → dropped from the stack.
    for _ in range(200):
        host.update(0.05)
        if not host.is_modal:
            break
    assert not host.is_modal


def test_host_input_only_to_topmost():
    host = D.DialogHost()
    host.set_size(800, 600)
    host.message("first", buttons=["OK"])
    top = host.input("second", default="")
    host.on_text("z")
    assert top.text_field.value == "z"
