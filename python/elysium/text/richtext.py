"""Rich text — styled-run documents (Qt's ``QTextDocument`` + a view widget).

A :class:`RichDocument` is a sequence of styled :class:`Run`\\ s (bold / italic /
size / colour / family / underline / hyperlink) and inline :class:`Image`\\ s,
with paragraph :class:`Break`\\ s. :meth:`RichDocument.layout` word-wraps them to
a width into baseline-aligned placements; :class:`RichTextView` renders a
document and hit-tests hyperlinks.

Layout uses the native ``measure_text_run`` (advance + ascent/descent) for
metrics and renders each run through the Skia paragraph path
(``draw_paragraph``), so bold (weight) and italic (a slant variation axis) are
real font styling, not faux effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from elysium.theme import Color, current_theme, with_alpha

__all__ = [
    "Run",
    "Image",
    "Break",
    "RichDocument",
    "RichTextView",
    "Placement",
]


@dataclass
class Run:
    """A styled span of text."""
    text: str = ""
    bold: bool = False
    italic: bool = False
    size: float | None = None
    color: Color | None = None
    family: str = ""
    underline: bool = False
    link: str | None = None


@dataclass
class Image:
    """An inline image (a ``path`` to decode, or just a sized placeholder)."""
    path: str | None = None
    w: float = 0.0
    h: float = 0.0
    link: str | None = None


class Break:
    """A hard paragraph break."""
    __slots__ = ()


@dataclass
class Placement:
    """A laid-out run/image fragment in document coordinates (relative to the
    document origin). ``baseline`` is the text baseline y."""
    kind: str               # "text" | "image"
    x: float
    y: float                # top
    w: float
    h: float
    baseline: float
    text: str = ""
    run: Any = None         # the source Run or Image
    link: str | None = None


def _measure(text: str, size: float) -> tuple[float, float, float]:
    from elysium._native import _native as _n
    return _n.measure_text_run(text, size)


@dataclass
class RichDocument:
    """An ordered list of ``Run`` / ``Image`` / ``Break`` items."""

    items: list[Any] = field(default_factory=list)
    default_size: float = 15.0
    default_color: Color | None = None
    line_leading: float = 1.3   # line-height multiplier

    def add(self, item: Any) -> "RichDocument":
        self.items.append(item)
        return self

    def add_text(self, text: str, **style) -> "RichDocument":
        return self.add(Run(text=text, **style))

    # --- layout -----------------------------------------------------------

    def _tokens(self, run: Run):
        """Split a run into words + single spaces, preserving spacing."""
        parts = run.text.split(" ")
        for i, word in enumerate(parts):
            if word:
                yield word
            if i < len(parts) - 1:
                yield " "

    def layout(self, width: float) -> tuple[list[Placement], float]:
        """Word-wrap to ``width``. Returns ``(placements, total_height)`` in
        document coordinates (origin at 0, 0). Each placement carries its own
        ascent in ``_asc`` so the second (baseline) pass aligns mixed sizes."""
        placements: list[Placement] = []
        line: list[Placement] = []
        x = 0.0
        top = 0.0

        def flush_line(force_height: float = 0.0) -> None:
            nonlocal x, top
            if not line:
                top += force_height
                x = 0.0
                return
            max_asc = max(p._asc for p in line)
            max_desc = max(p.h - p._asc for p in line)
            line_h = max(force_height, (max_asc + max_desc) * self.line_leading)
            baseline = top + max_asc
            for p in line:
                p.baseline = baseline
                p.y = baseline - p._asc
            placements.extend(line)
            line.clear()
            x = 0.0
            top += line_h

        for item in self.items:
            if isinstance(item, Break):
                flush_line(force_height=self.default_size * self.line_leading)
                continue
            if isinstance(item, Image):
                if x + item.w > width and line:
                    flush_line()
                p = Placement(kind="image", x=x, y=top, w=item.w, h=item.h,
                              baseline=top + item.h, run=item, link=item.link)
                p._asc = item.h          # type: ignore[attr-defined]
                line.append(p)
                x += item.w
                continue
            run: Run = item
            size = run.size if run.size is not None else self.default_size
            for tok in self._tokens(run):
                adv, asc, desc = _measure(tok, size)
                if tok != " " and x + adv > width and line:
                    flush_line()
                p = Placement(kind="text", x=x, y=top, w=adv, h=asc + desc,
                              baseline=top, text=tok, run=run, link=run.link)
                p._asc = asc             # type: ignore[attr-defined]
                line.append(p)
                x += adv
        flush_line()
        return placements, top


@dataclass
class RichTextView:
    """Renders a :class:`RichDocument` at ``x/y`` wrapped to ``w``, and
    hit-tests hyperlinks. Set ``on_link`` to handle clicks."""

    document: RichDocument = field(default_factory=RichDocument)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    on_link: Callable[[str], None] | None = None
    _placements: list[Placement] = field(default_factory=list, init=False)
    _content_h: float = field(default=0.0, init=False)

    def relayout(self) -> float:
        self._placements, self._content_h = self.document.layout(self.w)
        return self._content_h

    def content_height(self) -> float:
        if not self._placements:
            self.relayout()
        return self._content_h

    def link_at(self, mx: float, my: float) -> str | None:
        lx, ly = mx - self.x, my - self.y
        for p in self._placements:
            if p.link and p.x <= lx <= p.x + p.w and p.y <= ly <= p.y + p.h:
                return p.link
        return None

    def on_click(self, mx: float, my: float) -> bool:
        link = self.link_at(mx, my)
        if link is not None:
            if self.on_link is not None:
                self.on_link(link)
            return True
        return False

    def paint(self, dl: Any) -> None:
        t = current_theme()
        self.relayout()
        for p in self._placements:
            if p.kind == "image":
                if p.run.path:
                    dl.draw_image_file(p.run.path, self.x + p.x, self.y + p.y,
                                       p.w, p.h)
                else:
                    from elysium.components import _rounded_rect
                    dl.fill_path(_rounded_rect(self.x + p.x, self.y + p.y,
                                               p.w, p.h, 4),
                                 with_alpha(t.surface_variant, 1.0))
                continue
            run: Run = p.run
            size = run.size if run.size is not None else self.document.default_size
            if run.link is not None:
                color = t.primary
            elif run.color is not None:
                color = run.color
            elif self.document.default_color is not None:
                color = self.document.default_color
            else:
                color = t.on_surface
            weight = 700 if run.bold else 400
            axes = [("slnt", -10.0)] if run.italic else []
            dl.draw_paragraph(p.text, self.x + p.x, self.y + p.y, p.w + 4,
                              size, color, 0, run.family, weight, axes, False)
            if run.underline or run.link is not None:
                uy = self.y + p.baseline + 2
                dl.stroke_path(
                    f"M {self.x + p.x} {uy} L {self.x + p.x + p.w} {uy}",
                    with_alpha(color, 0.8), 1.0)
