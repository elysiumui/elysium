"""Autocomplete — a completion popup for text inputs (Qt's ``QCompleter``).

A :class:`Completer` matches a query against a candidate list (prefix first, then
optional fuzzy subsequence), exposes keyboard navigation, and paints a popover
list anchored under a text field. Wire it to a ``TextField`` /
``EditableComboBox``: feed the field's text to :meth:`update_query`, route
Up/Down/Enter/Escape through :meth:`on_key`, and paint it after the field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import current_theme, with_alpha, lighten
from elysium.components import Component, _rounded_rect

__all__ = ["Completer"]


def _is_subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(ch in it for ch in needle)


@dataclass
class Completer(Component):
    """A completion popup over ``candidates``. ``x/y/w`` anchor it (set them to
    the field's left edge and bottom); the panel grows downward."""

    candidates: list[str] = field(default_factory=list)
    fuzzy: bool = True
    max_visible: int = 8
    row_h: float = 30.0
    visible: bool = False
    query: str = ""
    selected: int = 0
    matches: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    on_accept: Callable[[str], None] | None = None

    # --- matching ---------------------------------------------------------

    def _rank(self, q: str) -> list[str]:
        ql = q.lower()
        prefix: list[str] = []
        contains: list[str] = []
        fuzzy: list[str] = []
        pool = list(dict.fromkeys(self.history + self.candidates))
        for c in pool:
            cl = c.lower()
            if cl.startswith(ql):
                prefix.append(c)
            elif ql in cl:
                contains.append(c)
            elif self.fuzzy and _is_subsequence(ql, cl):
                fuzzy.append(c)
        hist = set(self.history)
        prefix.sort(key=lambda c: (c not in hist, len(c), c.lower()))
        contains.sort(key=lambda c: (c not in hist, cl_index(c, ql), len(c)))
        fuzzy.sort(key=lambda c: (c not in hist, len(c), c.lower()))
        out: list[str] = []
        seen: set[str] = set()
        for c in prefix + contains + fuzzy:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def update_query(self, query: str) -> None:
        self.query = query
        self.matches = self._rank(query) if query else []
        self.selected = 0
        self.visible = bool(self.matches)

    def close(self) -> None:
        self.visible = False

    # --- keyboard ---------------------------------------------------------

    def move(self, delta: int) -> None:
        if not self.matches:
            return
        self.selected = (self.selected + delta) % len(self.matches)

    def current(self) -> str | None:
        if self.visible and 0 <= self.selected < len(self.matches):
            return self.matches[self.selected]
        return None

    def accept(self) -> str | None:
        value = self.current()
        if value is not None:
            if value not in self.history:
                self.history.insert(0, value)
            if self.on_accept is not None:
                self.on_accept(value)
            self.visible = False
        return value

    def on_key(self, key: str) -> bool:
        """Route a navigation key. Returns ``True`` if consumed."""
        if not self.visible:
            return False
        k = key.lower()
        if k in ("down", "arrowdown"):
            self.move(1)
            return True
        if k in ("up", "arrowup"):
            self.move(-1)
            return True
        if k in ("return", "enter"):
            self.accept()
            return True
        if k in ("escape", "esc"):
            self.close()
            return True
        return False

    # --- geometry + hit ---------------------------------------------------

    def visible_count(self) -> int:
        return min(len(self.matches), self.max_visible)

    def panel_height(self) -> float:
        return self.visible_count() * self.row_h + 8

    def hit_row(self, mx: float, my: float) -> int | None:
        if not self.visible:
            return None
        for i in range(self.visible_count()):
            ry = self.y + 4 + i * self.row_h
            if self.x <= mx <= self.x + self.w and ry <= my <= ry + self.row_h:
                return i
        return None

    def on_click(self, mx: float, my: float) -> bool:
        i = self.hit_row(mx, my)
        if i is None:
            return False
        self.selected = i
        self.accept()
        return True

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        if not self.visible or not self.matches:
            return
        t = current_theme()
        ph = self.panel_height()
        s = t.shadow_medium
        dl.gradient_card(self.x, self.y, self.w, ph, t.radius_medium,
                         lighten(t.surface, 0.03), t.surface,
                         s.blur, s.offset, s.color)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5,
                                     self.w - 1, ph - 1, t.radius_medium),
                       with_alpha(t.edge, 1.0), 1.0)
        qlen = len(self.query)
        for i in range(self.visible_count()):
            item = self.matches[i]
            ry = self.y + 4 + i * self.row_h
            if i == self.selected:
                dl.fill_path(_rounded_rect(self.x + 4, ry, self.w - 8,
                                           self.row_h, t.radius_small),
                             with_alpha(t.primary, 0.18))
            ty = ry + self.row_h * 0.66
            # Highlight a leading prefix match in the accent colour.
            if item.lower().startswith(self.query.lower()) and qlen:
                head = item[:qlen]
                tail = item[qlen:]
                dl.draw_text(head, self.x + 14, ty, t.font_size_body, t.primary)
                hw = len(head) * t.font_size_body * 0.55
                dl.draw_text(tail, self.x + 14 + hw, ty, t.font_size_body,
                             t.on_surface)
            else:
                dl.draw_text(item, self.x + 14, ty, t.font_size_body,
                             t.on_surface)


def cl_index(c: str, ql: str) -> int:
    return c.lower().find(ql)
