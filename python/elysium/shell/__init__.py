"""Application-shell widgets — the structural frame Elysium was missing for
Qt/PySide6 parity (the ``QMainWindow`` ecosystem).

These compose the framework's existing immediate-mode ``Component`` primitives
(``Button``, ``Label``, ``Menu``, ``Tabs`` …) into the layout widgets a real
desktop app needs. Every widget is an immediate-mode ``@dataclass`` Component:
it reads ``current_theme()`` at paint time (so it recolours with the theme) and
exposes plain methods the host calls to dispatch input.

Tier 4 — App-shell essentials. This module (Phase 1):

* :class:`GroupBox`  — a titled, bordered container with a content rect.
* :class:`StatusBar` — a bottom bar: a transient message + right-aligned
  permanent sections.
* :class:`Splitter`  — a draggable divider splitting an area into two panes
  (horizontal or vertical), with min-size clamping.
* :class:`MenuBar`   — a persistent in-window menu bar over the existing
  ``Menu`` / ``MenuItem`` popovers.

Later phases add ``ToolBar``/``ToolButton``, ``TabWidget``, and
``DockManager``/``DockWidget``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import current_theme, lighten, with_alpha
from elysium.components import Component, Menu, MenuItem, _rounded_rect

__all__ = [
    "GroupBox",
    "StatusBar",
    "Splitter",
    "MenuBar",
    "ToolButton",
    "ToolBar",
    "TabWidget",
    "DockWidget",
    "DockManager",
    "Drawer",
    "Stepper",
    "Wizard",
]

DOCK_AREAS = ("left", "right", "bottom", "center")


def _rect_path(x: float, y: float, w: float, h: float) -> str:
    """A plain (un-rounded) rectangle as an SVG path."""
    return f"M {x} {y} H {x + w} V {y + h} H {x} Z"


# ---------------------------------------------------------------------------
# GroupBox — a titled, bordered container (Qt's QGroupBox).
# ---------------------------------------------------------------------------

@dataclass
class GroupBox(Component):
    """A titled panel with a header row, a hairline divider, and a content
    area. Lay child widgets out inside :meth:`content_rect`."""

    title: str = ""
    radius: float | None = None
    header_h: float = 30.0
    pad: float = 12.0

    def content_rect(self) -> tuple[float, float, float, float]:
        """The inner rect (below the header, inset by ``pad``) for children."""
        top = self.y + self.header_h
        return (
            self.x + self.pad,
            top + self.pad,
            max(0.0, self.w - 2 * self.pad),
            max(0.0, self.h - self.header_h - 2 * self.pad),
        )

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.radius if self.radius is not None else t.radius_medium
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r),
                     t.surface_variant)
        dl.stroke_path(
            _rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
            with_alpha(t.edge, 1.0), 1.0)
        if self.title:
            dl.draw_text(self.title, self.x + 12,
                         self.y + self.header_h * 0.66,
                         t.font_size_body, t.on_surface)
            # Hairline divider under the header.
            dl.fill_path(_rect_path(self.x + 1, self.y + self.header_h,
                                    self.w - 2, 1.0),
                         with_alpha(t.edge, 0.7))


# ---------------------------------------------------------------------------
# StatusBar — a bottom bar with a message + right-aligned sections.
# ---------------------------------------------------------------------------

@dataclass
class StatusBar(Component):
    """A thin bar (Qt's QStatusBar): a transient left-aligned ``message`` and a
    list of right-aligned permanent ``sections`` (e.g. cursor pos, encoding)."""

    message: str = ""
    sections: list[str] = field(default_factory=list)
    section_gap: float = 18.0
    h: float = 24.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rect_path(self.x, self.y, self.w, self.h),
                     lighten(t.surface, 0.02))
        # Top hairline separator.
        dl.fill_path(_rect_path(self.x, self.y, self.w, 1.0),
                     with_alpha(t.edge, 0.8))
        cy = self.y + self.h * 0.66
        size = t.font_size_caption
        if self.message:
            dl.draw_text(self.message, self.x + 12, cy, size, t.on_surface_muted)
        rx = self.x + self.w - 12
        for sec in reversed(self.sections):
            approx_w = len(sec) * size * 0.6
            dl.draw_text(sec, rx - approx_w, cy, size, t.on_surface_muted)
            rx -= approx_w + self.section_gap


# ---------------------------------------------------------------------------
# Splitter — a draggable two-pane divider (Qt's QSplitter).
# ---------------------------------------------------------------------------

@dataclass
class Splitter(Component):
    """Splits its area into two panes with a draggable handle.

    ``orientation="horizontal"`` → left | right panes with a vertical handle;
    ``"vertical"`` → top / bottom panes with a horizontal handle. ``ratio`` is
    the first pane's fraction of the total. The caller lays its two children
    into :meth:`pane_rects`, paints the splitter, and routes presses/drags via
    :meth:`on_press` / :meth:`on_drag` / :meth:`on_release`.
    """

    orientation: str = "horizontal"
    ratio: float = 0.5
    handle: float = 6.0
    min_px: float = 48.0
    _dragging: bool = field(default=False, init=False, repr=False)
    _hover: bool = field(default=False, init=False, repr=False)

    def _length(self) -> float:
        return self.w if self.orientation == "horizontal" else self.h

    def _split_pos(self) -> float:
        if self.orientation == "horizontal":
            return self.x + self.ratio * self.w
        return self.y + self.ratio * self.h

    def pane_rects(self) -> tuple[tuple[float, float, float, float],
                                  tuple[float, float, float, float]]:
        sp = self._split_pos()
        half = self.handle / 2.0
        if self.orientation == "horizontal":
            a = (self.x, self.y, max(0.0, sp - half - self.x), self.h)
            b = (sp + half, self.y, max(0.0, self.x + self.w - sp - half), self.h)
        else:
            a = (self.x, self.y, self.w, max(0.0, sp - half - self.y))
            b = (self.x, sp + half, self.w, max(0.0, self.y + self.h - sp - half))
        return a, b

    def handle_rect(self) -> tuple[float, float, float, float]:
        sp = self._split_pos()
        half = self.handle / 2.0
        if self.orientation == "horizontal":
            return (sp - half, self.y, self.handle, self.h)
        return (self.x, sp - half, self.w, self.handle)

    def hit_handle(self, mx: float, my: float, grab: float = 3.0) -> bool:
        hx, hy, hw, hh = self.handle_rect()
        return (hx - grab <= mx <= hx + hw + grab
                and hy - grab <= my <= hy + hh + grab)

    def on_press(self, mx: float, my: float) -> bool:
        """Begin a drag if the press is on (or near) the handle."""
        if self.hit_handle(mx, my):
            self._dragging = True
            return True
        return False

    def on_drag(self, mx: float, my: float) -> None:
        if not self._dragging:
            return
        length = self._length()
        if length <= 0:
            return
        pos = (mx - self.x) if self.orientation == "horizontal" else (my - self.y)
        lo = self.min_px / length
        hi = 1.0 - self.min_px / length
        self.ratio = min(max(pos / length, lo), max(lo, hi))

    def on_release(self) -> None:
        self._dragging = False

    def update(self, dt: float, state: Any) -> None:  # type: ignore[override]
        self._hover = bool(state.get("hover")) if hasattr(state, "get") else False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        hx, hy, hw, hh = self.handle_rect()
        active = self._dragging or self._hover
        dl.fill_path(_rect_path(hx, hy, hw, hh),
                     with_alpha(t.primary, 0.18) if active
                     else with_alpha(t.edge, 0.5))
        # Three grip dots centred on the handle.
        cx, cy = hx + hw / 2.0, hy + hh / 2.0
        col = with_alpha(t.on_surface_muted, 0.9 if active else 0.5)
        for k in (-6.0, 0.0, 6.0):
            if self.orientation == "horizontal":
                dl.fill_path(_rounded_rect(cx - 1, cy + k - 1, 2, 2, 1), col)
            else:
                dl.fill_path(_rounded_rect(cx + k - 1, cy - 1, 2, 2, 1), col)


# ---------------------------------------------------------------------------
# MenuBar — a persistent in-window menu bar (Qt's QMenuBar).
# ---------------------------------------------------------------------------

@dataclass
class MenuBar(Component):
    """A horizontal strip of menu titles; clicking one opens its dropdown
    ``Menu``. Built on the existing ``Menu`` / ``MenuItem`` components.

    ``menus`` is a list of ``(title, [MenuItem, ...])``. The host calls
    :meth:`on_click` to toggle a menu, paints the bar, then paints
    :meth:`open_menu` (if any) last so the dropdown overlays siblings, and
    routes dropdown clicks through :meth:`dispatch_open_click`.
    """

    menus: list[tuple[str, list[MenuItem]]] = field(default_factory=list)
    open_index: int = -1
    item_pad: float = 14.0
    menu_w: float = 200.0
    h: float = 28.0
    _menu: Menu = field(default_factory=lambda: Menu(visible=True), init=False,
                        repr=False)

    def title_rects(self) -> list[tuple[int, str, float, float]]:
        """``(index, title, x, width)`` for each title, left-to-right."""
        t = current_theme()
        out: list[tuple[int, str, float, float]] = []
        cx = self.x + 6.0
        for i, (title, _items) in enumerate(self.menus):
            tw = len(title) * t.font_size_body * 0.6 + 2 * self.item_pad
            out.append((i, title, cx, tw))
            cx += tw
        return out

    def hit_title(self, mx: float, my: float) -> int:
        if not (self.y <= my <= self.y + self.h):
            return -1
        for i, _title, cx, tw in self.title_rects():
            if cx <= mx <= cx + tw:
                return i
        return -1

    def on_click(self, mx: float, my: float) -> bool:
        """Toggle the clicked title's menu. Returns True if a title was hit."""
        i = self.hit_title(mx, my)
        if i >= 0:
            self.open_index = -1 if self.open_index == i else i
            return True
        self.open_index = -1
        return False

    def open_menu(self) -> Menu | None:
        """The dropdown ``Menu`` for the open title, positioned under it (or
        ``None`` if nothing is open). Paint this last."""
        if not (0 <= self.open_index < len(self.menus)):
            return None
        _title, items = self.menus[self.open_index]
        for i, _ttl, cx, _tw in self.title_rects():
            if i == self.open_index:
                self._menu.items = items
                self._menu.x = cx
                self._menu.y = self.y + self.h + 2.0
                self._menu.w = self.menu_w
                self._menu.visible = True
                self._menu._vis_t = max(self._menu._vis_t, 1.0)
                return self._menu
        return None

    def dispatch_open_click(self, mx: float, my: float) -> bool:
        """Route a click while a dropdown is open: fire the item's callback (or
        just close). Returns True if the click was consumed by the dropdown
        layer (so the host should not also treat it as a canvas click)."""
        m = self.open_menu()
        if m is None:
            return False
        ih = m.item_h
        for idx, item in enumerate(m.items):
            ry = m.y + 4.0 + idx * ih
            if m.x <= mx <= m.x + m.w and ry <= my <= ry + ih:
                if item.on_click is not None:
                    item.on_click()
                self.open_index = -1
                return True
        # Click outside the open dropdown → close it (and consume).
        self.open_index = -1
        return True

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rect_path(self.x, self.y, self.w, self.h),
                     lighten(t.surface, 0.03))
        dl.fill_path(_rect_path(self.x, self.y + self.h - 1, self.w, 1.0),
                     with_alpha(t.edge, 0.8))
        for i, title, cx, tw in self.title_rects():
            if i == self.open_index:
                dl.fill_path(_rounded_rect(cx + 2, self.y + 3, tw - 4,
                                           self.h - 6, 4),
                             with_alpha(t.primary, 0.20))
            dl.draw_text(title, cx + self.item_pad, self.y + self.h * 0.66,
                         t.font_size_body, t.on_surface)
        # NOTE: the host paints open_menu() last so it overlays siblings.


