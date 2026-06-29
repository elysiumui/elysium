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
]


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
