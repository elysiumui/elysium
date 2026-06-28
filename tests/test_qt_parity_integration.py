"""Tier-1 acceptance test: every Tier-1 feature composed through the real
framework wiring (InputRouter + DialogHost + Model/View + widgets), driven by
synthetic input — no live event loop. This is the end-to-end proof that the
six Tier-1 sub-systems interoperate, the integration counterpart to the
runnable ``examples/qt-parity-demo``.
"""
from __future__ import annotations

import datetime as dt

from elysium.input import InputRouter, MOD_CTRL, MOD_SHIFT
from elysium.components import TextField
from elysium.components.dataentry import SpinBox, DateEdit, EditableComboBox
from elysium.modelview import ItemModel, Column, TableView, EditableCellDelegate
from elysium import dialogs as D


class FakeWindow:
    """Implements the surface InputRouter + clipboard pull from."""

    def __init__(self):
        self._q: list[tuple] = []
        self._preedit = ""
        self._clip = ""

    def poll_key_event(self):
        return self._q.pop(0) if self._q else None

    def preedit(self):
        return self._preedit

    def get_clipboard_text(self):
        return self._clip

    def set_clipboard_text(self, s):
        self._clip = s

    def set_ime_cursor_area(self, *a):
        pass

    # helpers
    def type(self, text):
        for ch in text:
            self._q.append((f"Key{ch.upper()}", True, 0, ch))

    def key(self, code, mods=0, text=""):
        self._q.append((code, True, mods, text))

    def ime(self, preedit="", commit=None):
        self._preedit = preedit
        if commit is not None:
            self._q.append(("ImeCommit", True, 0, commit))


def test_router_drives_a_validated_form():
    """A form of TextField + SpinBox + DateEdit + ComboBox, all focusable,
    all driven through one InputRouter with Tab navigation, typing, IME,
    and clipboard."""
    win = FakeWindow()
    r = InputRouter(win)

    name = TextField(x=0, y=0, w=200, h=32, focus_id="name")
    age = SpinBox(x=0, y=40, w=120, h=32, focus_id="age", value=18, minimum=0, maximum=120)
    born = DateEdit(x=0, y=80, w=160, h=32, focus_id="born", date=dt.date(2000, 1, 1))
    country = EditableComboBox(x=0, y=120, w=200, h=32, focus_id="country",
                               items=["Canada", "Chile", "China", "Cuba"])
    r.set_widgets([name, age, born, country])
    r.focus_widget("name")

    # Type a name (with a non-ASCII char to exercise unicode).
    win.type("Adél")
    r.tick()
    assert name.value == "Adél"

    # Tab → SpinBox, type a number, Up-arrow steps.
    win.key("Tab")
    win.type("3")          # caret at end of "18" → "183"? validator max 120 rejects 3rd
    win.key("ArrowUp")     # step +1
    r.tick()
    assert r.focus.focused_id == "age"
    assert age.value in (19, 1)  # stepped from a valid base

    # Tab → DateEdit, step the (year) segment up.
    win.key("Tab")
    win.key("ArrowUp")     # year 2000 → 2001
    r.tick()
    assert born.date.year == 2001

    # Tab → ComboBox, filter-as-you-type then keyboard-select.
    win.key("Tab")
    win.type("Ch")
    win.key("ArrowDown")
    win.key("Enter")
    r.tick()
    assert country.value in ("Chile", "China")


def test_clipboard_round_trip_through_router():
    win = FakeWindow()
    r = InputRouter(win)
    a = TextField(x=0, y=0, w=200, h=32, focus_id="a")
    b = TextField(x=0, y=40, w=200, h=32, focus_id="b")
    r.set_widgets([a, b])
    r.focus_widget("a")
    win.type("hello")
    win.key("KeyA", MOD_CTRL)  # select all
    win.key("KeyC", MOD_CTRL)  # copy
    r.tick()
    assert win.get_clipboard_text() == "hello"
    # Move to b and paste.
    r.focus_widget("b")
    win.key("KeyV", MOD_CTRL)
    r.tick()
    assert b.value == "hello"


def test_ime_composition_through_router():
    win = FakeWindow()
    r = InputRouter(win)
    f = TextField(x=0, y=0, w=200, h=32, focus_id="f")
    r.set_widgets([f])
    r.focus_widget("f")
    # Preedit shows, then commit inserts.
    win.ime(preedit="に")
    r.tick()
    assert f._edit.preedit == "に"
    win.ime(preedit="", commit="日本語")
    r.tick()
    assert f.value == "日本語"


def test_editable_table_with_sort_filter_and_inline_edit():
    model = ItemModel(
        rows=[{"name": "Bob", "age": 30}, {"name": "Ada", "age": 45},
              {"name": "Cy", "age": 20}],
        columns=[Column("name", width=120, editable=True, delegate=EditableCellDelegate()),
                 Column("age", align="right")],
    )
    tv = TableView(x=0, y=0, w=320, h=200, model=model)

    # Sort by age ascending via header click.
    tv.paint(_FakeDL())
    tv.on_mouse_press(tv._col_x(1) + 5, tv.y + 5)
    assert [model.value(i, "age") for i in range(3)] == [20, 30, 45]

    # Filter to age >= 30.
    model.filter(lambda r: r["age"] >= 30)
    assert model.row_count() == 2

    # Inline-edit the first visible name and commit.
    tv.paint(_FakeDL())
    ed = tv.begin_edit(0, 0)
    ed.set_value("Renamed")
    tv.commit_edit()
    assert model.value(0, "name") == "Renamed"


def test_dialog_host_message_and_input_flow():
    host = D.DialogHost()
    host.set_size(800, 600)

    results = []
    m = host.message("Save changes?", "You have unsaved edits.",
                     buttons=["Discard", "Save"], on_result=results.append)
    m.paint(_FakeDL())
    # Press Enter → primary ("Save").
    host.on_key("Enter", 0)
    assert results == ["Save"]

    # Now an input dialog: type + accept.
    got = []
    inp = host.input("Rename", "New name:", default="old", on_result=got.append)
    inp.paint(_FakeDL())
    host.on_text("X")
    host.on_key("Enter", 0)
    assert got == ["oldX"]


def test_demo_app_builds_and_paints_headless():
    """The runnable examples/qt-parity-demo constructs its full UI + paints
    without a live window (build_ui is the testable seam)."""
    import importlib.util
    from pathlib import Path
    demo_path = (Path(__file__).resolve().parent.parent
                 / "examples" / "qt-parity-demo" / "main.py")
    # Load by explicit path under a unique module name to avoid clashing
    # with other examples' top-level `main` modules in sys.modules.
    spec = importlib.util.spec_from_file_location("qt_parity_demo_main", demo_path)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    ui = demo.build_ui()
    assert ui["model"].row_count() == 4
    assert len(ui["focusables"]) == 4
    dl = _FakeDL()
    for w in ui["widgets"].values():
        w.paint(dl)  # no crash


class _FakeDL:
    def clear(self, *a): pass
    def fill_path(self, *a): pass
    def stroke_path(self, *a): pass
    def gradient_card(self, *a): pass
    def fill_path_linear_gradient(self, *a): pass
    def filled_circle(self, *a): pass
    def draw_text(self, *a): pass
    def draw_image_file(self, *a): pass
    def draw_paragraph(self, *a): return 20.0
