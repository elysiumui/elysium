"""Phase 2.5 component library — premium-quality defaults.

Every component:
  • reads colours + radii + shadows + motion rates from `current_theme()`
  • smoothly interpolates `hover` / `pressed` / `focused` progress (no
    discrete colour swaps)
  • paints through layered shadow + gradient + body + highlight passes
  • renders a focus ring in addition to hover lift on focused components

Wiring:

    btn = Button(x=100, y=100, w=120, h=40, label="Play",
                 on_click=lambda: ...)

    # In the per-frame loop:
    state = {"hover": btn.hit_test(*cursor) if cursor else False,
             "pressed": pressed and btn.hit_test(*cursor),
             "focused": focused_widget is btn}
    btn.update(dt, state)
    btn.paint(dl)
    if click_just_fired and btn.hit_test(*cursor):
        btn.fire_click()
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict

from elysium.theme import Color, Shadow, Theme, current_theme, mix, with_alpha, lighten


# Native text-shaping primitives (caret geometry / hit-testing) used by the
# editable text widgets. Imported lazily + guarded so the component library
# still imports when the native extension isn't built (tests, docs); a
# proportional-font estimate stands in so logic stays exercisable.
def _shaping():
    mod = getattr(_shaping, "_mod", "unset")
    if mod == "unset":
        try:
            from elysium._native import _native as _n
            mod = _n if hasattr(_n, "text_caret_x") else None
        except Exception:
            mod = None
        _shaping._mod = mod
    return mod


def _caret_x(text: str, size: float, index: int) -> float:
    n = _shaping()
    if n is not None:
        return float(n.text_caret_x(text, size, index))
    return len(text[:index]) * size * 0.55  # fallback estimate


def _hit_index(text: str, size: float, px: float) -> int:
    n = _shaping()
    if n is not None:
        return int(n.text_hit_index(text, size, max(0.0, px)))
    # Fallback: nearest by uniform-width estimate.
    if px <= 0:
        return 0
    return min(len(text), int(round(px / (size * 0.55))))


class ComponentState(TypedDict, total=False):
    hover:    bool
    pressed:  bool
    focused:  bool
    disabled: bool


def _rounded_rect(x: float, y: float, w: float, h: float, r: float) -> str:
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    return (
        f"M {x + r} {y} "
        f"L {x + w - r} {y} Q {x + w} {y} {x + w} {y + r} "
        f"L {x + w} {y + h - r} Q {x + w} {y + h} {x + w - r} {y + h} "
        f"L {x + r} {y + h} Q {x} {y + h} {x} {y + h - r} "
        f"L {x} {y + r} Q {x} {y} {x + r} {y} Z"
    )


def _circle(cx: float, cy: float, r: float) -> str:
    return (
        f"M {cx} {cy} m {-r} 0 "
        f"a {r} {r} 0 1 0 {2*r} 0 "
        f"a {r} {r} 0 1 0 {-2*r} 0 Z"
    )


def _layered_shadow(dl, x, y, w, h, radius, near: Shadow, far: Shadow) -> None:
    """Two-pass shadow: tight close-shadow + soft wide shadow."""
    # Wide / soft / far.
    fx, fy = far.offset
    dl.gradient_card(
        x + fx, y + fy, w, h, radius,
        far.color, far.color,
        far.blur, (0.0, 0.0),
        (0, 0, 0, 0),  # gradient_card draws shadow internally already
    )
    # Close / tight.
    nx, ny = near.offset
    dl.gradient_card(
        x + nx, y + ny, w, h, radius,
        near.color, near.color,
        near.blur, (0.0, 0.0),
        (0, 0, 0, 0),
    )


# ---------------------------------------------------------------------------
# Base component with smoothly-animated states.
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """Subclasses override `paint(dl)`. The host calls `update(dt, state)`
    each frame before paint."""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    _hover_t:    float = field(default=0.0, init=False, repr=False)
    _press_t:    float = field(default=0.0, init=False, repr=False)
    _focus_t:    float = field(default=0.0, init=False, repr=False)
    _disabled_t: float = field(default=0.0, init=False, repr=False)

    def hit_test(self, mx: float, my: float) -> bool:
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def update(self, dt: float, state: ComponentState) -> None:
        """Tick the smooth state-progress values toward their targets."""
        motion = current_theme().motion
        targets = (
            (1.0 if state.get("hover")    else 0.0, "_hover_t",    "hover_rate"),
            (1.0 if state.get("pressed")  else 0.0, "_press_t",    "press_rate"),
            (1.0 if state.get("focused")  else 0.0, "_focus_t",    "focus_rate"),
            (1.0 if state.get("disabled") else 0.0, "_disabled_t", "value_rate"),
        )
        for target, attr, rate in targets:
            current = getattr(self, attr)
            setattr(self, attr, motion.step(current, target, dt, rate))

    def paint(self, dl: Any) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Label.
# ---------------------------------------------------------------------------

@dataclass
class Label(Component):
    text: str = ""
    size: float | None = None
    color: Color | None = None
    align: str = "left"
    font_family: str = ""   # per-widget font override (opt-in)
    weight: int = 400       # per-widget font weight
    tabular: bool = False   # tabular (equal-width) numerals for aligned figures

    def paint(self, dl: Any) -> None:
        t = current_theme()
        size  = self.size  if self.size  is not None else t.font_size_body
        color = self.color if self.color is not None else t.on_surface
        approx_w = len(self.text) * size * 0.55
        if self.align == "center":
            tx = self.x + (self.w - approx_w) / 2.0
        elif self.align == "right":
            tx = self.x + self.w - approx_w
        else:
            tx = self.x
        ty = self.y + self.h * 0.7
        # Per-widget font / weight goes through the paragraph path (the only one
        # that takes a family + weight). The default path is unchanged
        # draw_text, so existing golden snapshots don't move.
        if self.font_family or self.weight != 400 or self.tabular:
            from elysium._native import _native as _n
            try:
                _adv, asc, _desc = _n.measure_text_run(self.text or "Ay", size)
            except Exception:
                asc = size * 0.8
            align_i = {"left": 0, "center": 1, "right": 2}.get(self.align, 0)
            box_w = self.w if self.w > 0 else approx_w + 8
            dl.draw_paragraph(self.text, self.x, ty - asc, box_w, size, color,
                              align_i, self.font_family, self.weight, [], False,
                              self.tabular)
        else:
            dl.draw_text(self.text, tx, ty, size, color)


# ---------------------------------------------------------------------------
# Button — solid / outline / ghost / glass variants.
# ---------------------------------------------------------------------------

@dataclass
class Ripple:
    """Material-style click ripple. Lives on a Button after a click; the
    Button ticks `age` each update and removes the ripple when age > 1."""
    x: float
    y: float
    age: float = 0.0
    max_radius: float = 80.0
    color: Color = (255, 255, 255, 200)


@dataclass
class Button(Component):
    label: str = ""
    on_click: Callable[[], None] | None = None
    variant: str = "solid"   # "solid" | "outline" | "ghost" | "glass" | "danger"
    radius: float | None = None
    text_size: float | None = None
    icon: str | None = None    # not yet wired — reserved
    ripples: list[Ripple] = field(default_factory=list)
    ripple_duration: float = 0.45  # seconds
    # Per-instance overrides (None = follow theme).
    fill_color: Color | None = None
    text_color: Color | None = None

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        # Advance + GC ripples.
        if self.ripples:
            for rp in self.ripples:
                rp.age += dt / max(self.ripple_duration, 1e-3)
            self.ripples = [rp for rp in self.ripples if rp.age < 1.0]

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.radius if self.radius is not None else t.radius_medium
        ts = self.text_size if self.text_size is not None else t.font_size_body

        # Smooth animated values. Studio finish: restrained, crisp motion —
        # a subtle lift, not a bounce.
        scale  = 1.0 + 0.012 * self._hover_t - 0.02 * self._press_t
        # Apply scale around the centre by adjusting bbox.
        cw = self.w * scale
        ch = self.h * scale
        cx = self.x + (self.w - cw) / 2.0
        cy = self.y + (self.h - ch) / 2.0

        # 1. Tight drop shadow (a hairline lift on hover, flat on press) — the
        # Studio look is flat-but-tactile, not heavily floated.
        shadow_strength = (1.0 - self._press_t) * (0.55 + 0.35 * self._hover_t)
        shadow_blur = t.shadow_close.blur * (1.0 + 0.6 * self._hover_t)
        shadow_off  = (0.0, 1.5 + 2.0 * self._hover_t - 1.0 * self._press_t)
        shadow_col  = with_alpha(t.shadow_close.color,
                                 (t.shadow_close.color[3] / 255.0) * shadow_strength)

        # 2. Body fill via gradient_card (top→bottom slight darken) +
        # variant-specific colours.
        if self.variant == "solid":
            base = self.fill_color if self.fill_color is not None else t.primary
            top  = lighten(base, 0.08)
            bot  = base
            text_color = self.text_color if self.text_color is not None else t.on_primary
        elif self.variant == "danger":
            base = self.fill_color if self.fill_color is not None else t.danger
            top  = lighten(base, 0.08)
            bot  = base
            text_color = self.text_color if self.text_color is not None else (255, 255, 255, 255)
        elif self.variant == "outline":
            top = bot = (0, 0, 0, 0)
            text_color = self.text_color if self.text_color is not None else t.on_surface
        elif self.variant == "ghost":
            base = self.fill_color if self.fill_color is not None else t.surface_variant
            top = bot = with_alpha(base, 0.0 + 0.10 * self._hover_t)
            text_color = self.text_color if self.text_color is not None else t.on_surface
        elif self.variant == "glass":
            base = self.fill_color if self.fill_color is not None else t.surface_variant
            top = with_alpha(lighten(base, 0.15), 0.55)
            bot = with_alpha(base,                0.40)
            text_color = self.text_color if self.text_color is not None else t.on_surface
        else:
            base = self.fill_color if self.fill_color is not None else t.primary
            top = bot = base
            text_color = self.text_color if self.text_color is not None else t.on_primary

        # Press feel: mix toward darker.
        if self._press_t > 0.01 and self.variant in ("solid", "danger"):
            top = mix(top, (0, 0, 0, top[3]), self._press_t * 0.18)
            bot = mix(bot, (0, 0, 0, bot[3]), self._press_t * 0.18)
        # Hover feel: brighter.
        if self._hover_t > 0.01 and self.variant in ("solid", "danger"):
            top = lighten(top, self._hover_t * 0.06)
            bot = lighten(bot, self._hover_t * 0.06)

        # Layered shadow as a real gradient_card painted below.
        if shadow_col[3] > 0 and self.variant not in ("ghost",):
            dl.gradient_card(
                cx, cy, cw, ch, r,
                top, bot,
                shadow_blur, shadow_off, shadow_col,
            )
        elif top[3] > 0 or bot[3] > 0:
            dl.gradient_card(cx, cy, cw, ch, r, top, bot, 0.0, (0.0, 0.0), (0, 0, 0, 0))

        # 3. Outline (for outline variant) + focus ring.
        if self.variant == "outline":
            border = t.on_surface
            # Outline by drawing a slightly-smaller-radius stroke as path.
            dl.stroke_path(_rounded_rect(cx + 1, cy + 1, cw - 2, ch - 2, max(0, r - 1)),
                           border, 1.5)
        if self._focus_t > 0.01:
            ring = with_alpha(t.accent, 0.4 * self._focus_t)
            dl.stroke_path(_rounded_rect(cx - 2, cy - 2, cw + 4, ch + 4, r + 2),
                           ring, 2.0)

        # 4. Studio finish on filled variants: a subtle top sheen + a crisp
        #    hairline edge for a flat-but-tactile, defined button.
        if self.variant in ("solid", "danger", "glass"):
            highlight_alpha = 0.10 * (1.0 - self._press_t)
            dl.fill_path_linear_gradient(
                _rounded_rect(cx + 1, cy + 1, cw - 2, ch * 0.5, r * 0.9),
                (cx, cy), (cx, cy + ch * 0.5),
                with_alpha((255, 255, 255, 255), highlight_alpha),
                with_alpha((255, 255, 255, 255), 0.0),
            )
            # Hairline edge — light along the top, a touch of shade along the
            # bottom, giving a thin tactile bevel without a heavy border.
            dl.stroke_path(
                _rounded_rect(cx + 0.5, cy + 0.5, cw - 1, ch - 1, r),
                with_alpha((255, 255, 255, 255), 0.10 * (1.0 - self._press_t)), 1.0)

        # 5. Label, centered.
        if self.label:
            approx_w = len(self.label) * ts * 0.55
            tx = cx + (cw - approx_w) / 2.0
            ty = cy + ch * 0.68
            dl.draw_text(self.label, tx, ty, ts,
                         with_alpha(text_color, 1.0 - 0.4 * self._disabled_t))

        # 6. Ripples on top — Material-style expanding circle with fade.
        # We approximate clipping by tapering alpha as the ripple exits
        # the button rect (true path-clip lands in Phase 3 alongside
        # path-aware hit testing).
        for rp in self.ripples:
            # Eased radius: fast at first, settles toward max.
            t_rp = rp.age
            eased = 1.0 - (1.0 - t_rp) ** 2
            radius = rp.max_radius * eased
            alpha = (1.0 - t_rp) * (rp.color[3] / 255.0)
            # Brighten on solid/danger, dim on light variants.
            if self.variant in ("ghost", "outline", "glass"):
                ripple_rgb = t.primary[:3]
            else:
                ripple_rgb = rp.color[:3]
            dl.fill_path(
                _circle(rp.x, rp.y, radius),
                with_alpha((*ripple_rgb, 255), alpha),
            )

    def fire_click(self, click_x: float | None = None, click_y: float | None = None) -> None:
        """Trigger the on_click handler AND spawn a ripple. Optional
        (click_x, click_y) place the ripple at the cursor; defaults to
        the button's centre."""
        if click_x is None: click_x = self.x + self.w / 2.0
        if click_y is None: click_y = self.y + self.h / 2.0
        # Max radius = farthest corner distance — guarantees the ripple
        # covers the whole button before fading.
        corners = [(self.x, self.y), (self.x + self.w, self.y),
                   (self.x, self.y + self.h), (self.x + self.w, self.y + self.h)]
        max_r = max(((cx - click_x) ** 2 + (cy - click_y) ** 2) ** 0.5
                    for cx, cy in corners)
        self.ripples.append(Ripple(x=click_x, y=click_y, max_radius=max_r))
        if self.on_click is not None:
            self.on_click()


