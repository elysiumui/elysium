"""Tier-1 Phase-5: data-entry widgets (spin/date/time/calendar/combo)."""
from __future__ import annotations

import datetime as dt

from elysium.components.dataentry import (
    SpinBox,
    DoubleSpinBox,
    DateEdit,
    TimeEdit,
    CalendarWidget,
    EditableComboBox,
)


class FakeDL:
    def __init__(self):
        self.texts: list[str] = []

    def fill_path(self, *a):
        pass

    def stroke_path(self, *a):
        pass

    def draw_text(self, s, *a):
        self.texts.append(str(s))


# --- SpinBox ----------------------------------------------------------------

def test_spinbox_step_and_clamp():
    sb = SpinBox(value=5, minimum=0, maximum=10, step=2)
    sb.step_by(1)
    assert sb.value == 7
    sb.step_by(5)  # 7 + 5*2 = 17 → clamp 10
    assert sb.value == 10
    sb.step_by(-100)
    assert sb.value == 0


def test_spinbox_wrap():
    sb = SpinBox(value=10, minimum=0, maximum=10, wrap=True)
    sb.step_by(1)
    assert sb.value == 0
    sb.step_by(-1)
    assert sb.value == 10


def test_spinbox_typing_respects_validator():
    sb = SpinBox(value=0, minimum=0, maximum=99)
    sb.set_value(4)
    sb.on_text("2")   # caret at end → "42" ok
    assert sb.value == 42
    sb.on_text("9")   # "429" > 99 → rejected
    assert sb.value == 42


def test_spinbox_stepper_buttons_paint_and_click():
    sb = SpinBox(x=0, y=0, w=120, h=32, value=1, minimum=0, maximum=10)
    sb._focus_t = 1.0
    sb.paint(FakeDL())  # lays out _up_rect/_down_rect
    ux, uy, uw, uh = sb._up_rect
    sb.on_mouse_press(ux + 1, uy + 1)
    assert sb.value == 2


def test_doublespinbox_decimals():
    ds = DoubleSpinBox(value=1.5, minimum=0.0, maximum=5.0, step=0.5, decimals=1)
    ds.step_by(1)
    assert abs(ds.value - 2.0) < 1e-9
    assert ds._edit.text == "2.0"


# --- DateEdit ---------------------------------------------------------------

def test_dateedit_segment_step_clamps_day():
    de = DateEdit(date=dt.date(2024, 1, 31))
    de._seg = 1                 # month segment
    de.on_key("ArrowUp", 0)     # Jan→Feb; day 31 invalid → clamp 29 (leap year)
    assert de.date == dt.date(2024, 2, 29)


def test_dateedit_year_wrap_segment_nav():
    de = DateEdit(date=dt.date(2020, 6, 15))
    de._seg = 2                 # day
    de.on_key("ArrowLeft", 0)   # → month segment
    assert de._seg == 1
    de.on_key("ArrowRight", 0)
    de.on_key("ArrowRight", 0)  # wraps day→year
    assert de._seg == 0


def test_dateedit_typing_digits():
    de = DateEdit(date=dt.date(2024, 1, 1))
    de._seg = 1
    de.on_text("0"); de.on_text("7")  # type month 07 → advances
    assert de.date.month == 7


# --- TimeEdit ---------------------------------------------------------------

def test_timeedit_hour_wrap():
    te = TimeEdit(time=dt.time(23, 59, 0))
    te._seg = 0
    te.on_key("ArrowUp", 0)
    assert te.time.hour == 0


def test_timeedit_without_seconds():
    te = TimeEdit(time=dt.time(10, 30, 0), show_seconds=False)
    assert len(te._segdefs()) == 2


# --- CalendarWidget ---------------------------------------------------------

def test_calendar_arrow_navigation():
    cw = CalendarWidget(selected=dt.date(2024, 3, 15))
    cw.on_key("ArrowRight", 0)
    assert cw.selected == dt.date(2024, 3, 16)
    cw.on_key("ArrowDown", 0)
    assert cw.selected == dt.date(2024, 3, 23)


def test_calendar_month_paging():
    cw = CalendarWidget(selected=dt.date(2024, 1, 15))
    cw.on_key("PageUp", 0)
    assert cw._view_month == 12 and cw._view_year == 2023


def test_calendar_click_selects_day():
    cw = CalendarWidget(x=0, y=0, w=240, h=220, selected=dt.date(2024, 3, 1))
    cw.paint(FakeDL())  # populates _cell_rects
    day_target, rect = cw._cell_rects[10]
    cw.on_mouse_press(rect[0] + 2, rect[1] + 2)
    assert cw.selected == day_target


# --- EditableComboBox -------------------------------------------------------

def test_combo_filter_as_you_type():
    cb = EditableComboBox(items=["Apple", "Apricot", "Banana", "Cherry"])
    cb.on_text("Ap")
    assert cb.filtered() == ["Apple", "Apricot"]


def test_combo_keyboard_select():
    cb = EditableComboBox(items=["Apple", "Apricot", "Banana"])
    cb.on_text("a")            # filters + opens
    assert cb.open
    cb.on_key("ArrowDown", 0)  # highlight 1
    cb.on_key("Enter", 0)
    assert cb.value in ("Apricot", "Banana")  # second match
    assert not cb.open


def test_combo_click_arrow_toggles_and_pick():
    cb = EditableComboBox(x=0, y=0, w=160, h=32, items=["X", "Y", "Z"])
    cb.paint(FakeDL())  # lays out arrow rect
    ax, ay, aw, ah = cb._arrow_rect
    cb.on_mouse_press(ax + 1, ay + 1)
    assert cb.open
    cb.paint(FakeDL())  # lays out item rects
    item, (x, y, w, h) = cb._item_rects[1]
    cb.on_mouse_press(x + 1, y + 1)
    assert cb.value == item and not cb.open
