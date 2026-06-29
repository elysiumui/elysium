"""Tier 4 Phase 1 — app-shell widgets: GroupBox, StatusBar, Splitter, MenuBar."""
from __future__ import annotations

import pytest

from elysium import theme as T
from elysium.components import MenuItem
from elysium.shell import GroupBox, StatusBar, Splitter, MenuBar


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def _render(widget, w=400, h=300):
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    widget.paint(dl)
    layer = n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


# --- GroupBox --------------------------------------------------------------

def test_groupbox_content_rect_inside_frame():
    gb = GroupBox(x=10, y=10, w=200, h=160, title="Transform", pad=12, header_h=30)
    cx, cy, cw, ch = gb.content_rect()
    assert cx == 10 + 12
    assert cy == 10 + 30 + 12
    assert cw == 200 - 24
    assert ch == 160 - 30 - 24
    assert _render(gb)[:4] == b"\x89PNG"


def test_groupbox_degenerate_size_clamps_nonnegative():
    gb = GroupBox(x=0, y=0, w=10, h=10, pad=12, header_h=30)
    _, _, cw, ch = gb.content_rect()
    assert cw >= 0 and ch >= 0


# --- StatusBar -------------------------------------------------------------

def test_statusbar_renders_with_message_and_sections():
    sb = StatusBar(x=0, y=276, w=400, h=24, message="Ready",
                   sections=["UTF-8", "Ln 12, Col 4", "100%"])
    assert _render(sb)[:4] == b"\x89PNG"


# --- Splitter --------------------------------------------------------------

def test_splitter_panes_partition_horizontally():
    s = Splitter(x=0, y=0, w=200, h=100, orientation="horizontal",
                 ratio=0.5, handle=6)
    a, b = s.pane_rects()
    # left pane ends before the handle, right pane begins after it
    assert a[0] == 0 and a[2] == pytest.approx(100 - 3)
    assert b[0] == pytest.approx(103) and b[2] == pytest.approx(97)
    # the two panes + handle tile the full width
    assert a[2] + s.handle + b[2] == pytest.approx(200)


def test_splitter_drag_clamps_to_min_px():
    s = Splitter(x=0, y=0, w=200, h=100, orientation="horizontal", min_px=40)
    hx, hy, hw, hh = s.handle_rect()
    assert s.on_press(hx + hw / 2, hy + hh / 2) is True
    # drag far past the left edge → clamped to min_px fraction
    s.on_drag(-500, 50)
    assert s.ratio == pytest.approx(40 / 200)
    s.on_drag(99999, 50)
    assert s.ratio == pytest.approx(1 - 40 / 200)
    s.on_release()
    assert s._dragging is False


def test_splitter_press_off_handle_does_not_drag():
    s = Splitter(x=0, y=0, w=200, h=100)
    assert s.on_press(20, 20) is False
    assert _render(s, 200, 100)[:4] == b"\x89PNG"


def test_splitter_vertical_orientation():
    s = Splitter(x=0, y=0, w=100, h=200, orientation="vertical", ratio=0.25)
    a, b = s.pane_rects()
    assert a[1] == 0 and a[3] == pytest.approx(50 - 3)
    assert b[1] == pytest.approx(53)


# --- MenuBar ---------------------------------------------------------------

def _menubar():
    fired = []
    menus = [
        ("File", [MenuItem(label="New", on_click=lambda: fired.append("new")),
                  MenuItem(label="Open", shortcut="Ctrl+O")]),
        ("Edit", [MenuItem(label="Undo", shortcut="Ctrl+Z"),
                  MenuItem(label="Redo")]),
        ("View", [MenuItem(label="Zoom In")]),
    ]
    return MenuBar(x=0, y=0, w=400, h=28, menus=menus), fired


def test_menubar_titles_laid_out_left_to_right():
    mb, _ = _menubar()
    rects = mb.title_rects()
    assert [r[1] for r in rects] == ["File", "Edit", "View"]
    xs = [r[2] for r in rects]
    assert xs == sorted(xs)  # strictly increasing


def test_menubar_click_toggles_open():
    mb, _ = _menubar()
    i, title, cx, tw = mb.title_rects()[0]
    assert mb.on_click(cx + 5, mb.y + 5) is True
    assert mb.open_index == 0
    # second click on the same title closes it
    mb.on_click(cx + 5, mb.y + 5)
    assert mb.open_index == -1


def test_menubar_open_menu_positioned_under_title():
    mb, _ = _menubar()
    mb.open_index = 1  # Edit
    m = mb.open_menu()
    assert m is not None
    _, _, cx, _ = mb.title_rects()[1]
    assert m.x == cx
    assert m.y == mb.y + mb.h + 2
    assert [it.label for it in m.items] == ["Undo", "Redo"]


