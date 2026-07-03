"""Data-entry widgets — Tier-1 Qt parity.

Spin boxes, date/time editors, a calendar, and an editable combo box — all
built on the Phase-2 text-editing core (`elysium.text.edit.EditableText`) and
the Editable protocol, so registering them with a window's InputRouter makes
them keyboard-editable with no per-app plumbing.

* :class:`SpinBox` / :class:`DoubleSpinBox` — QSpinBox / QDoubleSpinBox parity:
  type a number, Up/Down or scroll to step, clamp to range, optional wrap.
* :class:`DateEdit` / :class:`TimeEdit` — segmented editors (Y/M/D, H/M/S):
  Left/Right select a segment, Up/Down step it, digits type into it.
* :class:`CalendarWidget` — month grid; arrows move the day, PageUp/Down the
  month; click or Enter selects.
* :class:`EditableComboBox` — a text field + drop-down list with
  filter-as-you-type and keyboard selection.
"""
from __future__ import annotations

import calendar as _calmod
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from elysium.theme import Color, current_theme, with_alpha, lighten, mix
from elysium.components import Component, _rounded_rect, _caret_x


# ===========================================================================
# SpinBox / DoubleSpinBox
# ===========================================================================

@dataclass
class SpinBox(Component):
    """Integer spin box. Type a value, Up/Down (or scroll) to step, clamp to
    [minimum, maximum], optional wrap. Implements the Editable protocol."""
    value: int = 0
    minimum: int = 0
    maximum: int = 100
    step: int = 1
    wrap: bool = False
    prefix: str = ""
    suffix: str = ""
    focus_id: str = ""
    on_change: Optional[Callable[[int], None]] = None

    _edit: Any = field(default=None, init=False, repr=False)
    _blink_t: float = field(default=0.0, init=False, repr=False)
    _up_rect: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)
    _down_rect: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)

    _is_float: bool = field(default=False, init=False, repr=False)
    decimals: int = 0

    def __post_init__(self) -> None:
        from elysium.text.edit import EditableText
        from elysium.text.validate import IntValidator, DoubleValidator
        v = (DoubleValidator(self.minimum, self.maximum, self.decimals)
             if self._is_float else IntValidator(int(self.minimum), int(self.maximum)))
        self._edit = EditableText(text=self._fmt(self.value),
                                  caret=len(self._fmt(self.value)),
                                  validator=v.validate, on_change=self._on_text_change)

    # -- value <-> text -----------------------------------------------------

    def _fmt(self, v) -> str:
        if self._is_float:
            return f"{float(v):.{self.decimals}f}" if self.decimals else f"{float(v)}"
        return str(int(v))

    def _parse(self, text: str):
        try:
            return float(text) if self._is_float else int(text)
        except ValueError:
            return None

    def _on_text_change(self, text: str) -> None:
        v = self._parse(text)
        if v is not None:
            self.value = v
            if self.on_change:
                try: self.on_change(v)
                except Exception: pass

    def _clamp(self, v):
        if self.wrap:
            span = self.maximum - self.minimum
            if span <= 0:
                return self.minimum
            if v > self.maximum:
                return self.minimum + (v - self.maximum - 1) % (span + 1)
            if v < self.minimum:
                return self.maximum - (self.minimum - v - 1) % (span + 1)
            return v
        return max(self.minimum, min(self.maximum, v))

    def set_value(self, v) -> None:
        v = self._clamp(v)
        self.value = v
        self._edit.set_text(self._fmt(v))

    def step_by(self, n: int) -> None:
        cur = self._parse(self._edit.text)
        base = cur if cur is not None else self.value
        self.set_value(self._clamp(base + n * self.step))
        self._blink_t = 0.0

    # -- Editable protocol --------------------------------------------------

    def focus_rect(self):
        return (self.x, self.y, self.w, self.h)

    def wants_keys(self) -> bool:
        return self._disabled_t < 0.5

    def on_key(self, code: str, mods: int) -> bool:
        if code == "ArrowUp":
            self.step_by(+1); return True
        if code == "ArrowDown":
            self.step_by(-1); return True
        if code in ("Enter", "NumpadEnter"):
            self.set_value(self._clamp(self.value)); return True
        return self._edit.on_key(code, mods)

    def on_text(self, s: str) -> None:
        self._edit.on_text(s); self._blink_t = 0.0

    def on_ime_preedit(self, s): self._edit.set_preedit(s)
    def on_ime_commit(self, s): self._edit.commit_preedit(s)
    def selected_text(self): return self._edit.selected_text()
    def delete_selection(self): self._edit.delete_selection()

    def on_scroll(self, delta: float) -> None:
        self.step_by(1 if delta > 0 else -1)

    def caret_rect(self):
        t = current_theme()
        cx = self.x + 10 + _caret_x(self._edit.text, t.font_size_body, self._edit.caret)
        return (cx, self.y + 6, 2.0, self.h - 12)

    # -- mouse --------------------------------------------------------------

    def on_mouse_press(self, mx: float, my: float) -> bool:
        for rect, n in ((self._up_rect, +1), (self._down_rect, -1)):
            x, y, w, h = rect
            if x <= mx <= x + w and y <= my <= y + h:
                self.step_by(n)
                return True
        return False

    def update(self, dt: float, state=None) -> None:
        super().update(dt, state or {})
        self._blink_t += dt

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = t.radius_small
        focused = self._focus_t > 0.5
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), t.surface_variant)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        disp = self.prefix + self._edit.text + self.suffix
        dl.draw_text(disp, self.x + 10, self.y + self.h * 0.64, t.font_size_body, t.on_surface)
        # Stepper buttons.
        bw = 18.0
        bx = self.x + self.w - bw - 2
        self._up_rect = (bx, self.y + 2, bw, self.h / 2 - 2)
        self._down_rect = (bx, self.y + self.h / 2, bw, self.h / 2 - 2)
        for rect, glyph in ((self._up_rect, "▲"), (self._down_rect, "▼")):
            x, y, w, h = rect
            dl.fill_path(_rounded_rect(x, y, w, h, 3), with_alpha(t.on_surface, 0.06))
            dl.draw_text(glyph, x + 4, y + h * 0.72, t.font_size_caption * 0.9,
                         with_alpha(t.on_surface, 0.7))
        if focused and (self._blink_t % 1.06) < 0.53:
            cr = self.caret_rect()
            dl.fill_path(_rounded_rect(cr[0], cr[1], 2.0, cr[3], 1.0), t.accent)


