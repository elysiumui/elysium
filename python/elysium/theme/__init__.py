"""Phase 2.5 theme engine.

A `Theme` is a bundle of semantic colours + radii + shadow + motion
defaults that every component reads from. Apps can pick a built-in
theme (`light`, `midnight_glass`, `frost`, `dark`) or build one from
a single primary colour via `Theme.from_primary(...)`.

    from elysium.theme import set_theme, midnight_glass
    set_theme(midnight_glass())

Components consult `current_theme()` during paint, so a single
`set_theme(...)` recolours the entire UI on the next frame.
"""
from __future__ import annotations

import colorsys
import math
import threading
from dataclasses import dataclass, field, replace
from typing import Tuple

Color = Tuple[int, int, int, int]


# --- OKLCH / OKLab color science ------------------------------------------
# Implementation per https://bottosson.github.io/posts/oklab/  — Björn
# Ottosson's perceptually uniform color space. Mixing in OKLCH preserves
# vivid hues across the interpolation (sRGB mid-points go muddy grey).

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (max(c, 0.0) ** (1.0 / 2.4)) - 0.055


def rgb_to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
    R = _srgb_to_linear(r / 255.0)
    G = _srgb_to_linear(g / 255.0)
    B = _srgb_to_linear(b / 255.0)
    l = 0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B
    m = 0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B
    s = 0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B
    l_, m_, s_ = l ** (1/3), m ** (1/3), s ** (1/3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(L: float, a: float, b: float) -> tuple[int, int, int]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    R =  4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    G = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    B = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (
        max(0, min(255, int(_linear_to_srgb(R) * 255))),
        max(0, min(255, int(_linear_to_srgb(G) * 255))),
        max(0, min(255, int(_linear_to_srgb(B) * 255))),
    )


def hsla(h: float, s: float, lightness: float, a: float = 1.0) -> Color:
    """HSL → RGBA tuple. `h` in [0, 360), s/lightness/a in [0, 1]."""
    r, g, b = colorsys.hls_to_rgb(h / 360.0, lightness, s)
    return (int(r * 255), int(g * 255), int(b * 255), int(a * 255))


def mix(a, b, t: float) -> Color:
    """Perceptually-uniform lerp via OKLab. `t=0` → a, `t=1` → b.
    Alpha is mixed linearly — only the chromatic channels go through OKLab.
    Accepts 3- or 4-tuples on either side."""
    t = max(0.0, min(1.0, t))
    aL, aa, ab = rgb_to_oklab(a[0], a[1], a[2])
    bL, ba, bb = rgb_to_oklab(b[0], b[1], b[2])
    L = aL * (1 - t) + bL * t
    A = aa * (1 - t) + ba * t
    B = ab * (1 - t) + bb * t
    r, g, b_ = oklab_to_rgb(L, A, B)
    a_a = a[3] if len(a) >= 4 else 255
    b_a = b[3] if len(b) >= 4 else 255
    return (r, g, b_, int(a_a * (1 - t) + b_a * t))


def with_alpha(c: Color, alpha: float) -> Color:
    return (c[0], c[1], c[2], max(0, min(255, int(alpha * 255))))


def lighten(c, amount: float) -> Color:
    """Shift the OKLab L channel by `amount` (positive → lighter).
    Accepts a 3- or 4-tuple."""
    L, a, b = rgb_to_oklab(c[0], c[1], c[2])
    L = max(0.0, min(1.0, L + amount))
    r, g, b_ = oklab_to_rgb(L, a, b)
    alpha = c[3] if len(c) >= 4 else 255
    return (r, g, b_, alpha)


def darken(c: Color, amount: float) -> Color:
    return lighten(c, -amount)


@dataclass(frozen=True)
class Shadow:
    blur: float
    offset: tuple[float, float]
    color: Color


@dataclass(frozen=True)
class MotionPreset:
    """Per-state easing rates (1/s). Larger = snappier."""
    hover_rate: float = 18.0       # ~80% in 100 ms
    press_rate: float = 24.0       # ~80% in 75 ms — punchier
    focus_rate: float = 14.0
    value_rate: float = 16.0       # for slider value etc.

    def step(self, current: float, target: float, dt: float, rate_attr: str = "hover_rate") -> float:
        """Critically-damped exponential approach. Frame-rate independent."""
        import math
        rate = getattr(self, rate_attr)
        return current + (target - current) * (1.0 - math.exp(-dt * rate))


@dataclass(frozen=True)
class Theme:
    """A complete visual + motion contract for the component library."""
    name: str
    is_dark: bool

    # Semantic palette.
    primary: Color
    on_primary: Color
    accent: Color
    on_accent: Color
    surface: Color
    surface_variant: Color
    on_surface: Color
    on_surface_muted: Color
    edge: Color           # subtle borders
    overlay: Color        # backdrop scrim
    success: Color
    warning: Color
    danger: Color

    # Visual defaults.
    radius_small: float = 6.0
    radius_medium: float = 12.0
    radius_large: float = 20.0

    shadow_close:  Shadow = field(default_factory=lambda: Shadow(blur=8.0,  offset=(0.0, 2.0),  color=(0, 0, 0, 60)))
    shadow_medium: Shadow = field(default_factory=lambda: Shadow(blur=16.0, offset=(0.0, 6.0),  color=(0, 0, 0, 80)))
    shadow_far:    Shadow = field(default_factory=lambda: Shadow(blur=36.0, offset=(0.0, 18.0), color=(0, 0, 0, 100)))

    # Motion.
    motion: MotionPreset = field(default_factory=MotionPreset)

    # Typography.
    font_size_caption: float = 11.0
    font_size_body:    float = 14.0
    font_size_title:   float = 18.0
    font_size_display: float = 28.0
    font_family:       str = ""        # "" → platform default UI font

    # Spacing scale (8px-grid based) — components pull padding/gaps from here
    # instead of hard-coding, so density is themeable.
    space_xs: float = 4.0
    space_sm: float = 8.0
    space_md: float = 12.0
    space_lg: float = 16.0
    space_xl: float = 24.0

    # State opacities — disabled dimming, hover wash, focus-ring strength.
    opacity_disabled: float = 0.40
    opacity_hover:    float = 0.08
    opacity_focus:    float = 0.40

    # Hover / pressed colour deltas — components mix toward these.
    def hover_color(self, base: Color) -> Color:
        return lighten(base, 0.06 if not self.is_dark else 0.08)

    def pressed_color(self, base: Color) -> Color:
        return darken(base, 0.08)

    @staticmethod
    def from_primary(primary: Color, *, dark: bool = False, name: str = "custom") -> "Theme":
        """Derive a full palette from a single primary colour via HSL math."""
        ph, pl, ps = colorsys.rgb_to_hls(primary[0] / 255.0, primary[1] / 255.0, primary[2] / 255.0)
        deg_h = ph * 360.0

        if dark:
            surface         = hsla(deg_h, 0.10, 0.08, 1.0)
            surface_variant = hsla(deg_h, 0.12, 0.16, 1.0)
            on_surface      = hsla(deg_h, 0.08, 0.94, 1.0)
            on_surface_mut  = hsla(deg_h, 0.06, 0.62, 1.0)
            edge            = hsla(deg_h, 0.16, 0.22, 1.0)
            overlay         = (0, 0, 0, 160)
        else:
            surface         = hsla(deg_h, 0.04, 0.99, 1.0)
            surface_variant = hsla(deg_h, 0.10, 0.95, 1.0)
            on_surface      = hsla(deg_h, 0.18, 0.10, 1.0)
            on_surface_mut  = hsla(deg_h, 0.08, 0.42, 1.0)
            edge            = hsla(deg_h, 0.12, 0.88, 1.0)
            overlay         = (0, 0, 0, 80)

        on_primary = (255, 255, 255, 255) if pl < 0.6 else (0, 0, 0, 255)
        accent_hue = (deg_h + 28.0) % 360.0
        accent = hsla(accent_hue, min(0.95, ps + 0.05), pl, 1.0)
        on_accent = (255, 255, 255, 255) if pl < 0.6 else (0, 0, 0, 255)

        return Theme(
            name=name, is_dark=dark,
            primary=primary, on_primary=on_primary,
            accent=accent, on_accent=on_accent,
            surface=surface, surface_variant=surface_variant,
            on_surface=on_surface, on_surface_muted=on_surface_mut,
            edge=edge, overlay=overlay,
            success=hsla(140.0, 0.55, 0.45, 1.0),
            warning=hsla(36.0,  0.85, 0.55, 1.0),
            danger=hsla(0.0,    0.70, 0.55, 1.0),
        )


# ---------------------------------------------------------------------------
# Built-in themes.
# ---------------------------------------------------------------------------

def light() -> Theme:
    """Default Elysium Light — iris primary, near-white surface."""
    return Theme.from_primary((0x5B, 0x3F, 0xF5, 0xFF), dark=False, name="Elysium Light")


def dark() -> Theme:
    """Default Elysium Dark — iris primary on a deep indigo surface."""
    return Theme.from_primary((0x73, 0x5C, 0xFF, 0xFF), dark=True, name="Elysium Dark")


def midnight_glass() -> Theme:
    """Premium dark glassmorphic theme. Translucent surface, generous shadows."""
    base = Theme.from_primary((0x6B, 0xC6, 0xFF, 0xFF), dark=True, name="Midnight Glass")
    return replace(
        base,
        # Slightly more translucent surface for glass effect over backdrops.
        surface=(0x0E, 0x0B, 0x1A, 0xE0),
        surface_variant=(0x18, 0x14, 0x2C, 0xE6),
        edge=(0xFF, 0xFF, 0xFF, 0x14),
        radius_medium=14.0,
        radius_large=22.0,
        shadow_far=Shadow(blur=48.0, offset=(0.0, 22.0), color=(0, 0, 0, 140)),
    )


def frost() -> Theme:
    """Premium light glassmorphic theme. Bright, soft, airy."""
    base = Theme.from_primary((0x29, 0x8C, 0xFF, 0xFF), dark=False, name="Frost")
    return replace(
        base,
        surface=(0xFA, 0xFC, 0xFF, 0xF0),
        surface_variant=(0xE8, 0xF1, 0xFC, 0xF0),
        edge=(0x29, 0x8C, 0xFF, 0x24),
        radius_medium=14.0,
        radius_large=22.0,
    )


def oled() -> Theme:
    """OLED true-black dark theme. Background is pure #000 so pixels turn
    off on OLED panels; surfaces are 4–8% luminance glass overlays."""
    base = Theme.from_primary((0x8E, 0x6B, 0xFF, 0xFF), dark=True, name="OLED")
    return replace(
        base,
        surface=(0x00, 0x00, 0x00, 0xFF),         # true black
        surface_variant=(0x0A, 0x0A, 0x10, 0xFF), # ~4% luminance
        on_surface=(0xF2, 0xF2, 0xF5, 0xFF),
        on_surface_muted=(0xA0, 0xA0, 0xB0, 0xFF),
        edge=(0xFF, 0xFF, 0xFF, 0x1A),
        radius_medium=14.0,
        radius_large=22.0,
        shadow_close=Shadow(blur=6.0,  offset=(0.0, 2.0), color=(0, 0, 0, 200)),
        shadow_medium=Shadow(blur=18.0, offset=(0.0, 8.0), color=(0, 0, 0, 220)),
        shadow_far=Shadow(blur=56.0, offset=(0.0, 24.0), color=(0, 0, 0, 240)),
    )


def studio_dark() -> Theme:
    """Studio — clean professional dark. Slate-neutral surfaces, one confident
    iris accent, hairline edges, crisp 8px radii, roomy 8px-grid spacing. The
    Designer's default look and the recommended app theme."""
    base = Theme.from_primary((0x6C, 0x7C, 0xFF, 0xFF), dark=True, name="Studio Dark")
    return replace(
        base,
        surface=(0x1B, 0x1E, 0x24, 0xFF),
        surface_variant=(0x2A, 0x2F, 0x39, 0xFF),
        on_surface=(0xE8, 0xEB, 0xF0, 0xFF),
        on_surface_muted=(0x9A, 0xA3, 0xB2, 0xFF),
        edge=(0x2C, 0x32, 0x3C, 0xFF),
        overlay=(0x0A, 0x0C, 0x10, 0xB0),
        accent=(0x8A, 0x78, 0xFF, 0xFF),
        radius_small=5.0, radius_medium=8.0, radius_large=14.0,
        shadow_close=Shadow(blur=6.0, offset=(0.0, 1.0), color=(0, 0, 0, 70)),
        shadow_medium=Shadow(blur=14.0, offset=(0.0, 4.0), color=(0, 0, 0, 90)),
        shadow_far=Shadow(blur=30.0, offset=(0.0, 14.0), color=(0, 0, 0, 120)),
        font_family="Inter",
    )


def studio_light() -> Theme:
    """Studio — clean professional light (the 'Daylight' variant). Bright
    neutral surfaces, soft edges, the same crisp 8px geometry."""
    base = Theme.from_primary((0x5B, 0x3F, 0xF5, 0xFF), dark=False, name="Studio Light")
    return replace(
        base,
        surface=(0xF6, 0xF8, 0xFB, 0xFF),
        surface_variant=(0xFF, 0xFF, 0xFF, 0xFF),
        on_surface=(0x2A, 0x33, 0x42, 0xFF),
        on_surface_muted=(0x6B, 0x74, 0x84, 0xFF),
        edge=(0xDF, 0xE4, 0xEC, 0xFF),
        radius_small=5.0, radius_medium=8.0, radius_large=14.0,
        font_family="Inter",
    )


# ---------------------------------------------------------------------------
# Global current-theme.
# ---------------------------------------------------------------------------

_current_lock = threading.Lock()
_current: Theme = light()


def current_theme() -> Theme:
    with _current_lock:
        return _current


def set_theme(theme: Theme) -> None:
    """Swap the active theme. Components paint with the new theme on next frame.
    Also applies the theme's ``font_family`` app-wide (best-effort)."""
    global _current
    with _current_lock:
        _current = theme
    if theme.font_family:
        try:
            set_ui_font(theme.font_family)
        except Exception:
            pass


def set_ui_font(spec: str) -> bool:
    """Set the app-wide UI font. ``spec`` is either a family name (matched
    against installed fonts) or a path to a ``.ttf``/``.otf`` file to register
    so it renders regardless of what's installed. Returns True if a font file
    was successfully registered; setting a family name always returns True.
    No-op (returns False) when the native extension is unavailable."""
    try:
        from elysium._native import _native as _n  # type: ignore[attr-defined]
    except Exception:
        return False
    import os
    if (os.sep in spec or (os.altsep and os.altsep in spec)
            or spec.lower().endswith((".ttf", ".otf"))):
        try:
            return bool(_n.register_ui_font(spec))
        except Exception:
            return False
    try:
        _n.set_ui_font(spec)
    except Exception:
        return False
    return True


__all__ = [
    "Color", "Theme", "Shadow", "MotionPreset",
    "hsla", "mix", "with_alpha", "lighten", "darken",
    "light", "dark", "oled", "midnight_glass", "frost",
    "studio_dark", "studio_light",
    "current_theme", "set_theme", "set_ui_font",
]