@dataclass
class IconCloseButton(Component):
    """Circular close ❌ — used by the butterfly demo. Inherits the
    theme's smooth state interpolation."""
    on_click: Callable[[], None] | None = None
    stroke_width: float = 2.0

    def hit_test(self, mx: float, my: float) -> bool:
        cx = self.x + self.w / 2.0
        cy = self.y + self.h / 2.0
        r  = min(self.w, self.h) / 2.0
        return (mx - cx) ** 2 + (my - cy) ** 2 <= (r + 4) ** 2

    def paint(self, dl: Any) -> None:
        t = current_theme()
        cx = self.x + self.w / 2.0
        cy = self.y + self.h / 2.0
        r  = min(self.w, self.h) / 2.0
        scale = 1.0 + 0.10 * self._hover_t
        r *= scale
        # Backdrop scrim, theme-derived, with smooth opacity / colour mix.
        bg_idle = with_alpha((0, 0, 0), 0.65)
        bg_hover = with_alpha(t.danger, 0.85)
        bg = mix(bg_idle, bg_hover, self._hover_t)
        dl.fill_path(_circle(cx, cy, r), bg)
        # Subtle outer halo on hover.
        if self._hover_t > 0.01:
            dl.stroke_path(_circle(cx, cy, r + 2.0),
                           with_alpha(t.danger, 0.25 * self._hover_t), 2.0)
        # X glyph.
        a = r * 0.45
        ink = (255, 255, 255, 240)
        dl.stroke_path(f"M {cx - a} {cy - a} L {cx + a} {cy + a}", ink, self.stroke_width)
        dl.stroke_path(f"M {cx - a} {cy + a} L {cx + a} {cy - a}", ink, self.stroke_width)

    def fire_click(self) -> None:
        if self.on_click is not None:
            self.on_click()


# ---------------------------------------------------------------------------
# GlyphAtlas + IconButton (spec §6.6).
# ---------------------------------------------------------------------------


class GlyphAtlas:
    """Name → image-file registry for `IconButton`s. Skins ship custom
    glyph sets under ``<bundle>/assets/icons/<name>.png``; the skin
    loader (or any app code) populates the atlas by calling
    ``atlas.load_from_directory(path)`` and the IconButton component
    looks up its ``icon`` name to find the file to draw.

    The atlas falls back to text rendering when a glyph name has no
    entry, so authors can mix file-backed and unicode glyphs freely.
    """

    def __init__(self) -> None:
        self._icons: dict[str, str] = {}

    def load_from_directory(self, path: Any) -> int:
        """Scan ``path`` for ``.png`` / ``.svg`` / ``.jpg`` files and
        register each one under its filename stem. Returns the number
        of glyphs registered.

        Files in subdirectories are ignored  this is a flat namespace
        by design (matches the spec §6.6 layout
        ``assets/icons/<name>.png``)."""
        from pathlib import Path as _Path

        directory = _Path(path)
        if not directory.is_dir():
            return 0
        count = 0
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in (".png", ".svg", ".jpg", ".jpeg"):
                continue
            self._icons[entry.stem] = str(entry)
            count += 1
        return count

    def register(self, name: str, path: str) -> None:
        """Bind ``name`` to ``path`` directly, bypassing directory
        scan. Useful for tests + programmatic icon registration."""
        self._icons[name] = path

    def lookup(self, name: str) -> str | None:
        return self._icons.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._icons

    def __len__(self) -> int:
        return len(self._icons)


_default_atlas = GlyphAtlas()


def get_default_atlas() -> GlyphAtlas:
    """Process-wide glyph atlas. Use ``register`` /
    ``load_from_directory`` to populate it; `IconButton` consults it
    when ``IconButton.icon`` doesn't resolve via the per-instance
    ``atlas`` override."""
    return _default_atlas


@dataclass
class IconButton(Component):
    """Generic icon-only button. Resolves ``icon`` to a sprite via
    ``atlas`` (default: the process-wide atlas) and draws the image
    inside the bounding box; falls back to rendering ``icon`` as text
    when no atlas entry exists.

    Three variants:
      * ``ghost``  transparent surface, brightens on hover (default).
      * ``solid``  theme-primary fill.
      * ``outline``  stroked border, transparent fill.

    Hit-test is rectangular (bbox). For circular hit-tests use
    ``IconCloseButton`` / ``FAB``.
    """
    icon: str = ""
    tooltip: str = ""
    on_click: Callable[[], None] | None = None
    variant: str = "ghost"
    radius: float | None = None
    icon_size: float = 18.0
    icon_color: Color | None = None
    atlas: GlyphAtlas | None = None  # None → use process-wide atlas

    def fire_click(self) -> None:
        if self.on_click is not None:
            self.on_click()

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.radius if self.radius is not None else t.radius_small
        scale = 1.0 + 0.05 * self._hover_t - 0.04 * self._press_t
        cw = self.w * scale
        ch = self.h * scale
        cx = self.x + (self.w - cw) / 2.0
        cy = self.y + (self.h - ch) / 2.0
        # Background per variant.
        if self.variant == "solid":
            base = t.primary
            top = lighten(base, 0.10)
            bot = base
            dl.gradient_card(cx, cy, cw, ch, r, top, bot,
                             0.0, (0.0, 0.0), (0, 0, 0, 0))
        elif self.variant == "ghost":
            tint = with_alpha(t.surface_variant if hasattr(t, "surface_variant")
                              else t.on_surface, 0.10 * self._hover_t)
            if tint[3] > 0:
                dl.fill_path(_rounded_rect(cx, cy, cw, ch, r), tint)
        elif self.variant == "outline":
            dl.stroke_path(
                _rounded_rect(cx + 0.5, cy + 0.5, cw - 1, ch - 1, r),
                t.on_surface, 1.0)
        # Focus ring.
        if self._focus_t > 0.01:
            ring = with_alpha(t.accent, 0.4 * self._focus_t)
            dl.stroke_path(
                _rounded_rect(cx - 2, cy - 2, cw + 4, ch + 4, r + 2),
                ring, 2.0)
        # Icon: try atlas, fall back to text.
        atlas = self.atlas if self.atlas is not None else _default_atlas
        path = atlas.lookup(self.icon) if self.icon else None
        if path:
            # Centre the glyph inside the icon-size square.
            iw = ih = self.icon_size
            ix = cx + (cw - iw) / 2.0
            iy = cy + (ch - ih) / 2.0
            try:
                dl.draw_image_file(path, ix, iy, iw, ih)
            except Exception:
                path = None        # fall through to text fallback
        if not path and self.icon:
            ic = (self.icon_color if self.icon_color is not None
                  else (t.on_primary if self.variant == "solid"
                        else t.on_surface))
            approx_w = len(self.icon) * self.icon_size * 0.55
            dl.draw_text(self.icon,
                         cx + (cw - approx_w) / 2.0,
                         cy + ch * 0.68,
                         self.icon_size,
                         with_alpha(ic, 1.0 - 0.4 * self._disabled_t))


