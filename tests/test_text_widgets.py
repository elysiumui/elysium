"""Tier-1 Phase-2: TextField / TextArea widget integration.

Behaviour-level (no pixel goldens — cross-platform text rendering varies):
a fake DisplayList records draw calls so we can assert that the caret and
selection are emitted and that the Editable protocol drives the embedded
EditableText model correctly.
"""
from __future__ import annotations

from elysium.components import TextField, TextArea
from elysium.text import IntValidator, Mask
from elysium.input import MOD_SHIFT, MOD_CTRL


class FakeDL:
    def __init__(self):
        self.texts: list[str] = []
        self.fills: int = 0

    def fill_path(self, *a):
        self.fills += 1

    def stroke_path(self, *a):
        pass

    def draw_text(self, s, *a):
        self.texts.append(s)


def _focused(widget):
    widget._focus_t = 1.0
    return widget


# --- TextField --------------------------------------------------------------

def test_textfield_type_mirrors_value():
    seen = []
    tf = TextField(x=0, y=0, w=200, h=40, focus_id="f", on_change=seen.append)
    for ch in "hello":
        tf.on_text(ch)
    assert tf.value == "hello"          # mirror updated
    assert tf._edit.caret == 5
    assert seen[-1] == "hello"          # on_change fired


def test_textfield_selection_and_copy_semantics():
    tf = TextField(x=0, y=0, w=200, h=40, focus_id="f")
    for ch in "hello":
        tf.on_text(ch)
    tf.on_key("ArrowLeft", MOD_SHIFT)
    tf.on_key("ArrowLeft", MOD_SHIFT)
    assert tf.selected_text() == "lo"
    tf.delete_selection()
    assert tf.value == "hel"


def test_textfield_password_masks_glyphs():
    tf = _focused(TextField(x=0, y=0, w=200, h=40, focus_id="f", password=True))
    for ch in "secret":
        tf.on_text(ch)
    dl = FakeDL()
    tf.paint(dl)
    assert "secret" not in dl.texts
    assert any(set(s) == {"•"} for s in dl.texts)  # bullet string drawn


def test_textfield_validator_passthrough():
    tf = TextField(x=0, y=0, w=120, h=40, focus_id="f",
                   validator=IntValidator(0, 99).validate)
    for ch in "4":
        tf.on_text(ch)
    tf.on_text("x")   # rejected by validator
    tf.on_text("2")   # ok -> 42
    assert tf.value == "42"


def test_textfield_mask_passthrough():
    tf = TextField(x=0, y=0, w=160, h=40, focus_id="f", mask=Mask("000-000"))
    for ch in "123456":
        tf.on_text(ch)
    assert tf.value == "123-456"


def test_textfield_paste_flattens_newlines():
    tf = TextField(x=0, y=0, w=200, h=40, focus_id="f")
    tf.on_paste("a\nb\nc")
    assert tf.value == "a b c"


def test_textfield_caret_and_selection_drawn_when_focused():
    tf = _focused(TextField(x=0, y=0, w=200, h=40, focus_id="f"))
    for ch in "abcd":
        tf.on_text(ch)
    tf._blink_t = 0.0  # caret visible phase
    dl = FakeDL()
    tf.paint(dl)
    fills_no_sel = dl.fills
    # Now select and confirm an extra fill (selection rect) is emitted.
    tf.on_key("ArrowLeft", MOD_SHIFT)
    dl2 = FakeDL()
    tf.paint(dl2)
    assert dl2.fills > fills_no_sel


def test_textfield_ime_preedit_rendered():
    tf = _focused(TextField(x=0, y=0, w=200, h=40, focus_id="f"))
    tf.on_text("a")
    tf.on_ime_preedit("に")
    dl = FakeDL()
    tf.paint(dl)
    assert "に" in dl.texts
    tf.on_ime_commit("日")
    assert tf.value == "a日"


def test_textfield_caret_from_x_uses_shaping():
    tf = TextField(x=10, y=0, w=200, h=40, focus_id="f")
    for ch in "hello":
        tf.on_text(ch)
    # Click near the far left → caret at/near 0.
    i0 = tf.caret_from_x(tf.x + 12.0)
    assert i0 == 0
    # Click far right → caret at end.
    iend = tf.caret_from_x(tf.x + 12.0 + 10_000)
    assert iend == 5


# --- TextArea ---------------------------------------------------------------

def test_textarea_multiline_typing_and_enter():
    ta = TextArea(x=0, y=0, w=300, h=120, focus_id="t")
    for ch in "ab":
        ta.on_text(ch)
    ta.on_key("Enter", 0)
    for ch in "cd":
        ta.on_text(ch)
    assert ta.value == "ab\ncd"


def test_textarea_vertical_caret_movement():
    ta = TextArea(x=0, y=0, w=300, h=120, focus_id="t")
    ta.set_value("abcd\nefgh")
    ta._edit.set_caret(2)        # line 0 col 2
    ta.on_key("ArrowDown", 0)
    assert ta._edit.caret == 7   # line 1 col 2


def test_textarea_selection_across_lines_draws():
    ta = _focused(TextArea(x=0, y=0, w=300, h=120, focus_id="t"))
    ta.set_value("abc\ndef")
    ta._edit.anchor = 1
    ta._edit.caret = 6           # selection spans the newline
    dl = FakeDL()
    ta.paint(dl)
    # multiple fill_path calls (bg, border, ≥1 selection rect, caret)
    assert dl.fills >= 3


def test_textarea_caret_from_point_maps_line_and_col():
    ta = TextArea(x=0, y=0, w=300, h=120, focus_id="t")
    ta.set_value("abcd\nefgh")
    t_lh = ta._lh(__import__("elysium.theme", fromlist=["current_theme"]).current_theme())
    px, py = ta._pad()
    # Click on the second line, near its start → index in "efgh".
    idx = ta.caret_from_point(px, py + t_lh + 2)
    assert 5 <= idx <= 9
