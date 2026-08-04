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


# --- degenerate + missing data (QA priority report, items 1/5/6) -----------

class _CountDL:
    """Records draw calls so tests can assert on counts and path strings.
    The real native DisplayList renders but can't be introspected."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.texts: list[str] = []
        self.calls: dict[str, int] = {}

    def draw_text(self, s, *a, **k) -> None:
        self.texts.append(str(s))
        self.calls["draw_text"] = self.calls.get("draw_text", 0) + 1

    def stroke_path(self, d, *a, **k) -> None:
        self.paths.append(d)
        self.calls["stroke_path"] = self.calls.get("stroke_path", 0) + 1

    def fill_path(self, d, *a, **k) -> None:
        self.paths.append(d)
        self.calls["fill_path"] = self.calls.get("fill_path", 0) + 1

    def fill_path_linear_gradient(self, d, *a, **k) -> None:
        self.paths.append(d)
        self.calls["fill_grad"] = self.calls.get("fill_grad", 0) + 1

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.calls[name] = self.calls.get(name, 0) + 1
        return _rec

    @property
    def total(self) -> int:
        return sum(self.calls.values())


NAN = float("nan")
INF = float("inf")


def test_poly_output_unchanged_for_finite_points():
    """Compat pin: gap support must not alter path data for clean input."""
    from elysium.charts import _poly
    assert _poly([(0, 0), (1, 1)]) == "M 0.00 0.00 L 1.00 1.00"
    assert _poly([]) == ""
    assert _poly([(0, 0)]) == "M 0.00 0.00"


def test_poly_breaks_into_subpaths_on_gap():
    from elysium.charts import _poly
    d = _poly([(0, 0), (1, 1), None, (3, 3), (4, 4)])
    assert d == "M 0.00 0.00 L 1.00 1.00 M 3.00 3.00 L 4.00 4.00"
    assert "nan" not in d and "inf" not in d


def test_gridline_loop_terminates_on_tiny_range():
    """Item 1: an absolute epsilon with a relative step ran ~1e9 times.

    Pre-fix this emitted 2009 draw calls for 1e-9 data (2,000 gridlines
    stacked into a 200px plot) and hung forever at 1e-15.
    """
    for vals in ([1e-9, 2e-9, 3e-9], [1e-15, 2e-15, 3e-15]):
        dl = _CountDL()
        LineChart(series=[Series(values=vals)], x=0, y=0, w=300, h=200).paint(dl)
        assert dl.calls.get("stroke_path", 0) <= 16, vals
        assert dl.total == 9, vals          # identical to clean data


def test_bar_gridline_loop_terminates_on_tiny_range():
    """The same defect had a second, duplicated home in BarChart.paint."""
    dl = _CountDL()
    BarChart(series=[Series(values=[1e-12, 2e-12])],
             categories=["a", "b"], x=0, y=0, w=300, h=200).paint(dl)
    assert dl.calls.get("stroke_path", 0) <= 16


def test_nice_ticks_survives_non_finite():
    """Item 5/6 both originate here: math.floor/ceil raise on inf/NaN."""
    for lo, hi in ((0.0, INF), (NAN, 1.0), (-INF, INF), (NAN, NAN)):
        nlo, nhi, step = nice_ticks(lo, hi)
        assert math.isfinite(nlo) and math.isfinite(nhi) and math.isfinite(step)
        assert step > 0


def test_infinity_in_series_does_not_raise():
    """Item 5: pre-fix this was OverflowError during paint."""
    for cls in (LineChart, AreaChart, BarChart):
        dl = _CountDL()
        cls(series=[Series(values=[1.0, INF, 3.0])],
            x=0, y=0, w=300, h=200).paint(dl)
        assert not any("inf" in p for p in dl.paths)


def test_all_nan_series_renders_empty_plot_not_an_exception():
    """Item 6: pre-fix ValueError in Line/Area/Bar but silently painted by
    Sparkline — three behaviours from one input class."""
    for cls in (LineChart, AreaChart, BarChart):
        dl = _CountDL()
        cls(series=[Series(values=[NAN] * 3)], x=0, y=0, w=300, h=200).paint(dl)
        assert dl.calls.get("stroke_path", 0) >= 0      # axis only, no series
        assert not any("nan" in p for p in dl.paths)
    dl = _CountDL()
    Sparkline(values=[NAN] * 3, x=0, y=0, w=300, h=60).paint(dl)
    assert dl.total == 0                                # nothing to draw


def test_partial_nan_breaks_the_line_and_emits_no_nan_token():
    """The dangerous half of item 6: it did NOT crash, it silently drew a
    plausible-looking chart. Skia aborts on a 'nan' token, so the series
    actually vanished entirely."""
    dl = _CountDL()
    LineChart(series=[Series(values=[1.0, 2.0, NAN, 4.0, 5.0])],
              x=0, y=0, w=300, h=200).paint(dl)
    # Gridlines are stroked first, the series last.
    series = dl.paths[-1]
    assert series.count("M") == 2, series      # the gap is a subpath break
    assert not any("nan" in p for p in dl.paths)


def test_sparkline_non_finite_breaks_the_line():
    dl = _CountDL()
    Sparkline(values=[1.0, 2.0, NAN, 4.0, 5.0], x=0, y=0, w=300, h=60).paint(dl)
    assert not any("nan" in p for p in dl.paths)
    assert dl.calls.get("fill_grad", 0) == 2      # one closed fill per run


def test_stacked_gap_does_not_poison_upper_layers():
    c = LineChart(series=[Series(values=[1.0, NAN, 3.0]),
                          Series(values=[1.0, 1.0, 1.0])], stacked=True,
                  x=0, y=0, w=300, h=200)
    layers = c._stacked_values()
    assert math.isnan(layers[0][1])                   # gap in its own layer
    assert all(math.isfinite(v) for v in layers[1])   # ...but not above it
    assert layers[1] == [2.0, 1.0, 4.0]


def test_barchart_skips_non_finite_bars():
    c = BarChart(series=[Series(values=[5.0, INF, 8.0])],
                 categories=["a", "b", "c"], x=0, y=0, w=300, h=200)
    assert math.isfinite(c._max()) and c._max() >= 8.0
    dl = _CountDL()
    c.paint(dl)
    assert dl.calls.get("fill_path", 0) == 2          # the inf bar is absent


def test_donut_drops_non_finite_segments():
    c = DonutChart(segments=[("a", 1.0), ("b", NAN), ("c", 3.0)],
                   x=0, y=0, w=300, h=200)
    assert c.total() == 4.0                           # NaN excluded from scale
    dl = _CountDL()
    c.paint(dl)
    assert dl.calls.get("fill_path", 0) == 2          # 2 wedges, not 3
    dl2 = _CountDL()
    DonutChart(segments=[("a", INF)], x=0, y=0, w=300, h=200).paint(dl2)
    assert dl2.total == 0                             # nothing, and no raise


def test_degenerate_charts_still_render_through_native_pipeline():
    """The real Skia path: a 'nan' token makes the parser drop the draw call
    silently, so this guards the end-to-end behaviour, not just the strings."""
    assert _render(LineChart(series=[Series(values=[1.0, NAN, 3.0])],
                             x=0, y=0, w=380, h=240))[:4] == b"\x89PNG"
    assert _render(BarChart(series=[Series(values=[1e-15, 2e-15])],
                            categories=["a", "b"],
                            x=0, y=0, w=380, h=240))[:4] == b"\x89PNG"