# ---------------------------------------------------------------------------
# Card — layered shadow + gradient surface.
# ---------------------------------------------------------------------------

@dataclass
class Card(Component):
    radius: float | None = None
    elevation: str = "medium"   # "close" | "medium" | "far"
    fill: Color | None = None
    material: str = "elevated"  # "solid" | "elevated" | "glass"
    blur_sigma: float = 24.0    # only for material == "glass"

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.radius if self.radius is not None else t.radius_medium
        s = {"close": t.shadow_close, "medium": t.shadow_medium, "far": t.shadow_far}[self.elevation]
        if self.material == "glass":
            # GPU frosted-panel: background-blurred frosted card with edge.
            tint = self.fill if self.fill is not None else (255, 255, 255, 28) if t.is_dark else (255, 255, 255, 120)
            dl.frosted_panel(self.x, self.y, self.w, self.h, r,
                             self.blur_sigma, tint,
                             with_alpha(t.edge, 0.6))
            return
        body_top = self.fill if self.fill is not None else lighten(t.surface, 0.02)
        body_bot = self.fill if self.fill is not None else t.surface
        # Universal layered shadow (three stacked passes) for "elevated".
        if self.material == "elevated":
            for off, blur, alpha in ((s.offset[1] * 0.30, s.blur * 0.4, 0.12),
                                     (s.offset[1] * 0.70, s.blur * 0.7, 0.18),
                                     (s.offset[1] * 1.10, s.blur * 1.0, 0.20)):
                dl.gradient_card(
                    self.x, self.y, self.w, self.h, r,
                    body_top, body_bot,
                    blur, (s.offset[0], off),
                    (0, 0, 0, int(255 * alpha)))
        else:
            dl.gradient_card(self.x, self.y, self.w, self.h, r,
                             body_top, body_bot, s.blur, s.offset, s.color)
        # Subtle inner top-edge highlight on dark themes.
        if t.is_dark:
            dl.fill_path_linear_gradient(
                _rounded_rect(self.x + 1, self.y + 1, self.w - 2, self.h * 0.35, max(0, r - 1)),
                (self.x, self.y), (self.x, self.y + self.h * 0.35),
                with_alpha((255, 255, 255, 255), 0.08),
                with_alpha((255, 255, 255, 255), 0.0),
            )


# ---------------------------------------------------------------------------
# Toggle — iOS-style pill with smooth knob slide + colour fade.
# ---------------------------------------------------------------------------

@dataclass
class Toggle(Component):
    value: bool = False
    on_change: Callable[[bool], None] | None = None
    track_on_color:  Color | None = None
    track_off_color: Color | None = None
    knob_color:      Color | None = None
    _value_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.value else 0.0
        self._value_t = current_theme().motion.step(self._value_t, target, dt, "value_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.h / 2.0
        track_off = self.track_off_color or (
            t.surface_variant if not t.is_dark else lighten(t.surface_variant, 0.06))
        track_on  = self.track_on_color or t.primary
        bg = mix(track_off, track_on, self._value_t)
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), bg)
        # Inset shadow for depth (drawn as a thin dark line at top edge).
        dl.fill_path_linear_gradient(
            _rounded_rect(self.x, self.y, self.w, self.h * 0.5, r),
            (self.x, self.y), (self.x, self.y + self.h * 0.5),
            with_alpha((0, 0, 0, 255), 0.20),
            with_alpha((0, 0, 0, 255), 0.0),
        )
        # Knob.
        knob_r = r - 3.0
        knob_cx = self.x + r + (self.w - 2 * r) * self._value_t
        # Subtle drop shadow under knob.
        dl.fill_path(_circle(knob_cx, self.y + r + 1.5, knob_r),
                     with_alpha((0, 0, 0, 255), 0.30))
        # Knob body with radial highlight.
        dl.fill_path_radial_gradient(
            _circle(knob_cx, self.y + r, knob_r),
            (knob_cx - knob_r * 0.3, self.y + r - knob_r * 0.3),
            knob_r,
            self.knob_color or (255, 255, 255, 255),
            lighten(self.knob_color or (220, 220, 230, 255), 0.0),
        )
        # Hover: knob grows ever so slightly.
        if self._hover_t > 0.01:
            dl.stroke_path(_circle(knob_cx, self.y + r, knob_r + 1.0),
                           with_alpha(t.primary, 0.12 * self._hover_t), 1.0)

    def fire_toggle(self) -> None:
        self.value = not self.value
        if self.on_change is not None:
            self.on_change(self.value)


# ---------------------------------------------------------------------------
# Slider — glowing track + sculpted thumb with radial highlight.
# ---------------------------------------------------------------------------

@dataclass
class Slider(Component):
    value: float = 0.5
    min_value: float = 0.0
    max_value: float = 1.0
    on_change: Callable[[float], None] | None = None
    knob_r: float = 11.0
    track_color:    Color | None = None
    fill_color:     Color | None = None     # start of the filled-track gradient
    fill_end_color: Color | None = None     # end of the filled-track gradient

    def _fraction(self) -> float:
        return (self.value - self.min_value) / max(1e-9, self.max_value - self.min_value)

    def paint(self, dl: Any) -> None:
        t = current_theme()
        track_h = 5.0
        ty = self.y + (self.h - track_h) / 2.0
        # Track background.
        track_c = self.track_color or (
            t.surface_variant if not t.is_dark else lighten(t.surface_variant, 0.04))
        dl.fill_path(_rounded_rect(self.x, ty, self.w, track_h, track_h / 2.0), track_c)
        # Filled portion: gradient primary → accent.
        f = self._fraction()
        fill_w = max(0.0, self.w * f)
        if fill_w > 0:
            fill_a = self.fill_color or t.primary
            fill_b = self.fill_end_color or t.accent
            dl.fill_path_linear_gradient(
                _rounded_rect(self.x, ty, fill_w, track_h, track_h / 2.0),
                (self.x, ty), (self.x + fill_w, ty),
                fill_a, fill_b,
            )
            # Soft glow under the filled track.
            glow_alpha = 0.20 + 0.20 * self._hover_t
            dl.fill_path_linear_gradient(
                _rounded_rect(self.x, ty - 4, fill_w, track_h + 8, track_h / 2.0 + 4),
                (self.x, ty), (self.x, ty + track_h),
                with_alpha(t.primary, glow_alpha),
                with_alpha(t.primary, 0.0),
            )
        # Knob.
        kx = self.x + self.w * f
        ky = self.y + self.h / 2.0
        kr = self.knob_r + 2.5 * self._hover_t
        # Drop shadow.
        dl.fill_path(_circle(kx, ky + 2.0, kr),
                     with_alpha((0, 0, 0, 255), 0.35))
        # Body — radial gradient white → primary edge.
        dl.fill_path_radial_gradient(
            _circle(kx, ky, kr),
            (kx - kr * 0.35, ky - kr * 0.35),
            kr,
            (255, 255, 255, 255), lighten(t.primary, -0.06),
        )
        # Outline.
        dl.stroke_path(_circle(kx, ky, kr),
                       with_alpha(t.primary, 0.85), 1.5)
        # Focus ring.
        if self._focus_t > 0.01:
            dl.stroke_path(_circle(kx, ky, kr + 4.0),
                           with_alpha(t.accent, 0.4 * self._focus_t), 2.0)

    def set_from_x(self, mx: float) -> None:
        f = max(0.0, min(1.0, (mx - self.x) / max(1e-9, self.w)))
        prev = self.value
        self.value = self.min_value + f * (self.max_value - self.min_value)
        if self.on_change is not None and self.value != prev:
            self.on_change(self.value)


# ---------------------------------------------------------------------------
# TextField — rounded surface + floating label + focus underline.
# ---------------------------------------------------------------------------

