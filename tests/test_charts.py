"""Tier 8 Phase 1 — charts: helpers + render of every chart type."""
from __future__ import annotations

import math

import pytest

from elysium import theme as T
from elysium.charts import (
    Series, chart_palette, nice_ticks, format_money, format_pct, format_compact,
    Sparkline, LineChart, AreaChart, BarChart, DonutChart, PieChart, Legend,
)


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def _render(widget, w=400, h=260):
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    widget.paint(dl)
    layer = n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


# --- helpers ---------------------------------------------------------------

def test_nice_ticks_round_numbers():
    lo, hi, step = nice_ticks(0, 9540, target=5)
    assert lo == 0
    assert hi >= 9540
    assert step in (2000.0, 2500.0)  # 1/2/2.5/5 × 10ⁿ
    assert (hi - lo) % step == 0


def test_formatters():
    assert format_money(19540) == "$19,540"
    assert format_money(-1206) == "-$1,206"
    assert format_pct(21.4) == "21.4%"
    assert format_compact(15400) == "15.4k"
    assert format_compact(3_400_000) == "3.4M"


def test_palette_is_distinct():
    pal = chart_palette()
    assert len(pal) >= 6 and len(set(pal)) == len(pal)


# --- sparkline -------------------------------------------------------------

def test_sparkline_points_span_box():
    s = Sparkline(values=[1, 5, 2, 8, 3], x=0, y=0, w=100, h=40)
    pts = s._points()
    assert len(pts) == 5
    xs = [p[0] for p in pts]
    assert xs[0] == 0 and abs(xs[-1] - 100) < 1e-6
    assert all(0 <= p[1] <= 40 for p in pts)
    assert _render(s, 120, 60)[:4] == b"\x89PNG"


# --- line / area -----------------------------------------------------------

def test_linechart_plot_rect_inside():
    c = LineChart(series=[Series(values=[1, 2, 3])], x=0, y=0, w=400, h=240)
    px, py, pw, ph = c.plot_rect()
    assert px > 0 and pw < 400 and ph < 240


def test_area_chart_renders():
    vals = [3000 + 400 * math.sin(i / 2) for i in range(30)]
    c = AreaChart(series=[Series(values=vals, name="Net profit")],
                  x=0, y=0, w=420, h=240,
                  x_labels=[f"d{i}" for i in range(30)])
    assert _render(c, 420, 240)[:4] == b"\x89PNG"


def test_stacked_line_accumulates():
    c = LineChart(series=[Series(values=[1, 1, 1]), Series(values=[2, 2, 2])],
                  stacked=True, x=0, y=0, w=300, h=200)
    layers = c._stacked_values()
    assert layers[0] == [1, 1, 1]
    assert layers[1] == [3, 3, 3]   # stacked on top


# --- bar -------------------------------------------------------------------

def test_bar_chart_stacked_renders():
    c = BarChart(
        series=[Series(values=[5, 3, 8], name="COGS"),
                Series(values=[2, 4, 1], name="Ad")],
        categories=["Jan", "Feb", "Mar"], stacked=True,
        x=0, y=0, w=400, h=240)
    assert c._max() >= 10  # tallest stack = 8+1=9 → nice ceil ≥ 10
    assert _render(c)[:4] == b"\x89PNG"


# --- donut / pie -----------------------------------------------------------

def test_donut_total_and_wedge_geometry():
    d = DonutChart(segments=[("COGS", 8920), ("Ad", 3640), ("Refunds", 1206)],
                   x=0, y=0, w=200, h=200, center_value="$15.4k")
    assert d.total() == pytest.approx(8920 + 3640 + 1206)
    # a wedge path is a closed arc-bounded sector
    w = DonutChart._wedge(100, 100, 50, 90, -math.pi / 2, 0.0)
    assert w.startswith("M ") and w.endswith("Z") and " A " in w
    assert _render(d, 220, 220)[:4] == b"\x89PNG"


def test_pie_has_no_hole():
    assert PieChart().inner_ratio == 0.0


# --- legend ----------------------------------------------------------------

def test_legend_renders_entries_with_values():
    leg = Legend(entries=[("COGS", (91, 141, 239, 255), "$8,920"),
                          ("Ad spend", None, "$3,640")],
                 x=0, y=0, w=200)
    assert _render(leg, 220, 80)[:4] == b"\x89PNG"
