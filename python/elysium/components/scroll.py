"""Scroll system — Tier-2 Qt parity (QScrollBar / QScrollArea).

* :class:`ScrollBar` — a draggable track + thumb with click-to-page and
  auto-hide, driven by content/viewport lengths (offset in logical pixels).
* :class:`ScrollView` — a clipped, scrollable viewport: it translates +
  clips its content (via the display list's ``push_clip`` / ``push_transform``)
  and owns both scrollbars, mouse-wheel + drag scrolling, and flick momentum.

Wheel events arrive through the window's ``poll_scroll_delta`` and are routed
to the hovered scrollable by the :class:`elysium.input.InputRouter` (see its
``set_scrollables``). Both implement the lightweight ``Scrollable`` protocol
(``scroll_rect`` + ``on_scroll``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from elysium.theme import current_theme, with_alpha, lighten
from elysium.components import Component, _rounded_rect


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass
class ScrollBar(Component):
    """A scrollbar over a content range. ``value`` is the scroll offset in
    logical pixels in ``[0, max_offset]``; ``content`` / ``viewport`` are the
    total + visible lengths along the bar's axis."""
    orientation: str = "vertical"      # "vertical" | "horizontal"
    value: float = 0.0
    content: float = 0.0
    viewport: float = 0.0
    on_change: Optional[Callable[[float], None]] = None
    thickness: float = 10.0
    min_thumb: float = 24.0
    auto_hide: bool = True

    _drag: Optional[tuple[float, float]] = field(default=None, init=False, repr=False)

    # -- geometry -----------------------------------------------------------

    def max_offset(self) -> float:
        return max(0.0, self.content - self.viewport)

    def needed(self) -> bool:
        return self.content > self.viewport + 0.5

    def _track_len(self) -> float:
        return self.h if self.orientation == "vertical" else self.w

    def thumb_extent(self) -> tuple[float, float]:
        """Return ``(start, length)`` of the thumb along the track."""
        track = self._track_len()
        if self.content <= 0 or track <= 0:
            return (0.0, track)
        length = max(self.min_thumb, track * min(1.0, self.viewport / self.content))
        length = min(length, track)
        mo = self.max_offset()
        frac = 0.0 if mo <= 0 else _clamp(self.value / mo, 0.0, 1.0)
        start = frac * (track - length)
        return (start, length)

    def thumb_rect(self) -> tuple[float, float, float, float]:
        start, length = self.thumb_extent()
        if self.orientation == "vertical":
            return (self.x, self.y + start, self.w, length)
        return (self.x + start, self.y, length, self.h)

    # -- interaction --------------------------------------------------------

    def set_value(self, v: float) -> None:
        v = _clamp(v, 0.0, self.max_offset())
        if v != self.value:
            self.value = v
            if self.on_change:
                try: self.on_change(v)
                except Exception: pass

    def _pos_along(self, mx: float, my: float) -> float:
        return (my - self.y) if self.orientation == "vertical" else (mx - self.x)

    def on_mouse_press(self, mx: float, my: float) -> bool:
        if not (self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h):
            return False
        start, length = self.thumb_extent()
        pos = self._pos_along(mx, my)
        if start <= pos <= start + length:
            self._drag = (pos, self.value)          # grab the thumb
        else:
            # Page toward the click.
            page = self.viewport * (1.0 if pos > start else -1.0)
            self.set_value(self.value + page)
        return True

    def on_mouse_drag(self, mx: float, my: float) -> bool:
        if self._drag is None:
            return False
        track = self._track_len()
        _, length = self.thumb_extent()
        span = max(1e-6, track - length)
        pos0, val0 = self._drag
        dpos = self._pos_along(mx, my) - pos0
        self.set_value(val0 + (dpos / span) * self.max_offset())
        return True

    def on_mouse_release(self) -> None:
        self._drag = None

    # -- paint --------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        if self.auto_hide and not self.needed():
            return
        t = current_theme()
        r = min(self.w, self.h) / 2.0
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r),
                     with_alpha(t.on_surface, 0.06))
        tx, ty, tw, th = self.thumb_rect()
        hot = self._drag is not None or self._hover_t > 0.2
        col = with_alpha(t.on_surface, 0.45 if hot else 0.28)
        tr = min(tw, th) / 2.0
        dl.fill_path(_rounded_rect(tx, ty, tw, th, tr), col)


# Flick-momentum decay per second and the speed below which it stops.
_MOMENTUM_DECAY = 0.0025
_MOMENTUM_STOP = 6.0