@dataclass
class TextField(Component):
    """Single-line editable text field.

    Embeds an :class:`elysium.text.edit.EditableText` model and implements
    the :class:`elysium.input.Editable` protocol, so registering it with a
    window's ``InputRouter`` makes it fully editable: caret, selection,
    word navigation, undo/redo, clipboard, validators/masks, and IME — no
    per-app keystroke plumbing. Reads of ``.value`` stay valid (mirrored
    from the model)."""
    placeholder: str = ""
    value: str = ""
    on_change: Callable[[str], None] | None = None
    radius: float | None = None
    label: str = ""        # floats when focused / has content
    fill_color:   Color | None = None
    text_color:   Color | None = None
    accent_color: Color | None = None     # focus underline + label
    selection_color: Color | None = None  # themeable selection highlight
    focus_id: str = ""                    # set so InputRouter can target it
    password: bool = False                # render bullets instead of glyphs
    # Optional validation hooks forwarded to the EditableText model.
    validator: Callable[[str], int] | None = None
    mask: Any = None
    max_length: int | None = None
    font_size: float | None = None

    _edit: Any = field(default=None, init=False, repr=False)
    _blink_t: float = field(default=0.0, init=False, repr=False)
    _scroll_x: float = field(default=0.0, init=False, repr=False)
    _multiline: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        from elysium.text.edit import EditableText
        self._edit = EditableText(
            text=self.value, caret=len(self.value), multiline=self._multiline,
            validator=self.validator, mask=self.mask,
            max_length=self.max_length, on_change=self._sync_value,
        )

    # -- value mirror -------------------------------------------------------

    def _sync_value(self, text: str) -> None:
        self.value = text
        if self.on_change is not None:
            try: self.on_change(text)
            except Exception: pass

    def set_value(self, text: str) -> None:
        self._edit.set_text(text)

    # -- text geometry helpers ---------------------------------------------

    def _text_x(self) -> float:
        return self.x + 12.0

    def _baseline_y(self, t) -> float:
        return self.y + self.h * 0.66

    def _font(self, t) -> float:
        return self.font_size if self.font_size is not None else t.font_size_body

    def _display_text(self) -> str:
        e = self._edit
        if self.password and e.text:
            return "•" * len(e.text)
        return e.text

    # -- Editable protocol --------------------------------------------------

    def wants_keys(self) -> bool:
        return self._disabled_t < 0.5

    def focus_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def on_key(self, code: str, mods: int) -> bool:
        consumed = self._edit.on_key(code, mods)
        if consumed:
            self._blink_t = 0.0  # show caret immediately after a move/edit
        return consumed

    def on_text(self, s: str) -> None:
        self._edit.on_text(s)
        self._blink_t = 0.0

    def on_ime_preedit(self, s: str) -> None:
        self._edit.set_preedit(s)

    def on_ime_commit(self, s: str) -> None:
        self._edit.commit_preedit(s)

    def selected_text(self) -> str:
        return self._edit.selected_text()

    def delete_selection(self) -> None:
        self._edit.delete_selection()

    def on_paste(self, s: str) -> None:
        # Single-line fields paste a flattened (newline-stripped) string.
        self._edit.insert(s.replace("\n", " "))

    def caret_rect(self) -> tuple[float, float, float, float] | None:
        t = current_theme()
        size = self._font(t)
        cx = self._text_x() + _caret_x(self._edit.text, size, self._edit.caret) - self._scroll_x
        return (cx, self.y + 6.0, 2.0, self.h - 12.0)

    # -- mouse → caret (call from the app on click / drag) ------------------

    def caret_from_x(self, mx: float) -> int:
        t = current_theme()
        size = self._font(t)
        rel = mx - self._text_x() + self._scroll_x
        return _hit_index(self._edit.text, size, rel)

    def on_mouse_press(self, mx: float, my: float, *, extend: bool = False) -> None:
        self._edit.set_caret(self.caret_from_x(mx), select=extend)
        self._blink_t = 0.0

    def on_mouse_drag(self, mx: float, my: float) -> None:
        self._edit.set_caret(self.caret_from_x(mx), select=True)

    # -- per-frame ----------------------------------------------------------

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        self._blink_t += dt
        # Keep the caret horizontally in view (scroll long content).
        if self._focus_t > 0.5:
            t = current_theme()
            size = self._font(t)
            caret_px = _caret_x(self._edit.text, size, self._edit.caret)
            view_w = self.w - 24.0
            if caret_px - self._scroll_x > view_w:
                self._scroll_x = caret_px - view_w
            elif caret_px - self._scroll_x < 0:
                self._scroll_x = caret_px
            if self._scroll_x < 0:
                self._scroll_x = 0.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        e = self._edit
        r = self.radius if self.radius is not None else t.radius_small
        size = self._font(t)
        tx = self._text_x() - self._scroll_x
        by = self._baseline_y(t)
        focused = self._focus_t > 0.5
        # Background.
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r),
                     self.fill_color or t.surface_variant)
        # Outline — accent when focused, edge otherwise.
        line_color = mix(t.edge, t.accent, self._focus_t)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       line_color, 1.0)
        # Floating label.
        if self.label:
            float_t = max(self._focus_t, 1.0 if e.text else 0.0)
            lx = self.x + 12.0
            ly_unfocused = self.y + self.h * 0.62
            ly_focused   = self.y - 2.0
            ly = ly_unfocused + (ly_focused - ly_unfocused) * float_t
            ls = t.font_size_body + (t.font_size_caption - t.font_size_body) * float_t
            lcolor = mix(t.on_surface_muted, t.accent, float_t)
            dl.draw_text(self.label, lx, ly, ls, lcolor)
        # Selection highlight (behind the text).
        if focused and e.has_selection:
            lo, hi = e.selection()
            x0 = self._text_x() + _caret_x(e.text, size, lo) - self._scroll_x
            x1 = self._text_x() + _caret_x(e.text, size, hi) - self._scroll_x
            sel = self.selection_color or with_alpha(t.accent, 0.30)
            dl.fill_path(_rounded_rect(x0, self.y + 5.0, max(1.0, x1 - x0), self.h - 10.0, 2.0), sel)
        # Value or placeholder.
        disp = self._display_text()
        if disp:
            dl.draw_text(disp, tx, by, size, self.text_color or t.on_surface)
        elif self.placeholder and not self.label:
            # When a floating label exists it serves as the hint, so the
            # placeholder only shows on label-less fields.
            dl.draw_text(self.placeholder, tx, by, size, t.on_surface_muted)
        # IME preedit (underlined candidate text drawn after the caret pos).
        if focused and e.preedit:
            px = self._text_x() + _caret_x(e.text, size, e.caret) - self._scroll_x
            dl.draw_text(e.preedit, px, by, size, t.on_surface)
            pw = _caret_x(e.preedit, size, len(e.preedit))
            dl.fill_path(_rounded_rect(px, by + 3.0, pw, 1.5, 0.75), t.accent)
        # Caret (blinks ~1.6 Hz; solid while preedit is active).
        if focused and (e.preedit or (self._blink_t % 1.06) < 0.53):
            base = e.text
            cx = self._text_x() + _caret_x(base, size, e.caret) - self._scroll_x
            if e.preedit:
                cx += _caret_x(e.preedit, size, len(e.preedit))
            caret_col = self.accent_color or t.accent
            dl.fill_path(_rounded_rect(cx, self.y + 6.0, 2.0, self.h - 12.0, 1.0), caret_col)
        # Focus underline (expands from centre).
        if self._focus_t > 0.001:
            uw = (self.w - 24) * self._focus_t
            ux = self.x + 12 + ((self.w - 24) - uw) / 2.0
            uy = self.y + self.h - 2
            dl.fill_path(_rounded_rect(ux, uy, uw, 2.0, 1.0), self.accent_color or t.accent)


# ---------------------------------------------------------------------------
# ProgressBar — animated shimmer sweep.
# ---------------------------------------------------------------------------

@dataclass
class ProgressBar(Component):
    value: float = 0.0
    max_value: float = 1.0
    indeterminate: bool = False
    radius: float | None = None
    track_color:    Color | None = None
    fill_color:     Color | None = None
    fill_end_color: Color | None = None
    _shimmer_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        # Shimmer cycles every 1.6 seconds.
        self._shimmer_t = (self._shimmer_t + dt / 1.6) % 1.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.radius if self.radius is not None else self.h / 2.0
        # Track.
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r),
                     self.track_color or t.surface_variant)
        fill_a = self.fill_color or t.primary
        fill_b = self.fill_end_color or t.accent
        if self.indeterminate:
            # A 30%-wide gradient pulse that sweeps across the track.
            pulse_w = self.w * 0.30
            px = self.x + self._shimmer_t * (self.w + pulse_w) - pulse_w
            px = max(self.x, px)
            pw = min(pulse_w, self.x + self.w - px)
            if pw > 0:
                dl.fill_path_linear_gradient(
                    _rounded_rect(px, self.y, pw, self.h, r),
                    (px, self.y), (px + pw, self.y),
                    with_alpha(fill_a, 0.0),
                    fill_a,
                )
        else:
            # Determinate: filled portion + a shine sweep over it.
            f = max(0.0, min(1.0, self.value / max(1e-9, self.max_value)))
            fill_w = self.w * f
            if fill_w > 0:
                dl.fill_path_linear_gradient(
                    _rounded_rect(self.x, self.y, fill_w, self.h, r),
                    (self.x, self.y), (self.x + fill_w, self.y),
                    fill_a, fill_b,
                )
                # Shine sweep.
                shine_w = fill_w * 0.20
                sx = self.x + self._shimmer_t * (fill_w + shine_w) - shine_w
                sx = max(self.x, sx)
                sw = min(shine_w, self.x + fill_w - sx)
                if sw > 0:
                    dl.fill_path_linear_gradient(
                        _rounded_rect(sx, self.y, sw, self.h, r),
                        (sx, self.y), (sx + sw, self.y),
                        with_alpha((255, 255, 255, 255), 0.0),
                        with_alpha((255, 255, 255, 255), 0.40),
                    )


# ---------------------------------------------------------------------------
# Stack layout (unchanged).
# ---------------------------------------------------------------------------

@dataclass
class Stack(Component):
    direction: str = "vertical"
    gap: float = 8.0
    padding: float = 0.0
    children: list[Component] = field(default_factory=list)

    def layout(self) -> None:
        cursor = self.padding
        for child in self.children:
            if self.direction == "vertical":
                child.x = self.x + self.padding
                child.y = self.y + cursor
                child.w = self.w - 2 * self.padding
                cursor += child.h + self.gap
            else:
                child.x = self.x + cursor
                child.y = self.y + self.padding
                child.h = self.h - 2 * self.padding
                cursor += child.w + self.gap

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        for child in self.children:
            child.update(dt, {})

    def paint(self, dl: Any) -> None:
        self.layout()
        for child in self.children:
            child.paint(dl)


# ---------------------------------------------------------------------------
# Checkbox.
# ---------------------------------------------------------------------------

