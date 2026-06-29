"""Interactive 2D canvas — an item scene graph (Qt's ``QGraphicsScene`` /
``QGraphicsView`` / ``QGraphicsItem``).

A :class:`Scene` owns a z-ordered list of :class:`Item`\\ s, each with
scene-space bounds, a hit-test, and a ``paint(dl)``. Built-in items cover the
common shapes (rect / ellipse / line / path / text); subclass :class:`Item` for
anything custom. A :class:`GraphicsView` (Phase 2) pans/zooms and renders the
scene; interaction (select / rubber-band / drag, Phase 3) layers on top.

This module (Tier 5 Phase 1): the scene-graph model + built-in items. Items
paint in **scene coordinates** — the view applies the viewport transform around
them — so an item's ``paint`` never needs to know the pan/zoom.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from elysium.theme import Color, current_theme, with_alpha
from elysium.components import _rounded_rect

__all__ = [
    "Item",
    "RectItem",
    "EllipseItem",
    "LineItem",
    "PathItem",
    "TextItem",
    "Scene",
]


def _ellipse_path(cx: float, cy: float, rx: float, ry: float) -> str:
    """An ellipse centred at ``(cx, cy)`` as two SVG arcs."""
    return (f"M {cx - rx} {cy} "
            f"a {rx} {ry} 0 1 0 {2 * rx} 0 "
            f"a {rx} {ry} 0 1 0 {-2 * rx} 0 Z")


# ---------------------------------------------------------------------------
# Item base.
# ---------------------------------------------------------------------------

@dataclass
class Item:
    """Base scene item. ``x/y/w/h`` are the axis-aligned bounds in scene space.
    Subclasses override :meth:`paint` (and usually :meth:`contains` for a
    shape-accurate hit-test)."""

    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    z: int = 0
    visible: bool = True
    selectable: bool = True
    selected: bool = False
    opacity: float = 1.0
    data: dict = field(default_factory=dict)

    def scene_bounds(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def contains(self, sx: float, sy: float) -> bool:
        """Hit-test a point in scene space (default: bounds rectangle)."""
        return (self.x <= sx <= self.x + self.w
                and self.y <= sy <= self.y + self.h)

    def move_by(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy

    def paint(self, dl: Any) -> None:  # pragma: no cover - base is abstract-ish
        pass

    # Shared selection outline (called by the view, in scene space).
    def paint_selection(self, dl: Any, inflate: float = 2.0) -> None:
        t = current_theme()
        bx, by, bw, bh = self.scene_bounds()
        dl.stroke_path(
            _rounded_rect(bx - inflate, by - inflate,
                          bw + 2 * inflate, bh + 2 * inflate, 3),
            with_alpha(t.primary, 0.9), 1.5)


# ---------------------------------------------------------------------------
# Built-in items.
# ---------------------------------------------------------------------------

@dataclass
class RectItem(Item):
    fill: Color | None = None
    stroke: Color | None = None
    stroke_width: float = 1.5
    radius: float = 6.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        fill = self.fill if self.fill is not None else t.surface_variant
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                     with_alpha(fill, self.opacity))
        stroke = self.stroke if self.stroke is not None else t.edge
        dl.stroke_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                       with_alpha(stroke, self.opacity), self.stroke_width)


@dataclass
class EllipseItem(Item):
    fill: Color | None = None
    stroke: Color | None = None
    stroke_width: float = 1.5

    def _path(self) -> str:
        return _ellipse_path(self.x + self.w / 2.0, self.y + self.h / 2.0,
                             self.w / 2.0, self.h / 2.0)

    def contains(self, sx: float, sy: float) -> bool:
        rx, ry = self.w / 2.0, self.h / 2.0
        if rx <= 0 or ry <= 0:
            return False
        cx, cy = self.center()
        return ((sx - cx) / rx) ** 2 + ((sy - cy) / ry) ** 2 <= 1.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        fill = self.fill if self.fill is not None else t.surface_variant
        dl.fill_path(self._path(), with_alpha(fill, self.opacity))
        stroke = self.stroke if self.stroke is not None else t.edge
        dl.stroke_path(self._path(), with_alpha(stroke, self.opacity),
                       self.stroke_width)


@dataclass
class LineItem(Item):
    """A line between two scene points. ``x/y/w/h`` are kept in sync as the
    bounding box so selection + culling work uniformly."""

    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    stroke: Color | None = None
    stroke_width: float = 2.0
    tolerance: float = 4.0

    def __post_init__(self) -> None:
        self._sync_bounds()

    def _sync_bounds(self) -> None:
        self.x = min(self.x1, self.x2)
        self.y = min(self.y1, self.y2)
        self.w = abs(self.x2 - self.x1)
        self.h = abs(self.y2 - self.y1)

    def move_by(self, dx: float, dy: float) -> None:
        self.x1 += dx; self.y1 += dy
        self.x2 += dx; self.y2 += dy
        self._sync_bounds()

    def contains(self, sx: float, sy: float) -> bool:
        # Distance from the point to the segment.
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        if seg2 == 0:
            d2 = (sx - x1) ** 2 + (sy - y1) ** 2
        else:
            tt = max(0.0, min(1.0, ((sx - x1) * dx + (sy - y1) * dy) / seg2))
            px, py = x1 + tt * dx, y1 + tt * dy
            d2 = (sx - px) ** 2 + (sy - py) ** 2
        return d2 <= self.tolerance ** 2

    def paint(self, dl: Any) -> None:
        t = current_theme()
        stroke = self.stroke if self.stroke is not None else t.on_surface
        dl.stroke_path(f"M {self.x1} {self.y1} L {self.x2} {self.y2}",
                       with_alpha(stroke, self.opacity), self.stroke_width)


@dataclass
class PathItem(Item):
    """An arbitrary SVG-path item. ``d`` is in scene coordinates; supply
    ``x/y/w/h`` as its bounding box (used for selection, culling, and the
    default bounds hit-test)."""

    d: str = ""
    fill: Color | None = None
    stroke: Color | None = None
    stroke_width: float = 1.5

    def paint(self, dl: Any) -> None:
        t = current_theme()
        if self.fill is not None:
            dl.fill_path(self.d, with_alpha(self.fill, self.opacity))
        stroke = self.stroke if self.stroke is not None else t.on_surface
        if self.stroke is not None or self.fill is None:
            dl.stroke_path(self.d, with_alpha(stroke, self.opacity),
                           self.stroke_width)


@dataclass
class TextItem(Item):
    text: str = ""
    size: float = 14.0
    color: Color | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        color = self.color if self.color is not None else t.on_surface
        dl.draw_text(self.text, self.x, self.y + self.h * 0.72, self.size,
                     with_alpha(color, self.opacity))


# ---------------------------------------------------------------------------
# Scene.
# ---------------------------------------------------------------------------

@dataclass
class Scene:
    """A z-ordered collection of :class:`Item`\\ s. Painting walks items back to
    front; hit-testing walks front to back (topmost first)."""

    items: list[Item] = field(default_factory=list)

    # --- structure --------------------------------------------------------

    def add(self, item: Item) -> Item:
        self.items.append(item)
        return item

    def remove(self, item: Item) -> None:
        if item in self.items:
            self.items.remove(item)

    def clear(self) -> None:
        self.items.clear()

    def z_sorted(self) -> list[Item]:
        """Items back-to-front (stable within equal z)."""
        return sorted(self.items, key=lambda it: it.z)

    def raise_to_top(self, item: Item) -> None:
        if self.items:
            item.z = max(it.z for it in self.items) + 1

    def lower_to_bottom(self, item: Item) -> None:
        if self.items:
            item.z = min(it.z for it in self.items) - 1

    # --- queries ----------------------------------------------------------

    def items_at(self, sx: float, sy: float) -> list[Item]:
        """Visible items containing the scene point, topmost first."""
        hit = [it for it in self.items if it.visible and it.contains(sx, sy)]
        return sorted(hit, key=lambda it: it.z, reverse=True)

    def item_at(self, sx: float, sy: float) -> Item | None:
        hits = self.items_at(sx, sy)
        return hits[0] if hits else None

    def items_in_rect(self, rx: float, ry: float, rw: float, rh: float,
                      contained: bool = False) -> list[Item]:
        """Items intersecting (or, if ``contained``, fully inside) a scene
        rect — the rubber-band query."""
        out = []
        for it in self.items:
            if not it.visible:
                continue
            bx, by, bw, bh = it.scene_bounds()
            if contained:
                inside = (bx >= rx and by >= ry
                          and bx + bw <= rx + rw and by + bh <= ry + rh)
            else:
                inside = not (bx > rx + rw or bx + bw < rx
                              or by > ry + rh or by + bh < ry)
            if inside:
                out.append(it)
        return out

    def bounding_rect(self) -> tuple[float, float, float, float]:
        """Union of all item bounds (``(0, 0, 0, 0)`` when empty)."""
        if not self.items:
            return (0.0, 0.0, 0.0, 0.0)
        xs0 = min(it.x for it in self.items)
        ys0 = min(it.y for it in self.items)
        xs1 = max(it.x + it.w for it in self.items)
        ys1 = max(it.y + it.h for it in self.items)
        return (xs0, ys0, xs1 - xs0, ys1 - ys0)

    # --- selection --------------------------------------------------------

    def selected_items(self) -> list[Item]:
        return [it for it in self.items if it.selected]

    def clear_selection(self) -> None:
        for it in self.items:
            it.selected = False

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        """Paint every visible item back-to-front, with selection outlines on
        top. Called by the view inside the viewport transform."""
        ordered = self.z_sorted()
        for it in ordered:
            if it.visible:
                it.paint(dl)
        for it in ordered:
            if it.visible and it.selected:
                it.paint_selection(dl)