@dataclass
class DoubleSpinBox(SpinBox):
    """Floating-point spin box. Same as SpinBox but value/range are floats and
    ``decimals`` controls precision + the validator."""
    value: float = 0.0
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 0.1
    decimals: int = 2

    def __post_init__(self) -> None:
        self._is_float = True
        super().__post_init__()


# ===========================================================================
# DateEdit / TimeEdit — segmented editors
# ===========================================================================

@dataclass
class _SegmentedEdit(Component):
    focus_id: str = ""
    _seg: int = field(default=0, init=False, repr=False)
    _typed: str = field(default="", init=False, repr=False)
    _blink_t: float = field(default=0.0, init=False, repr=False)

    # subclasses define: _segments() -> list[(value, min, max, width)],
    # _set_segment(i, v), _join() -> str

    def focus_rect(self):
        return (self.x, self.y, self.w, self.h)

    def wants_keys(self) -> bool:
        return self._disabled_t < 0.5

    def _segdefs(self) -> list:
        raise NotImplementedError

    def _commit_typed(self) -> None:
        if not self._typed:
            return
        segs = self._segdefs()
        v, lo, hi, _ = segs[self._seg]
        try:
            nv = int(self._typed)
        except ValueError:
            nv = v
        nv = max(lo, min(hi, nv))
        self._set_segment(self._seg, nv)
        self._typed = ""

    def on_key(self, code: str, mods: int) -> bool:
        segs = self._segdefs()
        if code == "ArrowLeft":
            self._commit_typed(); self._seg = (self._seg - 1) % len(segs); return True
        if code == "ArrowRight":
            self._commit_typed(); self._seg = (self._seg + 1) % len(segs); return True
        if code in ("ArrowUp", "ArrowDown"):
            self._commit_typed()
            v, lo, hi, _ = segs[self._seg]
            delta = 1 if code == "ArrowUp" else -1
            nv = v + delta
            if nv > hi: nv = lo
            if nv < lo: nv = hi
            self._set_segment(self._seg, nv); return True
        if code in ("Enter", "NumpadEnter"):
            self._commit_typed(); return True
        return False

    def on_text(self, s: str) -> None:
        for ch in s:
            if ch.isdigit():
                self._typed += ch
                _, lo, hi, _ = self._segdefs()[self._seg]
                if len(self._typed) >= len(str(hi)):
                    self._commit_typed()
                    self._seg = min(self._seg + 1, len(self._segdefs()) - 1)
        self._blink_t = 0.0

    def update(self, dt: float, state=None) -> None:
        super().update(dt, state or {})
        self._blink_t += dt

    def on_mouse_press(self, mx: float, my: float) -> bool:
        # Pick the segment by x position.
        segs = self._segdefs()
        t = current_theme()
        x = self.x + 10
        for i, (_, _, _, w) in enumerate(segs):
            if x <= mx <= x + w:
                self._commit_typed(); self._seg = i; return True
            x += w + 8
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        focused = self._focus_t > 0.5
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, t.radius_small), t.surface_variant)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, t.radius_small),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        segs = self._segdefs()
        x = self.x + 10
        for i, (v, lo, hi, w) in enumerate(segs):
            txt = self._typed if (i == self._seg and self._typed) else self._render_seg(i, v)
            if focused and i == self._seg:
                dl.fill_path(_rounded_rect(x - 2, self.y + 5, w + 4, self.h - 10, 3),
                             with_alpha(t.accent, 0.20))
            dl.draw_text(txt, x, self.y + self.h * 0.66, t.font_size_body, t.on_surface)
            if i < len(segs) - 1:
                dl.draw_text(self._sep, x + w, self.y + self.h * 0.66, t.font_size_body,
                             with_alpha(t.on_surface, 0.6))
            x += w + 8

    _sep: str = field(default="-", init=False, repr=False)

    def _render_seg(self, i: int, v: int) -> str:
        width = len(str(self._segdefs()[i][2]))
        return str(v).zfill(width)


