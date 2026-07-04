"""Model/View — Tier-1 Qt parity for data-driven lists, tables, and trees.

Qt's Model/View separates *what* the data is (a model) from *how* it's shown
(a view) with pluggable per-cell renderers (delegates). Elysium's version is
idiomatic and reactive — :class:`ItemModel` holds rows, derives a
sorted/filtered *view* lazily, and bumps a version counter on change so the
immediate-mode views repaint — plus a thin :class:`QtItemModelAdapter`
(``rowCount``/``columnCount``/``data``/``setData``…) so developers porting
from ``QAbstractItemModel`` feel at home.

Views (:class:`TableView`, :class:`ListView`, :class:`TreeView`) are
virtualized — only the rows visible in their rect are painted, so a 100k-row
model stays at frame rate. Cells render through a :class:`Delegate`
(:class:`TextDelegate`, :class:`EditableCellDelegate`, and the differentiator
:class:`Mesh3DDelegate` for a GPU 3-D thumbnail per cell).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Sequence

from elysium.theme import Color, current_theme, with_alpha, lighten, mix
from elysium.components import Component, TextField, _rounded_rect


# ===========================================================================
# Columns + model
# ===========================================================================

@dataclass
class Column:
    key: str
    title: str = ""
    width: float = 120.0
    align: str = "left"          # left | right | center
    sortable: bool = True
    filterable: bool = True
    editable: bool = False
    delegate: Optional["Delegate"] = None

    def __post_init__(self) -> None:
        if not self.title:
            self.title = self.key.replace("_", " ").title()


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _set(row: Any, key: str, value: Any) -> None:
    if isinstance(row, dict):
        row[key] = value
    else:
        setattr(row, key, value)


class ItemModel:
    """A list of row records (dicts or objects) + column metadata. Derives a
    sorted/filtered *view* lazily and version-stamps every mutation so views
    know when to rebuild. Pair with reactive ``signal`` in app code if you
    want push updates; the views themselves poll per frame."""

    def __init__(self, rows: Optional[Sequence[Any]] = None,
                 columns: Optional[Sequence[Column]] = None) -> None:
        self._rows: list[Any] = list(rows or [])
        self.columns: list[Column] = list(columns or [])
        self._sort_key: Optional[str] = None
        self._sort_reverse: bool = False
        self._filter: Optional[Callable[[Any], bool]] = None
        self._version: int = 0
        self._view_cache: Optional[list[Any]] = None
        self._view_version: int = -1
        self._on_change: list[Callable[[], None]] = []

    # -- change tracking ----------------------------------------------------

    def on_change(self, fn: Callable[[], None]) -> None:
        self._on_change.append(fn)

    def _bump(self) -> None:
        self._version += 1
        for fn in self._on_change:
            try: fn()
            except Exception: pass

    @property
    def version(self) -> int:
        return self._version

    # -- source mutations ---------------------------------------------------

    def set_rows(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows); self._bump()

    def rows(self) -> list[Any]:
        """The source rows in insertion order (unsorted, unfiltered). Use
        :meth:`view` for the sorted/filtered display order."""
        return list(self._rows)

    def append(self, row: Any) -> None:
        self._rows.append(row); self._bump()

    def insert(self, index: int, row: Any) -> None:
        self._rows.insert(index, row); self._bump()

    def remove(self, row: Any) -> None:
        try:
            self._rows.remove(row); self._bump()
        except ValueError:
            pass

    def remove_at(self, source_index: int) -> None:
        if 0 <= source_index < len(self._rows):
            del self._rows[source_index]; self._bump()

    def update_at(self, source_index: int, key: str, value: Any) -> None:
        if 0 <= source_index < len(self._rows):
            _set(self._rows[source_index], key, value); self._bump()

    def clear(self) -> None:
        self._rows.clear(); self._bump()

    # -- sort / filter ------------------------------------------------------

    def sort(self, key: str, reverse: bool = False) -> None:
        self._sort_key = key; self._sort_reverse = reverse; self._bump()

    def toggle_sort(self, key: str) -> None:
        """Cycle a column: asc → desc → unsorted."""
        if self._sort_key != key:
            self._sort_key, self._sort_reverse = key, False
        elif not self._sort_reverse:
            self._sort_reverse = True
        else:
            self._sort_key = None
        self._bump()

    @property
    def sort_state(self) -> tuple[Optional[str], bool]:
        return (self._sort_key, self._sort_reverse)

    def clear_sort(self) -> None:
        self._sort_key = None; self._bump()

    def filter(self, predicate: Optional[Callable[[Any], bool]]) -> None:
        self._filter = predicate; self._bump()

    # -- derived view -------------------------------------------------------

    def view(self) -> list[Any]:
        if self._view_version != self._version:
            rows = self._rows
            if self._filter is not None:
                rows = [r for r in rows if self._filter(r)]
            if self._sort_key is not None:
                key = self._sort_key
                rows = sorted(
                    rows,
                    key=lambda r: (_get(r, key) is None, _sort_key_val(_get(r, key))),
                    reverse=self._sort_reverse,
                )
            self._view_cache = list(rows)
            self._view_version = self._version
        return self._view_cache  # type: ignore[return-value]

    def row_count(self) -> int:
        return len(self.view())

    def value(self, view_index: int, key: str) -> Any:
        v = self.view()
        if 0 <= view_index < len(v):
            return _get(v[view_index], key)
        return None

    def set_value(self, view_index: int, key: str, value: Any) -> None:
        v = self.view()
        if 0 <= view_index < len(v):
            _set(v[view_index], key, value)
            self._bump()


def _sort_key_val(v: Any) -> Any:
    """Make heterogeneous values *totally* orderable by returning a
    ``(type_rank, value)`` tuple, so a column mixing numbers, strings, and
    None never raises ``TypeError`` on comparison. Numbers (rank 1) sort
    numerically and before strings (rank 2); None (handled by the caller's
    is-None flag) ranks lowest."""
    if v is None:
        return (0, 0.0)
    if isinstance(v, (int, float, bool)):
        return (1, float(v))
    return (2, str(v).lower())


class QtItemModelAdapter:
    """QAbstractItemModel-shaped facade over an :class:`ItemModel`, for
    developers porting from PySide6/Qt. Roles mirror Qt's ints
    (DisplayRole=0, EditRole=2)."""

    DisplayRole = 0
    EditRole = 2

    def __init__(self, model: ItemModel) -> None:
        self._m = model

    def rowCount(self) -> int:
        return self._m.row_count()

    def columnCount(self) -> int:
        return len(self._m.columns)

    def headerData(self, section: int) -> str:
        cols = self._m.columns
        return cols[section].title if 0 <= section < len(cols) else ""

    def index(self, row: int, column: int) -> tuple[int, int]:
        return (row, column)

    def parent(self, index: tuple[int, int]) -> None:
        return None  # flat model

    def data(self, index: tuple[int, int], role: int = DisplayRole) -> Any:
        row, col = index
        cols = self._m.columns
        if not (0 <= col < len(cols)):
            return None
        return self._m.value(row, cols[col].key)

    def setData(self, index: tuple[int, int], value: Any,
                role: int = EditRole) -> bool:
        row, col = index
        cols = self._m.columns
        if not (0 <= col < len(cols)) or not cols[col].editable:
            return False
        self._m.set_value(row, cols[col].key, value)
        return True

    def flags(self, index: tuple[int, int]) -> dict:
        _, col = index
        cols = self._m.columns
        editable = 0 <= col < len(cols) and cols[col].editable
        return {"editable": editable, "selectable": True, "enabled": True}


# ===========================================================================
# Delegates
# ===========================================================================

class Delegate(Protocol):
    def paint(self, dl: Any, rect: tuple[float, float, float, float],
              value: Any, *, selected: bool, theme: Any) -> None: ...

    def editable(self) -> bool: ...


@dataclass
class TextDelegate:
    align: str = "left"

    def editable(self) -> bool:
        return False

    def paint(self, dl, rect, value, *, selected, theme) -> None:
        x, y, w, h = rect
        s = "" if value is None else str(value)
        size = theme.font_size_body
        col = theme.on_surface if selected else with_alpha(theme.on_surface, 0.9)
        tw = len(s) * size * 0.55
        if self.align == "right":
            tx = x + w - 8 - tw
        elif self.align == "center":
            tx = x + (w - tw) / 2.0
        else:
            tx = x + 8
        dl.draw_text(s, tx, y + h * 0.66, size, col)


@dataclass
class EditableCellDelegate(TextDelegate):
    """Same rendering as TextDelegate, but the view may swap in a TextField
    editor when the cell is double-clicked / Enter-activated."""

    def editable(self) -> bool:
        return True

    def make_editor(self, value: Any) -> TextField:
        return TextField(value="" if value is None else str(value),
                         focus_id="cell_editor")


@dataclass
class Mesh3DDelegate:
    """Differentiator: render a small GPU 3-D thumbnail per cell. The cell
    value is a mesh spec (path or library name); we render it once via the
    PBR engine and cache the PNG, falling back to a colored chip while it
    loads / if rendering is unavailable. Lets a data table show real 3-D
    previews — impossible in Qt's item views without a custom OpenGL widget."""
    size: int = 0  # 0 → fill cell height

    _cache: dict = field(default_factory=dict, init=False, repr=False)

    def editable(self) -> bool:
        return False

    def paint(self, dl, rect, value, *, selected, theme) -> None:
        x, y, w, h = rect
        side = self.size or (h - 6)
        cx, cy = x + 6, y + (h - side) / 2.0
        png = self._thumbnail(value, int(side))
        if png:
            try:
                dl.draw_image_file(png, cx, cy, side, side)
                return
            except Exception:
                pass
        # Fallback chip.
        dl.fill_path(_rounded_rect(cx, cy, side, side, 4),
                     with_alpha(theme.accent, 0.5))

    def _thumbnail(self, value: Any, side: int) -> Optional[str]:
        if not value:
            return None
        key = (str(value), side)
        if key in self._cache:
            return self._cache[key]
        path = None
        try:
            from elysium.render import pbr as _pbr
            import tempfile, hashlib, os
            if str(value).startswith("file:"):
                mesh = _pbr.import_mesh_from_file(str(value).split(":", 1)[1])
            else:
                fac = _pbr.MESH_LIBRARY.get(str(value))
                mesh = fac() if fac else None
            if mesh is not None:
                mat = _pbr.Material()
                obj = _pbr.MeshObject(mesh=mesh, materials=[mat])
                env = _pbr.to_environment(_pbr.STUDIOS["Default Soft Studio"])
                rgba = _pbr.render_mesh(side, side, obj, env, transparent_bg=True)
                png_bytes = _pbr.rgba_to_png(rgba, side, side)
                d = os.path.join(tempfile.gettempdir(), "elysium-mv-thumbs")
                os.makedirs(d, exist_ok=True)
                hx = hashlib.md5(repr(key).encode()).hexdigest()[:10]
                path = os.path.join(d, f"{hx}-{side}.png")
                if not os.path.exists(path):
                    with open(path, "wb") as f:
                        f.write(png_bytes)
        except Exception:
            path = None
        self._cache[key] = path
        return path