def test_menubar_dispatch_fires_item_callback():
    mb, fired = _menubar()
    mb.open_index = 0
    m = mb.open_menu()
    # click the first item ("New")
    row_y = m.y + 4 + 0 * m.item_h
    handled = mb.dispatch_open_click(m.x + 10, row_y + 5)
    assert handled is True
    assert fired == ["new"]
    assert mb.open_index == -1  # closes after activation


def test_menubar_click_outside_open_dropdown_closes():
    mb, _ = _menubar()
    mb.open_index = 2
    handled = mb.dispatch_open_click(9999, 9999)
    assert handled is True
    assert mb.open_index == -1


def test_menubar_renders():
    mb, _ = _menubar()
    mb.open_index = 0
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    mb.paint(dl)
    m = mb.open_menu()
    if m is not None:
        m.paint(dl)
    layer = n.SkiaLayer(400, 200)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


# --- ToolBar / ToolButton (Phase 2) ---------------------------------------

from elysium.shell import ToolButton, ToolBar, TabWidget  # noqa: E402


def _dot_icon(dl, cx, cy, size, color):
    from elysium.components import _rounded_rect
    dl.fill_path(_rounded_rect(cx - size / 2, cy - size / 2, size, size, 3), color)


def test_toolbutton_click_respects_enabled():
    fired = []
    b = ToolButton(label="Run", on_click=lambda: fired.append(1))
    b.click()
    assert fired == [1]
    b.enabled = False
    b.click()
    assert fired == [1]  # disabled → no fire


def test_toolbar_layout_positions_buttons_and_spacer():
    a = ToolButton(icon=_dot_icon)
    b = ToolButton(icon=_dot_icon)
    c = ToolButton(icon=_dot_icon)
    tb = ToolBar(x=0, y=0, w=400, h=36, button=30, gap=4, pad=6,
                 items=[a, "separator", b, "spacer", c])
    tb.layout()
    # a then b are left-packed; c is pushed to the right by the spacer
    assert a.x == 6
    assert b.x > a.x
    assert c.x > b.x + 100  # spacer opened a big gap
    assert a.w == a.h == 30
    assert _render(tb, 400, 40)[:4] == b"\x89PNG"


def test_toolbar_hit_returns_button():
    a = ToolButton(icon=_dot_icon)
    tb = ToolBar(x=0, y=0, w=200, h=36, items=[a])
    tb.layout()
    assert tb.hit(a.x + 5, a.y + 5) is a
    assert tb.hit(190, 5) is None


def test_toolbar_vertical_orientation():
    a = ToolButton(icon=_dot_icon)
    b = ToolButton(icon=_dot_icon)
    tb = ToolBar(x=0, y=0, w=36, h=300, orientation="vertical", items=[a, b])
    tb.layout()
    assert a.x == b.x        # same column
    assert b.y > a.y         # stacked downward


# --- TabWidget (Phase 2) ---------------------------------------------------

def _tabwidget(closable=False):
    from elysium.components import Label
    tabs = [("Code", Label(text="code")),
            ("Preview", Label(text="preview")),
            ("Console", Label(text="console"))]
    return TabWidget(x=0, y=0, w=400, h=240, tabs=tabs, closable=closable)


def test_tabwidget_content_rect_below_strip():
    tw = _tabwidget()
    cx, cy, cw, ch = tw.content_rect()
    assert cy == tw.y + tw.tab_h
    assert ch == tw.h - tw.tab_h


def test_tabwidget_click_switches_tab():
    tw = _tabwidget()
    changed = []
    tw.on_change = lambda i: changed.append(i)
    _, _, tx, _w = tw.tab_rects()[1]
    assert tw.on_click(tx + 5, tw.y + 5) is True
    assert tw.current == 1 and changed == [1]


def test_tabwidget_close_removes_tab():
    tw = _tabwidget(closable=True)
    closed = []
    tw.on_close = lambda i: closed.append(i)
    _, _, tx, twd = tw.tab_rects()[0]
    cxr = tw._close_rect(tx, twd)
    handled = tw.on_click(cxr[0] + 2, cxr[1] + 2)
    assert handled is True
    assert closed == [0]
    assert [t[0] for t in tw.tabs] == ["Preview", "Console"]


def test_tabwidget_paints_active_content():
    tw = _tabwidget()
    tw.current = 2
    assert _render(tw, 400, 240)[:4] == b"\x89PNG"
    # active content got laid into the content rect
    content = tw.tabs[2][1]
    cx, cy, cw, ch = tw.content_rect()
    assert content.x == cx and content.w == cw