@dataclass
class DateEdit(_SegmentedEdit):
    date: _dt.date = field(default_factory=_dt.date.today)
    on_change: Optional[Callable[[_dt.date], None]] = None
    _sep: str = field(default="-", init=False, repr=False)

    def _segdefs(self):
        d = self.date
        last = _calmod.monthrange(d.year, d.month)[1]
        return [(d.year, 1, 9999, 44.0), (d.month, 1, 12, 22.0), (d.day, 1, last, 22.0)]

    def _set_segment(self, i: int, v: int) -> None:
        d = self.date
        y, m, day = d.year, d.month, d.day
        if i == 0: y = v
        elif i == 1: m = v
        else: day = v
        last = _calmod.monthrange(y, m)[1]
        day = min(day, last)
        self.date = _dt.date(y, m, day)
        if self.on_change:
            try: self.on_change(self.date)
            except Exception: pass


@dataclass
class TimeEdit(_SegmentedEdit):
    time: _dt.time = field(default_factory=lambda: _dt.time(0, 0, 0))
    show_seconds: bool = True
    on_change: Optional[Callable[[_dt.time], None]] = None
    _sep: str = field(default=":", init=False, repr=False)

    def _segdefs(self):
        t = self.time
        segs = [(t.hour, 0, 23, 22.0), (t.minute, 0, 59, 22.0)]
        if self.show_seconds:
            segs.append((t.second, 0, 59, 22.0))
        return segs

    def _set_segment(self, i: int, v: int) -> None:
        t = self.time
        h, m, s = t.hour, t.minute, t.second
        if i == 0: h = v
        elif i == 1: m = v
        else: s = v
        self.time = _dt.time(h, m, s)
        if self.on_change:
            try: self.on_change(self.time)
            except Exception: pass


# ===========================================================================
# CalendarWidget
# ===========================================================================