_DEFAULT_DELEGATE = TextDelegate()


# ===========================================================================
# Views
# ===========================================================================

@dataclass
class TableView(Component):
    """Virtualized, columnar data table over an :class:`ItemModel`. Clickable
    sort headers, horizontal scroll, row selection, and editable cells via an
    :class:`EditableCellDelegate`. Only the rows visible in ``(x,y,w,h)``
    paint."""
    model: ItemModel = None  # type: ignore[assignment]
    row_height: float = 26.0
    header_height: float = 28.0
    show_header: bool = True
    scroll: float = 0.0          # vertical, in rows
    scroll_x: float = 0.0        # horizontal, in px
    selected_row: int = -1       # index into the model's view()
    on_select: Optional[Callable[[int], None]] = None
    on_activate: Optional[Callable[[int], None]] = None
    striped: bool = True

    _editor: Optional[TextField] = field(default=None, init=False, repr=False)
    _edit_cell: tuple[int, int] = field(default=(-1, -1), init=False, repr=False)
    _header_rects: list[tuple[int, tuple]] = field(default_factory=list, init=False, repr=False)
    _resize_key: Optional[str] = field(default=None, init=False, repr=False)

    # -- geometry -----------------------------------------------------------

    def _body_top(self) -> float:
        return self.y + (self.header_height if self.show_header else 0.0)

    def visible_row_range(self) -> tuple[int, int]:
        from elysium.components.virtual import row_window
        n = self.model.row_count() if self.model else 0
        body_h = self.h - (self.header_height if self.show_header else 0)
        return row_window(n, body_h, self.row_height, self.scroll)

    def _col_x(self, col_index: int) -> float:
        x = self.x - self.scroll_x
        for c in self.model.columns[:col_index]:
            x += c.width
        return x

    # -- paint --------------------------------------------------------------

    def paint(self, dl: Any) -> None:
        t = current_theme()
        if self.model is None:
            return
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, t.radius_small), t.surface)
        cols = self.model.columns
        if self.show_header:
            self._paint_header(dl, t, cols)
        # Rows.
        s_start, s_end = self.visible_row_range()
        body_top = self._body_top()
        for vi in range(s_start, s_end):
            yy = body_top + (vi - s_start) * self.row_height
            selected = vi == self.selected_row
            if selected:
                dl.fill_path(_rounded_rect(self.x + 1, yy, self.w - 2, self.row_height - 1, 2),
                             with_alpha(t.primary, 0.20))
            elif self.striped and vi % 2 == 1:
                dl.fill_path(_rounded_rect(self.x + 1, yy, self.w - 2, self.row_height - 1, 0),
                             with_alpha(t.on_surface, 0.04))
            cx = self.x - self.scroll_x
            for col in cols:
                rect = (cx, yy, col.width, self.row_height)
                # skip cells fully outside the viewport horizontally
                if cx + col.width >= self.x and cx <= self.x + self.w:
                    if not (self._editor is not None and self._edit_cell == (vi, cols.index(col))):
                        val = self.model.value(vi, col.key)
                        deleg = col.delegate or _DEFAULT_DELEGATE
                        deleg.paint(dl, rect, val, selected=selected, theme=t)
                cx += col.width
        # Active inline editor on top.
        if self._editor is not None:
            self._editor.paint(dl)

    def _paint_header(self, dl, t, cols) -> None:
        self._header_rects = []
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.header_height, t.radius_small),
                     lighten(t.surface, 0.03))
        sk, srev = self.model.sort_state
        cx = self.x - self.scroll_x
        for ci, col in enumerate(cols):
            self._header_rects.append((ci, (cx, self.y, col.width, self.header_height)))
            label = col.title
            if sk == col.key:
                label += "  ▾" if srev else "  ▴"
            dl.draw_text(label, cx + 8, self.y + self.header_height * 0.66,
                         t.font_size_caption, with_alpha(t.on_surface, 0.9))
            cx += col.width
        dl.fill_path(_rounded_rect(self.x, self.y + self.header_height - 1, self.w, 1, 0),
                     with_alpha(t.edge, 0.6))

    # -- hit testing / interaction -----------------------------------------

    def row_at(self, my: float) -> int:
        body_top = self._body_top()
        if my < body_top:
            return -1
        s_start, _ = self.visible_row_range()
        vi = s_start + int((my - body_top) // self.row_height)
        return vi if 0 <= vi < self.model.row_count() else -1

    def col_at(self, mx: float) -> int:
        cx = self.x - self.scroll_x
        for ci, col in enumerate(self.model.columns):
            if cx <= mx < cx + col.width:
                return ci
            cx += col.width
        return -1

    # -- column resize ------------------------------------------------------

    def header_border_at(self, mx: float, my: float, grab: float = 4.0) -> Optional[str]:
        """The column key whose right header border is under ``mx`` (a resize
        target), or None. Only within the header band."""
        if self.model is None or not self.show_header:
            return None
        if not (self.y <= my <= self.y + self.header_height):
            return None
        cx = self.x - self.scroll_x
        for col in self.model.columns:
            cx += col.width
            if abs(mx - cx) <= grab:
                return col.key
        return None

    def resize_col(self, key: str, width: float) -> None:
        """Set column ``key``'s width, clamped to a sensible minimum (40px)."""
        if self.model is None:
            return
        for c in self.model.columns:
            if c.key == key:
                c.width = max(40.0, float(width))
                return

    def cursor_at(self, mx: float, my: float, grab: float = 4.0) -> Optional[str]:
        """``"ew-resize"`` — the horizontal double-arrow (↔) resize affordance —
        over a column-header border, or while a resize is in progress; else
        ``None``. Coordinates are window-local (the same space as
        ``win.cursor_position`` and the view's ``x``/``y``); apply it each frame,
        e.g. ``win.set_cursor(table.cursor_at(*win.cursor_position) or "default")``."""
        if self._resize_key is not None:
            return "ew-resize"
        if self.header_border_at(mx, my, grab) is not None:
            return "ew-resize"
        return None

    def on_mouse_press(self, mx: float, my: float, *, double: bool = False) -> bool:
        if self.model is None:
            return False
        # A header border grabs a column resize (takes priority over sort).
        border = self.header_border_at(mx, my)
        if border is not None:
            self._resize_key = border
            return True
        # Header click → sort.
        if self.show_header and self.y <= my <= self.y + self.header_height:
            for ci, (hx, hy, hw, hh) in self._header_rects:
                if hx <= mx <= hx + hw and self.model.columns[ci].sortable:
                    self.model.toggle_sort(self.model.columns[ci].key)
                    return True
            return True
        row = self.row_at(my)
        if row < 0:
            return False
        self.selected_row = row
        if self.on_select:
            try: self.on_select(row)
            except Exception: pass
        col = self.col_at(mx)
        if double and col >= 0 and self.model.columns[col].editable:
            self.begin_edit(row, col)
        elif double and self.on_activate:
            try: self.on_activate(row)
            except Exception: pass
        return True

    def on_mouse_drag(self, mx: float, my: float) -> None:
        """Continue an in-progress column resize; no-op otherwise, so an app can
        forward every drag here safely. Pairs with :meth:`on_mouse_release`."""
        if self._resize_key is None or self.model is None:
            return
        cols = self.model.columns
        j = next((i for i, c in enumerate(cols) if c.key == self._resize_key), None)
        if j is not None:
            self.resize_col(self._resize_key, mx - self._col_x(j))

    def on_mouse_release(self) -> None:
        """End a column resize (drop the grabbed header border)."""
        self._resize_key = None

    # -- inline editing -----------------------------------------------------

    def begin_edit(self, row: int, col: int) -> Optional[TextField]:
        cols = self.model.columns
        if not (0 <= col < len(cols)) or not cols[col].editable:
            return None
        deleg = cols[col].delegate
        val = self.model.value(row, cols[col].key)
        ed = deleg.make_editor(val) if isinstance(deleg, EditableCellDelegate) \
            else TextField(value="" if val is None else str(val), focus_id="cell_editor")
        # Position over the cell.
        body_top = self._body_top()
        s_start, _ = self.visible_row_range()
        ed.x = self._col_x(col)
        ed.y = body_top + (row - s_start) * self.row_height
        ed.w = cols[col].width
        ed.h = self.row_height
        ed._focus_t = 1.0
        self._editor = ed
        self._edit_cell = (row, col)
        return ed

    def commit_edit(self) -> None:
        if self._editor is None:
            return
        row, col = self._edit_cell
        cols = self.model.columns
        self.model.set_value(row, cols[col].key, self._editor.value)
        self._editor = None
        self._edit_cell = (-1, -1)

    def cancel_edit(self) -> None:
        self._editor = None
        self._edit_cell = (-1, -1)

    @property
    def editing(self) -> bool:
        return self._editor is not None


@dataclass
class ListView(TableView):
    """Single-column virtualized list. Convenience over TableView with one
    column and no header."""
    label_key: str = "label"

    def __post_init__(self) -> None:
        if self.model is not None and not self.model.columns:
            self.model.columns = [Column(self.label_key, title="", width=self.w, sortable=False)]
        self.show_header = False


@dataclass
class TreeView(Component):
    """Virtualized hierarchical view. Rows are supplied pre-flattened with a
    ``depth`` (like the existing Tree), built from a nested model via
    :func:`flatten_tree`. Reuses the row-range virtualization pattern."""
    nodes: list["TreeNode"] = field(default_factory=list)
    row_height: float = 24.0
    indent: float = 16.0
    scroll: float = 0.0
    selected_id: str = ""
    on_select: Optional[Callable[[str], None]] = None
    on_toggle: Optional[Callable[[str], None]] = None

    _flat: list[tuple] = field(default_factory=list, init=False, repr=False)

    def _flatten(self) -> list[tuple]:
        out: list[tuple] = []

        def walk(node: "TreeNode", depth: int) -> None:
            out.append((node, depth))
            if node.expanded:
                for c in node.children:
                    walk(c, depth + 1)

        for n in self.nodes:
            walk(n, 0)
        return out

    def visible_row_range(self, total: int) -> tuple[int, int]:
        from elysium.components.virtual import row_window
        return row_window(total, self.h, self.row_height, self.scroll)

    def paint(self, dl: Any) -> None:
        t = current_theme()
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, t.radius_small), t.surface)
        self._flat = self._flatten()
        s_start, s_end = self.visible_row_range(len(self._flat))
        for i in range(s_start, s_end):
            node, depth = self._flat[i]
            yy = self.y + (i - s_start) * self.row_height
            if node.id == self.selected_id:
                dl.fill_path(_rounded_rect(self.x + 2, yy, self.w - 4, self.row_height - 1, 3),
                             with_alpha(t.primary, 0.18))
            x0 = self.x + 8 + depth * self.indent
            if node.children:
                cx, cy = x0 + 6, yy + self.row_height / 2
                d = (f"M {cx-4} {cy-2} L {cx+4} {cy-2} L {cx} {cy+3} Z" if node.expanded
                     else f"M {cx-2} {cy-4} L {cx+3} {cy} L {cx-2} {cy+4} Z")
                dl.fill_path(d, t.on_surface)
                x0 += 16
            dl.draw_text(node.label, x0, yy + self.row_height * 0.7,
                         t.font_size_body, t.on_surface)

    def hit(self, mx: float, my: float) -> Optional[tuple[str, str]]:
        if not (self.x <= mx <= self.x + self.w and self.y <= my):
            return None
        idx = int((my - self.y) // self.row_height) + max(0, int(self.scroll))
        if not (0 <= idx < len(self._flat)):
            return None
        node, depth = self._flat[idx]
        x0 = self.x + 8 + depth * self.indent
        kind = "chevron" if (node.children and mx < x0 + 16) else "label"
        if kind == "chevron":
            node.expanded = not node.expanded
            if self.on_toggle:
                try: self.on_toggle(node.id)
                except Exception: pass
        else:
            self.selected_id = node.id
            if self.on_select:
                try: self.on_select(node.id)
                except Exception: pass
        return (node.id, kind)


@dataclass
class TreeNode:
    id: str
    label: str
    children: list["TreeNode"] = field(default_factory=list)
    expanded: bool = False
    user_data: Any = None


__all__ = [
    "Column", "ItemModel", "QtItemModelAdapter",
    "Delegate", "TextDelegate", "EditableCellDelegate", "Mesh3DDelegate",
    "TableView", "ListView", "TreeView", "TreeNode",
]
