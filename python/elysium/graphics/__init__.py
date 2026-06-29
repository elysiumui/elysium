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
    "GraphicsView",
    "SceneController",
]


def _rects_intersect(a: tuple[float, float, float, float],
                     b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax > bx + bw or ax + aw < bx or ay > by + bh or ay + ah < by)


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
    resizable: bool = True
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
        # A line is defined by its endpoints; bounding-box resize handles would
        # not reshape it, so it moves but doesn't resize via the controller.
        self.resizable = False

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

    def __post_init__(self) -> None:
        # The path data is fixed in scene space; bbox resize wouldn't transform
        # it, so a path item moves but doesn't resize via the controller.
        self.resizable = False

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


# ---------------------------------------------------------------------------
# GraphicsView — a pan/zoom viewport onto a Scene (Qt's QGraphicsView).
# ---------------------------------------------------------------------------

@dataclass
class GraphicsView:
    """A rectangular viewport (``x/y/w/h`` in screen space) that pans and zooms
    over a :class:`Scene` and renders it (with off-screen culling).

    Coordinate model: a scene point maps to the screen as
    ``screen = view_origin + (scene - pan) * zoom``, where ``(pan_x, pan_y)`` is
    the scene coordinate shown at the view's top-left. :meth:`to_view` /
    :meth:`to_scene` convert between the spaces; pointer handlers should map
    screen coords to scene coords with :meth:`to_scene` before querying the
    scene.
    """

    scene: Scene = field(default_factory=Scene)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    zoom: float = 1.0
    min_zoom: float = 0.1
    max_zoom: float = 8.0
    background: Color | None = None
    _panning: bool = field(default=False, init=False, repr=False)
    _pan_last: tuple[float, float] = field(default=(0.0, 0.0), init=False,
                                           repr=False)

    # --- coordinate mapping ----------------------------------------------

    def to_view(self, sx: float, sy: float) -> tuple[float, float]:
        return (self.x + (sx - self.pan_x) * self.zoom,
                self.y + (sy - self.pan_y) * self.zoom)

    def to_scene(self, vx: float, vy: float) -> tuple[float, float]:
        return (self.pan_x + (vx - self.x) / self.zoom,
                self.pan_y + (vy - self.y) / self.zoom)

    def visible_scene_rect(self) -> tuple[float, float, float, float]:
        sx, sy = self.to_scene(self.x, self.y)
        return (sx, sy, self.w / self.zoom, self.h / self.zoom)

    def contains_view(self, vx: float, vy: float) -> bool:
        return (self.x <= vx <= self.x + self.w
                and self.y <= vy <= self.y + self.h)

    # --- pan / zoom -------------------------------------------------------

    def set_zoom(self, zoom: float) -> None:
        self.zoom = min(max(zoom, self.min_zoom), self.max_zoom)

    def zoom_at(self, vx: float, vy: float, factor: float) -> None:
        """Zoom by ``factor`` while keeping the scene point under ``(vx, vy)``
        fixed on screen (cursor-anchored zoom)."""
        sx, sy = self.to_scene(vx, vy)
        self.set_zoom(self.zoom * factor)
        # Re-pan so (sx, sy) maps back to (vx, vy).
        self.pan_x = sx - (vx - self.x) / self.zoom
        self.pan_y = sy - (vy - self.y) / self.zoom

    def pan_by(self, dvx: float, dvy: float) -> None:
        """Pan by a screen-pixel delta."""
        self.pan_x -= dvx / self.zoom
        self.pan_y -= dvy / self.zoom

    def begin_pan(self, vx: float, vy: float) -> None:
        self._panning = True
        self._pan_last = (vx, vy)

    def drag_pan(self, vx: float, vy: float) -> None:
        if not self._panning:
            return
        self.pan_by(vx - self._pan_last[0], vy - self._pan_last[1])
        self._pan_last = (vx, vy)

    def end_pan(self) -> None:
        self._panning = False

    def fit(self, margin: float = 24.0,
            rect: tuple[float, float, float, float] | None = None) -> None:
        """Pan + zoom so ``rect`` (or the whole scene) fills the viewport with a
        ``margin`` (screen px) border."""
        r = rect if rect is not None else self.scene.bounding_rect()
        rx, ry, rw, rh = r
        if rw <= 0 or rh <= 0 or self.w <= 0 or self.h <= 0:
            return
        zx = (self.w - 2 * margin) / rw
        zy = (self.h - 2 * margin) / rh
        self.set_zoom(min(zx, zy))
        # Centre the rect in the viewport.
        self.pan_x = rx + rw / 2.0 - (self.w / 2.0) / self.zoom
        self.pan_y = ry + rh / 2.0 - (self.h / 2.0) / self.zoom

    # --- culling + paint --------------------------------------------------

    def visible_items(self) -> list[Item]:
        """Scene items (back-to-front) that intersect the viewport — i.e. what
        :meth:`paint` actually draws after culling."""
        vis = self.visible_scene_rect()
        return [it for it in self.scene.z_sorted()
                if it.visible and _rects_intersect(it.scene_bounds(), vis)]

    def paint(self, dl: Any) -> None:
        t = current_theme()
        bg = self.background if self.background is not None else t.surface
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, 0), bg)
        # Clip to the viewport (screen space), then apply the scene transform.
        dl.push_clip(self.x, self.y, self.w, self.h)
        dl.save_with_transform(self.x - self.pan_x * self.zoom,
                               self.y - self.pan_y * self.zoom,
                               self.zoom, self.zoom, 0.0)
        items = self.visible_items()
        for it in items:
            it.paint(dl)
        for it in items:
            if it.selected:
                it.paint_selection(dl)
        dl.restore()
        dl.pop_clip()