# ---------------------------------------------------------------------------
# ToolButton / ToolBar — icon/text tool strips (Qt's QToolBar/QToolButton).
# ---------------------------------------------------------------------------

@dataclass
class ToolButton(Component):
    """A compact icon (and/or label) button for toolbars. ``icon`` is a painter
    ``(dl, cx, cy, size, color) -> None`` so any glyph source can be plugged in
    (a lambda, a framework ``GlyphAtlas``, or the Designer's icon registry).
    ``checked`` renders the toggled/active state."""

    label: str = ""
    icon: Callable[[Any, float, float, float, Any], None] | None = None
    checked: bool = False
    enabled: bool = True
    tooltip: str = ""
    on_click: Callable[[], None] | None = None
    icon_size: float = 18.0
    radius: float = 7.0

    def click(self) -> None:
        if self.enabled and self.on_click is not None:
            self.on_click()

    def paint(self, dl: Any) -> None:
        t = current_theme()
        if self.checked:
            dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                         with_alpha(t.primary, 0.20))
        elif self._hover_t > 0.01 and self.enabled:
            dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, self.radius),
                         with_alpha(t.on_surface, 0.07 * self._hover_t))
        fg = t.primary if self.checked else t.on_surface
        if not self.enabled:
            fg = with_alpha(fg, t.opacity_disabled)
        cx = self.x + self.w / 2.0
        cy = self.y + self.h / 2.0
        if self.icon is not None:
            iy = cy if not self.label else self.y + self.h * 0.40
            self.icon(dl, cx, iy, self.icon_size, fg)
            if self.label:
                approx = len(self.label) * t.font_size_caption * 0.55
                dl.draw_text(self.label, cx - approx / 2.0,
                             self.y + self.h - 6, t.font_size_caption, fg)
        elif self.label:
            approx = len(self.label) * t.font_size_body * 0.55
            dl.draw_text(self.label, cx - approx / 2.0,
                         cy + t.font_size_body * 0.35, t.font_size_body, fg)