@dataclass
class CalendarWidget(Component):
    selected: _dt.date = field(default_factory=_dt.date.today)
    focus_id: str = ""
    on_change: Optional[Callable[[_dt.date], None]] = None
    _view_year: int = field(default=0, init=False, repr=False)
    _view_month: int = field(default=0, init=False, repr=False)
    _cell_rects: list = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._view_year = self.selected.year
        self._view_month = self.selected.month

    def focus_rect(self):
        return (self.x, self.y, self.w, self.h)

    def wants_keys(self) -> bool:
        return True

    def _shift_month(self, delta: int) -> None:
        m = self._view_month + delta
        y = self._view_year
        while m > 12: m -= 12; y += 1
        while m < 1: m += 12; y -= 1
        self._view_month, self._view_year = m, y

    def _select(self, d: _dt.date) -> None:
        self.selected = d
        self._view_year, self._view_month = d.year, d.month
        if self.on_change:
            try: self.on_change(d)
            except Exception: pass

    def on_key(self, code: str, mods: int) -> bool:
        delta = {"ArrowLeft": -1, "ArrowRight": 1, "ArrowUp": -7, "ArrowDown": 7}.get(code)
        if delta is not None:
            self._select(self.selected + _dt.timedelta(days=delta)); return True
        if code == "PageUp":
            self._shift_month(-1); return True
        if code == "PageDown":
            self._shift_month(1); return True
        return False

    def on_mouse_press(self, mx: float, my: float) -> bool:
        for d, (x, y, w, h) in self._cell_rects:
            if x <= mx <= x + w and y <= my <= y + h:
                self._select(d); return True
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, t.radius_medium), t.surface)
        # Header: Month Year.
        title = f"{_calmod.month_name[self._view_month]} {self._view_year}"
        dl.draw_text(title, self.x + 12, self.y + 22, t.font_size_body, t.on_surface)
        # Weekday row + grid.
        cols, rows = 7, 6
        gx = self.x + 8
        gy = self.y + 36
        cw = (self.w - 16) / cols
        ch = (self.h - 44) / (rows + 1)
        for i, wd in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            dl.draw_text(wd, gx + i * cw + 4, gy + ch * 0.7, t.font_size_caption,
                         with_alpha(t.on_surface, 0.6))
        self._cell_rects = []
        first_wd, days_in = _calmod.monthrange(self._view_year, self._view_month)
        day = 1
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx < first_wd or day > days_in:
                    continue
                d = _dt.date(self._view_year, self._view_month, day)
                cx = gx + col * cw
                cy = gy + (row + 1) * ch
                rect = (cx, cy, cw, ch)
                self._cell_rects.append((d, rect))
                if d == self.selected:
                    dl.fill_path(_rounded_rect(cx + 2, cy + 1, cw - 4, ch - 2, 4),
                                 with_alpha(t.primary, 0.85))
                elif d == _dt.date.today():
                    dl.stroke_path(_rounded_rect(cx + 2, cy + 1, cw - 4, ch - 2, 4),
                                   with_alpha(t.accent, 0.7), 1.0)
                col_fg = (255, 255, 255, 255) if d == self.selected else t.on_surface
                dl.draw_text(str(day), cx + 6, cy + ch * 0.66, t.font_size_body, col_fg)
                day += 1


# ===========================================================================
# EditableComboBox
# ===========================================================================

