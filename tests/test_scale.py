"""Tier-3: large-data / scale tests. These assert *algorithmic* behavior —
only the visible window is built/painted, damage stays bounded — not wall-clock
time, so they're stable across CI hardware.
"""
from __future__ import annotations

from elysium.testing import CaptureDL
from elysium.components.virtual import VirtualList, VirtualForm, visible_window
from elysium.modelview import ItemModel, Column, TableView


def test_virtuallist_100k_paints_only_visible():
    painted: list[int] = []
    vl = VirtualList(x=0, y=0, w=400, h=300, item_count=100_000, item_height=20.0,
                     render_item=lambda dl, i, *a: painted.append(i))
    vl.paint(CaptureDL())
    # viewport 300 / 20 ≈ 15 rows + overscan — nowhere near 100k.
    assert len(painted) < 25
    assert painted[0] == 0


def test_virtuallist_scrolled_window_is_constant_size():
    counts = []
    vl = VirtualList(x=0, y=0, w=400, h=300, item_count=1_000_000, item_height=20.0,
                     render_item=lambda dl, i, *a: None)
    for offset in (0, 5_000, 5_000_000, 19_999_000):
        vl.set_scroll(offset)
        first, last, _ = vl.visible_range()
        counts.append(last - first)
    # The painted window is the same small size regardless of scroll depth.
    assert max(counts) < 25
    assert max(counts) - min(counts) <= 2


def test_tableview_100k_visible_row_range_bounded():
    rows = [{"v": i} for i in range(100_000)]
    m = ItemModel(rows=rows, columns=[Column("v")])
    tv = TableView(x=0, y=0, w=200, h=400, model=m, row_height=20.0)
    s, e = tv.visible_row_range()
    assert e - s < 25
    # Painting touches only the visible window's cells.
    dl = CaptureDL()
    tv.paint(dl)
    assert dl.calls.get("draw_text", 0) < 60


def test_itemmodel_large_sort_filter_view_cached():
    rows = [{"k": (i * 7919) % 100_000} for i in range(100_000)]
    m = ItemModel(rows=rows, columns=[Column("k")])
    m.toggle_sort("k")
    v1 = m.view()
    assert v1[0]["k"] <= v1[-1]["k"]            # sorted
    # The derived view is cached until a mutation bumps the version.
    assert m.view() is v1
    m.filter(lambda r: r["k"] < 1000)
    assert m.view() is not v1
    assert all(r["k"] < 1000 for r in m.view())


def test_virtualform_50_fields_only_visible_painted():
    heights = [44.0] * 200
    painted: list[int] = []
    vf = VirtualForm(x=0, y=0, w=400, h=300, row_heights=heights,
                     render_row=lambda dl, i, *a: painted.append(i))
    vf.set_scroll(44.0 * 100)
    vf.paint(CaptureDL())
    assert painted[0] == 100 and len(painted) < 12


def test_visible_window_math_is_o1():
    # The window function does not iterate the item list — same result whether
    # count is 100 or 100 million.
    a = visible_window(100, 20.0, 300.0, 200.0)
    b = visible_window(100_000_000, 20.0, 300.0, 200.0)
    assert a[0] == b[0]                          # same first index
    assert (a[1] - a[0]) == (b[1] - b[0])        # same window size