_SEPARATOR = "separator"
_SPACER = "spacer"


@dataclass
class ToolBar(Component):
    """A strip of :class:`ToolButton`\\ s with separators and a flexible spacer.

    ``items`` is a list of ``ToolButton`` | ``"separator"`` | ``"spacer"``.
    Call :meth:`layout` (or :meth:`paint`, which lays out first) to assign each
    button's geometry; :meth:`hit` maps a point to a button. ``"spacer"`` pushes
    everything after it to the far edge.
    """

    items: list[Any] = field(default_factory=list)
    orientation: str = "horizontal"
    button: float = 30.0
    gap: float = 4.0
    pad: float = 6.0
    icon_size: float = 18.0

    @property
    def _buttons(self) -> list[ToolButton]:
        return [it for it in self.items if isinstance(it, ToolButton)]

    def layout(self) -> None:
        horiz = self.orientation == "horizontal"
        # First pass: total fixed extent + spacer count.
        fixed = 0.0
        spacers = 0
        for it in self.items:
            if it == _SPACER:
                spacers += 1
            elif it == _SEPARATOR:
                fixed += self.gap * 2 + 1
            elif isinstance(it, ToolButton):
                fixed += self.button + self.gap
        avail = (self.w if horiz else self.h) - 2 * self.pad
        spacer_px = max(0.0, (avail - fixed) / spacers) if spacers else 0.0
        cur = (self.x if horiz else self.y) + self.pad
        cross = (self.y if horiz else self.x)
        for it in self.items:
            if it == _SPACER:
                cur += spacer_px
            elif it == _SEPARATOR:
                cur += self.gap * 2 + 1
            elif isinstance(it, ToolButton):
                if horiz:
                    it.x, it.y = cur, cross + (self.h - self.button) / 2.0
                else:
                    it.x, it.y = cross + (self.w - self.button) / 2.0, cur
                it.w = it.h = self.button
                it.icon_size = self.icon_size
                cur += self.button + self.gap

    def hit(self, mx: float, my: float) -> ToolButton | None:
        for b in self._buttons:
            if b.enabled and b.hit_test(mx, my):
                return b
        return None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        self.layout()
        dl.fill_path(_rect_path(self.x, self.y, self.w, self.h),
                     lighten(t.surface, 0.02))
        # Bottom (horizontal) / right (vertical) hairline.
        if self.orientation == "horizontal":
            dl.fill_path(_rect_path(self.x, self.y + self.h - 1, self.w, 1.0),
                         with_alpha(t.edge, 0.7))
        else:
            dl.fill_path(_rect_path(self.x + self.w - 1, self.y, 1.0, self.h),
                         with_alpha(t.edge, 0.7))
        # Separators (re-walk to know their positions relative to buttons).
        horiz = self.orientation == "horizontal"
        cur = (self.x if horiz else self.y) + self.pad
        avail = (self.w if horiz else self.h) - 2 * self.pad
        spacers = sum(1 for it in self.items if it == _SPACER)
        fixed = sum((self.gap * 2 + 1) if it == _SEPARATOR
                    else (self.button + self.gap) if isinstance(it, ToolButton)
                    else 0.0 for it in self.items)
        spacer_px = max(0.0, (avail - fixed) / spacers) if spacers else 0.0
        for it in self.items:
            if it == _SPACER:
                cur += spacer_px
            elif it == _SEPARATOR:
                sx = cur + self.gap
                if horiz:
                    dl.fill_path(_rect_path(sx, self.y + 6, 1.0, self.h - 12),
                                 with_alpha(t.edge, 0.9))
                else:
                    dl.fill_path(_rect_path(self.x + 6, sx, self.w - 12, 1.0),
                                 with_alpha(t.edge, 0.9))
                cur += self.gap * 2 + 1
            elif isinstance(it, ToolButton):
                it.paint(dl)
                cur += self.button + self.gap