@dataclass
class EditableComboBox(Component):
    """Text field + drop-down list with filter-as-you-type. The text is
    editable; the popup shows items matching the current text; Up/Down +
    Enter select, click selects."""
    items: Sequence[str] = field(default_factory=list)
    value: str = ""
    focus_id: str = ""
    placeholder: str = ""
    on_change: Optional[Callable[[str], None]] = None
    open: bool = False
    row_height: float = 26.0
    max_visible: int = 6

    _edit: Any = field(default=None, init=False, repr=False)
    _highlight: int = field(default=0, init=False, repr=False)
    _item_rects: list = field(default_factory=list, init=False, repr=False)
    _arrow_rect: tuple = field(default=(0, 0, 0, 0), init=False, repr=False)

    def __post_init__(self) -> None:
        from elysium.text.edit import EditableText
        self._edit = EditableText(text=self.value, caret=len(self.value),
                                  on_change=self._on_text_change)

    def _on_text_change(self, text: str) -> None:
        self.value = text
        self._highlight = 0
        if self.on_change:
            try: self.on_change(text)
            except Exception: pass

    def filtered(self) -> list[str]:
        q = self._edit.text.lower()
        if not q:
            return list(self.items)
        return [it for it in self.items if q in it.lower()]

    # Editable protocol
    def focus_rect(self):
        return (self.x, self.y, self.w, self.h)

    def wants_keys(self) -> bool:
        return self._disabled_t < 0.5

    def on_key(self, code: str, mods: int) -> bool:
        items = self.filtered()
        if code == "ArrowDown":
            self.open = True
            self._highlight = min(self._highlight + 1, max(0, len(items) - 1)); return True
        if code == "ArrowUp":
            self._highlight = max(self._highlight - 1, 0); return True
        if code in ("Enter", "NumpadEnter"):
            if self.open and items:
                self._choose(items[self._highlight]); return True
            return False
        if code == "Escape":
            if self.open:
                self.open = False; return True
            return False
        consumed = self._edit.on_key(code, mods)
        if consumed:
            self.open = True
        return consumed

    def on_text(self, s: str) -> None:
        self._edit.on_text(s); self.open = True

    def on_ime_preedit(self, s): self._edit.set_preedit(s)
    def on_ime_commit(self, s): self._edit.commit_preedit(s)
    def selected_text(self): return self._edit.selected_text()
    def delete_selection(self): self._edit.delete_selection()

    def _choose(self, item: str) -> None:
        self._edit.set_text(item)
        self.value = item
        self.open = False
        if self.on_change:
            try: self.on_change(item)
            except Exception: pass

    def on_mouse_press(self, mx: float, my: float) -> bool:
        ax, ay, aw, ah = self._arrow_rect
        if ax <= mx <= ax + aw and ay <= my <= ay + ah:
            self.open = not self.open
            return True
        if self.open:
            for item, (x, y, w, h) in self._item_rects:
                if x <= mx <= x + w and y <= my <= y + h:
                    self._choose(item); return True
        if self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h:
            self.open = True
            return True
        self.open = False
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = t.radius_small
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), t.surface_variant)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        disp = self._edit.text or self.placeholder
        col = t.on_surface if self._edit.text else t.on_surface_muted
        dl.draw_text(disp, self.x + 10, self.y + self.h * 0.64, t.font_size_body, col)
        # Drop arrow.
        aw = 22.0
        self._arrow_rect = (self.x + self.w - aw, self.y, aw, self.h)
        acx = self.x + self.w - aw / 2
        acy = self.y + self.h / 2
        dl.fill_path(f"M {acx-4} {acy-2} L {acx+4} {acy-2} L {acx} {acy+3} Z",
                     with_alpha(t.on_surface, 0.7))
        # Popup list.
        self._item_rects = []
        if self.open:
            items = self.filtered()[: self.max_visible]
            py = self.y + self.h + 2
            ph = len(items) * self.row_height
            if items:
                dl.fill_path(_rounded_rect(self.x, py, self.w, ph + 4, r), lighten(t.surface, 0.03))
                dl.stroke_path(_rounded_rect(self.x + 0.5, py + 0.5, self.w - 1, ph + 3, r),
                               with_alpha(t.edge, 0.8), 1.0)
            for i, item in enumerate(items):
                iy = py + 2 + i * self.row_height
                rect = (self.x, iy, self.w, self.row_height)
                self._item_rects.append((item, rect))
                if i == self._highlight:
                    dl.fill_path(_rounded_rect(self.x + 2, iy, self.w - 4, self.row_height - 1, 3),
                                 with_alpha(t.primary, 0.20))
                dl.draw_text(item, self.x + 10, iy + self.row_height * 0.66,
                             t.font_size_body, t.on_surface)


__all__ = [
    "SpinBox", "DoubleSpinBox", "DateEdit", "TimeEdit",
    "CalendarWidget", "EditableComboBox",
]
