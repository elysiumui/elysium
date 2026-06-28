"""Tier-2 Phase-9: the UiHarness QTest-equivalent.

Includes harness-based rewrites of two Tier-1 integration scenarios (validated
form typing; editable table click→sort→inline-edit) to prove the harness
replaces the bespoke per-test FakeWindow + InputRouter wiring.
"""
from __future__ import annotations

import datetime as dt

from elysium.testing import UiHarness, CTRL
from elysium.components import TextField
from elysium.components.dataentry import SpinBox, DateEdit, EditableComboBox
from elysium.components.scroll import ScrollView
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate


# --- harness primitives -----------------------------------------------------

def test_type_routes_to_focused_field():
    f = TextField(x=0, y=0, w=200, h=32, focus_id="name")
    h = UiHarness([f])
    h.focus("name").type("Ada")
    assert h.find("name").value == "Ada"


def test_find_and_find_by():
    a = TextField(x=0, y=0, w=100, h=30, focus_id="a")
    b = TextField(x=0, y=40, w=100, h=30, focus_id="b")
    h = UiHarness([a, b])
    assert h.find("b") is b
    assert h.find_by(lambda w: getattr(w, "focus_id", None) == "a") is a


def test_tab_navigation_moves_focus():
    a = TextField(x=0, y=0, w=100, h=30, focus_id="a")
    b = TextField(x=0, y=40, w=100, h=30, focus_id="b")
    h = UiHarness([a, b]).focus("a")
    h.key("Tab")
    assert h.focused_id == "b"


def test_click_widget_focuses_and_hits():
    f = TextField(x=10, y=10, w=200, h=40, focus_id="email")
    h = UiHarness([f])
    h.click_widget("email")
    assert h.focused_id == "email"


def test_clipboard_via_harness():
    a = TextField(x=0, y=0, w=200, h=32, focus_id="a")
    b = TextField(x=0, y=40, w=200, h=32, focus_id="b")
    h = UiHarness([a, b])
    h.focus("a").type("copyme")
    h.key("KeyA", CTRL).key("KeyC", CTRL)
    h.focus("b").key("KeyV", CTRL)
    assert h.find("b").value == "copyme"


def test_ime_commit_via_harness():
    f = TextField(x=0, y=0, w=200, h=32, focus_id="f")
    h = UiHarness([f]).focus("f")
    h.ime(preedit="に")
    assert f._edit.preedit == "に"
    h.ime(commit="日本語")
    assert f.value == "日本語"


def test_scroll_routes_to_hovered_scrollview():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=800)
    h = UiHarness([sv])
    h.scroll(0, -60, at=(50, 50))
    assert sv.scroll_y == 60.0


def test_texts_capture_for_visual_assertion():
    f = TextField(x=0, y=0, w=200, h=40, focus_id="f", label="Email")
    h = UiHarness([f]).focus("f").type("hi")
    assert "hi" in h.texts()


def test_play_script():
    f = TextField(x=0, y=0, w=200, h=32, focus_id="name")
    h = UiHarness([f])
    h.play([("focus", "name"), ("type", "Ada"), ("type", " Lovelace")])
    assert h.find("name").value == "Ada Lovelace"


# --- converted integration scenarios ---------------------------------------

def test_validated_form_via_harness():
    """Tier-1 'router drives a validated form', rewritten on the harness."""
    name = TextField(x=0, y=0, w=200, h=32, focus_id="name")
    age = SpinBox(x=0, y=40, w=120, h=32, focus_id="age", value=18, minimum=0, maximum=120)
    born = DateEdit(x=0, y=80, w=160, h=32, focus_id="born", date=dt.date(2000, 1, 1))
    country = EditableComboBox(x=0, y=120, w=200, h=32, focus_id="country",
                               items=["Canada", "Chile", "China"])
    h = UiHarness([name, age, born, country]).focus("name")
    h.type("Ada")
    assert name.value == "Ada"
    h.key("Tab").key("ArrowUp")          # → age, step up
    assert h.focused_id == "age" and age.value == 19
    h.key("Tab").key("ArrowUp")          # → born, year up
    assert born.date.year == 2001
    h.key("Tab").type("Ch").key("ArrowDown").key("Enter")  # → combo, filter+pick
    assert country.value in ("Chile", "China")


def test_editable_table_via_harness():
    """Tier-1 'editable table sort + inline edit', rewritten on the harness."""
    model = ItemModel(
        rows=[{"name": "Bob", "age": 30}, {"name": "Ada", "age": 45}, {"name": "Cy", "age": 20}],
        columns=[Column("name", width=120, editable=True, delegate=EditableCellDelegate()),
                 Column("age", align="right")],
    )
    tv = TableView(x=0, y=0, w=320, h=200, model=model)
    h = UiHarness([tv])
    h.paint()                             # lay out header rects
    # Click the "age" header → sort ascending.
    h.click(tv._col_x(1) + 5, tv.y + 5)
    assert [model.value(i, "age") for i in range(3)] == [20, 30, 45]
    # Inline-edit row 0 name.
    ed = tv.begin_edit(0, 0)
    ed.set_value("Renamed")
    tv.commit_edit()
    assert model.value(0, "name") == "Renamed"