# ---------------------------------------------------------------------------
# TabWidget — a tab strip + routed content panel (Qt's QTabWidget).
# ---------------------------------------------------------------------------

@dataclass
class TabWidget(Component):
    """A tab strip with content-width tabs plus a content panel that routes to
    the active tab. ``tabs`` is ``[(title, content), ...]`` where ``content`` is
    any object with ``x/y/w/h`` + ``paint(dl)`` (typically a Component) or
    ``None``. Set ``closable`` for per-tab close buttons.

    The host calls :meth:`on_click` to switch/close tabs, then :meth:`paint`,
    which lays the active content into :meth:`content_rect` and paints it.
    """

    tabs: list[tuple[str, Any]] = field(default_factory=list)
    current: int = 0
    tab_h: float = 32.0
    closable: bool = False
    on_change: Callable[[int], None] | None = None
    on_close: Callable[[int], None] | None = None

    def tab_rects(self) -> list[tuple[int, str, float, float]]:
        t = current_theme()
        out: list[tuple[int, str, float, float]] = []
        cx = self.x
        for i, (title, _content) in enumerate(self.tabs):
            tw = len(title) * t.font_size_body * 0.6 + 28
            if self.closable:
                tw += 18
            out.append((i, title, cx, tw))
            cx += tw
        return out

    def content_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y + self.tab_h, self.w,
                max(0.0, self.h - self.tab_h))

    def _close_rect(self, tx: float, tw: float) -> tuple[float, float, float, float]:
        s = 14.0
        return (tx + tw - s - 8, self.y + (self.tab_h - s) / 2.0, s, s)

    def hit_tab(self, mx: float, my: float) -> tuple[str, int] | None:
        """Returns ``("close", i)`` if a tab's close button was hit, else
        ``("tab", i)`` for the tab body, else ``None``."""
        if not (self.y <= my <= self.y + self.tab_h):
            return None
        for i, _title, tx, tw in self.tab_rects():
            if tx <= mx <= tx + tw:
                if self.closable:
                    cxr = self._close_rect(tx, tw)
                    if (cxr[0] <= mx <= cxr[0] + cxr[2]
                            and cxr[1] <= my <= cxr[1] + cxr[3]):
                        return ("close", i)
                return ("tab", i)
        return None

    def on_click(self, mx: float, my: float) -> bool:
        hit = self.hit_tab(mx, my)
        if hit is None:
            return False
        kind, i = hit
        if kind == "close":
            self.close(i)
        else:
            self.select(i)
        return True

    def select(self, idx: int) -> None:
        if 0 <= idx < len(self.tabs) and idx != self.current:
            self.current = idx
            if self.on_change is not None:
                self.on_change(idx)

    def close(self, idx: int) -> None:
        if not (0 <= idx < len(self.tabs)):
            return
        if self.on_close is not None:
            self.on_close(idx)
        del self.tabs[idx]
        if self.current >= len(self.tabs):
            self.current = max(0, len(self.tabs) - 1)

    def paint(self, dl: Any) -> None:
        t = current_theme()
        # Tab strip background + content panel.
        dl.fill_path(_rect_path(self.x, self.y, self.w, self.tab_h),
                     lighten(t.surface, 0.02))
        crect = self.content_rect()
        dl.fill_path(_rounded_rect(crect[0], crect[1], crect[2], crect[3],
                                   t.radius_small), t.surface_variant)
        for i, title, tx, tw in self.tab_rects():
            active = i == self.current
            if active:
                dl.fill_path(_rect_path(tx, self.y, tw, self.tab_h),
                             t.surface_variant)
                # Top accent bar marks the active tab.
                dl.fill_path(_rect_path(tx, self.y, tw, 2.0), t.primary)
            color = t.on_surface if active else t.on_surface_muted
            dl.draw_text(title, tx + 12, self.y + self.tab_h * 0.64,
                         t.font_size_body, color)
            if self.closable:
                cxr = self._close_rect(tx, tw)
                cc = cxr[0] + cxr[2] / 2.0
                cm = cxr[1] + cxr[3] / 2.0
                xcol = with_alpha(t.on_surface_muted, 0.9)
                dl.stroke_path(
                    f"M {cc-3} {cm-3} L {cc+3} {cm+3} M {cc+3} {cm-3} "
                    f"L {cc-3} {cm+3}", xcol, 1.3)
        # Hairline under the strip, except beneath the active tab.
        dl.fill_path(_rect_path(self.x, self.y + self.tab_h - 1, self.w, 1.0),
                     with_alpha(t.edge, 0.6))
        # Route + paint the active content.
        if 0 <= self.current < len(self.tabs):
            content = self.tabs[self.current][1]
            if content is not None and hasattr(content, "paint"):
                content.x, content.y = crect[0], crect[1]
                content.w, content.h = crect[2], crect[3]
                content.paint(dl)


