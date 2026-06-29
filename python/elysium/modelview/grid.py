"""DataGrid — an Excel-grade editable spreadsheet over :class:`ItemModel`.

Builds on the existing Model/View (``ItemModel`` + ``Column``) and adds the
spreadsheet features a bulk editor needs that the virtualized ``TableView``
doesn't: **frozen/pinned leading columns**, **column resize / reorder /
show-hide**, **rectangular range selection**, **copy / paste TSV** (paste an
Excel block into a cell range), **fill-down**, **per-cell validation badges**,
and **per-cell pending-edit highlighting**. Rows are virtualized (only the
visible window paints), so a 100k-row catalog stays at frame rate.

**Column sorting** (``sortable``, on by default) and a **per-column filter row**
(``filterable``, off by default) are both optional and configurable: sorting
honours each :class:`Column`'s ``sortable`` flag and cycles asc → desc →
unsorted on a header click; filtering honours ``Column.filterable``, shows a
search box under each header, and narrows the body live. Both delegate to the
underlying :class:`ItemModel` (``toggle_sort`` / ``filter``), so cell state and
virtualization keep working.

Cell state (dirty / error) is keyed by the *row object identity*, so it stays
correct across sorts and filters. ``copy()`` / ``paste(text)`` operate on plain
TSV strings (so they're testable and clipboard-agnostic);
``copy_to_clipboard()`` is the best-effort system-clipboard convenience.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from elysium.theme import current_theme, with_alpha, lighten
from elysium.components import Component, _rounded_rect
from elysium.modelview import ItemModel, Column, _get

__all__ = ["DataGrid"]


def _rect(x: float, y: float, w: float, h: float) -> str:
    return f"M {x} {y} H {x + w} V {y + h} H {x} Z"


@dataclass
class DataGrid(Component):
    """A spreadsheet grid bound to an :class:`ItemModel`. Selection, copy/paste,
    fill-down, frozen columns, and per-cell validation/pending state, with
    virtualized row painting."""

    model: ItemModel = None  # type: ignore[assignment]
    row_h: float = 28.0
    header_h: float = 32.0
    frozen_cols: int = 0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    sortable: bool = True            # header-click column sorting (optional)
    filterable: bool = False         # per-column search/filter row (optional)
    filter_h: float = 26.0           # height of the filter row when filterable
    filter_match: Optional[Callable[[Any, str], bool]] = None  # custom matcher
    validators: dict = field(default_factory=dict)   # col_key -> (value)->str|None
    formatter: Optional[Callable[[Any, Column], str]] = None
    anchor: Optional[tuple] = field(default=None)     # (row, col) selection start
    active: Optional[tuple] = field(default=None)     # (row, col) selection end
    filter_focus: Optional[str] = field(default=None)  # focused filter column key
    _hidden: set = field(default_factory=set)
    _order: Optional[list] = field(default=None)
    _filters: dict = field(default_factory=dict)      # col_key -> query string
    _dirty: set = field(default_factory=set)          # (id(row), key)
    _errors: dict = field(default_factory=dict)       # (id(row), key) -> message
    _resize_key: Optional[str] = field(default=None, init=False, repr=False)

    # --- columns ----------------------------------------------------------

    def _ordered(self) -> list[Column]:
        cols = self.model.columns
        order = self._order if self._order is not None else range(len(cols))
        return [cols[i] for i in order]

    def visible_cols(self) -> list[Column]:
        return [c for c in self._ordered() if c.key not in self._hidden]

    def set_col_visible(self, key: str, visible: bool) -> None:
        if visible:
            self._hidden.discard(key)
        else:
            self._hidden.add(key)

    def resize_col(self, key: str, width: float) -> None:
        for c in self.model.columns:
            if c.key == key:
                c.width = max(40.0, width)

    def move_col(self, key: str, to_index: int) -> None:
        cols = self.model.columns
        order = list(self._order if self._order is not None else range(len(cols)))
        src = next((p for p, i in enumerate(order) if cols[i].key == key), None)
        if src is None:
            return
        idx = order.pop(src)
        order.insert(max(0, min(to_index, len(order))), idx)
        self._order = order

    def _frozen_width(self) -> float:
        vis = self.visible_cols()
        return sum(c.width for c in vis[:self.frozen_cols])

    def content_width(self) -> float:
        return sum(c.width for c in self.visible_cols())

    def _col_x(self, j: int) -> float:
        """Screen x of the left edge of visible-column ``j``."""
        vis = self.visible_cols()
        if j < self.frozen_cols:
            return self.x + sum(c.width for c in vis[:j])
        return (self.x + self._frozen_width()
                + sum(c.width for c in vis[self.frozen_cols:j]) - self.scroll_x)

    def max_scroll_x(self) -> float:
        return max(0.0, self.content_width() - self.w)

    def _filter_strip_h(self) -> float:
        return self.filter_h if self.filterable else 0.0

    def _head_total(self) -> float:
        return self.header_h + self._filter_strip_h()

    def max_scroll_y(self) -> float:
        return max(0.0, self.model.row_count() * self.row_h
                   - (self.h - self._head_total()))

    # --- geometry / hit-testing ------------------------------------------

    def _body_top(self) -> float:
        return self.y + self._head_total()

    def visible_rows(self) -> range:
        top = int(self.scroll_y / self.row_h)
        count = int((self.h - self._head_total()) / self.row_h) + 2
        return range(top, min(self.model.row_count(), top + count))

    def _col_at_x(self, mx: float) -> Optional[int]:
        """Visible-column index under screen-x ``mx`` (frozen band wins), or None."""
        vis = self.visible_cols()
        frozen_right = self.x + self._frozen_width()
        for j in range(min(self.frozen_cols, len(vis))):
            cx = self._col_x(j)
            if cx <= mx <= cx + vis[j].width:
                return j
        if mx >= frozen_right:
            for j in range(self.frozen_cols, len(vis)):
                cx = self._col_x(j)
                if cx <= mx <= cx + vis[j].width and cx >= frozen_right - 0.5:
                    return j
        return None

    def cell_at(self, mx: float, my: float) -> Optional[tuple]:
        """``(view_row, visible_col)`` for a screen point in the body, else None."""
        bt = self._body_top()
        if not (self.y <= my and bt <= my <= self.y + self.h
                and self.x <= mx <= self.x + self.w):
            return None
        row = int((my - bt + self.scroll_y) / self.row_h)
        if not (0 <= row < self.model.row_count()):
            return None
        j = self._col_at_x(mx)
        return None if j is None else (row, j)

    def header_col_at(self, mx: float, my: float) -> Optional[int]:
        """Visible-column index whose header label is under the point, or None."""
        if not (self.y <= my <= self.y + self.header_h):
            return None
        return self._col_at_x(mx)

    def filter_cell_at(self, mx: float, my: float) -> Optional[str]:
        """Column *key* of the filter box under the point, or None."""
        if not self.filterable:
            return None
        top = self.y + self.header_h
        if not (top <= my <= top + self.filter_h):
            return None
        j = self._col_at_x(mx)
        vis = self.visible_cols()
        return vis[j].key if j is not None and j < len(vis) else None

    def header_border_at(self, mx: float, my: float, grab: float = 4.0):
        """The column key whose right header border is under ``mx`` (for a
        resize), or None."""
        if not (self.y <= my <= self.y + self.header_h):
            return None
        vis = self.visible_cols()
        for j, c in enumerate(vis):
            edge = self._col_x(j) + c.width
            if abs(mx - edge) <= grab:
                return c.key
        return None

    # --- selection --------------------------------------------------------

    def selected_range(self) -> Optional[tuple]:
        """``(r0, c0, r1, c1)`` normalized, or None."""
        if self.anchor is None or self.active is None:
            return None
        (ar, ac), (br, bc) = self.anchor, self.active
        return (min(ar, br), min(ac, bc), max(ar, br), max(ac, bc))

    def select(self, row: int, col: int, extend: bool = False) -> None:
        if not extend or self.anchor is None:
            self.anchor = (row, col)
        self.active = (row, col)

    def on_press(self, mx: float, my: float, shift: bool = False) -> bool:
        border = self.header_border_at(mx, my)
        if border is not None:
            self._resize_key = border
            return True
        # Header label click → sort (optional / per-column).
        hc = self.header_col_at(mx, my)
        if hc is not None:
            self.sort_by(self.visible_cols()[hc].key)
            return True
        # Filter box click → focus it (optional / per-column).
        fk = self.filter_cell_at(mx, my)
        if fk is not None:
            col = next((c for c in self.model.columns if c.key == fk), None)
            self.filter_focus = fk if (col is None or col.filterable) else None
            return True
        cell = self.cell_at(mx, my)
        if cell is None:
            self.filter_focus = None
            return False
        self.filter_focus = None
        self.select(cell[0], cell[1], extend=shift)
        return True

    def on_drag(self, mx: float, my: float) -> None:
        if self._resize_key is not None:
            vis = self.visible_cols()
            j = next((p for p, c in enumerate(vis) if c.key == self._resize_key),
                     None)
            if j is not None:
                self.resize_col(self._resize_key, mx - self._col_x(j))
            return
        cell = self.cell_at(mx, my)
        if cell is not None:
            self.select(cell[0], cell[1], extend=True)

    def on_release(self) -> None:
        self._resize_key = None

    # --- sorting ----------------------------------------------------------

    def sort_by(self, key: str) -> None:
        """Cycle column ``key`` asc → desc → unsorted. No-op when sorting is
        disabled (``self.sortable``) or the column is not ``Column.sortable``."""
        if not self.sortable:
            return
        col = next((c for c in self.model.columns if c.key == key), None)
        if col is None or not col.sortable:
            return
        self.model.toggle_sort(key)
        self.anchor = self.active = None   # selection is positional; clear it

    # --- filtering --------------------------------------------------------

    def _default_match(self, value: Any, query: str) -> bool:
        return query.lower() in ("" if value is None else str(value)).lower()

    def active_filters(self) -> dict:
        """The live ``{col_key: query}`` map (non-empty queries only)."""
        return dict(self._filters)

    def set_filter(self, key: str, query: str) -> None:
        """Set (or clear, if ``query`` is empty) the search text for column
        ``key`` and re-apply. No-op when the column is not ``Column.filterable``."""
        col = next((c for c in self.model.columns if c.key == key), None)
        if col is not None and not col.filterable:
            return
        if query:
            self._filters[key] = query
        else:
            self._filters.pop(key, None)
        self._apply_filters()

    def clear_filters(self) -> None:
        self._filters.clear()
        self.filter_focus = None
        self._apply_filters()

    def _apply_filters(self) -> None:
        flt = dict(self._filters)
        match = self.filter_match or self._default_match
        if not flt:
            self.model.filter(None)
        else:
            def predicate(row: Any) -> bool:
                return all(match(_get(row, k), q) for k, q in flt.items())
            self.model.filter(predicate)
        self.anchor = self.active = None   # the view changed; drop positional sel
        self.scroll_y = min(self.scroll_y, self.max_scroll_y())

    def focus_filter(self, key: Optional[str]) -> None:
        self.filter_focus = key

    def on_text(self, text: str) -> None:
        """Append typed text to the focused filter box (no-op if none focused)."""
        if self.filter_focus is None or not text:
            return
        cur = self._filters.get(self.filter_focus, "")
        self.set_filter(self.filter_focus, cur + text)

    def on_backspace(self) -> None:
        """Delete the last character of the focused filter box."""
        if self.filter_focus is None:
            return
        cur = self._filters.get(self.filter_focus, "")
        self.set_filter(self.filter_focus, cur[:-1])

    # --- cell values + validation ----------------------------------------

    def _row_obj(self, view_row: int) -> Any:
        v = self.model.view()
        return v[view_row] if 0 <= view_row < len(v) else None

    def cell_text(self, view_row: int, col: Column) -> str:
        val = self.model.value(view_row, col.key)
        if self.formatter is not None:
            return self.formatter(val, col)
        return "" if val is None else str(val)

    def is_dirty(self, view_row: int, col: Column) -> bool:
        row = self._row_obj(view_row)
        return row is not None and (id(row), col.key) in self._dirty

    def cell_error(self, view_row: int, col: Column) -> Optional[str]:
        row = self._row_obj(view_row)
        return self._errors.get((id(row), col.key)) if row is not None else None

    def dirty_count(self) -> int:
        return len(self._dirty)

    def error_count(self) -> int:
        return len(self._errors)

    def clear_pending(self) -> None:
        self._dirty.clear()
        self._errors.clear()

    def set_cell(self, view_row: int, col_index: int, value: Any) -> None:
        vis = self.visible_cols()
        if not (0 <= col_index < len(vis)):
            return
        col = vis[col_index]
        row = self._row_obj(view_row)
        if row is None:
            return
        self.model.set_value(view_row, col.key, value)
        self._dirty.add((id(row), col.key))
        validator = self.validators.get(col.key)
        key = (id(row), col.key)
        if validator is not None:
            err = validator(value)
            if err:
                self._errors[key] = err
            else:
                self._errors.pop(key, None)

    # --- copy / paste / fill ---------------------------------------------

    def copy(self) -> str:
        """The selected range as TSV (rows by ``\\n``, cells by ``\\t``)."""
        rng = self.selected_range()
        if rng is None:
            return ""
        r0, c0, r1, c1 = rng
        vis = self.visible_cols()
        lines = []
        for r in range(r0, r1 + 1):
            cells = []
            for c in range(c0, min(c1 + 1, len(vis))):
                v = self.model.value(r, vis[c].key)
                cells.append("" if v is None else str(v))
            lines.append("\t".join(cells))
        return "\n".join(lines)

    def paste(self, text: str) -> int:
        """Paste TSV starting at the active (or anchor) cell. Returns the number
        of cells written. New values are marked dirty + validated."""
        start = self.active or self.anchor
        if start is None or not text:
            return 0
        r0, c0 = start
        written = 0
        rows = text.split("\n")
        for dr, line in enumerate(rows):
            for dc, cell in enumerate(line.split("\t")):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < self.model.row_count():
                    self.set_cell(r, c, cell)
                    written += 1
        return written

    def fill_down(self) -> int:
        """Copy the top row of the selection down to the rest. Returns cells
        written."""
        rng = self.selected_range()
        if rng is None:
            return 0
        r0, c0, r1, c1 = rng
        vis = self.visible_cols()
        written = 0
        for c in range(c0, min(c1 + 1, len(vis))):
            src = self.model.value(r0, vis[c].key)
            for r in range(r0 + 1, r1 + 1):
                self.set_cell(r, c, src)
                written += 1
        return written

    def copy_to_clipboard(self) -> str:
        text = self.copy()
        try:  # best-effort system clipboard
            from elysium._native import _native as _n
            _n.set_clipboard_text(text)
        except Exception:
            pass
        return text

    # --- paint ------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        t = current_theme()
        vis = self.visible_cols()
        bt = self._body_top()
        frozen_right = self.x + self._frozen_width()
        rng = self.selected_range()
        sort_key, sort_rev = self.model.sort_state

        def paint_col_band(cols_range, clip: bool) -> None:
            if clip:
                dl.push_clip(frozen_right, self.y,
                             self.x + self.w - frozen_right, self.h)
            for j in cols_range:
                col = vis[j]
                cx = self._col_x(j)
                cw = col.width
                # Header cell.
                dl.fill_path(_rect(cx, self.y, cw, self.header_h),
                             lighten(t.surface, 0.03))
                title = col.title
                if sort_key == col.key:
                    title += " ▾" if sort_rev else " ▴"
                dl.draw_text(title, cx + 8, self.y + self.header_h * 0.64,
                             t.font_size_caption, t.on_surface)
                # Filter box (optional).
                if self.filterable:
                    fy = self.y + self.header_h
                    dl.fill_path(_rect(cx, fy, cw, self.filter_h),
                                 lighten(t.surface, 0.015))
                    if col.filterable:
                        bx, by = cx + 4, fy + 3
                        bw, bh = cw - 8, self.filter_h - 6
                        dl.fill_path(_rounded_rect(bx, by, bw, bh, 4), t.surface)
                        q = self._filters.get(col.key, "")
                        if self.filter_focus == col.key:
                            dl.stroke_path(
                                _rounded_rect(bx + 0.5, by + 0.5, bw - 1, bh - 1, 4),
                                t.primary, 1.2)
                        elif q:
                            dl.stroke_path(
                                _rounded_rect(bx + 0.5, by + 0.5, bw - 1, bh - 1, 4),
                                with_alpha(t.primary, 0.5), 1.0)
                        label = q if q else "Filter…"
                        color = (t.on_surface if q
                                 else with_alpha(t.on_surface_muted, 0.7))
                        dl.draw_text(label, bx + 7, by + bh * 0.72,
                                     t.font_size_caption, color)
                # Body cells (virtualized).
                for r in self.visible_rows():
                    ry = bt + r * self.row_h - self.scroll_y
                    selected = (rng is not None and rng[0] <= r <= rng[2]
                                and rng[1] <= j <= rng[3])
                    if self.is_dirty(r, col):
                        dl.fill_path(_rect(cx, ry, cw, self.row_h),
                                     with_alpha(t.success, 0.16))
                    if selected:
                        dl.fill_path(_rect(cx, ry, cw, self.row_h),
                                     with_alpha(t.primary, 0.16))
                    txt = self.cell_text(r, col)
                    align = col.align
                    if align == "right":
                        approx = len(txt) * t.font_size_body * 0.55
                        tx = cx + cw - approx - 8
                    else:
                        tx = cx + 8
                    dl.draw_text(txt, tx, ry + self.row_h * 0.66,
                                 t.font_size_body, t.on_surface)
                    if self.cell_error(r, col) is not None:
                        dl.fill_path(
                            f"M {cx+cw-8} {ry+2} L {cx+cw-2} {ry+2} "
                            f"L {cx+cw-2} {ry+8} Z", t.danger)
                # Column separator.
                dl.fill_path(_rect(cx + cw - 1, self.y, 1, self.h),
                             with_alpha(t.edge, 0.5))
            if clip:
                dl.pop_clip()

        # Background.
        dl.fill_path(_rect(self.x, self.y, self.w, self.h), t.surface)
        # Scrolled band (clipped), then frozen band on top.
        paint_col_band(range(self.frozen_cols, len(vis)), clip=True)
        if self.frozen_cols:
            paint_col_band(range(0, self.frozen_cols), clip=False)
            dl.fill_path(_rect(frozen_right - 1, self.y, 2, self.h),
                         with_alpha(t.edge, 1.0))
        # Header bottom hairline (+ a second below the filter strip).
        dl.fill_path(_rect(self.x, self.y + self.header_h - 1, self.w, 1),
                     with_alpha(t.edge, 0.8))
        if self.filterable:
            dl.fill_path(_rect(self.x, self._body_top() - 1, self.w, 1),
                         with_alpha(t.edge, 0.8))
        # Active-cell outline.
        if self.active is not None:
            ar, ac = self.active
            if ac < len(vis) and ar in self.visible_rows():
                ax = self._col_x(ac)
                ay = bt + ar * self.row_h - self.scroll_y
                dl.stroke_path(_rounded_rect(ax + 0.5, ay + 0.5,
                                             vis[ac].width - 1, self.row_h - 1, 2),
                               t.primary, 1.5)