@dataclass
class Checkbox(Component):
    value: bool = False
    label: str = ""
    on_change: Callable[[bool], None] | None = None
    fill_color:  Color | None = None      # checked background
    box_color:   Color | None = None      # unchecked background
    check_color: Color | None = None      # check mark
    text_color:  Color | None = None
    _value_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.value else 0.0
        self._value_t = current_theme().motion.step(self._value_t, target, dt, "value_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        box_size = min(self.h, 20.0)
        bx, by = self.x, self.y + (self.h - box_size) / 2.0
        # Background: surface_variant → primary on check.
        unchecked = self.box_color or t.surface_variant
        checked   = self.fill_color or t.primary
        bg = mix(unchecked, checked, self._value_t)
        dl.fill_path(_rounded_rect(bx, by, box_size, box_size, 4.0), bg)
        dl.stroke_path(_rounded_rect(bx + 0.5, by + 0.5, box_size - 1, box_size - 1, 4.0),
                       mix(t.edge, checked, self._value_t), 1.0)
        # Check mark: drawn proportional to _value_t.
        check_c = self.check_color or t.on_primary
        if self._value_t > 0.05:
            ax, ay = bx + box_size * 0.22, by + box_size * 0.52
            mx, my = bx + box_size * 0.42, by + box_size * 0.72
            ex, ey = bx + box_size * 0.78, by + box_size * 0.30
            t1 = min(self._value_t * 2.0, 1.0)
            lx = ax + (mx - ax) * t1
            ly = ay + (my - ay) * t1
            dl.stroke_path(f"M {ax} {ay} L {lx} {ly}", check_c, 2.0)
            if self._value_t > 0.5:
                t2 = (self._value_t - 0.5) * 2.0
                tx = mx + (ex - mx) * t2
                ty = my + (ey - my) * t2
                dl.stroke_path(f"M {mx} {my} L {tx} {ty}", check_c, 2.0)
        # Label.
        if self.label:
            dl.draw_text(self.label, bx + box_size + 10.0,
                         by + box_size * 0.78,
                         t.font_size_body, self.text_color or t.on_surface)

    def fire_toggle(self) -> None:
        self.value = not self.value
        if self.on_change is not None:
            self.on_change(self.value)


# ---------------------------------------------------------------------------
# Radio.
# ---------------------------------------------------------------------------

@dataclass
class Radio(Component):
    value: bool = False
    label: str = ""
    on_change: Callable[[bool], None] | None = None
    fill_color:  Color | None = None       # outer ring background
    accent_color: Color | None = None      # inner dot
    text_color:  Color | None = None
    _value_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.value else 0.0
        self._value_t = current_theme().motion.step(self._value_t, target, dt, "value_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = min(self.h, 20.0) / 2.0
        cx, cy = self.x + r, self.y + self.h / 2.0
        accent = self.accent_color or t.primary
        dl.fill_path(_circle(cx, cy, r), self.fill_color or t.surface_variant)
        dl.stroke_path(_circle(cx, cy, r),
                       mix(t.edge, accent, self._value_t), 1.5)
        if self._value_t > 0.01:
            inner_r = r * 0.5 * self._value_t
            dl.fill_path(_circle(cx, cy, inner_r), accent)
        if self.label:
            dl.draw_text(self.label, cx + r + 10.0, cy + 6.0,
                         t.font_size_body, self.text_color or t.on_surface)

    def fire_select(self) -> None:
        self.value = True
        if self.on_change is not None:
            self.on_change(True)


# ---------------------------------------------------------------------------
# TextArea — multi-line TextField.
# ---------------------------------------------------------------------------

@dataclass
class TextArea(Component):
    """Multi-line editable text area. Like :class:`TextField` it embeds an
    :class:`EditableText` (with ``multiline=True``) and implements the
    Editable protocol, adding hard-newline line layout, vertical caret
    movement, cross-line selection, and vertical scroll. Lines are split on
    ``\\n``; visual soft-wrap of over-long lines is a later refinement."""
    placeholder: str = ""
    value: str = ""
    on_change: Callable[[str], None] | None = None
    radius: float | None = None
    focus_id: str = ""
    selection_color: Color | None = None
    accent_color: Color | None = None
    font_size: float | None = None
    line_height: float | None = None

    _edit: Any = field(default=None, init=False, repr=False)
    _blink_t: float = field(default=0.0, init=False, repr=False)
    _scroll_y: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        from elysium.text.edit import EditableText
        self._edit = EditableText(
            text=self.value, caret=len(self.value), multiline=True,
            on_change=self._sync_value)

    def _sync_value(self, text: str) -> None:
        self.value = text
        if self.on_change is not None:
            try: self.on_change(text)
            except Exception: pass

    def set_value(self, text: str) -> None:
        self._edit.set_text(text)

    # geometry
    def _font(self, t) -> float:
        return self.font_size if self.font_size is not None else t.font_size_body

    def _lh(self, t) -> float:
        return self.line_height if self.line_height is not None else self._font(t) * 1.45

    def _pad(self) -> tuple[float, float]:
        return (self.x + 12.0, self.y + 10.0)

    def _caret_line_col(self) -> tuple[int, int]:
        e = self._edit
        before = e.text[: e.caret]
        line = before.count("\n")
        col = e.caret - (before.rfind("\n") + 1)
        return line, col

    # Editable protocol
    def wants_keys(self) -> bool:
        return self._disabled_t < 0.5

    def focus_rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def on_key(self, code: str, mods: int) -> bool:
        consumed = self._edit.on_key(code, mods)
        if consumed:
            self._blink_t = 0.0
        return consumed

    def on_text(self, s: str) -> None:
        self._edit.on_text(s); self._blink_t = 0.0

    def on_ime_preedit(self, s: str) -> None:
        self._edit.set_preedit(s)

    def on_ime_commit(self, s: str) -> None:
        self._edit.commit_preedit(s)

    def selected_text(self) -> str:
        return self._edit.selected_text()

    def delete_selection(self) -> None:
        self._edit.delete_selection()

    def on_paste(self, s: str) -> None:
        self._edit.insert(s)

    def caret_rect(self) -> tuple[float, float, float, float] | None:
        t = current_theme()
        px, py = self._pad()
        line, col = self._caret_line_col()
        size = self._font(t)
        line_text = self._edit.text.split("\n")[line] if self._edit.text else ""
        cx = px + _caret_x(line_text, size, col)
        cy = py + line * self._lh(t) - self._scroll_y
        return (cx, cy, 2.0, size + 4.0)

    def caret_from_point(self, mx: float, my: float) -> int:
        t = current_theme()
        px, py = self._pad()
        size = self._font(t)
        lines = self._edit.text.split("\n")
        line = int(max(0, min(len(lines) - 1, (my - py + self._scroll_y) // self._lh(t))))
        col = _hit_index(lines[line], size, mx - px)
        return sum(len(l) + 1 for l in lines[:line]) + col

    def on_mouse_press(self, mx: float, my: float, *, extend: bool = False) -> None:
        self._edit.set_caret(self.caret_from_point(mx, my), select=extend)
        self._blink_t = 0.0

    def on_mouse_drag(self, mx: float, my: float) -> None:
        self._edit.set_caret(self.caret_from_point(mx, my), select=True)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        self._blink_t += dt
        if self._focus_t > 0.5:
            t = current_theme()
            line, _ = self._caret_line_col()
            lh = self._lh(t)
            caret_top = line * lh
            view_h = self.h - 20.0
            if caret_top - self._scroll_y > view_h - lh:
                self._scroll_y = caret_top - (view_h - lh)
            elif caret_top - self._scroll_y < 0:
                self._scroll_y = caret_top
            if self._scroll_y < 0:
                self._scroll_y = 0.0

    def paint(self, dl: Any) -> None:
        t = current_theme()
        e = self._edit
        r = self.radius if self.radius is not None else t.radius_small
        size = self._font(t)
        lh = self._lh(t)
        px, py = self._pad()
        focused = self._focus_t > 0.5
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), t.surface_variant)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        if not e.text and self.placeholder:
            dl.draw_text(self.placeholder, px, py + size, size, t.on_surface_muted)
        lines = e.text.split("\n")
        # Selection rectangles per line.
        if focused and e.has_selection:
            lo, hi = e.selection()
            sel_col = self.selection_color or with_alpha(t.accent, 0.30)
            char = 0
            for li, line in enumerate(lines):
                lstart, lend = char, char + len(line)
                a = max(lo, lstart); b = min(hi, lend)
                if a < b or (lo <= lend < hi and lstart <= lo):
                    x0 = px + _caret_x(line, size, max(0, a - lstart))
                    x1 = px + _caret_x(line, size, max(0, b - lstart))
                    ly = py + li * lh - self._scroll_y
                    if x1 > x0:
                        dl.fill_path(_rounded_rect(x0, ly, x1 - x0, lh, 2.0), sel_col)
                char = lend + 1
        # Text, line by line (clipped to the visible band by the y check).
        for li, line in enumerate(lines):
            ly = py + li * lh - self._scroll_y
            if ly + lh < self.y or ly > self.y + self.h:
                continue
            if line:
                dl.draw_text(line, px, ly + size, size, t.on_surface)
        # Caret.
        if focused and (self._blink_t % 1.06) < 0.53:
            cr = self.caret_rect()
            if cr is not None:
                dl.fill_path(_rounded_rect(cr[0], cr[1], 2.0, cr[3], 1.0),
                             self.accent_color or t.accent)


# ---------------------------------------------------------------------------
# Divider.
# ---------------------------------------------------------------------------

@dataclass
class Divider(Component):
    orientation: str = "horizontal"  # "horizontal" | "vertical"
    color: Color | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        c = self.color or t.edge
        if self.orientation == "horizontal":
            cy = self.y + self.h / 2.0
            dl.fill_path(_rounded_rect(self.x, cy - 0.5, self.w, 1.0, 0.5), c)
        else:
            cx = self.x + self.w / 2.0
            dl.fill_path(_rounded_rect(cx - 0.5, self.y, 1.0, self.h, 0.5), c)


# ---------------------------------------------------------------------------
# Badge — small pill, used for counts / status.
# ---------------------------------------------------------------------------

@dataclass
class Badge(Component):
    text: str = ""
    variant: str = "primary"   # primary | accent | success | warning | danger | neutral
    fill_color: Color | None = None
    text_color: Color | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        palette = {"primary": t.primary, "accent": t.accent,
                   "success": t.success, "warning": t.warning,
                   "danger":  t.danger,  "neutral": t.surface_variant}
        fg_palette = {"neutral": t.on_surface}
        bg = self.fill_color or palette.get(self.variant, t.primary)
        fg = self.text_color or fg_palette.get(self.variant, t.on_primary)
        r = self.h / 2.0
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), bg)
        if self.text:
            approx_w = len(self.text) * t.font_size_caption * 0.55
            tx = self.x + (self.w - approx_w) / 2.0
            dl.draw_text(self.text, tx, self.y + self.h * 0.68,
                         t.font_size_caption, fg)


# ---------------------------------------------------------------------------
# Avatar — circular image or initial.
# ---------------------------------------------------------------------------

@dataclass
class Avatar(Component):
    initial: str = "?"
    image_path: str | None = None
    bg: Color | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = min(self.w, self.h) / 2.0
        cx, cy = self.x + self.w / 2.0, self.y + self.h / 2.0
        if self.image_path:
            # Image: draw it clipped to the circle (Phase 3 will add real
            # clipping; for now use draw_image with the image fitted).
            dl.draw_image_file_region(self.image_path,
                                      0, 0, 1024, 1024,  # the image's own bbox
                                      self.x, self.y, self.w, self.h)
            dl.stroke_path(_circle(cx, cy, r - 1.0), with_alpha(t.edge, 0.6), 1.0)
        else:
            bg = self.bg if self.bg is not None else t.primary
            dl.fill_path(_circle(cx, cy, r), bg)
            if self.initial:
                ts = r * 0.9
                approx_w = len(self.initial) * ts * 0.55
                tx = cx - approx_w / 2.0
                dl.draw_text(self.initial[0].upper(), tx, cy + ts * 0.35,
                             ts, t.on_primary)


# ---------------------------------------------------------------------------
# Chip — pill with optional close X.
# ---------------------------------------------------------------------------

@dataclass
class Chip(Component):
    label: str = ""
    on_remove: Callable[[], None] | None = None
    bg: Color | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        bg = self.bg if self.bg is not None else t.surface_variant
        if self._hover_t > 0.01:
            bg = lighten(bg, 0.04 * self._hover_t)
        r = self.h / 2.0
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), bg)
        # Label.
        pad_x = 12.0
        if self.label:
            dl.draw_text(self.label, self.x + pad_x, self.y + self.h * 0.68,
                         t.font_size_caption, t.on_surface)
        # Optional close glyph at right.
        if self.on_remove is not None:
            xcx = self.x + self.w - self.h / 2.0
            xcy = self.y + self.h / 2.0
            a = self.h * 0.18
            dl.stroke_path(f"M {xcx - a} {xcy - a} L {xcx + a} {xcy + a}",
                           t.on_surface_muted, 1.5)
            dl.stroke_path(f"M {xcx - a} {xcy + a} L {xcx + a} {xcy - a}",
                           t.on_surface_muted, 1.5)


# ---------------------------------------------------------------------------
# Spinner — indeterminate circular progress.
# ---------------------------------------------------------------------------