# ---------------------------------------------------------------------------
# DockWidget / DockManager — dockable, tabbed panels (Qt's QDockWidget).
# ---------------------------------------------------------------------------

@dataclass
class DockWidget(Component):
    """A dockable panel: a ``title`` and a ``content`` (any object with
    ``x/y/w/h`` + ``paint``). The :class:`DockManager` owns its placement; this
    type is mostly an identity + content holder. ``id`` must be unique within a
    manager (used for layout save/restore)."""

    id: str = ""
    title: str = ""
    content: Any = None
    closable: bool = True

    def paint_content(self, dl: Any, rect: tuple[float, float, float, float]) -> None:
        if self.content is not None and hasattr(self.content, "paint"):
            self.content.x, self.content.y = rect[0], rect[1]
            self.content.w, self.content.h = rect[2], rect[3]
            self.content.paint(dl)


@dataclass
class DockManager(Component):
    """Arranges :class:`DockWidget`\\ s into docked areas around a central area
    (Qt's ``QMainWindow`` dock system).

    Areas are ``"left"`` / ``"right"`` / ``"bottom"`` / ``"center"``. Each area
    is a tabbed region (multiple widgets share it via a tab strip). Splitter
    handles between the docked areas and the centre resize them. Dragging a
    tab shows drop-zone overlays and re-docks the widget on release. The whole
    layout serialises to/from a plain dict (wire to ``elysium.settings``).
    """

    areas: dict[str, list[DockWidget]] = field(
        default_factory=lambda: {a: [] for a in DOCK_AREAS})
    active: dict[str, int] = field(
        default_factory=lambda: {a: 0 for a in DOCK_AREAS})
    sizes: dict[str, float] = field(
        default_factory=lambda: {"left": 220.0, "right": 260.0, "bottom": 160.0})
    handle: float = 6.0
    tab_h: float = 28.0
    min_area: float = 80.0
    _drag: dict | None = field(default=None, init=False, repr=False)
    _resize: str | None = field(default=None, init=False, repr=False)
    _hover_zone: str | None = field(default=None, init=False, repr=False)

    # --- structure --------------------------------------------------------

    def add(self, dw: DockWidget, area: str = "center") -> DockWidget:
        self.areas.setdefault(area, []).append(dw)
        return dw

    def find(self, dock_id: str) -> tuple[str, int] | None:
        for area, lst in self.areas.items():
            for i, dw in enumerate(lst):
                if dw.id == dock_id:
                    return (area, i)
        return None

    def move(self, dw: DockWidget, area: str) -> None:
        for lst in self.areas.values():
            if dw in lst:
                lst.remove(dw)
        self.areas.setdefault(area, []).append(dw)
        self.active[area] = len(self.areas[area]) - 1

    def close(self, area: str, idx: int) -> None:
        lst = self.areas.get(area, [])
        if 0 <= idx < len(lst):
            del lst[idx]
            if self.active.get(area, 0) >= len(lst):
                self.active[area] = max(0, len(lst) - 1)

    # --- geometry ---------------------------------------------------------

    def _eff(self, area: str) -> float:
        """Effective size of a docked area (0 when empty)."""
        if area == "center" or not self.areas.get(area):
            return 0.0
        return self.sizes.get(area, 0.0)

    def area_rect(self, area: str) -> tuple[float, float, float, float]:
        x, y, w, h = self.x, self.y, self.w, self.h
        L, R, B = self._eff("left"), self._eff("right"), self._eff("bottom")
        hl = self.handle if L else 0.0
        hr = self.handle if R else 0.0
        hb = self.handle if B else 0.0
        if area == "left":
            return (x, y, L, h)
        if area == "right":
            return (x + w - R, y, R, h)
        cx = x + L + hl
        cw = max(0.0, w - L - hl - R - hr)
        if area == "bottom":
            return (cx, y + h - B, cw, B)
        # center
        return (cx, y, cw, max(0.0, h - B - hb))

    def handle_rect(self, area: str) -> tuple[float, float, float, float] | None:
        if self._eff(area) <= 0:
            return None
        ax, ay, aw, ah = self.area_rect(area)
        hsz = self.handle
        if area == "left":
            return (ax + aw, ay, hsz, ah)
        if area == "right":
            return (ax - hsz, ay, hsz, ah)
        if area == "bottom":
            return (ax, ay - hsz, aw, hsz)
        return None

    def content_rect(self, area: str) -> tuple[float, float, float, float]:
        ax, ay, aw, ah = self.area_rect(area)
        return (ax, ay + self.tab_h, aw, max(0.0, ah - self.tab_h))

    def tab_rects(self, area: str) -> list[tuple[int, float, float]]:
        """``(index, x, width)`` for each tab in ``area``."""
        t = current_theme()
        ax, _ay, _aw, _ah = self.area_rect(area)
        out: list[tuple[int, float, float]] = []
        cx = ax
        for i, dw in enumerate(self.areas.get(area, [])):
            tw = len(dw.title) * t.font_size_caption * 0.6 + 26
            if dw.closable:
                tw += 16
            out.append((i, cx, tw))
            cx += tw
        return out

    # --- hit-testing ------------------------------------------------------

    def hit(self, mx: float, my: float):
        for area in DOCK_AREAS:
            if not self.areas.get(area):
                continue
            hr = self.handle_rect(area)
            if hr and hr[0] - 3 <= mx <= hr[0] + hr[2] + 3 \
                    and hr[1] - 3 <= my <= hr[1] + hr[3] + 3:
                return ("handle", area, -1)
        for area in DOCK_AREAS:
            ax, ay, aw, _ah = self.area_rect(area)
            if not (ax <= mx <= ax + aw and ay <= my <= ay + self.tab_h):
                continue
            for i, tx, tw in self.tab_rects(area):
                if tx <= mx <= tx + tw:
                    dw = self.areas[area][i]
                    if dw.closable and mx >= tx + tw - 18:
                        return ("close", area, i)
                    return ("tab", area, i)
        return None

    def on_press(self, mx: float, my: float) -> bool:
        h = self.hit(mx, my)
        if h is None:
            return False
        kind, area, idx = h
        if kind == "handle":
            self._resize = area
            return True
        if kind == "close":
            self.close(area, idx)
            return True
        if kind == "tab":
            self.active[area] = idx
            self._drag = {"area": area, "idx": idx, "mx": mx, "my": my,
                          "armed": False}
            return True
        return False

    def on_drag(self, mx: float, my: float) -> None:
        if self._resize is not None:
            self._resize_area(self._resize, mx, my)
            return
        if self._drag is not None:
            # Arm the drag only after a small threshold so a click still selects.
            if (abs(mx - self._drag["mx"]) + abs(my - self._drag["my"])) > 6:
                self._drag["armed"] = True
            if self._drag["armed"]:
                self._hover_zone = self._zone_at(mx, my)

    def on_release(self) -> None:
        if self._drag is not None and self._drag.get("armed") and self._hover_zone:
            dw = self.areas[self._drag["area"]][self._drag["idx"]]
            self.move(dw, self._hover_zone)
        self._drag = None
        self._resize = None
        self._hover_zone = None

    def _resize_area(self, area: str, mx: float, my: float) -> None:
        if area == "left":
            self.sizes["left"] = self._clamp(mx - self.x)
        elif area == "right":
            self.sizes["right"] = self._clamp(self.x + self.w - mx)
        elif area == "bottom":
            self.sizes["bottom"] = self._clamp(self.y + self.h - my)

    def _clamp(self, v: float) -> float:
        return min(max(v, self.min_area), max(self.min_area, self.w * 0.6))

    # --- drop zones -------------------------------------------------------

    def drop_zones(self) -> dict[str, tuple[float, float, float, float]]:
        """Edge/centre drop targets (for the drag overlay), keyed by area."""
        cx, cy, cw, ch = self.area_rect("center")
        d = min(cw, ch) * 0.28
        return {
            "left":   (cx, cy, d, ch),
            "right":  (cx + cw - d, cy, d, ch),
            "bottom": (cx, cy + ch - d, cw, d),
            "center": (cx + d, cy + d, max(0.0, cw - 2 * d),
                       max(0.0, ch - 2 * d)),
        }

    def _zone_at(self, mx: float, my: float) -> str | None:
        # Centre wins ties; then edges.
        zones = self.drop_zones()
        for area in ("center", "left", "right", "bottom"):
            zx, zy, zw, zh = zones[area]
            if zx <= mx <= zx + zw and zy <= my <= zy + zh:
                return area
        return None

    # --- persistence ------------------------------------------------------

    def serialize(self) -> dict:
        return {
            "areas": {a: [dw.id for dw in self.areas.get(a, [])]
                      for a in DOCK_AREAS},
            "active": dict(self.active),
            "sizes": dict(self.sizes),
        }

    def restore(self, data: dict, registry: dict[str, DockWidget]) -> None:
        """Rebuild from :meth:`serialize` output. ``registry`` maps id → the
        live ``DockWidget`` (unknown ids are skipped)."""
        self.areas = {a: [registry[i] for i in data.get("areas", {}).get(a, [])
                          if i in registry] for a in DOCK_AREAS}
        self.active = {a: int(data.get("active", {}).get(a, 0))
                       for a in DOCK_AREAS}
        self.sizes.update({k: float(v) for k, v in data.get("sizes", {}).items()})

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        t = current_theme()
        for area in DOCK_AREAS:
            widgets = self.areas.get(area, [])
            if not widgets:
                continue
            ax, ay, aw, ah = self.area_rect(area)
            # Panel + tab strip.
            dl.fill_path(_rect_path(ax, ay, aw, ah),
                         t.surface_variant if area != "center"
                         else lighten(t.surface, 0.01))
            dl.fill_path(_rect_path(ax, ay, aw, self.tab_h),
                         lighten(t.surface, 0.02))
            act = self.active.get(area, 0)
            for i, tx, tw in self.tab_rects(area):
                dw = widgets[i]
                active = i == act
                if active:
                    dl.fill_path(_rect_path(tx, ay, tw, self.tab_h),
                                 t.surface_variant)
                    dl.fill_path(_rect_path(tx, ay, tw, 2.0), t.primary)
                col = t.on_surface if active else t.on_surface_muted
                dl.draw_text(dw.title, tx + 10, ay + self.tab_h * 0.64,
                             t.font_size_caption, col)
                if dw.closable:
                    cc, cm = tx + tw - 11, ay + self.tab_h / 2.0
                    dl.stroke_path(
                        f"M {cc-3} {cm-3} L {cc+3} {cm+3} M {cc+3} {cm-3} "
                        f"L {cc-3} {cm+3}", with_alpha(t.on_surface_muted, 0.8), 1.3)
            dl.fill_path(_rect_path(ax, ay + self.tab_h - 1, aw, 1.0),
                         with_alpha(t.edge, 0.6))
            # Active widget content.
            if widgets:
                widgets[min(act, len(widgets) - 1)].paint_content(
                    dl, self.content_rect(area))
            # Resize handle.
            hr = self.handle_rect(area)
            if hr:
                dl.fill_path(_rect_path(*hr), with_alpha(t.edge, 0.5))
        # Drag drop-zone overlay.
        if self._drag is not None and self._drag.get("armed"):
            zones = self.drop_zones()
            for area, rect in zones.items():
                hot = area == self._hover_zone
                dl.fill_path(_rect_path(*rect),
                             with_alpha(t.primary, 0.28 if hot else 0.08))
                if hot:
                    dl.stroke_path(_rounded_rect(rect[0] + 1, rect[1] + 1,
                                                 rect[2] - 2, rect[3] - 2, 4),
                                   with_alpha(t.primary, 0.9), 1.5)


