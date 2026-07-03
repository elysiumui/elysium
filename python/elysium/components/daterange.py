"""Segmented control + date-range picker — the dashboard date bar.

:class:`SegmentedControl` is the pill-style toggle (Yesterday / 7 days / 30 days
/ Custom); :class:`DateRangePicker` wraps it with preset → ``(start, end)`` date
math and a custom range, matching the date bar both dashboards use.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import current_theme, with_alpha, lighten
from elysium.components import Component, _rounded_rect

__all__ = ["SegmentedControl", "DateRangePicker", "preset_range", "PRESETS"]

PRESETS = ["Today", "Yesterday", "Last 7 days", "Last 30 days", "Custom"]


def preset_range(name: str, today: _dt.date) -> tuple[_dt.date, _dt.date] | None:
    """``(start, end)`` for a preset name, or ``None`` for "Custom"."""
    day = _dt.timedelta(days=1)
    if name == "Today":
        return (today, today)
    if name == "Yesterday":
        y = today - day
        return (y, y)
    if "7" in name:
        return (today - 6 * day, today)
    if "30" in name:
        return (today - 29 * day, today)
    return None


# ---------------------------------------------------------------------------
# SegmentedControl.
# ---------------------------------------------------------------------------

@dataclass
class SegmentedControl(Component):
    options: list[str] = field(default_factory=list)
    selected: int = 0
    on_change: Callable[[int], None] | None = None
    h: float = 30.0
    radius: float = 8.0

    def _seg_w(self) -> float:
        return self.w / max(1, len(self.options))

    def seg_rect(self, i: int) -> tuple[float, float, float, float]:
        sw = self._seg_w()
        return (self.x + i * sw, self.y, sw, self.h)

    def hit_index(self, mx: float, my: float) -> int | None:
        if not (self.y <= my <= self.y + self.h and self.x <= mx <= self.x + self.w):
            return None
        return min(len(self.options) - 1, int((mx - self.x) / self._seg_w()))

    def select(self, i: int) -> None:
        if 0 <= i < len(self.options) and i != self.selected:
            self.selected = i
            if self.on_change is not None:
                self.on_change(i)

    def on_click(self, mx: float, my: float) -> bool:
        i = self.hit_index(mx, my)
        if i is None:
            return False
        self.select(i)
        return True

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                     t.surface_variant)
        for i, opt in enumerate(self.options):
            sx, sy, sw, sh = self.seg_rect(i)
            active = i == self.selected
            if active:
                dl.fill_path(_rounded_rect(sx + 2, sy + 2, sw - 4, sh - 4,
                                           self.radius - 2),
                             lighten(t.surface, 0.06))
                dl.stroke_path(_rounded_rect(sx + 2.5, sy + 2.5, sw - 5, sh - 5,
                                             self.radius - 2),
                               with_alpha(t.edge, 0.8), 1.0)
            color = t.on_surface if active else t.on_surface_muted
            approx = len(opt) * t.font_size_caption * 0.55
            dl.draw_text(opt, sx + (sw - approx) / 2, sy + sh * 0.64,
                         t.font_size_caption, color)


# ---------------------------------------------------------------------------
# DateRangePicker.
# ---------------------------------------------------------------------------

@dataclass
class DateRangePicker(Component):
    """A preset date-range bar. ``current_range(today)`` returns the active
    ``(start, end)``; "Custom" uses ``start`` / ``end`` (set them from your own
    calendar UI). ``on_change`` fires ``(start, end)`` on preset change."""

    presets: list[str] = field(default_factory=lambda: list(PRESETS))
    selected: int = 3                       # Last 30 days
    start: _dt.date | None = None
    end: _dt.date | None = None
    on_change: Callable[[_dt.date, _dt.date], None] | None = None
    h: float = 30.0
    _seg: SegmentedControl = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._seg = SegmentedControl(options=self.presets, selected=self.selected)

    def is_custom(self) -> bool:
        return self.presets[self.selected] == "Custom"

    def current_range(self, today: _dt.date | None = None) \
            -> tuple[_dt.date, _dt.date] | None:
        today = today or _dt.date.today()
        if self.is_custom():
            if self.start and self.end:
                return (min(self.start, self.end), max(self.start, self.end))
            return None
        return preset_range(self.presets[self.selected], today)

    def select_preset(self, i: int, today: _dt.date | None = None) -> None:
        self.selected = i
        self._seg.selected = i
        rng = self.current_range(today)
        if rng is not None:
            self.start, self.end = rng
            if self.on_change is not None:
                self.on_change(*rng)

    def on_click(self, mx: float, my: float,
                 today: _dt.date | None = None) -> bool:
        i = self._seg.hit_index(mx, my)
        if i is None:
            return False
        self.select_preset(i, today)
        return True

    def paint(self, dl: Any) -> None:
        self._seg.x, self._seg.y = self.x, self.y
        self._seg.w, self._seg.h = self.w, self.h
        self._seg.selected = self.selected
        self._seg.paint(dl)
