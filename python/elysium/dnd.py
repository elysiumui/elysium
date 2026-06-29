"""Inter-widget drag-and-drop — Qt's ``QDrag`` / ``QMimeData`` / drop events.

A :class:`DragController` orchestrates a drag: the source arms a drag on press,
a small move threshold promotes it to an active drag carrying typed
:class:`MimeData`, registered :class:`DropZone`\\ s highlight as the cursor
passes over ones that accept the payload, and releasing over an accepting zone
delivers the drop. A drag *ghost* follows the cursor.

This is in-app, widget-to-widget drag-and-drop (distinct from the native
file-drop / outbound-drag in ``elysium.native``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import current_theme, with_alpha
from elysium.components import _rounded_rect

__all__ = [
    "MimeData",
    "DropZone",
    "DragController",
]

TEXT = "text/plain"


@dataclass
class MimeData:
    """A typed payload carried by a drag (Qt's ``QMimeData``). Map MIME-type
    strings to arbitrary Python values; ``TEXT`` is the convenience text slot."""

    _data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(cls, text: str) -> "MimeData":
        m = cls()
        m.set_text(text)
        return m

    def set_text(self, text: str) -> None:
        self._data[TEXT] = text

    @property
    def text(self) -> str:
        return self._data.get(TEXT, "")

    def set_data(self, fmt: str, value: Any) -> None:
        self._data[fmt] = value

    def data(self, fmt: str, default: Any = None) -> Any:
        return self._data.get(fmt, default)

    def has_format(self, fmt: str) -> bool:
        return fmt in self._data

    def formats(self) -> list[str]:
        return list(self._data.keys())


@dataclass
class DropZone:
    """A region that can accept drops. Give it a ``rect`` (or a custom ``hit``),
    an ``accept(mime) -> bool`` predicate, and an ``on_drop(mime, x, y) -> bool``
    handler."""

    rect: tuple[float, float, float, float] | None = None
    accept: Callable[[MimeData], bool] = field(default=lambda m: True)
    on_drop: Callable[[MimeData, float, float], bool] | None = None
    hit: Callable[[float, float], bool] | None = None
    data: dict = field(default_factory=dict)

    def contains(self, x: float, y: float) -> bool:
        if self.hit is not None:
            return self.hit(x, y)
        if self.rect is None:
            return False
        rx, ry, rw, rh = self.rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh


@dataclass
class DragController:
    """Routes pointer events into a drag-and-drop interaction over a set of
    :class:`DropZone`\\ s. The host calls :meth:`press` / :meth:`move` /
    :meth:`release` with screen coords and :meth:`paint` each frame."""

    targets: list[DropZone] = field(default_factory=list)
    threshold: float = 6.0
    _pending: dict | None = field(default=None, init=False, repr=False)
    _active: dict | None = field(default=None, init=False, repr=False)
    _hover: DropZone | None = field(default=None, init=False, repr=False)
    _pos: tuple[float, float] = field(default=(0.0, 0.0), init=False, repr=False)

    def add_zone(self, zone: DropZone) -> DropZone:
        self.targets.append(zone)
        return zone

    # --- lifecycle --------------------------------------------------------

    def press(self, mx: float, my: float, mime: MimeData,
              ghost: Callable[[Any, float, float], None] | None = None,
              hotspot: tuple[float, float] = (0.0, 0.0),
              source: Any = None) -> None:
        """Arm a *potential* drag at a press. It becomes active only once the
        pointer moves past :attr:`threshold` (so a plain click is unaffected)."""
        self._pending = {"mx": mx, "my": my, "mime": mime, "ghost": ghost,
                         "hotspot": hotspot, "source": source}
        self._pos = (mx, my)

    def move(self, mx: float, my: float) -> bool:
        """Returns ``True`` once a drag is active. Promotes a pending drag past
        the threshold and tracks the hovered drop zone."""
        self._pos = (mx, my)
        if self._active is None and self._pending is not None:
            if (abs(mx - self._pending["mx"]) + abs(my - self._pending["my"])
                    > self.threshold):
                self._active = self._pending
                self._pending = None
        if self._active is not None:
            self._hover = self._zone_at(mx, my)
            return True
        return False

    def release(self, mx: float, my: float) -> bool:
        """Finish: drop on the accepting zone under the cursor (if any).
        Returns ``True`` if a drop was delivered."""
        dropped = False
        if self._active is not None:
            zone = self._zone_at(mx, my)
            if zone is not None and zone.on_drop is not None:
                dropped = bool(zone.on_drop(self._active["mime"], mx, my))
        self._pending = None
        self._active = None
        self._hover = None
        return dropped

    def cancel(self) -> None:
        self._pending = None
        self._active = None
        self._hover = None

    # --- queries ----------------------------------------------------------

    def is_dragging(self) -> bool:
        return self._active is not None

    def mime(self) -> MimeData | None:
        return self._active["mime"] if self._active else None

    def current_target(self) -> DropZone | None:
        return self._hover

    def _zone_at(self, mx: float, my: float) -> DropZone | None:
        mime = self._active["mime"] if self._active else None
        # Topmost (last-added) accepting zone under the cursor.
        for zone in reversed(self.targets):
            if zone.contains(mx, my) and (mime is None or zone.accept(mime)):
                return zone
        return None

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        if self._active is None:
            return
        t = current_theme()
        # Highlight the accepting target under the cursor.
        if self._hover is not None and self._hover.rect is not None:
            rx, ry, rw, rh = self._hover.rect
            dl.fill_path(_rounded_rect(rx, ry, rw, rh, 6),
                         with_alpha(t.primary, 0.14))
            dl.stroke_path(_rounded_rect(rx + 1, ry + 1, rw - 2, rh - 2, 6),
                           with_alpha(t.primary, 0.9), 1.5)
        # Drag ghost at the cursor (offset by the grab hotspot).
        mx, my = self._pos
        hx, hy = self._active["hotspot"]
        gx, gy = mx - hx, my - hy
        ghost = self._active["ghost"]
        if ghost is not None:
            ghost(dl, gx, gy)
        else:
            label = self._active["mime"].text or "item"
            w = max(60.0, len(label) * 7.5 + 20)
            dl.fill_path(_rounded_rect(gx, gy, w, 26, 6),
                         with_alpha(t.surface_variant, 0.95))
            dl.stroke_path(_rounded_rect(gx, gy, w, 26, 6),
                           with_alpha(t.primary, 0.8), 1.0)
            dl.draw_text(label, gx + 10, gy + 17, t.font_size_caption,
                         t.on_surface)