@dataclass
class Spinner(Component):
    size: float = 28.0
    _phase: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        self._phase = (self._phase + dt / 1.0) % 1.0   # 1 rotation per second

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = self.size / 2.0
        cx, cy = self.x + self.w / 2.0, self.y + self.h / 2.0
        # Track ring (faint).
        dl.stroke_path(_circle(cx, cy, r), with_alpha(t.primary, 0.18), 3.0)
        # Active arc — drawn as 8 dot segments with decreasing alpha.
        for i in range(8):
            phase_i = (self._phase - i / 8.0) % 1.0
            alpha = max(0.0, 1.0 - phase_i)
            a = (i / 8.0) * 2.0 * math.pi
            dot_x = cx + r * math.cos(a)
            dot_y = cy + r * math.sin(a)
            dl.fill_path(_circle(dot_x, dot_y, 2.4),
                         with_alpha(t.primary, alpha))


# ---------------------------------------------------------------------------
# Tooltip — small caption box, typically rendered near a hover target.
# ---------------------------------------------------------------------------

@dataclass
class Tooltip(Component):
    text: str = ""
    visible: bool = False
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        alpha = self._vis_t
        bg = (24, 22, 35, int(0xE0 * alpha))
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, 6.0), bg)
        if self.text:
            dl.draw_text(self.text, self.x + 10.0,
                         self.y + self.h * 0.68, t.font_size_caption,
                         with_alpha((255, 255, 255, 255), alpha))


# ---------------------------------------------------------------------------
# Tabs — horizontal tab bar with sliding indicator.
# ---------------------------------------------------------------------------

