"""Layout primitives. The single biggest API gap relative to Qt.

`Stack(direction, spacing, padding, align, justify)` is the workhorse —
all other layouts (`Row`, `Col`, `Grid`, `Form`) compose from it.

    from elysium import layout
    root = layout.Col(spacing=12, padding=16, children=[
        ui.Label(text="Account"),
        layout.Row(spacing=8, children=[
            ui.TextField(w=240),
            ui.Button(label="Save"),
        ]),
    ])
    root.layout(x=0, y=0, w=app_w, h=app_h)
    root.paint(dl)

Components stay absolute-positioned internally; the layout containers
reposition them by mutating `x/y/w/h` during `layout()`. That keeps the
runtime painter simple (no second pass) while letting authors describe
intent declaratively.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# Alignment constants
START, CENTER, END, STRETCH = "start", "center", "end", "stretch"
SPACE_BETWEEN, SPACE_AROUND, SPACE_EVENLY = "between", "around", "evenly"

ROW, COL, GRID = "row", "col", "grid"


@dataclass
class Stack:
    """A flex-box-ish container.

    direction : 'row' | 'col'
    spacing   : pixels between children
    padding   : (top, right, bottom, left) or scalar
    align     : 'start' | 'center' | 'end' | 'stretch' — cross-axis
    justify   : 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly'
                — main-axis distribution
    grow      : per-child flex weights, list[float] (defaults to all-zero)
    """
    direction: str = COL
    spacing:   float = 8.0
    padding:   tuple[float, float, float, float] | float = 12.0
    align:     str = START
    justify:   str = START
    grow:      list[float] = field(default_factory=list)
    children:  list[Any] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    def _pads(self) -> tuple[float, float, float, float]:
        p = self.padding
        if isinstance(p, (int, float)):
            return (p, p, p, p)
        if len(p) == 2:
            return (p[0], p[1], p[0], p[1])
        return tuple(p)         # type: ignore[return-value]

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h
        pt, pr, pb, pl = self._pads()
        inner_x = x + pl
        inner_y = y + pt
        inner_w = max(0.0, w - pl - pr)
        inner_h = max(0.0, h - pt - pb)

        if not self.children:
            return

        is_row = self.direction == ROW
        main_total = inner_w if is_row else inner_h
        cross_total = inner_h if is_row else inner_w
        gap_total = self.spacing * (len(self.children) - 1)

        # Compute natural main-axis size of each child (its current w or h).
        nat = [(c.w if is_row else c.h) for c in self.children]
        nat_sum = sum(nat)

        # Distribute leftover space among flex-grow children.
        grow = list(self.grow) + [0.0] * (len(self.children) - len(self.grow))
        grow_total = sum(grow)
        leftover = main_total - gap_total - nat_sum
        sizes = list(nat)
        if grow_total > 0 and leftover > 0:
            for i, g in enumerate(grow):
                sizes[i] += leftover * (g / grow_total)
        used = sum(sizes) + gap_total

        # Justify (main-axis offset + extra spacing).
        offset = 0.0
        extra_gap = 0.0
        free = main_total - used
        if free > 0:
            if   self.justify == CENTER:  offset = free / 2
            elif self.justify == END:     offset = free
            elif self.justify == SPACE_BETWEEN and len(self.children) > 1:
                extra_gap = free / (len(self.children) - 1)
            elif self.justify == SPACE_AROUND:
                extra_gap = free / len(self.children)
                offset = extra_gap / 2
            elif self.justify == SPACE_EVENLY:
                extra_gap = free / (len(self.children) + 1)
                offset = extra_gap

        cursor = (inner_x if is_row else inner_y) + offset
        for i, child in enumerate(self.children):
            s = sizes[i]
            # Cross-axis sizing + alignment.
            cross_nat = child.h if is_row else child.w
            if self.align == STRETCH:
                cross = cross_total
            else:
                cross = cross_nat
            if   self.align == CENTER: cross_offset = (cross_total - cross) / 2
            elif self.align == END:    cross_offset = cross_total - cross
            else:                      cross_offset = 0.0

            if is_row:
                child.x = cursor
                child.y = inner_y + cross_offset
                child.w = s
                child.h = cross
            else:
                child.x = inner_x + cross_offset
                child.y = cursor
                child.w = cross
                child.h = s
            if hasattr(child, "layout") and not isinstance(child, Stack):
                # Some children may be Stacks themselves; only call layout on
                # nested layout containers, not on regular Components.
                pass
            if isinstance(child, Stack):
                child.layout(child.x, child.y, child.w, child.h)
            cursor += s + self.spacing + extra_gap

    def paint(self, dl: Any) -> None:
        for c in self.children:
            if hasattr(c, "update"):
                # Light per-frame tick so animation states converge.
                try: c.update(0.016, {})
                except TypeError: pass
            c.paint(dl)

    def hit_test(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h


def Row(spacing: float = 8.0, padding: float | tuple = 0.0,
        align: str = CENTER, justify: str = START,
        grow: list[float] | None = None,
        children: Iterable[Any] = ()) -> Stack:
    return Stack(direction=ROW, spacing=spacing, padding=padding,
                 align=align, justify=justify,
                 grow=list(grow or []), children=list(children))


def Col(spacing: float = 8.0, padding: float | tuple = 0.0,
        align: str = STRETCH, justify: str = START,
        grow: list[float] | None = None,
        children: Iterable[Any] = ()) -> Stack:
    return Stack(direction=COL, spacing=spacing, padding=padding,
                 align=align, justify=justify,
                 grow=list(grow or []), children=list(children))


@dataclass
class Grid:
    """Uniform grid: `cols` columns, evenly-spaced cells. Children flow
    left-to-right, top-to-bottom."""
    cols: int = 2
    gap_x: float = 8.0
    gap_y: float = 8.0
    padding: float | tuple = 0.0
    children: list[Any] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    def _pads(self) -> tuple[float, float, float, float]:
        p = self.padding
        if isinstance(p, (int, float)): return (p, p, p, p)
        if len(p) == 2: return (p[0], p[1], p[0], p[1])
        return tuple(p)             # type: ignore[return-value]

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h
        pt, pr, pb, pl = self._pads()
        inner_x = x + pl; inner_y = y + pt
        inner_w = max(0.0, w - pl - pr)
        rows = (len(self.children) + self.cols - 1) // max(1, self.cols)
        cell_w = (inner_w - self.gap_x * (self.cols - 1)) / max(1, self.cols)
        # Cell height matches each child's existing h (uniform rows).
        for i, c in enumerate(self.children):
            row = i // self.cols
            col = i % self.cols
            c.x = inner_x + col * (cell_w + self.gap_x)
            c.y = inner_y + row * (c.h + self.gap_y)
            c.w = cell_w
            if isinstance(c, (Stack, Grid)):
                c.layout(c.x, c.y, c.w, c.h)

    def paint(self, dl: Any) -> None:
        for c in self.children:
            if hasattr(c, "update"):
                try: c.update(0.016, {})
                except TypeError: pass
            c.paint(dl)


def Form(spacing: float = 8.0, label_w: float = 120.0,
         padding: float | tuple = 0.0,
         rows: Iterable[tuple[Any, Any]] = ()) -> Stack:
    """Label / field rows. Each row is a `Row` with a fixed-width label."""
    return Col(spacing=spacing, padding=padding, children=[
        Row(spacing=8.0, align=CENTER, children=[lbl, field])
        for (lbl, field) in rows
    ])


__all__ = [
    "Stack", "Grid", "Row", "Col", "Form",
    "ROW", "COL", "GRID",
    "START", "CENTER", "END", "STRETCH",
    "SPACE_BETWEEN", "SPACE_AROUND", "SPACE_EVENLY",
]