# ---------------------------------------------------------------------------
# Drawer — a slide-out content panel (Qt's QDockWidget floating, but content).
# ---------------------------------------------------------------------------

@dataclass
class Drawer(Component):
    """A panel that slides in from an edge over the area it covers (``x/y/w/h``
    = the overlaid region, usually the whole window). ``content`` is any object
    with ``x/y/w/h`` + ``paint``. The host ticks :meth:`update` for the slide
    animation, paints it last, and routes clicks via :meth:`on_click`."""

    side: str = "right"          # left | right | bottom
    size: float = 360.0
    open: bool = False
    title: str = ""
    content: Any = None
    scrim: float = 0.45
    header_h: float = 44.0
    on_close: Callable[[], None] | None = None
    _t: float = field(default=0.0, init=False, repr=False)

    def set_open(self, value: bool) -> None:
        self.open = value

    def update(self, dt: float, state: Any) -> None:  # type: ignore[override]
        target = 1.0 if self.open else 0.0
        self._t = current_theme().motion.step(self._t, target, dt, "hover_rate")

    def panel_rect(self) -> tuple[float, float, float, float]:
        t = self._t
        if self.side == "right":
            return (self.x + self.w - self.size * t, self.y, self.size, self.h)
        if self.side == "left":
            return (self.x - self.size * (1 - t), self.y, self.size, self.h)
        # bottom
        return (self.x, self.y + self.h - self.size * t, self.w, self.size)

    def content_rect(self) -> tuple[float, float, float, float]:
        px, py, pw, ph = self.panel_rect()
        return (px, py + self.header_h, pw, max(0.0, ph - self.header_h))

    def _close_rect(self) -> tuple[float, float, float, float]:
        px, py, pw, _ph = self.panel_rect()
        return (px + pw - 30, py + 12, 18, 18)

    def on_click(self, mx: float, my: float) -> bool:
        if self._t < 0.5:
            return False
        cx, cy, cw, ch = self._close_rect()
        if cx - 4 <= mx <= cx + cw + 4 and cy - 4 <= my <= cy + ch + 4:
            self._do_close()
            return True
        px, py, pw, ph = self.panel_rect()
        if not (px <= mx <= px + pw and py <= my <= py + ph):
            self._do_close()           # clicked the scrim
            return True
        return False                   # inside the panel — let content handle it

    def _do_close(self) -> None:
        self.open = False
        if self.on_close is not None:
            self.on_close()

    def paint(self, dl: Any) -> None:
        if self._t < 0.01:
            return
        t = current_theme()
        dl.fill_path(_rect_path(self.x, self.y, self.w, self.h),
                     with_alpha((0, 0, 0, 255), self.scrim * self._t))
        px, py, pw, ph = self.panel_rect()
        s = t.shadow_far
        dl.gradient_card(px, py, pw, ph, 0.0, lighten(t.surface, 0.02), t.surface,
                         s.blur, s.offset, s.color)
        if self.title:
            dl.draw_text(self.title, px + 16, py + self.header_h * 0.62, 14,
                         t.on_surface)
        cx, cy, cw, ch = self._close_rect()
        ccx, ccy = cx + cw / 2, cy + ch / 2
        dl.stroke_path(f"M {ccx-4} {ccy-4} L {ccx+4} {ccy+4} M {ccx+4} {ccy-4} "
                       f"L {ccx-4} {ccy+4}", with_alpha(t.on_surface_muted, 0.9), 1.4)
        dl.fill_path(_rect_path(px, py + self.header_h - 1, pw, 1.0),
                     with_alpha(t.edge, 0.7))
        c = self.content
        if c is not None and hasattr(c, "paint") and self._t > 0.5:
            c.x, c.y, c.w, c.h = self.content_rect()
            c.paint(dl)


