"""Charts — data visualization for dashboards (Qt's QtCharts class of widget).

Immediate-mode chart components that paint onto a ``DisplayList`` using only the
existing path primitives (``stroke_path`` for polylines, ``fill_path`` with SVG
arc ``A`` commands for donut wedges), so there is no native dependency. Every
chart reads ``current_theme()`` at paint time and recolours with the theme.

Components: :class:`Sparkline`, :class:`LineChart` / :class:`AreaChart`,
:class:`BarChart`, :class:`DonutChart` / :class:`PieChart`, and a
:class:`Legend`. Data goes in as :class:`Series`. Number formatting helpers
(:func:`format_money`, :func:`format_pct`, :func:`format_compact`) keep axis and
label text consistent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import Color, current_theme, with_alpha, lighten, mix
from elysium.components import _rounded_rect

__all__ = [
    "Series",
    "chart_palette",
    "nice_ticks",
    "format_money",
    "format_pct",
    "format_compact",
    "Sparkline",
    "LineChart",
    "AreaChart",
    "BarChart",
    "DonutChart",
    "PieChart",
    "Legend",
]


# ---------------------------------------------------------------------------
# Data + helpers.
# ---------------------------------------------------------------------------

@dataclass
class Series:
    """One data series. ``values`` are y-values (x is the index); ``color`` is
    optional (the palette fills in)."""
    values: list[float] = field(default_factory=list)
    name: str = ""
    color: Color | None = None


def chart_palette(t: Any = None) -> list[Color]:
    """A categorical palette ordered for good adjacent contrast. Finance-leaning
    (the COGS / ad-spend / refunds / shipping / fees accent family) but theme
    primary/accent lead so charts feel native to the active theme."""
    t = t or current_theme()
    return [
        t.primary,
        (0x5B, 0x8D, 0xEF, 0xFF),   # COGS blue
        (0xF4, 0xA9, 0x3C, 0xFF),   # ad-spend amber
        (0x2D, 0xC4, 0xA7, 0xFF),   # shipping teal
        (0xA7, 0x8B, 0xFA, 0xFF),   # fees violet
        (0xFB, 0x71, 0x85, 0xFF),   # refunds rose
        t.accent,
        (0x1F, 0x9D, 0x6B, 0xFF),   # profit green
    ]


def nice_ticks(lo: float, hi: float, target: int = 5) -> tuple[float, float, float]:
    """Return ``(nice_lo, nice_hi, step)`` covering ``[lo, hi]`` with ~``target``
    round ticks (1/2/5 × 10ⁿ)."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(1, target)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    else:
        step = 10 * mag
    nlo = math.floor(lo / step) * step
    nhi = math.ceil(hi / step) * step
    return (nlo, nhi, step)


def format_money(v: float, symbol: str = "$", decimals: int = 0) -> str:
    neg = v < 0
    s = f"{symbol}{abs(v):,.{decimals}f}"
    return f"-{s}" if neg else s


def format_pct(v: float, decimals: int = 1) -> str:
    return f"{v:.{decimals}f}%"


def format_compact(v: float) -> str:
    """``12500`` → ``12.5k``; ``3_400_000`` → ``3.4M``."""
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            return f"{v / div:.1f}{suf}".replace(".0", "")
    return f"{v:.0f}"


