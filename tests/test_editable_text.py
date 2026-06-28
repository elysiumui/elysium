"""Tier-1 Phase-2: EditableText model + validators + masks (pure logic)."""
from __future__ import annotations

from elysium.text import (
    EditableText,
    IntValidator,
    DoubleValidator,
    RegexValidator,
    Mask,
    Acceptable,
    Intermediate,
    Invalid,
)


# --- typing / caret ---------------------------------------------------------

def test_type_and_caret():
    e = EditableText()
    e.on_text("hello")
    assert e.text == "hello"
    assert e.caret == 5 and e.anchor == 5


def test_insert_at_caret_mid_string():
    e = EditableText(text="helo", caret=3)
    e.on_text("l")  # -> hello
    assert e.text == "hello"
    assert e.caret == 4


def test_backspace_and_delete_forward():
    e = EditableText(text="abc", caret=2)
    assert e.backspace() and e.text == "ac" and e.caret == 1
    e2 = EditableText(text="abc", caret=1)
    assert e2.delete_forward() and e2.text == "ac" and e2.caret == 1


def test_move_left_right_clamped():
    e = EditableText(text="ab", caret=0)
    e.move_left()
    assert e.caret == 0
    e.move_right(); e.move_right(); e.move_right()
    assert e.caret == 2


# --- selection --------------------------------------------------------------

def test_shift_arrow_selection():
    e = EditableText(text="hello", caret=0)
    e.move_right(select=True)
    e.move_right(select=True)
    assert e.selection() == (0, 2)
    assert e.selected_text() == "he"


def test_typing_replaces_selection():
    e = EditableText(text="hello", caret=0)
    e.anchor = 0; e.caret = 5  # select all
    e.on_text("X")
    assert e.text == "X" and e.caret == 1


def test_select_all():
    e = EditableText(text="hello world")
    e.select_all()
    assert e.selection() == (0, 11)
    assert e.has_selection


def test_collapse_selection_on_plain_arrow():
    e = EditableText(text="hello", caret=0)
    e.anchor = 0; e.caret = 3
    e.move_right()  # collapses to right edge of selection
    assert not e.has_selection and e.caret == 3
    e.anchor = 1; e.caret = 4
    e.move_left()  # collapses to left edge
    assert not e.has_selection and e.caret == 1


# --- word navigation --------------------------------------------------------

def test_word_jump():
    e = EditableText(text="foo bar baz", caret=0)
    e.move_word_right()
    assert e.caret == 3  # end of "foo"
    e.move_word_right()
    assert e.caret == 7  # end of "bar"
    e.move_word_left()
    assert e.caret == 4  # start of "bar"


def test_delete_word_back():
    e = EditableText(text="foo bar", caret=7)
    assert e.delete_word_back()
    assert e.text == "foo "


# --- undo / redo ------------------------------------------------------------

def test_undo_redo_typing_coalesced():
    e = EditableText()
    for ch in "hello":
        e.on_text(ch)
    # Coalesced run → one undo removes the whole run.
    assert e.undo()
    assert e.text == ""
    assert e.redo()
    assert e.text == "hello"


def test_undo_separates_after_caret_move():
    e = EditableText()
    e.on_text("abc")
    e.move_left()       # breaks coalescing
    e.on_text("X")      # new group: "abXc"
    assert e.text == "abXc"
    e.undo()            # removes only "X"
    assert e.text == "abc"
    e.undo()            # removes "abc"
    assert e.text == ""


# --- home/end + multiline ---------------------------------------------------

def test_home_end_single_line():
    e = EditableText(text="hello", caret=2)
    e.move_home(); assert e.caret == 0
    e.move_end();  assert e.caret == 5


def test_multiline_vertical_movement_preserves_column():
    e = EditableText(text="abcd\nefgh\nij", multiline=True, caret=2)  # line 0 col 2
    e.move_down()
    assert e.caret == 7  # line 1 col 2 ("efgh" -> index 5+2)
    e.move_down()
    assert e.caret == 12  # line 2 "ij" shorter → clamped to end (col 2 > len)
    e.move_up()
    assert e.caret == 7


def test_multiline_enter_inserts_newline():
    e = EditableText(text="ab", multiline=True, caret=1)
    assert e.on_key("Enter", 0)
    assert e.text == "a\nb"


def test_single_line_enter_not_consumed():
    e = EditableText(text="ab", multiline=False, caret=1)
    assert e.on_key("Enter", 0) is False
    assert e.text == "ab"


# --- validators -------------------------------------------------------------

def test_int_validator_blocks_invalid_insert():
    e = EditableText(validator=IntValidator(0, 999).validate)
    for ch in "12":
        assert e.insert(ch)
    assert not e.insert("a")  # letter rejected
    assert e.text == "12"
    # Exceeding max is rejected.
    e.insert("3")  # 123 ok
    assert e.text == "123"


def test_int_validator_states():
    v = IntValidator(-10, 10)
    assert v.validate("") == Intermediate
    assert v.validate("-") == Intermediate
    assert v.validate("5") == Acceptable
    assert v.validate("11") == Invalid
    assert v.validate("x") == Invalid


def test_double_validator_states():
    v = DoubleValidator(0.0, 100.0, decimals=2)
    assert v.validate("") == Intermediate
    assert v.validate("1.") == Intermediate
    assert v.validate("1.5") == Acceptable
    assert v.validate("1.555") == Invalid  # too many decimals
    assert v.validate("abc") == Invalid


def test_regex_validator():
    v = RegexValidator(r"[A-Z]{3}\d{2}")
    assert v.validate("ABC12") == Acceptable
    assert v.validate("") == Intermediate
    assert v.validate("123") == Invalid


# --- masks ------------------------------------------------------------------

def test_mask_digit_groups():
    m = Mask("000-000")
    assert m.apply("123456") == "123-456"
    assert m.apply("12") == "12"
    assert m.is_complete("123-456")
    assert not m.is_complete("123-45")


def test_mask_filters_bad_chars():
    m = Mask("AA-00")
    assert m.apply("xy12") == "xy-12"
    # digits where letters required get skipped
    assert m.apply("9xy12").startswith("xy") or m.apply("xy12") == "xy-12"


def test_mask_in_editable():
    e = EditableText(mask=Mask("000-000"))
    for ch in "123456":
        e.on_text(ch)
    assert e.text == "123-456"


# --- IME --------------------------------------------------------------------

def test_ime_preedit_then_commit():
    e = EditableText(text="a", caret=1)
    e.set_preedit("に")
    assert e.preedit == "に"
    e.commit_preedit("日本")
    assert e.preedit == ""
    assert e.text == "a日本"


# --- on_change callback -----------------------------------------------------

def test_on_change_fires():
    seen = []
    e = EditableText(on_change=seen.append)
    e.on_text("hi")
    e.backspace()
    assert seen[-1] == "h"