# ---------------------------------------------------------------------------
# Stepper / Wizard — a multi-step flow (Qt's QWizard).
# ---------------------------------------------------------------------------

@dataclass
class Stepper(Component):
    """A numbered step indicator. ``steps`` are titles; steps before ``current``
    show a check, ``current`` is accented, later steps are muted."""

    steps: list[str] = field(default_factory=list)
    current: int = 0
    h: float = 40.0
    dot: float = 24.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        n = len(self.steps)
        if n == 0:
            return
        seg = self.w / n
        cy = self.y + self.dot / 2 + 2
        for i, title in enumerate(self.steps):
            cx = self.x + seg * i + seg / 2
            done, active = i < self.current, i == self.current
            r = self.dot / 2
            # Connector to the previous dot.
            if i > 0:
                pcx = self.x + seg * (i - 1) + seg / 2
                col = t.primary if i <= self.current else with_alpha(t.edge, 1.0)
                dl.stroke_path(f"M {pcx + r} {cy} L {cx - r} {cy}", col, 2.0)
            if done:
                dl.fill_path(_rounded_rect(cx - r, cy - r, self.dot, self.dot, r),
                             t.primary)
                dl.stroke_path(f"M {cx-5} {cy} L {cx-1.5} {cy+4} L {cx+5} {cy-4}",
                               (255, 255, 255, 255), 1.8)
            elif active:
                dl.fill_path(_rounded_rect(cx - r, cy - r, self.dot, self.dot, r),
                             with_alpha(t.primary, 0.22))
                dl.stroke_path(_rounded_rect(cx - r + 0.5, cy - r + 0.5,
                                             self.dot - 1, self.dot - 1, r),
                               t.primary, 1.5)
                dl.draw_text(str(i + 1), cx - 4, cy + 4, 12, t.primary)
            else:
                dl.stroke_path(_rounded_rect(cx - r + 0.5, cy - r + 0.5,
                                             self.dot - 1, self.dot - 1, r),
                               with_alpha(t.edge, 1.0), 1.5)
                dl.draw_text(str(i + 1), cx - 4, cy + 4, 12, t.on_surface_muted)
            col = t.on_surface if (done or active) else t.on_surface_muted
            approx = len(title) * 10 * 0.55
            dl.draw_text(title, cx - approx / 2, cy + r + 14, 10.5, col)


