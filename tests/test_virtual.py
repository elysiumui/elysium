"""Tier-2 Phase-3: virtualization (VirtualList, VirtualForm, shared windowing)."""
from __future__ import annotations

from elysium.components.virtual import (
    visible_window, row_window, VirtualList, VirtualForm,
)


class FakeDL:
    def __init__(self):
        self.rows: list[int] = []
        self.clips = 0

    def push_clip(self, *a): self.clips += 1
    def pop_clip(self, *a): pass
    def fill_path(self, *a): pass
    def stroke_path(self, *a): pass


# --- pure windowing ---------------------------------------------------------

def test_visible_window_basic():
    first, last, first_y = visible_window(1000, 20.0, 200.0, 0.0)
    assert first == 0 and last <= 13 and first_y == 0.0


def test_visible_window_scrolled():
    first, last, first_y = visible_window(1000, 20.0, 200.0, 105.0)
    assert first == 5            # 105 // 20 = 5
    assert first_y == 5 * 20.0 - 105.0  # -5.0, partial first row
    assert last - first <= 13


def test_visible_window_overscan():
    f0, l0, _ = visible_window(1000, 20.0, 200.0, 200.0, overscan=0)
    f2, l2, _ = visible_window(1000, 20.0, 200.0, 200.0, overscan=2)
    assert f2 == f0 - 2 and l2 >= l0


def test_row_window_matches_legacy_formula():
    # The exact formula TableView used before the refactor.
    n, viewport, rh, scroll = 500, 260.0, 26.0, 7
    start = max(0, int(scroll))
    rows = int(viewport / rh) + 1
    assert row_window(n, viewport, rh, scroll) == (start, min(n, start + rows))


# --- VirtualList ------------------------------------------------------------

def test_virtuallist_paints_only_visible():
    painted = []
    vl = VirtualList(x=0, y=0, w=300, h=200, item_count=10_000, item_height=20.0,
                     render_item=lambda dl, i, x, y, w, h: painted.append(i))
    vl.paint(FakeDL())
    # ~ (200/20)+~ rows + overscan, nowhere near 10k.
    assert len(painted) < 20
    assert painted[0] == 0


def test_virtuallist_scroll_shifts_window():
    painted = []
    vl = VirtualList(x=0, y=0, w=300, h=200, item_count=10_000, item_height=20.0,
                     render_item=lambda dl, i, *a: painted.append(i))
    vl.on_scroll(0, -1000)       # scroll down 1000px → row 50
    vl.paint(FakeDL())
    assert painted[0] >= 48 and painted[0] <= 50


def test_virtuallist_scroll_clamps():
    vl = VirtualList(x=0, y=0, w=300, h=200, item_count=100, item_height=20.0)
    vl.on_scroll(0, -1e9)
    assert vl.scroll_y == vl.max_scroll() == 100 * 20.0 - 200.0
    vl.on_scroll(0, 1e9)
    assert vl.scroll_y == 0.0


def test_virtuallist_index_at_and_scroll_to():
    vl = VirtualList(x=0, y=10, w=300, h=200, item_count=1000, item_height=20.0)
    assert vl.index_at(10) == 0          # first row at viewport top
    assert vl.index_at(10 + 45) == 2     # 45px down → row 2
    vl.scroll_to_index(500)
    # Row 500 now within the viewport.
    f, l, _ = vl.visible_range()
    assert f <= 500 < l


def test_virtuallist_bar_visible_only_when_overflowing():
    small = VirtualList(x=0, y=0, w=300, h=400, item_count=5, item_height=20.0)
    assert not small._bar_visible() and small.viewport_w() == 300.0
    big = VirtualList(x=0, y=0, w=300, h=200, item_count=5000, item_height=20.0,
                      bar_thickness=10.0)
    assert big._bar_visible() and big.viewport_w() == 290.0


# --- VirtualForm ------------------------------------------------------------

def test_virtualform_variable_heights():
    heights = [30.0, 50.0, 20.0, 80.0, 40.0, 60.0, 100.0, 25.0]
    painted = []
    vf = VirtualForm(x=0, y=0, w=300, h=120, row_heights=heights,
                     render_row=lambda dl, i, *a: painted.append(i))
    # Scroll so the band starts mid-way.
    vf.set_scroll(60.0)  # past rows 0 (30) and into row 1 (30..80)
    vf.paint(FakeDL())
    assert painted[0] == 1               # row 1 spans 30..80, visible at scroll 60
    assert vf.content_height() == sum(heights)


def test_virtualform_only_visible_rows():
    heights = [25.0] * 4000
    painted = []
    vf = VirtualForm(x=0, y=0, w=300, h=200, row_heights=heights,
                     render_row=lambda dl, i, *a: painted.append(i))
    vf.set_scroll(25.0 * 1000)
    vf.paint(FakeDL())
    assert len(painted) < 16
    assert painted[0] == 1000


# --- model/view refactor stayed behavior-preserving -------------------------

def test_tableview_visible_row_range_unchanged():
    from elysium.modelview import ItemModel, Column, TableView
    rows = [{"a": i} for i in range(10_000)]
    m = ItemModel(rows=rows, columns=[Column("a")])
    tv = TableView(x=0, y=0, w=200, h=200, model=m, row_height=20.0, show_header=True,
                   header_height=28.0)
    s, e = tv.visible_row_range()
    body = 200 - 28
    assert (s, e) == (0, min(10_000, int(body / 20.0) + 1))
