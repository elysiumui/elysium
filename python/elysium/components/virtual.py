"""Virtualization — Tier-2 Qt parity for scale.

Only the items visible in a viewport are built + painted, so a 100k-row list
or a 200-field form stays at frame rate. This generalizes the windowing math
that the Tier-1 model/view tables grew ad-hoc (`visible_row_range`) into:

* :func:`visible_window` / :func:`row_window` — pure windowing helpers.
* :class:`VirtualList` — a scrollable, fixed-row-height virtualized list that
  paints rows through a callback and clips to its viewport.
* :class:`VirtualForm` — a vertical stack of variable-height rows (forms with
  many fields), virtualized via cumulative offsets + binary search.

Both pair with the Phase-2 :class:`elysium.components.scroll.ScrollBar` and the
``Scrollable`` protocol so wheel events route through the InputRouter, and with
Phase-1 dirty-rect (stable per-row command bounds → tiny damage on edit).
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from elysium.components.scroll import ScrollBar, _clamp


def visible_window(
    count: int, item_height: float, viewport: float,
    scroll_px: float, overscan: int = 0,
) -> tuple[int, int, float]:
    """Fixed-height virtualization. Returns ``(first, last, first_y)`` where
    ``last`` is exclusive and ``first_y`` is the y of ``first`` relative to
    the viewport top (≤ 0). Paint indices ``[first, last)``."""
    if item_height <= 0 or count <= 0 or viewport <= 0:
        return (0, 0, 0.0)
    first = max(0, int(scroll_px // item_height) - overscan)
    visible = int(viewport // item_height) + 2 + 2 * overscan
    last = min(count, first + visible)
    first_y = first * item_height - scroll_px
    return (first, last, first_y)


def row_window(
    count: int, viewport: float, row_height: float, scroll_rows: float,
) -> tuple[int, int]:
    """Row-indexed visible window (the Tier-1 model/view convention: scroll
    measured in rows). Returns ``(start, end)`` with ``end`` exclusive."""
    if row_height <= 0:
        return (0, 0)
    start = max(0, int(scroll_rows))
    rows = int(viewport / row_height) + 1
    return (start, min(count, start + rows))


@dataclass
class VirtualList:
    """Scrollable, fixed-height virtualized list. The host supplies
    ``item_count`` + ``item_height`` and a ``render_item(dl, index, x, y, w, h)``
    callback; only visible rows are painted. Implements the ``Scrollable``
    protocol (``scroll_rect`` + ``on_scroll``)."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    item_count: int = 0
    item_height: float = 28.0
    render_item: Optional[Callable[[Any, int, float, float, float, float], None]] = None
    scroll_y: float = 0.0
    overscan: int = 1
    bar_thickness: float = 10.0

    vbar: ScrollBar = field(default=None, init=False, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.vbar = ScrollBar(orientation="vertical", on_change=self._on_vbar,
                              thickness=self.bar_thickness)

    # -- metrics ------------------------------------------------------------

    def content_height(self) -> float:
        return self.item_count * self.item_height

    def _bar_visible(self) -> bool:
        return self.content_height() > self.h + 0.5

    def viewport_w(self) -> float:
        return self.w - (self.bar_thickness if self._bar_visible() else 0.0)

    def max_scroll(self) -> float:
        return max(0.0, self.content_height() - self.h)

    def scroll_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    # -- scrolling ----------------------------------------------------------

    def set_scroll(self, y: float) -> None:
        self.scroll_y = _clamp(y, 0.0, self.max_scroll())

    def on_scroll(self, dx: float, dy: float, precise: bool = False) -> None:
        self.set_scroll(self.scroll_y - dy)

    def _on_vbar(self, v: float) -> None:
        self.scroll_y = _clamp(v, 0.0, self.max_scroll())

    def visible_range(self) -> tuple[int, int, float]:
        return visible_window(self.item_count, self.item_height, self.h,
                              self.scroll_y, self.overscan)

    def index_at(self, my: float) -> int:
        """Item index at viewport y ``my``, or -1 if outside the content."""
        idx = int((my - self.y + self.scroll_y) // self.item_height)
        return idx if 0 <= idx < self.item_count else -1

    def scroll_to_index(self, index: int) -> None:
        top = index * self.item_height
        if top < self.scroll_y:
            self.set_scroll(top)
        elif top + self.item_height > self.scroll_y + self.h:
            self.set_scroll(top + self.item_height - self.h)

    # -- paint --------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        vw = self.viewport_w()
        first, last, first_y = self.visible_range()
        dl.push_clip(self.x, self.y, vw, self.h)
        y = self.y + first_y
        for i in range(first, last):
            if self.render_item is not None:
                self.render_item(dl, i, self.x, y, vw, self.item_height)
            y += self.item_height
        dl.pop_clip()
        if self._bar_visible():
            self.vbar.x = self.x + vw
            self.vbar.y = self.y
            self.vbar.w = self.bar_thickness
            self.vbar.h = self.h
            self.vbar.content = self.content_height()
            self.vbar.viewport = self.h
            self.vbar.value = self.scroll_y
            self.vbar.paint(dl)

    def on_mouse_press(self, mx: float, my: float) -> bool:
        if self._bar_visible():
            self.vbar.x = self.x + self.viewport_w()
            self.vbar.y, self.vbar.w, self.vbar.h = self.y, self.bar_thickness, self.h
            self.vbar.content, self.vbar.viewport, self.vbar.value = (
                self.content_height(), self.h, self.scroll_y)
            if self.vbar.on_mouse_press(mx, my):
                return True
        return False


@dataclass
class VirtualForm:
    """Vertical stack of variable-height rows, virtualized. ``row_heights``
    gives each row's height; ``render_row(dl, index, x, y, w, h)`` paints one.
    Uses cumulative offsets + binary search to find the visible band."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    row_heights: Sequence[float] = field(default_factory=list)
    render_row: Optional[Callable[[Any, int, float, float, float, float], None]] = None
    scroll_y: float = 0.0
    bar_thickness: float = 10.0

    vbar: ScrollBar = field(default=None, init=False, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.vbar = ScrollBar(orientation="vertical", on_change=self._on_vbar,
                              thickness=self.bar_thickness)

    def _offsets(self) -> list[float]:
        """Cumulative top offset of each row + total height as the last entry."""
        offs = [0.0]
        acc = 0.0
        for hgt in self.row_heights:
            acc += hgt
            offs.append(acc)
        return offs

    def content_height(self) -> float:
        return sum(self.row_heights)

    def _bar_visible(self) -> bool:
        return self.content_height() > self.h + 0.5

    def max_scroll(self) -> float:
        return max(0.0, self.content_height() - self.h)

    def scroll_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def set_scroll(self, y: float) -> None:
        self.scroll_y = _clamp(y, 0.0, self.max_scroll())

    def on_scroll(self, dx: float, dy: float, precise: bool = False) -> None:
        self.set_scroll(self.scroll_y - dy)

    def _on_vbar(self, v: float) -> None:
        self.scroll_y = _clamp(v, 0.0, self.max_scroll())

    def visible_range(self) -> tuple[int, int]:
        """``(first, last)`` rows intersecting the viewport (last exclusive)."""
        offs = self._offsets()
        n = len(self.row_heights)
        if n == 0:
            return (0, 0)
        # First row whose bottom edge is past the scroll top.
        first = max(0, bisect_right(offs, self.scroll_y) - 1)
        bottom = self.scroll_y + self.h
        last = first
        while last < n and offs[last] < bottom:
            last += 1
        return (first, last)

    def paint(self, dl: Any) -> None:
        vw = self.w - (self.bar_thickness if self._bar_visible() else 0.0)
        offs = self._offsets()
        first, last = self.visible_range()
        dl.push_clip(self.x, self.y, vw, self.h)
        for i in range(first, last):
            row_y = self.y + offs[i] - self.scroll_y
            if self.render_row is not None:
                self.render_row(dl, i, self.x, row_y, vw, self.row_heights[i])
        dl.pop_clip()
        if self._bar_visible():
            self.vbar.x = self.x + vw
            self.vbar.y, self.vbar.w, self.vbar.h = self.y, self.bar_thickness, self.h
            self.vbar.content, self.vbar.viewport, self.vbar.value = (
                self.content_height(), self.h, self.scroll_y)
            self.vbar.paint(dl)


__all__ = ["visible_window", "row_window", "VirtualList", "VirtualForm"]