@dataclass
class Wizard(Component):
    """A multi-step flow: a :class:`Stepper` header, the active step's content,
    and a Back/Next footer. ``steps`` are ``(title, content)``; content is any
    object with ``x/y/w/h`` + ``paint``."""

    steps: list[tuple[str, Any]] = field(default_factory=list)
    current: int = 0
    header_h: float = 64.0
    footer_h: float = 56.0
    next_label: str = "Next"
    finish_label: str = "Finish"
    on_change: Callable[[int], None] | None = None
    on_finish: Callable[[], None] | None = None

    def content_rect(self) -> tuple[float, float, float, float]:
        return (self.x + 16, self.y + self.header_h,
                self.w - 32, max(0.0, self.h - self.header_h - self.footer_h))

    def can_back(self) -> bool:
        return self.current > 0

    def is_last(self) -> bool:
        return self.current >= len(self.steps) - 1

    def back(self) -> None:
        if self.can_back():
            self.current -= 1
            if self.on_change is not None:
                self.on_change(self.current)

    def next(self) -> None:
        if self.is_last():
            if self.on_finish is not None:
                self.on_finish()
        else:
            self.current += 1
            if self.on_change is not None:
                self.on_change(self.current)

    def _back_rect(self) -> tuple[float, float, float, float]:
        by = self.y + self.h - self.footer_h + 11
        return (self.x + 16, by, 90, 34)

    def _next_rect(self) -> tuple[float, float, float, float]:
        by = self.y + self.h - self.footer_h + 11
        return (self.x + self.w - 16 - 110, by, 110, 34)

    def on_click(self, mx: float, my: float) -> bool:
        bx, by, bw, bh = self._back_rect()
        if self.can_back() and bx <= mx <= bx + bw and by <= my <= by + bh:
            self.back()
            return True
        nx, ny, nw, nh = self._next_rect()
        if nx <= mx <= nx + nw and ny <= my <= ny + nh:
            self.next()
            return True
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        Stepper(steps=[s[0] for s in self.steps], current=self.current,
                x=self.x + 16, y=self.y + 12, w=self.w - 32).paint(dl)
        if 0 <= self.current < len(self.steps):
            content = self.steps[self.current][1]
            if content is not None and hasattr(content, "paint"):
                content.x, content.y, content.w, content.h = self.content_rect()
                content.paint(dl)
        dl.fill_path(_rect_path(self.x, self.y + self.h - self.footer_h,
                                self.w, 1.0), with_alpha(t.edge, 0.7))
        if self.can_back():
            bx, by, bw, bh = self._back_rect()
            dl.fill_path(_rounded_rect(bx, by, bw, bh, 8),
                         with_alpha(t.on_surface, 0.0))
            dl.stroke_path(_rounded_rect(bx + 0.5, by + 0.5, bw - 1, bh - 1, 8),
                           with_alpha(t.edge, 1.0), 1.0)
            dl.draw_text("Back", bx + bw / 2 - 16, by + 22, 13, t.on_surface)
        nx, ny, nw, nh = self._next_rect()
        dl.fill_path(_rounded_rect(nx, ny, nw, nh, 8), t.primary)
        dl.fill_path(_rounded_rect(nx + 1, ny + 1, nw - 2, 2, 7),
                     with_alpha((255, 255, 255, 255), 0.10))
        lbl = self.finish_label if self.is_last() else self.next_label
        dl.draw_text(lbl, nx + nw / 2 - len(lbl) * 3.5, ny + 22, 13,
                     (255, 255, 255, 255))
