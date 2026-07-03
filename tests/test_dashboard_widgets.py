"""Tier 8 Phase 2 — dashboard & flow widgets: MetricCard, Alert/Inbox,
SegmentedControl, DateRangePicker, Drawer, Stepper, Wizard."""
from __future__ import annotations

import datetime as dt

import pytest

from elysium import theme as T
from elysium.components import Label
from elysium.components.dashboard import MetricCard, Alert, NotificationInbox
from elysium.components.daterange import (
    SegmentedControl, DateRangePicker, preset_range, PRESETS,
)
from elysium.shell import Drawer, Stepper, Wizard


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def _render(widget, w=400, h=240, pre=None):
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    if pre:
        pre(dl)
    widget.paint(dl)
    layer = n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


# --- MetricCard ------------------------------------------------------------

def test_metric_delta_color_direction_and_polarity():
    t = T.current_theme()
    # up + good_up → green
    up_good = MetricCard(delta_dir=1, good_up=True)._delta_color(t)
    assert up_good == t.success
    # up + good_up=False (e.g. refund drag) → red
    up_bad = MetricCard(delta_dir=1, good_up=False)._delta_color(t)
    assert up_bad == t.danger
    # neutral → muted
    assert MetricCard(delta_dir=0)._delta_color(t) == t.on_surface_muted


def test_metric_card_renders_with_spark():
    c = MetricCard(x=10, y=10, w=200, h=110, label="Net profit",
                   value="$4,182", delta="12.4%", delta_dir=1, sub="vs prior day",
                   spark=[1, 3, 2, 5, 4, 6, 8])
    assert _render(c, 240, 140)[:4] == b"\x89PNG"


# --- Alert / NotificationInbox ---------------------------------------------

def test_alert_dismiss_and_action_clicks():
    fired = {"dismiss": 0, "action": 0}
    a = Alert(x=0, y=0, w=300, severity="warning", title="4 SKUs missing cost",
              action_label="Fix in COGS wizard",
              on_action=lambda: fired.__setitem__("action", 1),
              on_dismiss=lambda: fired.__setitem__("dismiss", 1))
    cx, cy, cw, ch = a.close_rect()
    assert a.on_click(cx + 2, cy + 2) is True
    assert fired["dismiss"] == 1
    assert a.on_click(a.x + 20, a.y + a.h - 14) is True   # action link
    assert fired["action"] == 1


def test_inbox_layout_and_dismiss():
    a1 = Alert(title="A", severity="warning")
    a2 = Alert(title="B", severity="danger")
    inbox = NotificationInbox(x=0, y=0, w=300, h=300, alerts=[a1, a2])
    inbox.layout()
    assert a2.y > a1.y and a1.w == 300
    inbox.dismiss(a1)
    assert inbox.alerts == [a2]
    assert _render(inbox, 320, 200)[:4] == b"\x89PNG"


# --- SegmentedControl / DateRangePicker ------------------------------------

def test_segmented_select_and_hit():
    changed = []
    sc = SegmentedControl(x=0, y=0, w=300, h=30,
                          options=["Yesterday", "7d", "30d", "Custom"],
                          on_change=changed.append)
    assert sc.hit_index(160, 15) == 2          # third of four segments
    assert sc.on_click(160, 15) is True
    assert sc.selected == 2 and changed == [2]
    assert _render(sc, 320, 50)[:4] == b"\x89PNG"


def test_preset_range_math():
    today = dt.date(2026, 6, 28)
    assert preset_range("Today", today) == (today, today)
    assert preset_range("Yesterday", today) == (dt.date(2026, 6, 27),) * 2
    assert preset_range("Last 7 days", today) == (dt.date(2026, 6, 22), today)
    assert preset_range("Last 30 days", today) == (dt.date(2026, 5, 30), today)
    assert preset_range("Custom", today) is None


def test_date_range_picker_selects_and_custom():
    today = dt.date(2026, 6, 28)
    got = []
    p = DateRangePicker(x=0, y=0, w=360, h=30, on_change=lambda s, e: got.append((s, e)))
    p.select_preset(1, today)                  # Yesterday
    assert p.current_range(today) == (dt.date(2026, 6, 27),) * 2
    assert got[-1] == (dt.date(2026, 6, 27),) * 2
    # switching to Custom carries the prior range until you set your own;
    # with start/end cleared it is None.
    p.select_preset(PRESETS.index("Custom"), today)
    assert p.is_custom()
    p.start = p.end = None
    assert p.current_range(today) is None
    p.start, p.end = dt.date(2026, 6, 1), dt.date(2026, 6, 10)
    assert p.current_range(today) == (dt.date(2026, 6, 1), dt.date(2026, 6, 10))
    assert _render(p, 380, 50)[:4] == b"\x89PNG"


# --- Drawer ----------------------------------------------------------------

def test_drawer_slides_from_right():
    d = Drawer(x=0, y=0, w=800, h=600, side="right", size=360, title="Order")
    d._t = 0.0
    assert d.panel_rect()[0] == 800           # fully off-screen right
    d._t = 1.0
    assert d.panel_rect()[0] == 800 - 360     # fully in
    cr = d.content_rect()
    assert cr[1] == d.panel_rect()[1] + d.header_h


def test_drawer_click_scrim_closes():
    closed = []
    d = Drawer(x=0, y=0, w=800, h=600, side="right", size=360, open=True,
               on_close=lambda: closed.append(1))
    d._t = 1.0
    # click far left (on the scrim, outside the right panel)
    assert d.on_click(50, 300) is True
    assert d.open is False and closed == [1]


def test_drawer_renders():
    d = Drawer(x=0, y=0, w=400, h=300, side="right", size=200, open=True,
               title="Detail", content=Label(text="body"))
    d._t = 1.0
    assert _render(d, 400, 300)[:4] == b"\x89PNG"


# --- Stepper / Wizard ------------------------------------------------------

def test_stepper_renders():
    s = Stepper(x=0, y=0, w=400, h=40,
                steps=["File", "Map", "Cleanup", "Validate", "Save"], current=2)
    assert _render(s, 420, 70)[:4] == b"\x89PNG"


def test_wizard_navigation():
    changed, finished = [], []
    w = Wizard(x=0, y=0, w=480, h=320,
               steps=[("File", Label(text="a")), ("Map", Label(text="b")),
                      ("Save", Label(text="c"))],
               on_change=changed.append, on_finish=lambda: finished.append(1))
    assert w.can_back() is False and w.is_last() is False
    nx, ny, nw, nh = w._next_rect()
    assert w.on_click(nx + 5, ny + 5) is True        # Next → step 1
    assert w.current == 1 and changed == [1]
    w.next()                                          # → step 2 (last)
    assert w.is_last()
    w.next()                                          # finish
    assert finished == [1]
    bx, by, bw, bh = w._back_rect()
    assert w.on_click(bx + 5, by + 5) is True         # Back
    assert w.current == 1


def test_wizard_renders_active_content():
    w = Wizard(x=0, y=0, w=480, h=320,
               steps=[("File", Label(text="step a")), ("Map", Label(text="step b"))],
               current=0)
    assert _render(w, 480, 320)[:4] == b"\x89PNG"
    cx, cy, cw, ch = w.content_rect()
    assert w.steps[0][1].x == cx     # active content laid into the content rect