@dataclass
class Tabs(Component):
    items: list[str] = field(default_factory=list)
    selected: int = 0
    on_change: Callable[[int], None] | None = None
    _indicator_x: float = field(default=0.0, init=False, repr=False)
    _indicator_w: float = field(default=0.0, init=False, repr=False)

    def _tab_rect(self, idx: int) -> tuple[float, float]:
        if not self.items: return (self.x, 0.0)
        tab_w = self.w / len(self.items)
        return (self.x + idx * tab_w, tab_w)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target_x, target_w = self._tab_rect(self.selected)
        motion = current_theme().motion
        self._indicator_x = motion.step(self._indicator_x, target_x, dt, "value_rate")
        self._indicator_w = motion.step(self._indicator_w, target_w, dt, "value_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        # Bottom track.
        dl.fill_path(_rounded_rect(self.x, self.y + self.h - 1, self.w, 1.0, 0.5),
                     t.edge)
        # Each tab label.
        for i, item in enumerate(self.items):
            tx, tw = self._tab_rect(i)
            color = t.primary if i == self.selected else t.on_surface_muted
            approx_w = len(item) * t.font_size_body * 0.55
            cx = tx + (tw - approx_w) / 2.0
            dl.draw_text(item, cx, self.y + self.h * 0.66,
                         t.font_size_body, color)
        # Sliding indicator (3px tall) under the selected tab.
        if self._indicator_w > 0:
            dl.fill_path_linear_gradient(
                _rounded_rect(self._indicator_x + 12,
                              self.y + self.h - 3,
                              max(0, self._indicator_w - 24), 3.0, 1.5),
                (self._indicator_x, 0), (self._indicator_x + self._indicator_w, 0),
                t.primary, t.accent,
            )

    def hit_index(self, mx: float, my: float) -> int | None:
        if not self.hit_test(mx, my) or not self.items: return None
        tab_w = self.w / len(self.items)
        return int((mx - self.x) / tab_w)

    def select(self, idx: int) -> None:
        if 0 <= idx < len(self.items) and idx != self.selected:
            self.selected = idx
            if self.on_change is not None:
                self.on_change(idx)


# ---------------------------------------------------------------------------
# Modal — overlay scrim + dialog card.
# ---------------------------------------------------------------------------

@dataclass
class Modal(Component):
    visible: bool = False
    title: str = ""
    body: str = ""
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        # Scrim covers the entire window.
        dl.fill_path(_rounded_rect(0, 0, max(self.w, 2000), max(self.h, 2000), 0),
                     with_alpha(t.overlay, self._vis_t))
        # Centered card.
        card_w = max(320.0, self.w * 0.4)
        card_h = max(180.0, self.h * 0.35)
        cx = self.x + (self.w - card_w) / 2.0
        cy = self.y + (self.h - card_h) / 2.0
        # Entrance: card scales up slightly from 0.95.
        scale = 0.92 + 0.08 * self._vis_t
        sw = card_w * scale
        sh = card_h * scale
        scx = cx + (card_w - sw) / 2.0
        scy = cy + (card_h - sh) / 2.0
        s = t.shadow_far
        dl.gradient_card(scx, scy, sw, sh, t.radius_large,
                         lighten(t.surface, 0.02), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        if self.title:
            dl.draw_text(self.title, scx + 24, scy + 36,
                         t.font_size_title, t.on_surface)
        if self.body:
            dl.draw_text(self.body, scx + 24, scy + 72,
                         t.font_size_body, t.on_surface_muted)


# ---------------------------------------------------------------------------
# Toast — slide-in transient notification.
# ---------------------------------------------------------------------------

@dataclass
class Toast(Component):
    text: str = ""
    variant: str = "info"   # info | success | warning | danger
    visible: bool = False
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        palette = {"info": t.primary, "success": t.success,
                   "warning": t.warning, "danger": t.danger}
        accent_bar = palette.get(self.variant, t.primary)
        # Slide-in from the right: x offset by (1 - vis_t) * 40.
        slide = (1.0 - self._vis_t) * 40.0
        sx = self.x + slide
        s = t.shadow_medium
        dl.gradient_card(sx, self.y, self.w, self.h, t.radius_medium,
                         lighten(t.surface, 0.02), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        # Accent bar on the left.
        dl.fill_path(_rounded_rect(sx + 4, self.y + 6, 4.0, self.h - 12, 2.0),
                     with_alpha(accent_bar, self._vis_t))
        if self.text:
            dl.draw_text(self.text, sx + 18, self.y + self.h * 0.66,
                         t.font_size_body,
                         with_alpha(t.on_surface, self._vis_t))


# ---------------------------------------------------------------------------
# Dropdown — closed button + open list.
# ---------------------------------------------------------------------------

@dataclass
class Dropdown(Component):
    items: list[str] = field(default_factory=list)
    selected: int = 0
    open: bool = False
    on_change: Callable[[int], None] | None = None
    _open_t: float = field(default=0.0, init=False, repr=False)
    item_h: float = 36.0

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.open else 0.0
        self._open_t = current_theme().motion.step(self._open_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = t.radius_small
        # Closed button.
        bg = mix(t.surface_variant, lighten(t.surface_variant, 0.05), self._hover_t)
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r), bg)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        # Selected value.
        if self.items and 0 <= self.selected < len(self.items):
            dl.draw_text(self.items[self.selected],
                         self.x + 12.0, self.y + self.h * 0.66,
                         t.font_size_body, t.on_surface)
        # Caret.
        cx = self.x + self.w - 18
        cy = self.y + self.h / 2.0
        dl.stroke_path(f"M {cx - 5} {cy - 2} L {cx} {cy + 3} L {cx + 5} {cy - 2}",
                       t.on_surface_muted, 1.5)
        # Open panel.
        if self._open_t > 0.01:
            panel_h = len(self.items) * self.item_h * self._open_t
            py = self.y + self.h + 4
            s = t.shadow_medium
            dl.gradient_card(self.x, py, self.w, panel_h, r,
                             t.surface, t.surface, s.blur, s.offset,
                             with_alpha(s.color, (s.color[3] / 255.0) * self._open_t))
            for i, item in enumerate(self.items):
                row_y = py + i * self.item_h
                if i == self.selected:
                    dl.fill_path(_rounded_rect(self.x + 4, row_y + 2,
                                               self.w - 8, self.item_h - 4, 4),
                                 with_alpha(t.primary, 0.15 * self._open_t))
                dl.draw_text(item, self.x + 12,
                             row_y + self.item_h * 0.66,
                             t.font_size_body,
                             with_alpha(t.on_surface, self._open_t))


# ---------------------------------------------------------------------------
# Menu — vertical popover with rows.
# ---------------------------------------------------------------------------

@dataclass
class MenuItem:
    label: str
    on_click: Callable[[], None] | None = None
    icon: str | None = None
    shortcut: str | None = None
    danger: bool = False


@dataclass
class Menu(Component):
    items: list[MenuItem] = field(default_factory=list)
    visible: bool = False
    _vis_t: float = field(default=0.0, init=False, repr=False)
    item_h: float = 32.0

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        panel_h = len(self.items) * self.item_h + 8
        scale = 0.96 + 0.04 * self._vis_t
        # Card panel.
        s = t.shadow_medium
        dl.gradient_card(self.x, self.y, self.w, panel_h * scale,
                         t.radius_medium,
                         lighten(t.surface, 0.02), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        for i, item in enumerate(self.items):
            row_y = self.y + 4 + i * self.item_h
            color = t.danger if item.danger else t.on_surface
            dl.draw_text(item.label, self.x + 12,
                         row_y + self.item_h * 0.66,
                         t.font_size_body,
                         with_alpha(color, self._vis_t))
            if item.shortcut:
                approx_w = len(item.shortcut) * t.font_size_caption * 0.55
                dl.draw_text(item.shortcut, self.x + self.w - approx_w - 12,
                             row_y + self.item_h * 0.66,
                             t.font_size_caption,
                             with_alpha(t.on_surface_muted, self._vis_t))


# ---------------------------------------------------------------------------
# Popover — generic floating panel.
# ---------------------------------------------------------------------------

@dataclass
class Popover(Component):
    visible: bool = False
    radius: float | None = None
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        r = self.radius if self.radius is not None else t.radius_medium
        scale = 0.96 + 0.04 * self._vis_t
        sw = self.w * scale
        sh = self.h * scale
        sx = self.x + (self.w - sw) / 2.0
        sy = self.y + (self.h - sh) / 2.0
        s = t.shadow_far
        dl.gradient_card(sx, sy, sw, sh, r,
                         lighten(t.surface, 0.03), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))


# ---------------------------------------------------------------------------
# Accordion — header that toggles to reveal body.
# ---------------------------------------------------------------------------

@dataclass
class Accordion(Component):
    title: str = ""
    open: bool = False
    body_h: float = 80.0
    _open_t: float = field(default=0.0, init=False, repr=False)
    header_h: float = 44.0

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.open else 0.0
        self._open_t = current_theme().motion.step(self._open_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        t = current_theme()
        # Header.
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.header_h,
                                   t.radius_small), t.surface_variant)
        if self.title:
            dl.draw_text(self.title, self.x + 16,
                         self.y + self.header_h * 0.66,
                         t.font_size_body, t.on_surface)
        # Caret rotates.
        cx = self.x + self.w - 22
        cy = self.y + self.header_h / 2.0
        a = self._open_t * math.pi / 2.0
        # Rotate a triangle around (cx, cy).
        def rp(px, py): return (cx + px * math.cos(a) - py * math.sin(a),
                                cy + px * math.sin(a) + py * math.cos(a))
        p1 = rp(-5, -2); p2 = rp(0, 3); p3 = rp(5, -2)
        dl.stroke_path(f"M {p1[0]} {p1[1]} L {p2[0]} {p2[1]} L {p3[0]} {p3[1]}",
                       t.on_surface_muted, 1.5)
        # Body — height animates.
        body_y = self.y + self.header_h + 4
        body_h = self.body_h * self._open_t
        if body_h > 0.5:
            dl.fill_path(_rounded_rect(self.x, body_y, self.w, body_h, t.radius_small),
                         t.surface)


# ---------------------------------------------------------------------------
# ComboBox — text input + dropdown suggestions (composed of TextField + Dropdown).
# ---------------------------------------------------------------------------

@dataclass
class ComboBox(Component):
    value: str = ""
    items: list[str] = field(default_factory=list)
    on_change: Callable[[str], None] | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = t.radius_small
        dl.fill_path(_rounded_rect(self.x, self.y, self.w, self.h, r),
                     t.surface_variant)
        dl.stroke_path(_rounded_rect(self.x + 0.5, self.y + 0.5, self.w - 1, self.h - 1, r),
                       mix(t.edge, t.accent, self._focus_t), 1.0)
        # Display value or first item.
        text = self.value or (self.items[0] if self.items else "")
        if text:
            dl.draw_text(text, self.x + 12, self.y + self.h * 0.66,
                         t.font_size_body, t.on_surface)
        # Down caret.
        cx = self.x + self.w - 18
        cy = self.y + self.h / 2.0
        dl.stroke_path(f"M {cx - 5} {cy - 2} L {cx} {cy + 3} L {cx + 5} {cy - 2}",
                       t.on_surface_muted, 1.5)


# ---------------------------------------------------------------------------
# Pagination — prev / pages / next.
# ---------------------------------------------------------------------------

@dataclass
class Pagination(Component):
    page: int = 1
    total: int = 5
    on_change: Callable[[int], None] | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        # Render up to `total` pages, clamped to a window of 5 around the current.
        max_show = 7
        if self.total <= max_show:
            pages = list(range(1, self.total + 1))
        else:
            start = max(1, self.page - 2)
            end = min(self.total, start + max_show - 1)
            pages = list(range(start, end + 1))

        pill_w = 32.0
        gap = 6.0
        total_w = len(pages) * pill_w + (len(pages) - 1) * gap
        sx = self.x + (self.w - total_w) / 2.0
        for i, p in enumerate(pages):
            px = sx + i * (pill_w + gap)
            py = self.y + (self.h - pill_w) / 2.0
            is_cur = (p == self.page)
            bg = t.primary if is_cur else t.surface_variant
            fg = t.on_primary if is_cur else t.on_surface
            dl.fill_path(_rounded_rect(px, py, pill_w, pill_w, t.radius_small), bg)
            label = str(p)
            approx_w = len(label) * t.font_size_body * 0.55
            dl.draw_text(label, px + (pill_w - approx_w) / 2.0,
                         py + pill_w * 0.68,
                         t.font_size_body, fg)


# ---------------------------------------------------------------------------
# Breadcrumb — slash-separated path.
# ---------------------------------------------------------------------------

@dataclass
class Breadcrumb(Component):
    items: list[str] = field(default_factory=list)
    on_click: Callable[[int], None] | None = None

    def paint(self, dl: Any) -> None:
        t = current_theme()
        cursor = self.x
        for i, item in enumerate(self.items):
            color = t.on_surface if i == len(self.items) - 1 else t.on_surface_muted
            dl.draw_text(item, cursor, self.y + self.h * 0.66,
                         t.font_size_body, color)
            approx_w = len(item) * t.font_size_body * 0.55
            cursor += approx_w + 4
            if i < len(self.items) - 1:
                dl.draw_text("/", cursor, self.y + self.h * 0.66,
                             t.font_size_body, t.on_surface_muted)
                cursor += 10


# ---------------------------------------------------------------------------
# CommandPalette — modal-like overlay with search field + result list.
# ---------------------------------------------------------------------------

@dataclass
class CommandPalette(Component):
    visible: bool = False
    query: str = ""
    items: list[str] = field(default_factory=list)
    selected: int = 0
    on_run: Callable[[str], None] | None = None
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        # Scrim.
        dl.fill_path(_rounded_rect(0, 0, max(self.w, 2000), max(self.h, 2000), 0),
                     with_alpha(t.overlay, self._vis_t * 0.7))
        # Panel.
        panel_w = max(420.0, self.w * 0.4)
        panel_h = 320.0
        px = self.x + (self.w - panel_w) / 2.0
        py = self.y + self.h * 0.15
        scale = 0.96 + 0.04 * self._vis_t
        sw, sh = panel_w * scale, panel_h * scale
        sx = px + (panel_w - sw) / 2.0
        sy = py + (panel_h - sh) / 2.0
        s = t.shadow_far
        dl.gradient_card(sx, sy, sw, sh, t.radius_large,
                         lighten(t.surface, 0.04), t.surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        # Search field.
        dl.draw_text(self.query if self.query else "Type a command…",
                     sx + 20, sy + 38, t.font_size_title,
                     with_alpha(t.on_surface if self.query else t.on_surface_muted,
                                self._vis_t))
        # Divider.
        dl.fill_path(_rounded_rect(sx + 16, sy + 60, sw - 32, 1.0, 0.5),
                     with_alpha(t.edge, self._vis_t))
        # Results.
        for i, item in enumerate(self.items[:6]):
            row_y = sy + 72 + i * 34
            if i == self.selected:
                dl.fill_path(_rounded_rect(sx + 12, row_y, sw - 24, 30, 6.0),
                             with_alpha(t.primary, 0.18 * self._vis_t))
            dl.draw_text(item, sx + 20, row_y + 20,
                         t.font_size_body,
                         with_alpha(t.on_surface, self._vis_t))


# ---------------------------------------------------------------------------
# Snackbar — bottom-anchored toast (Material-style).
# ---------------------------------------------------------------------------

@dataclass
class Snackbar(Component):
    text: str = ""
    action_label: str = ""
    on_action: Callable[[], None] | None = None
    visible: bool = False
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(self._vis_t, target, dt, "hover_rate")

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01: return
        t = current_theme()
        # Slide in from bottom.
        slide = (1.0 - self._vis_t) * 30.0
        sy = self.y + slide
        s = t.shadow_medium
        dl.gradient_card(self.x, sy, self.w, self.h, t.radius_medium,
                         lighten(t.on_surface, -0.05), t.on_surface,
                         s.blur, s.offset,
                         with_alpha(s.color, (s.color[3] / 255.0) * self._vis_t))
        if self.text:
            dl.draw_text(self.text, self.x + 16, sy + self.h * 0.66,
                         t.font_size_body,
                         with_alpha(t.surface, self._vis_t))
        if self.action_label:
            approx_w = len(self.action_label) * t.font_size_body * 0.55
            dl.draw_text(self.action_label,
                         self.x + self.w - approx_w - 16,
                         sy + self.h * 0.66,
                         t.font_size_body,
                         with_alpha(t.accent, self._vis_t))


# ---------------------------------------------------------------------------
# Tree — virtualized hierarchical list.
# ---------------------------------------------------------------------------

@dataclass
class TreeRow:
    """One row in a `Tree`. Authors pre-flatten their hierarchy into the
    display order they want, marking depth + expandable + expanded on
    each row. The Tree only knows how to paint + hit-test the flat list;
    expand / collapse logic lives in the host so reactive trees stay
    simple (the host re-builds the flat list when state changes).

    `user_data` carries any payload the host wants to round-trip through
    the callback (e.g. a placement index, an asset path).
    """
    id: str
    label: str
    depth: int = 0
    expandable: bool = False
    expanded: bool = False
    selected: bool = False
    icon_color: Color | None = None
    user_data: Any = None


@dataclass
class Tree(Component):
    """Virtualised hierarchical list. Designed for the Designer's
    Project Explorer  Maya-style row layout with a chevron on
    expandable rows, an optional kind-dot, and the row label. Only the
    rows currently visible inside ``(x, y, w, h)`` actually paint.

    Hosts call:
        tree.rows = build_flat_rows(...)
        tree.update(dt, {"hover": ...})
        tree.paint(dl)
        hit = tree.hit_test_row(mx, my)   # (row_id, "chevron"|"label")

    Spec source: §6.1 (250 LOC + tests).
    """
    rows: list[TreeRow] = field(default_factory=list)
    on_select: Callable[[str], None] | None = None
    on_toggle: Callable[[str], None] | None = None
    row_height: float = 20.0
    indent: float = 14.0
    cell_pad_x: float = 8.0
    chevron_w: float = 12.0
    scroll: float = 0.0
    fill_background: bool = True

    def visible_row_range(self) -> tuple[int, int]:
        if self.row_height <= 0:
            return (0, 0)
        start = max(0, int(self.scroll))
        n = int(self.h / self.row_height) + 1
        return (start, min(len(self.rows), start + n))

    def paint(self, dl: Any) -> None:
        t = current_theme()
        if self.fill_background:
            dl.fill_path(
                _rounded_rect(self.x, self.y, self.w, self.h,
                              t.radius_small),
                t.surface)
        s_start, s_end = self.visible_row_range()
        for i in range(s_start, s_end):
            row = self.rows[i]
            yy = self.y + (i - s_start) * self.row_height
            if row.selected:
                dl.fill_path(
                    _rounded_rect(self.x + 2, yy, self.w - 4,
                                  self.row_height - 1, 3),
                    with_alpha(t.primary, 0.18))
            x0 = self.x + self.cell_pad_x + row.depth * self.indent
            if row.expandable:
                cx = x0 + self.chevron_w / 2
                cy = yy + self.row_height / 2
                if row.expanded:
                    d = (f"M {cx - 4} {cy - 2} L {cx + 4} {cy - 2} "
                         f"L {cx} {cy + 3} Z")
                else:
                    d = (f"M {cx - 2} {cy - 4} L {cx + 3} {cy} "
                         f"L {cx - 2} {cy + 4} Z")
                dl.fill_path(d, t.on_surface)
                x0 += self.chevron_w + 2
            if row.icon_color is not None:
                dl.fill_path(_circle(x0 + 4, yy + self.row_height / 2,
                                     3.0),
                             row.icon_color)
                x0 += 12
            dl.draw_text(
                row.label, x0,
                yy + self.row_height * 0.7,
                t.font_size_body * 0.95,
                t.on_surface if row.selected
                else with_alpha(t.on_surface, 0.85))

    def hit_test_row(self, mx: float, my: float
                     ) -> tuple[str, str] | None:
        """Return ``(row_id, hit_kind)`` where ``hit_kind`` is
        ``"chevron"`` for the expand toggle area or ``"label"`` for the
        rest of the row. Returns ``None`` when the point is outside
        the tree or below the visible rows."""
        if not (self.x <= mx <= self.x + self.w
                and self.y <= my <= self.y + self.h):
            return None
        s_start, _ = self.visible_row_range()
        i = s_start + int((my - self.y) / self.row_height)
        if not (0 <= i < len(self.rows)):
            return None
        row = self.rows[i]
        x0 = self.x + self.cell_pad_x + row.depth * self.indent
        if row.expandable and x0 <= mx <= x0 + self.chevron_w:
            return (row.id, "chevron")
        return (row.id, "label")


# ---------------------------------------------------------------------------
# NumericField — TextField-style numeric input with Maya scrub-on-drag.
# ---------------------------------------------------------------------------

@dataclass
class NumericField(Component):
    """Numeric input field with scrub-on-drag (Maya-style horizontal
    drag on the label scrubs the value). API:

        nf = NumericField(label="X", value=1.0, step=0.1,
                          min_value=0.0, max_value=10.0,
                          on_change=lambda v: ...)
        nf.update(dt, {"hover": hover, "focused": focused})
        nf.paint(dl)
        if drag_started and nf.hit_test(*cursor):
            nf.scrub_start(*cursor)
        if dragging: nf.scrub_drag(*cursor)
        if drag_released: nf.scrub_end()

    The text representation is built by ``format.format(value)``. If
    that fails (custom format strings + edge values) the raw ``repr``
    is used.

    Spec source: §6.3 (80 LOC + tests).
    """
    value: float = 0.0
    label: str = ""
    on_change: Callable[[float], None] | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float = 1.0
    format: str = "{:.2f}"
    scrub_sensitivity: float = 1.0
    _scrub_origin: tuple[float, float] | None = field(
        default=None, init=False, repr=False)
    _scrub_value:  float = field(default=0.0, init=False, repr=False)

    def _format_value(self) -> str:
        try:
            return self.format.format(self.value)
        except Exception:
            return repr(self.value)

    def paint(self, dl: Any) -> None:
        t = current_theme()
        r = t.radius_small
        dl.fill_path(
            _rounded_rect(self.x, self.y, self.w, self.h, r),
            mix(t.surface, t.on_surface, 0.05))
        if self.label:
            dl.draw_text(self.label, self.x + 8,
                         self.y + self.h * 0.66,
                         t.font_size_body * 0.9,
                         with_alpha(t.on_surface, 0.7))
        vtxt = self._format_value()
        approx_w = len(vtxt) * t.font_size_body * 0.55
        dl.draw_text(vtxt,
                     self.x + self.w - approx_w - 8,
                     self.y + self.h * 0.66,
                     t.font_size_body, t.on_surface)
        if self._hover_t > 0.01 or self._focus_t > 0.01:
            outline = mix(with_alpha(t.primary, 0.0),
                          with_alpha(t.primary, 0.55),
                          max(self._hover_t, self._focus_t))
            dl.stroke_path(
                _rounded_rect(self.x + 0.5, self.y + 0.5,
                              self.w - 1, self.h - 1, r),
                outline, 1.0)

    def scrub_start(self, mx: float, my: float) -> None:
        self._scrub_origin = (mx, my)
        self._scrub_value = self.value

    def scrub_drag(self, mx: float, my: float) -> None:
        if self._scrub_origin is None:
            return
        dx = mx - self._scrub_origin[0]
        new = self._scrub_value + dx * self.step * self.scrub_sensitivity
        if self.min_value is not None:
            new = max(new, self.min_value)
        if self.max_value is not None:
            new = min(new, self.max_value)
        if new != self.value:
            self.value = new
            if self.on_change is not None:
                self.on_change(new)

    def scrub_end(self) -> None:
        self._scrub_origin = None


# ---------------------------------------------------------------------------
# FAB — floating action button.
# ---------------------------------------------------------------------------

@dataclass
class FAB(Component):
    """Floating Action Button. Circular, drop-shadowed, primary-tinted
    trigger meant for the canonical "one big action" placement
    (bottom-right corner). Designed for the Aether trigger in the
    Elysium Designer  the Designer wires ``on_click`` to a flyout
    toggle (§12 answer 5).

    Hit-test is circular, not bbox.

    Spec source: §6.4 (60 LOC + tests).
    """
    icon: str = ""
    tooltip: str = ""
    on_click: Callable[[], None] | None = None
    variant: str = "primary"        # "primary" | "accent" | "surface"
    fill_color: Color | None = None
    icon_color: Color | None = None
    icon_size: float = 18.0

    def hit_test(self, mx: float, my: float) -> bool:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r = min(self.w, self.h) / 2
        return (mx - cx) ** 2 + (my - cy) ** 2 <= (r + 2) ** 2

    def paint(self, dl: Any) -> None:
        t = current_theme()
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r = min(self.w, self.h) / 2
        scale = 1.0 + 0.07 * self._hover_t - 0.05 * self._press_t
        r_eff = max(2.0, r * scale)
        base = (self.fill_color if self.fill_color is not None else
                {"primary": t.primary, "accent": t.accent,
                 "surface": t.surface}.get(self.variant, t.primary))
        top = lighten(base, 0.10)
        bot = base
        s = t.shadow_medium
        shadow_off = (s.offset[0], s.offset[1] + 4.0 * self._hover_t
                      - 2.0 * self._press_t)
        shadow_strength = 0.6 + 0.4 * self._hover_t
        dl.gradient_card(
            cx - r_eff, cy - r_eff, r_eff * 2, r_eff * 2, r_eff,
            top, bot,
            s.blur * (0.7 + 0.5 * self._hover_t), shadow_off,
            with_alpha(s.color,
                        (s.color[3] / 255.0) * shadow_strength))
        if self.icon:
            ic = (self.icon_color if self.icon_color is not None
                  else (t.on_primary if self.variant == "primary"
                        else (255, 255, 255, 255)))
            approx_w = len(self.icon) * self.icon_size * 0.55
            dl.draw_text(self.icon,
                         cx - approx_w / 2,
                         cy + self.icon_size * 0.32,
                         self.icon_size,
                         with_alpha(ic, 1.0 - 0.4 * self._disabled_t))

    def fire_click(self) -> None:
        if self.on_click is not None:
            self.on_click()


# ---------------------------------------------------------------------------
# RadialPopover — radial marking menu.
# ---------------------------------------------------------------------------

@dataclass
class RadialPopover(Component):
    """Radial marking menu  Maya-style donut of wedges around a
    centre point. Author the items as ``(id, label)`` pairs; the
    component lays them out at evenly-spaced angles starting at the
    top (12 o'clock) and going clockwise. Set ``visible=True`` to
    animate it in.

    Spec source: §6.2 (100 LOC + tests).
    """
    items: list[tuple[str, str]] = field(default_factory=list)
    visible: bool = False
    on_select: Callable[[str], None] | None = None
    radius: float = 80.0
    inner_radius: float = 24.0
    selected_id: str | None = None
    _vis_t: float = field(default=0.0, init=False, repr=False)

    def update(self, dt: float, state: ComponentState) -> None:
        super().update(dt, state)
        target = 1.0 if self.visible else 0.0
        self._vis_t = current_theme().motion.step(
            self._vis_t, target, dt, "hover_rate")

    def hit_test_item(self, mx: float, my: float) -> str | None:
        if not self.items:
            return None
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        dx, dy = mx - cx, my - cy
        d = (dx * dx + dy * dy) ** 0.5
        if not (self.inner_radius <= d <= self.radius):
            return None
        n = len(self.items)
        ang = math.atan2(dy, dx) + math.pi / 2     # 0 at top
        if ang < 0:
            ang += 2 * math.pi
        seg = 2 * math.pi / n
        i = int((ang + seg / 2) / seg) % n
        return self.items[i][0]

    def paint(self, dl: Any) -> None:
        if self._vis_t < 0.01 or not self.items:
            return
        t = current_theme()
        n = len(self.items)
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        outer = self.radius * (0.85 + 0.15 * self._vis_t)
        inner = self.inner_radius
        seg = 2 * math.pi / n
        for i, (item_id, label) in enumerate(self.items):
            am = -math.pi / 2 + i * seg
            a0 = am - seg / 2
            a1 = am + seg / 2
            x0o = cx + outer * math.cos(a0); y0o = cy + outer * math.sin(a0)
            x1o = cx + outer * math.cos(a1); y1o = cy + outer * math.sin(a1)
            x0i = cx + inner * math.cos(a1); y0i = cy + inner * math.sin(a1)
            x1i = cx + inner * math.cos(a0); y1i = cy + inner * math.sin(a0)
            large = 1 if seg > math.pi else 0
            d = (f"M {x0o} {y0o} A {outer} {outer} 0 {large} 1 "
                 f"{x1o} {y1o} L {x0i} {y0i} A {inner} {inner} 0 "
                 f"{large} 0 {x1i} {y1i} Z")
            sel = (self.selected_id == item_id)
            fill = with_alpha(
                t.primary if sel else t.surface,
                (0.9 if sel else 0.94) * self._vis_t)
            dl.fill_path(d, fill)
            dl.stroke_path(d,
                           with_alpha(t.edge,
                                      0.7 * self._vis_t), 1.0)
            lx = cx + (inner + outer) * 0.5 * math.cos(am)
            ly = cy + (inner + outer) * 0.5 * math.sin(am)
            approx_w = len(label) * t.font_size_body * 0.55
            txt_col = (t.on_primary if sel
                       else with_alpha(t.on_surface, self._vis_t))
            dl.draw_text(label, lx - approx_w / 2, ly + 4,
                         t.font_size_body, txt_col)


__all__ = [
    "Component", "ComponentState", "Ripple",
    "Label", "Button", "IconCloseButton",
    "Card", "Toggle", "Slider", "TextField", "ProgressBar", "Stack",
    # Phase 2.5 expansion:
    "Checkbox", "Radio", "TextArea", "Divider", "Badge", "Avatar", "Chip",
    "Spinner", "Tooltip", "Tabs", "Modal", "Toast", "Dropdown", "Menu",
    "MenuItem", "Popover", "Accordion", "ComboBox", "Pagination",
    "Breadcrumb", "CommandPalette", "Snackbar",
    # Phase 3 (self-host) expansion:
    "Tree", "TreeRow", "NumericField", "FAB", "RadialPopover",
    "IconButton", "GlyphAtlas", "get_default_atlas",
]