# ---------------------------------------------------------------------------
# SceneController — selection / rubber-band / move / resize interaction.
# ---------------------------------------------------------------------------

_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


@dataclass
class SceneController:
    """The interaction layer over a :class:`GraphicsView`: click-select (with
    additive multi-select), rubber-band selection, drag-to-move, and resize
    handles for a single resizable selection. Optional grid ``snap``.

    The host feeds it **screen-space** pointer coords; it maps to the scene via
    the view. Call :meth:`paint_overlay` after the view paints, so the
    rubber-band rect and handles draw on top in screen space.
    """

    view: GraphicsView
    snap: float = 0.0
    handle_size: float = 8.0
    _mode: str = field(default="idle", init=False)        # idle|move|resize|band
    _start: tuple[float, float] = field(default=(0.0, 0.0), init=False)
    _band: tuple[float, float, float, float] | None = field(default=None, init=False)
    _handle: str | None = field(default=None, init=False)
    _orig: dict = field(default_factory=dict, init=False)

    @property
    def scene(self) -> Scene:
        return self.view.scene

    def selection(self) -> list[Item]:
        return self.scene.selected_items()

    def _snap(self, v: float) -> float:
        return round(v / self.snap) * self.snap if self.snap > 0 else v

    # --- resize handles (screen space) -----------------------------------

    def handle_rects(self) -> dict[str, tuple[float, float, float, float]]:
        """Screen-space handle squares for a single resizable selection (empty
        otherwise). Handles are constant-size regardless of zoom."""
        sel = self.selection()
        if len(sel) != 1 or not sel[0].resizable:
            return {}
        it = sel[0]
        bx, by, bw, bh = it.scene_bounds()
        vx0, vy0 = self.view.to_view(bx, by)
        vx1, vy1 = self.view.to_view(bx + bw, by + bh)
        mx, my = (vx0 + vx1) / 2.0, (vy0 + vy1) / 2.0
        s = self.handle_size
        pts = {
            "nw": (vx0, vy0), "n": (mx, vy0), "ne": (vx1, vy0),
            "e": (vx1, my), "se": (vx1, vy1), "s": (mx, vy1),
            "sw": (vx0, vy1), "w": (vx0, my),
        }
        return {k: (px - s / 2, py - s / 2, s, s) for k, (px, py) in pts.items()}

    def _hit_handle(self, vx: float, vy: float) -> str | None:
        for name, (hx, hy, hw, hh) in self.handle_rects().items():
            if hx - 2 <= vx <= hx + hw + 2 and hy - 2 <= vy <= hy + hh + 2:
                return name
        return None

    # --- pointer dispatch -------------------------------------------------

    def on_press(self, vx: float, vy: float, additive: bool = False) -> bool:
        if not self.view.contains_view(vx, vy):
            return False
        # 1. A resize handle of the current single selection.
        handle = self._hit_handle(vx, vy)
        if handle is not None:
            self._mode = "resize"
            self._handle = handle
            it = self.selection()[0]
            self._orig = {id(it): it.scene_bounds()}
            return True
        sx, sy = self.view.to_scene(vx, vy)
        hit = self.scene.item_at(sx, sy)
        # 2. An item → select (respect additive) + begin move.
        if hit is not None and hit.selectable:
            if additive:
                hit.selected = not hit.selected
            elif not hit.selected:
                self.scene.clear_selection()
                hit.selected = True
            self._mode = "move"
            self._start = (sx, sy)
            self._orig = {id(it): (it.x, it.y) for it in self.selection()}
            return True
        # 3. Empty space → rubber-band (clear unless additive).
        if not additive:
            self.scene.clear_selection()
        self._mode = "band"
        self._start = (sx, sy)
        self._band = (sx, sy, 0.0, 0.0)
        return True

    def on_drag(self, vx: float, vy: float) -> None:
        sx, sy = self.view.to_scene(vx, vy)
        if self._mode == "move":
            dx = self._snap(sx - self._start[0])
            dy = self._snap(sy - self._start[1])
            for it in self.selection():
                ox, oy = self._orig.get(id(it), (it.x, it.y))
                it.move_by((ox + dx) - it.x, (oy + dy) - it.y)
        elif self._mode == "resize":
            self._apply_resize(sx, sy)
        elif self._mode == "band":
            x0, y0 = self._start
            self._band = (min(x0, sx), min(y0, sy), abs(sx - x0), abs(sy - y0))

    def on_release(self) -> None:
        if self._mode == "band" and self._band is not None:
            for it in self.scene.items_in_rect(*self._band):
                if it.selectable:
                    it.selected = True
        self._mode = "idle"
        self._handle = None
        self._band = None
        self._orig = {}

    def _apply_resize(self, sx: float, sy: float, min_size: float = 8.0) -> None:
        sel = self.selection()
        if not sel:
            return
        it = sel[0]
        ox, oy, ow, oh = self._orig[id(it)]
        left, right, top, bottom = ox, ox + ow, oy, oy + oh
        h = self._handle or ""
        if "w" in h:
            left = self._snap(sx)
        if "e" in h:
            right = self._snap(sx)
        if "n" in h:
            top = self._snap(sy)
        if "s" in h:
            bottom = self._snap(sy)
        nx, nw = min(left, right), max(min_size, abs(right - left))
        ny, nh = min(top, bottom), max(min_size, abs(bottom - top))
        it.x, it.y, it.w, it.h = nx, ny, nw, nh

    # --- overlay paint ----------------------------------------------------

    def paint_overlay(self, dl: Any) -> None:
        t = current_theme()
        # Rubber-band (map the scene rect back to screen).
        if self._band is not None:
            bx, by, bw, bh = self._band
            vx0, vy0 = self.view.to_view(bx, by)
            vx1, vy1 = self.view.to_view(bx + bw, by + bh)
            rx, ry = min(vx0, vx1), min(vy0, vy1)
            rw, rh = abs(vx1 - vx0), abs(vy1 - vy0)
            dl.fill_path(_rounded_rect(rx, ry, rw, rh, 1),
                         with_alpha(t.primary, 0.12))
            dl.stroke_path(_rounded_rect(rx, ry, rw, rh, 1),
                           with_alpha(t.primary, 0.8), 1.0)
        # Resize handles.
        for _name, (hx, hy, hw, hh) in self.handle_rects().items():
            dl.fill_path(_rounded_rect(hx, hy, hw, hh, 2), t.primary)
            dl.stroke_path(_rounded_rect(hx, hy, hw, hh, 2),
                           with_alpha((255, 255, 255, 255), 0.9), 1.0)