@dataclass
class ScrollView(Component):
    """A clipped scrollable viewport over content of size
    ``(content_w, content_h)``. Call :meth:`paint` with a callback that draws
    the content in content-space (origin = content top-left). Implements the
    ``Scrollable`` protocol so the InputRouter can deliver wheel events."""
    content_w: float = 0.0
    content_h: float = 0.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    on_change: Optional[Callable[[float, float], None]] = None
    bar_thickness: float = 10.0
    show_vertical: bool = True
    show_horizontal: bool = True

    vbar: ScrollBar = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    hbar: ScrollBar = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _vel: tuple[float, float] = field(default=(0.0, 0.0), init=False, repr=False)

    def __post_init__(self) -> None:
        self.vbar = ScrollBar(orientation="vertical", on_change=self._on_vbar,
                              thickness=self.bar_thickness)
        self.hbar = ScrollBar(orientation="horizontal", on_change=self._on_hbar,
                              thickness=self.bar_thickness)

    # -- geometry -----------------------------------------------------------

    def _vbar_visible(self) -> bool:
        return self.show_vertical and self.content_h > self.viewport_h() + 0.5

    def _hbar_visible(self) -> bool:
        return self.show_horizontal and self.content_w > self.viewport_w() + 0.5

    def viewport_w(self) -> float:
        return self.w - (self.bar_thickness if (self.show_vertical and
                         self.content_h > self.h + 0.5) else 0.0)

    def viewport_h(self) -> float:
        return self.h - (self.bar_thickness if (self.show_horizontal and
                         self.content_w > self.w + 0.5) else 0.0)

    def max_x(self) -> float:
        return max(0.0, self.content_w - self.viewport_w())

    def max_y(self) -> float:
        return max(0.0, self.content_h - self.viewport_h())

    def scroll_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.viewport_w(), self.viewport_h())

    # -- scrolling ----------------------------------------------------------

    def set_scroll(self, x: float, y: float) -> None:
        nx = _clamp(x, 0.0, self.max_x())
        ny = _clamp(y, 0.0, self.max_y())
        if (nx, ny) != (self.scroll_x, self.scroll_y):
            self.scroll_x, self.scroll_y = nx, ny
            if self.on_change:
                try: self.on_change(nx, ny)
                except Exception: pass

    def on_scroll(self, dx: float, dy: float, precise: bool = False) -> None:
        # Natural direction: scrolling down (dy<0 from the OS) moves content up.
        self.set_scroll(self.scroll_x - dx, self.scroll_y - dy)
        self._vel = (-dx, -dy) if precise else (0.0, 0.0)

    def scroll_to_rect(self, rx: float, ry: float, rw: float, rh: float) -> None:
        """Scroll the minimum amount so the content-space rect is visible."""
        x, y = self.scroll_x, self.scroll_y
        if rx < x: x = rx
        elif rx + rw > x + self.viewport_w(): x = rx + rw - self.viewport_w()
        if ry < y: y = ry
        elif ry + rh > y + self.viewport_h(): y = ry + rh - self.viewport_h()
        self.set_scroll(x, y)

    def update(self, dt: float, state: Any = None) -> None:
        super().update(dt, state or {})
        vx, vy = self._vel
        if abs(vx) > _MOMENTUM_STOP or abs(vy) > _MOMENTUM_STOP:
            self.set_scroll(self.scroll_x + vx * dt, self.scroll_y + vy * dt)
            k = _MOMENTUM_DECAY ** dt
            self._vel = (vx * k, vy * k)
        else:
            self._vel = (0.0, 0.0)

    # -- mouse to bars ------------------------------------------------------

    def _on_vbar(self, v: float) -> None:
        self.set_scroll(self.scroll_x, v)

    def _on_hbar(self, v: float) -> None:
        self.set_scroll(v, self.scroll_y)

    def _sync_bars(self) -> None:
        vw, vh = self.viewport_w(), self.viewport_h()
        self.vbar.x = self.x + vw
        self.vbar.y = self.y
        self.vbar.w = self.bar_thickness
        self.vbar.h = vh
        self.vbar.content, self.vbar.viewport, self.vbar.value = self.content_h, vh, self.scroll_y
        self.hbar.x = self.x
        self.hbar.y = self.y + vh
        self.hbar.w = vw
        self.hbar.h = self.bar_thickness
        self.hbar.content, self.hbar.viewport, self.hbar.value = self.content_w, vw, self.scroll_x

    def on_mouse_press(self, mx: float, my: float) -> bool:
        self._sync_bars()
        if self._vbar_visible() and self.vbar.on_mouse_press(mx, my):
            return True
        if self._hbar_visible() and self.hbar.on_mouse_press(mx, my):
            return True
        return False

    def on_mouse_drag(self, mx: float, my: float) -> bool:
        return self.vbar.on_mouse_drag(mx, my) or self.hbar.on_mouse_drag(mx, my)

    def on_mouse_release(self) -> None:
        self.vbar.on_mouse_release()
        self.hbar.on_mouse_release()

    # -- paint --------------------------------------------------------------

    def paint(self, dl: Any, paint_content: Optional[Callable[[Any], None]] = None) -> None:
        self._sync_bars()
        vw, vh = self.viewport_w(), self.viewport_h()
        if paint_content is not None:
            dl.push_clip(self.x, self.y, vw, vh)
            dl.push_transform(self.x - self.scroll_x, self.y - self.scroll_y)
            try:
                paint_content(dl)
            finally:
                dl.pop_transform()
                dl.pop_clip()
        if self._vbar_visible():
            self.vbar.paint(dl)
        if self._hbar_visible():
            self.hbar.paint(dl)


__all__ = ["ScrollBar", "ScrollView"]