def _poly(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    d = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    for x, y in points[1:]:
        d += f" L {x:.2f} {y:.2f}"
    return d


# ---------------------------------------------------------------------------
# Sparkline — a tiny inline trend (for MetricCards / table cells).
# ---------------------------------------------------------------------------

@dataclass
class Sparkline:
    values: list[float] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    color: Color | None = None
    fill: bool = True
    stroke_width: float = 1.5
    dot: bool = True

    def _points(self) -> list[tuple[float, float]]:
        vals = self.values
        if not vals:
            return []
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        n = len(vals)
        step = self.w / max(1, n - 1)
        pad = self.h * 0.12
        return [(self.x + i * step,
                 self.y + self.h - pad - ((v - lo) / span) * (self.h - 2 * pad))
                for i, v in enumerate(vals)]

    def paint(self, dl: Any) -> None:
        t = current_theme()
        pts = self._points()
        if len(pts) < 2:
            return
        color = self.color or t.primary
        if self.fill:
            base = self.y + self.h
            area = pts + [(pts[-1][0], base), (pts[0][0], base)]
            dl.fill_path_linear_gradient(
                _poly(area) + " Z", (0, self.y), (0, base),
                with_alpha(color, 0.22), with_alpha(color, 0.0))
        dl.stroke_path(_poly(pts), color, self.stroke_width)
        if self.dot:
            dl.filled_circle(pts[-1][0], pts[-1][1], self.stroke_width + 1.2, color)


# ---------------------------------------------------------------------------
# LineChart / AreaChart.
# ---------------------------------------------------------------------------

@dataclass
class LineChart:
    series: list[Series] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    area: bool = False
    stacked: bool = False
    x_labels: list[str] | None = None
    y_format: Callable[[float], str] | None = None
    show_grid: bool = True
    show_axis: bool = True
    pad_left: float = 44.0
    pad_bottom: float = 22.0
    pad_top: float = 8.0
    pad_right: float = 8.0
    stroke_width: float = 2.0

    # --- geometry ---------------------------------------------------------

    def plot_rect(self) -> tuple[float, float, float, float]:
        pl = self.pad_left if self.show_axis else 4.0
        pb = self.pad_bottom if self.show_axis else 4.0
        return (self.x + pl, self.y + self.pad_top,
                max(0.0, self.w - pl - self.pad_right),
                max(0.0, self.h - pb - self.pad_top))

    def _stacked_values(self) -> list[list[float]]:
        if not self.stacked:
            return [s.values for s in self.series]
        out: list[list[float]] = []
        running = [0.0] * (max((len(s.values) for s in self.series), default=0))
        for s in self.series:
            cum = []
            for i, v in enumerate(s.values):
                running[i] += v
                cum.append(running[i])
            out.append(cum)
        return out

    def _value_range(self) -> tuple[float, float]:
        layers = self._stacked_values()
        flat = [v for layer in layers for v in layer]
        if not flat:
            return (0.0, 1.0)
        lo = min(0.0, min(flat))
        hi = max(flat)
        nlo, nhi, _ = nice_ticks(lo, hi)
        return (nlo, nhi)

    def _map(self, i: int, v: float, n: int, lo: float, hi: float,
             rect) -> tuple[float, float]:
        rx, ry, rw, rh = rect
        x = rx + (i / max(1, n - 1)) * rw
        yv = ry + rh - ((v - lo) / ((hi - lo) or 1.0)) * rh
        return (x, yv)

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        t = current_theme()
        rect = self.plot_rect()
        rx, ry, rw, rh = rect
        lo, hi = self._value_range()
        pal = chart_palette(t)
        # Grid + y-axis ticks.
        if self.show_axis:
            _nlo, _nhi, step = nice_ticks(lo, hi)
            yfmt = self.y_format or format_compact
            v = lo
            while v <= hi + 1e-6:
                gy = ry + rh - ((v - lo) / ((hi - lo) or 1.0)) * rh
                if self.show_grid:
                    dl.stroke_path(f"M {rx} {gy:.2f} L {rx + rw} {gy:.2f}",
                                   with_alpha(t.edge, 0.5), 1.0)
                dl.draw_text(yfmt(v), self.x + 4, gy + 4, 10, t.on_surface_muted)
                v += step
        layers = self._stacked_values()
        n = max((len(s.values) for s in self.series), default=0)
        prev_pts: list[tuple[float, float]] | None = None
        for idx, s in enumerate(self.series):
            vals = layers[idx]
            color = s.color or pal[idx % len(pal)]
            pts = [self._map(i, v, n, lo, hi, rect) for i, v in enumerate(vals)]
            if len(pts) < 2:
                continue
            if self.area:
                if self.stacked and prev_pts is not None:
                    base = list(reversed(prev_pts))
                else:
                    base = [(pts[-1][0], ry + rh), (pts[0][0], ry + rh)]
                dl.fill_path_linear_gradient(
                    _poly(pts + base) + " Z", (0, ry), (0, ry + rh),
                    with_alpha(color, 0.28), with_alpha(color, 0.04))
            dl.stroke_path(_poly(pts), color, self.stroke_width)
            prev_pts = pts
        # X labels.
        if self.show_axis and self.x_labels:
            k = max(1, len(self.x_labels) // 6)
            for i, lab in enumerate(self.x_labels):
                if i % k:
                    continue
                lx = rx + (i / max(1, len(self.x_labels) - 1)) * rw
                dl.draw_text(lab, lx - len(lab) * 2.6, ry + rh + 14, 10,
                             t.on_surface_muted)


@dataclass
class AreaChart(LineChart):
    """A :class:`LineChart` with the area filled (and optionally stacked)."""
    area: bool = True


# ---------------------------------------------------------------------------
# BarChart.
# ---------------------------------------------------------------------------

@dataclass
class BarChart:
    series: list[Series] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    stacked: bool = False
    y_format: Callable[[float], str] | None = None
    show_axis: bool = True
    pad_left: float = 44.0
    pad_bottom: float = 22.0
    pad_top: float = 8.0
    pad_right: float = 8.0
    radius: float = 3.0

    def plot_rect(self) -> tuple[float, float, float, float]:
        pl = self.pad_left if self.show_axis else 4.0
        pb = self.pad_bottom if self.show_axis else 4.0
        return (self.x + pl, self.y + self.pad_top,
                max(0.0, self.w - pl - self.pad_right),
                max(0.0, self.h - pb - self.pad_top))

    def _max(self) -> float:
        if self.stacked:
            n = max((len(s.values) for s in self.series), default=0)
            totals = [sum(s.values[i] if i < len(s.values) else 0
                          for s in self.series) for i in range(n)]
            hi = max(totals, default=1.0)
        else:
            hi = max((v for s in self.series for v in s.values), default=1.0)
        return nice_ticks(0.0, hi)[1]

    def paint(self, dl: Any) -> None:
        t = current_theme()
        rx, ry, rw, rh = self.plot_rect()
        hi = self._max() or 1.0
        pal = chart_palette(t)
        n = len(self.categories) or max(
            (len(s.values) for s in self.series), default=0)
        if n == 0:
            return
        if self.show_axis:
            _a, _b, step = nice_ticks(0.0, hi)
            yfmt = self.y_format or format_compact
            v = 0.0
            while v <= hi + 1e-6:
                gy = ry + rh - (v / hi) * rh
                dl.stroke_path(f"M {rx} {gy:.2f} L {rx + rw} {gy:.2f}",
                               with_alpha(t.edge, 0.5), 1.0)
                dl.draw_text(yfmt(v), self.x + 4, gy + 4, 10, t.on_surface_muted)
                v += step
        group_w = rw / n
        ns = len(self.series)
        for ci in range(n):
            gx = rx + ci * group_w
            if self.stacked:
                acc = 0.0
                bw = group_w * 0.6
                bx = gx + (group_w - bw) / 2
                for si, s in enumerate(self.series):
                    val = s.values[ci] if ci < len(s.values) else 0.0
                    bh = (val / hi) * rh
                    by = ry + rh - (acc / hi) * rh - bh
                    dl.fill_path(_rounded_rect(bx, by, bw, bh, self.radius),
                                 s.color or pal[si % len(pal)])
                    acc += val
            else:
                bw = (group_w * 0.7) / max(1, ns)
                for si, s in enumerate(self.series):
                    val = s.values[ci] if ci < len(s.values) else 0.0
                    bh = (val / hi) * rh
                    bx = gx + group_w * 0.15 + si * bw
                    dl.fill_path(_rounded_rect(bx, ry + rh - bh, bw - 2, bh,
                                               self.radius),
                                 s.color or pal[si % len(pal)])
            if self.show_axis and ci < len(self.categories):
                lab = self.categories[ci]
                dl.draw_text(lab, gx + group_w / 2 - len(lab) * 2.6,
                             ry + rh + 14, 10, t.on_surface_muted)


# ---------------------------------------------------------------------------
# DonutChart / PieChart.
# ---------------------------------------------------------------------------

@dataclass
class DonutChart:
    """A donut (or pie when ``inner_ratio == 0``). ``segments`` are
    ``(label, value, color|None)``; an optional centre label/value is shown."""
    segments: list[tuple] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    inner_ratio: float = 0.62
    gap_deg: float = 1.5
    center_label: str = ""
    center_value: str = ""

    def _geom(self) -> tuple[float, float, float]:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r = min(self.w, self.h) / 2 - 2
        return (cx, cy, r)

    @staticmethod
    def _wedge(cx, cy, r0, r1, a0, a1) -> str:
        large = 1 if (a1 - a0) > math.pi else 0
        x0o, y0o = cx + r1 * math.cos(a0), cy + r1 * math.sin(a0)
        x1o, y1o = cx + r1 * math.cos(a1), cy + r1 * math.sin(a1)
        x1i, y1i = cx + r0 * math.cos(a1), cy + r0 * math.sin(a1)
        x0i, y0i = cx + r0 * math.cos(a0), cy + r0 * math.sin(a0)
        return (f"M {x0o:.2f} {y0o:.2f} "
                f"A {r1:.2f} {r1:.2f} 0 {large} 1 {x1o:.2f} {y1o:.2f} "
                f"L {x1i:.2f} {y1i:.2f} "
                f"A {r0:.2f} {r0:.2f} 0 {large} 0 {x0i:.2f} {y0i:.2f} Z")

    def total(self) -> float:
        return sum(max(0.0, float(v)) for _l, v, *_ in self.segments) or 1.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        cx, cy, r1 = self._geom()
        r0 = r1 * self.inner_ratio
        pal = chart_palette(t)
        total = self.total()
        gap = math.radians(self.gap_deg)
        a = -math.pi / 2  # start at top
        for i, seg in enumerate(self.segments):
            label, value = seg[0], float(seg[1])
            color = seg[2] if len(seg) > 2 and seg[2] else pal[i % len(pal)]
            frac = max(0.0, value) / total
            a1 = a + frac * (2 * math.pi)
            if a1 - a > gap:
                dl.fill_path(self._wedge(cx, cy, r0, r1, a + gap / 2,
                                         a1 - gap / 2), color)
            a = a1
        if self.center_value:
            tw = len(self.center_value) * 9
            dl.draw_text(self.center_value, cx - tw / 2, cy + 2, 18, t.on_surface)
        if self.center_label:
            lw = len(self.center_label) * 3.2
            dl.draw_text(self.center_label, cx - lw, cy - 14, 10,
                         t.on_surface_muted)


@dataclass
class PieChart(DonutChart):
    inner_ratio: float = 0.0


# ---------------------------------------------------------------------------
# Legend.
# ---------------------------------------------------------------------------

@dataclass
class Legend:
    """``entries`` are ``(label, color|None)`` or ``(label, color, value_str)``;
    laid out as one row per entry with a swatch."""
    entries: list[tuple] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    row_h: float = 22.0
    swatch: float = 10.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        pal = chart_palette(t)
        for i, e in enumerate(self.entries):
            label = e[0]
            color = e[1] if len(e) > 1 and e[1] else pal[i % len(pal)]
            ry = self.y + i * self.row_h
            cy = ry + self.row_h / 2
            dl.fill_path(_rounded_rect(self.x, cy - self.swatch / 2,
                                       self.swatch, self.swatch, 3), color)
            dl.draw_text(label, self.x + self.swatch + 8, cy + 4, 12,
                         t.on_surface)
            if len(e) > 2 and e[2]:
                vw = len(str(e[2])) * 7.0
                dl.draw_text(str(e[2]), self.x + self.w - vw, cy + 4, 12,
                             t.on_surface_muted)
