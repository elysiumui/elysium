"""Procedural Blue Morpho butterfly rendered with Skia paths.

Drawn entirely from gradients + bezier outlines + thin veins; no raster
asset. The geometry is parameterised by `flap_t` ∈ [0, 1] so the wings
can be animated by interpolating their horizontal scale.

Reference: the Blue Morpho photograph that motivated this demo —
bright iridescent blue inner wings, deep purple shading toward the
body, dark veining along radial lines, and an orange/white spotted
margin around the outer edge.

The butterfly is centered in a `(width, height)` canvas; geometry is
expressed in canvas coordinates so the same code paints offscreen
goldens and the live animated window.
"""
from __future__ import annotations

import math
from typing import Iterable

# --- Palette — Blue Morpho species characteristics. -------------------------
# (Procedural stylisation, not a trace of any specific photograph.)
HIGHLIGHT_BLUE       = (0x6B, 0xC6, 0xFF, 0xFF)   # metallic shine
IRIDESCENT_BLUE      = (0x29, 0x8C, 0xFF, 0xFF)   # core wing colour
DEEPER_BLUE          = (0x14, 0x49, 0xCC, 0xFF)   # outer edge of upper wing
ROYAL_PURPLE         = (0x35, 0x16, 0x70, 0xFF)   # body-side shadow (deeper)
DARK_PURPLE          = (0x12, 0x04, 0x28, 0xFF)   # wing-tip darkening
MARGIN_BAND          = (0x3A, 0x1C, 0x10, 0xFF)   # dark brown band along outer edge
EDGE_BROWN           = (0x1A, 0x0B, 0x05, 0xFF)   # outermost wing edge (near black)
HIGHLIGHT_WHITE      = (0xFF, 0xFA, 0xEE, 0xFF)   # cream highlight spots
SPOT_ORANGE          = (0xFF, 0x9F, 0x42, 0xFF)   # orange margin spots
SPOT_CREAM           = (0xF7, 0xE8, 0xC8, 0xFF)
VEIN_BLACK           = (0x08, 0x04, 0x10, 0xE0)   # dark veins
VEIN_FINE            = (0x12, 0x08, 0x18, 0xA0)   # thinner cross-veins
BODY_BROWN           = (0x1F, 0x0E, 0x06, 0xFF)
BODY_HIGHLIGHT       = (0x6B, 0x40, 0x22, 0xFF)
BODY_FUZZ            = (0x4A, 0x2C, 0x18, 0xC0)


def _left_upper_wing(cx: float, cy: float, scale_x: float, scale_y: float, flap: float) -> str:
    """Forewing outline — wider, rounder tip, gentler concave trailing edge."""
    span = 480.0 * scale_x * flap
    anchor_y = cy - 100.0 * scale_y
    # Top "leading edge" arcs up-and-out.
    top_x  = cx - span * 0.55
    top_y  = cy - 200.0 * scale_y
    # Rounded outer tip — slightly drooping for the natural sweep.
    tip_x  = cx - span
    tip_y  = cy - 130.0 * scale_y
    # Inner trailing edge bottom (where it meets the hindwing).
    inner_x = cx - span * 0.25
    inner_y = cy + 40.0 * scale_y
    return (
        f"M {cx - 18 * scale_x} {anchor_y} "
        # Leading edge: smooth arc up and out toward the top.
        f"C {cx - span * 0.30} {anchor_y - 90 * scale_y}, "
        f"  {top_x - 30 * scale_x} {top_y - 30 * scale_y}, "
        f"  {top_x} {top_y} "
        # Curve around the rounded tip.
        f"C {top_x - 80 * scale_x} {top_y - 5 * scale_y}, "
        f"  {tip_x + 10 * scale_x} {tip_y - 50 * scale_y}, "
        f"  {tip_x} {tip_y} "
        f"C {tip_x + 30 * scale_x} {tip_y + 30 * scale_y}, "
        f"  {tip_x + 50 * scale_x} {tip_y + 80 * scale_y}, "
        f"  {cx - span * 0.6} {inner_y - 30 * scale_y} "
        # Concave trailing edge back to body.
        f"C {inner_x - 40 * scale_x} {inner_y - 10 * scale_y}, "
        f"  {cx - 30 * scale_x} {cy - 20 * scale_y}, "
        f"  {cx - 18 * scale_x} {anchor_y} Z"
    )


def _left_lower_wing(cx: float, cy: float, scale_x: float, scale_y: float, flap: float) -> str:
    """Hindwing — broader than the forewing, scalloped trailing edge."""
    span = 380.0 * scale_x * flap
    anchor_y = cy + 40.0 * scale_y
    # Outer tip of the hindwing.
    tip_x = cx - span * 0.95
    tip_y = cy + 140.0 * scale_y
    # Bottom of the trailing edge (closest to abdomen).
    bottom_x = cx - span * 0.30
    bottom_y = cy + 280.0 * scale_y
    return (
        f"M {cx - 18 * scale_x} {anchor_y} "
        # Top edge: a long, gentle arc out to the tip.
        f"C {cx - span * 0.55} {anchor_y - 30 * scale_y}, "
        f"  {tip_x + 30 * scale_x} {tip_y - 90 * scale_y}, "
        f"  {tip_x} {tip_y} "
        # Around the rounded outer edge with two slight scallops.
        f"C {tip_x + 20 * scale_x} {tip_y + 50 * scale_y}, "
        f"  {tip_x + 30 * scale_x} {tip_y + 110 * scale_y}, "
        f"  {cx - span * 0.55} {tip_y + 130 * scale_y} "
        f"C {cx - span * 0.45} {tip_y + 145 * scale_y}, "
        f"  {bottom_x - 30 * scale_x} {bottom_y - 10 * scale_y}, "
        f"  {bottom_x} {bottom_y} "
        # Trailing edge back to body.
        f"C {bottom_x + 30 * scale_x} {bottom_y - 30 * scale_y}, "
        f"  {cx - 10 * scale_x} {anchor_y + 100 * scale_y}, "
        f"  {cx - 18 * scale_x} {anchor_y} Z"
    )


def _wing_veins(cx: float, cy: float, scale: float, flap: float) -> Iterable[tuple[str, float]]:
    """Radiating veins from the body outward; yields (path, stroke_width)."""
    base_x = cx - 18 * scale
    base_y = cy - 60 * scale

    # Upper wing — main radial veins (thicker).
    upper_main = [
        (0.98, -218, 1.6),  # leading edge / tip
        (0.92, -180, 1.4),
        (0.85, -140, 1.4),
        (0.76, -100, 1.4),
        (0.66,  -60, 1.4),
        (0.55,  -28, 1.3),
        (0.43,    0, 1.3),
        (0.30,   20, 1.2),
        (0.18,   28, 1.2),
    ]
    for t, dy, w in upper_main:
        tx = cx - t * 460 * scale * flap
        ty = cy + dy * scale
        ctrl_x = (base_x + tx) * 0.5
        ctrl_y = base_y - 30 * scale
        yield (f"M {base_x} {base_y} Q {ctrl_x} {ctrl_y} {tx} {ty}", w * scale)

    # Upper wing — fine cross-veins between the main ones.
    for i in range(len(upper_main) - 1):
        t1, dy1, _ = upper_main[i]
        t2, dy2, _ = upper_main[i + 1]
        # Two short cross-veins per gap.
        for f in (0.4, 0.7):
            x1 = cx - (t1 * f + 0.05) * 460 * scale * flap
            y1 = cy + dy1 * scale * f
            x2 = cx - (t2 * f + 0.05) * 460 * scale * flap
            y2 = cy + dy2 * scale * f
            yield (f"M {x1} {y1} L {x2} {y2}", 0.6 * scale)

    # Lower wing — main veins (radiating from base of thorax).
    lower_base_y = cy + 40 * scale
    lower_main = [
        (0.95, 170, 1.5),
        (0.85, 220, 1.4),
        (0.70, 260, 1.4),
        (0.50, 280, 1.4),
        (0.30, 280, 1.3),
        (0.13, 265, 1.2),
        (0.03, 230, 1.1),
    ]
    for t, dy, w in lower_main:
        tx = cx - t * 360 * scale * flap
        ty = cy + dy * scale
        ctrl_x = (base_x + tx) * 0.5
        ctrl_y = lower_base_y + 60 * scale
        yield (f"M {base_x} {lower_base_y} Q {ctrl_x} {ctrl_y} {tx} {ty}", w * scale)

    # Lower wing — cross-veins.
    for i in range(len(lower_main) - 1):
        t1, dy1, _ = lower_main[i]
        t2, dy2, _ = lower_main[i + 1]
        for f in (0.5, 0.8):
            x1 = cx - t1 * f * 360 * scale * flap
            y1 = cy + (dy1 * f + 40) * scale
            x2 = cx - t2 * f * 360 * scale * flap
            y2 = cy + (dy2 * f + 40) * scale
            yield (f"M {x1} {y1} L {x2} {y2}", 0.6 * scale)


def _wing_margin_spots(cx: float, cy: float, scale: float, flap: float) -> Iterable[tuple[float, float, float, tuple[int,int,int,int]]]:
    """Pale spots in two parallel rows along the wing margin (Blue Morpho
    characteristic). Yields (x, y, radius, color) tuples."""
    # Upper wing: outer row of cream dots, inner row of smaller dark dots.
    upper_outer = [(0.97, -200), (0.92, -150), (0.85, -100), (0.78, -55), (0.70, -20)]
    for t, dy in upper_outer:
        x = cx - t * 460 * scale * flap + 6 * scale
        y = cy + dy * scale
        yield (x, y, 3.5 * scale, SPOT_CREAM)
    # Inner row (slightly inboard, smaller).
    for t, dy in upper_outer:
        x = cx - (t - 0.06) * 460 * scale * flap + 6 * scale
        y = cy + dy * scale + 10 * scale
        yield (x, y, 1.8 * scale, EDGE_BROWN)

    # Lower wing — bolder cream + orange dots along the scalloped trailing edge.
    lower_outer = [(0.92, 165), (0.78, 215), (0.60, 260), (0.40, 280), (0.22, 280), (0.08, 255)]
    for t, dy in lower_outer:
        x = cx - t * 360 * scale * flap + 8 * scale
        y = cy + dy * scale
        yield (x, y, 4.0 * scale, SPOT_CREAM)
    # Tiny orange + dark companion dots for visual richness.
    for t, dy in lower_outer:
        x = cx - (t - 0.05) * 360 * scale * flap + 8 * scale
        y = cy + dy * scale - 10 * scale
        yield (x, y, 2.2 * scale, SPOT_ORANGE)


def _body_path(cx: float, cy: float, scale: float) -> str:
    """Tapered body — head at top, plump thorax under the wings, abdomen
    tapering down. The head IS the top of the body (no separate sphere)."""
    head_y     = cy - 200 * scale
    thorax_y   = cy - 60 * scale
    abdomen_y  = cy + 250 * scale
    # Widest at the thorax (between the two wings).
    return (
        f"M {cx - 4 * scale} {head_y} "                       # left side of head
        f"C {cx - 8 * scale} {head_y + 30 * scale}, "
        f"  {cx - 16 * scale} {thorax_y - 30 * scale}, "
        f"  {cx - 17 * scale} {thorax_y} "                    # left thorax bulge
        f"C {cx - 18 * scale} {thorax_y + 60 * scale}, "
        f"  {cx - 10 * scale} {cy + 100 * scale}, "
        f"  {cx - 6 * scale}  {cy + 200 * scale} "
        f"C {cx - 4 * scale}  {abdomen_y - 20 * scale}, "
        f"  {cx - 2 * scale}  {abdomen_y - 10 * scale}, "
        f"  {cx} {abdomen_y} "                                # abdomen tip
        f"C {cx + 2 * scale}  {abdomen_y - 10 * scale}, "
        f"  {cx + 4 * scale}  {abdomen_y - 20 * scale}, "
        f"  {cx + 6 * scale}  {cy + 200 * scale} "
        f"C {cx + 10 * scale} {cy + 100 * scale}, "
        f"  {cx + 18 * scale} {thorax_y + 60 * scale}, "
        f"  {cx + 17 * scale} {thorax_y} "
        f"C {cx + 16 * scale} {thorax_y - 30 * scale}, "
        f"  {cx + 8 * scale}  {head_y + 30 * scale}, "
        f"  {cx + 4 * scale}  {head_y} "
        f"C {cx + 4 * scale}  {head_y - 8 * scale}, "
        f"  {cx - 4 * scale}  {head_y - 8 * scale}, "
        f"  {cx - 4 * scale}  {head_y} Z"
    )


def _antenna_paths(cx: float, cy: float, scale: float, flap: float) -> tuple[str, str]:
    """Two thin curved antennae sweeping outward + up from the head."""
    head_x = cx
    head_y = cy - 200 * scale
    spread = 1.0 + 0.25 * flap
    # The shape: from the head, gently curve outward and up. Length ~ 180 * scale.
    left = (
        f"M {head_x - 3 * scale} {head_y - 4 * scale} "
        f"C {head_x - 25 * scale * spread} {head_y - 60 * scale}, "
        f"  {head_x - 55 * scale * spread} {head_y - 130 * scale}, "
        f"  {head_x - 70 * scale * spread} {head_y - 175 * scale}"
    )
    right = (
        f"M {head_x + 3 * scale} {head_y - 4 * scale} "
        f"C {head_x + 25 * scale * spread} {head_y - 60 * scale}, "
        f"  {head_x + 55 * scale * spread} {head_y - 130 * scale}, "
        f"  {head_x + 70 * scale * spread} {head_y - 175 * scale}"
    )
    return left, right


def draw(layer, width: int, height: int, flap_t: float = 1.0, scale: float = 1.0) -> None:
    """Render the butterfly into a target with the SkiaLayer-compatible
    paint API: `clear`, `fill_path`, `fill_path_linear_gradient`,
    `fill_path_radial_gradient`, `stroke_path`, `save_with_transform`,
    `restore`. A SkiaLayer satisfies this; so does the DisplayList
    builder (via `push_transform` / `pop_transform`).

    `flap_t ∈ [0, 1]` — 0 is folded, 1 is fully open.
    """
    cx = width / 2.0
    cy = height / 2.0 + 30 * scale  # nudge down so antennae fit

    # Smooth ease so the bottom of the flap dwells slightly.
    flap = 0.55 + 0.45 * math.cos(math.pi * (1.0 - flap_t))
    # Map cosine result back to [0.1, 1.0] usable wing-open range.
    flap = max(0.1, min(1.0, (flap - 0.10) / 0.90))

    # --- Left wings -------------------------------------------------------
    up_path = _left_upper_wing(cx, cy, scale, scale, flap)
    lo_path = _left_lower_wing(cx, cy, scale, scale, flap)

    # Outer dark margin first — a slightly enlarged silhouette in EDGE_BROWN.
    layer.fill_path_linear_gradient(
        up_path,
        (cx, cy - 200 * scale),
        (cx - 460 * scale * flap, cy + 30 * scale),
        DEEPER_BLUE, EDGE_BROWN,
    )
    layer.fill_path_linear_gradient(
        lo_path,
        (cx, cy + 30 * scale),
        (cx - 360 * scale * flap, cy + 290 * scale),
        DEEPER_BLUE, EDGE_BROWN,
    )

    # Inner iridescent fill: bright cyan-blue near the body, fading to
    # deep blue at the margin. Radial gradient sells the iridescence.
    layer.fill_path_radial_gradient(
        up_path,
        (cx - 80 * scale, cy - 80 * scale),
        320 * scale * flap,
        IRIDESCENT_BLUE, DEEPER_BLUE,
    )
    layer.fill_path_radial_gradient(
        lo_path,
        (cx - 60 * scale, cy + 100 * scale),
        260 * scale * flap,
        IRIDESCENT_BLUE, ROYAL_PURPLE,
    )

    # Metallic highlight: a small bright spot in the upper-inner third of
    # each wing where the iridescent scales catch the light brightest.
    layer.fill_path_radial_gradient(
        up_path,
        (cx - 130 * scale * flap, cy - 110 * scale),
        140 * scale * flap,
        HIGHLIGHT_BLUE, (HIGHLIGHT_BLUE[0], HIGHLIGHT_BLUE[1], HIGHLIGHT_BLUE[2], 0),
    )
    layer.fill_path_radial_gradient(
        lo_path,
        (cx - 100 * scale * flap, cy + 80 * scale),
        110 * scale * flap,
        HIGHLIGHT_BLUE, (HIGHLIGHT_BLUE[0], HIGHLIGHT_BLUE[1], HIGHLIGHT_BLUE[2], 0),
    )

    # Deep purple shadow near body where wings join.
    body_shadow = (
        f"M {cx - 18 * scale} {cy - 200 * scale} "
        f"C {cx - 90 * scale} {cy - 80 * scale}, "
        f"  {cx - 80 * scale} {cy + 200 * scale}, "
        f"  {cx - 18 * scale} {cy + 280 * scale} L {cx - 18 * scale} {cy - 200 * scale} Z"
    )
    layer.fill_path_linear_gradient(
        body_shadow,
        (cx - 18 * scale, cy),
        (cx - 70 * scale, cy),
        (*ROYAL_PURPLE[:3], 0xA0),
        (*ROYAL_PURPLE[:3], 0x00),
    )

    # Wing veins.
    for v, w in _wing_veins(cx, cy, scale, flap):
        layer.stroke_path(v, VEIN_BLACK, max(0.6, w))

    # Margin spots (cream + orange + dark — Blue Morpho double-row pattern).
    for (sx, sy, sr, sc) in _wing_margin_spots(cx, cy, scale, flap):
        layer.fill_path(
            f"M {sx} {sy} m {-sr} 0 a {sr} {sr} 0 1 0 {sr*2} 0 a {sr} {sr} 0 1 0 {-sr*2} 0 Z",
            sc,
        )

    # --- Right wings: mirror the left side via canvas scale_x = -1 -------
    layer.save_with_transform(cx, 0.0, -1.0, 1.0, 0.0)
    up_path_r = _left_upper_wing(0.0, cy, scale, scale, flap)
    lo_path_r = _left_lower_wing(0.0, cy, scale, scale, flap)

    layer.fill_path_linear_gradient(
        up_path_r,
        (0.0, cy - 200 * scale),
        (-460 * scale * flap, cy + 30 * scale),
        DEEPER_BLUE, EDGE_BROWN,
    )
    layer.fill_path_linear_gradient(
        lo_path_r,
        (0.0, cy + 30 * scale),
        (-360 * scale * flap, cy + 290 * scale),
        DEEPER_BLUE, EDGE_BROWN,
    )
    layer.fill_path_radial_gradient(
        up_path_r,
        (-80 * scale, cy - 80 * scale),
        320 * scale * flap,
        IRIDESCENT_BLUE, DEEPER_BLUE,
    )
    layer.fill_path_radial_gradient(
        lo_path_r,
        (-60 * scale, cy + 100 * scale),
        260 * scale * flap,
        IRIDESCENT_BLUE, ROYAL_PURPLE,
    )
    body_shadow_r = (
        f"M {-18 * scale} {cy - 200 * scale} "
        f"C {-90 * scale} {cy - 80 * scale}, "
        f"  {-80 * scale} {cy + 200 * scale}, "
        f"  {-18 * scale} {cy + 280 * scale} L {-18 * scale} {cy - 200 * scale} Z"
    )
    layer.fill_path_linear_gradient(
        body_shadow_r,
        (-18 * scale, cy),
        (-70 * scale, cy),
        (*ROYAL_PURPLE[:3], 0xA0),
        (*ROYAL_PURPLE[:3], 0x00),
    )
    for v, w in _wing_veins(0.0, cy, scale, flap):
        layer.stroke_path(v, VEIN_BLACK, max(0.6, w))
    for (sx, sy, sr, sc) in _wing_margin_spots(0.0, cy, scale, flap):
        layer.fill_path(
            f"M {sx} {sy} m {-sr} 0 a {sr} {sr} 0 1 0 {sr*2} 0 a {sr} {sr} 0 1 0 {-sr*2} 0 Z",
            sc,
        )
    layer.restore()

    # --- Body (drawn on top so it overlaps both wings) -------------------
    body = _body_path(cx, cy, scale)
    # Dark base.
    layer.fill_path(body, BODY_BROWN)
    # A thin highlighted ridge down the centre for a 3D feel.
    ridge = (
        f"M {cx - 2 * scale} {cy - 200 * scale} "
        f"L {cx - 2 * scale} {cy + 280 * scale} "
        f"L {cx + 2 * scale} {cy + 280 * scale} "
        f"L {cx + 2 * scale} {cy - 200 * scale} Z"
    )
    layer.fill_path_linear_gradient(
        ridge,
        (cx - 5 * scale, cy),
        (cx + 5 * scale, cy),
        BODY_HIGHLIGHT, BODY_BROWN,
    )
    # Faint segment lines on the abdomen.
    for i in range(0, 8):
        y = cy + (40 + i * 30) * scale
        layer.stroke_path(
            f"M {cx - 9 * scale} {y} Q {cx} {y + 3 * scale} {cx + 9 * scale} {y}",
            (0, 0, 0, 0x80), 1.0,
        )

    # --- Antennae -------------------------------------------------------
    left_a, right_a = _antenna_paths(cx, cy, scale, flap)
    layer.stroke_path(left_a,  EDGE_BROWN, max(1.5, 2.0 * scale))
    layer.stroke_path(right_a, EDGE_BROWN, max(1.5, 2.0 * scale))
    # Antenna club tips (Blue Morpho has subtly clubbed antennae).
    spread = 1.0 + 0.25 * flap
    head_y = cy - 200 * scale
    tip_l_x = cx - 70 * scale * spread
    tip_r_x = cx + 70 * scale * spread
    tip_y   = head_y - 175 * scale
    layer.fill_path(
        f"M {tip_l_x} {tip_y} m -3 0 a 3 3 0 1 0 6 0 a 3 3 0 1 0 -6 0 Z",
        EDGE_BROWN,
    )
    layer.fill_path(
        f"M {tip_r_x} {tip_y} m -3 0 a 3 3 0 1 0 6 0 a 3 3 0 1 0 -6 0 Z",
        EDGE_BROWN,
    )

    # --- Tiny eye highlights -------------------------------------------
    eye_y = head_y + 10 * scale
    layer.fill_path(
        f"M {cx - 6 * scale} {eye_y} m -2 0 a 2 2 0 1 0 4 0 a 2 2 0 1 0 -4 0 Z",
        (0, 0, 0, 0xFF),
    )
    layer.fill_path(
        f"M {cx + 6 * scale} {eye_y} m -2 0 a 2 2 0 1 0 4 0 a 2 2 0 1 0 -4 0 Z",
        (0, 0, 0, 0xFF),
    )


# When this file is run as a standalone app (`python butterfly.py`),
# the host first imports `main.py` (which sits next to this file) and
# `main.py` constructs the App + window, exposes a module-level `win`,
# and then re-imports / re-executes this file's hook block. When this
# file is imported in isolation — e.g. by `tests/test_butterfly.py`
# which only calls `butterfly.draw(...)` — there is no real `win` in
# the namespace, so the `@win.on(...)` decorators below would raise
# `NameError` at import time. Define a no-op stub so importing the
# module always succeeds; the real `win` shadows this when the app
# host loads it.
if "win" not in globals():
    class _NoopWindow:
        """Stub for import-time hook registration. ``.on(name)`` returns
        a no-op decorator; ``win[id]`` returns self so attribute assignment
        in handler bodies is harmless. Only used when ``butterfly.py`` is
        imported without an app host."""

        def on(self, _name):
            def _deco(fn):
                return fn
            return _deco

        def __getitem__(self, _key):
            return self

        def __setattr__(self, _name, _value):
            pass

    win = _NoopWindow()


@win.on("app.boot")
def on_app_boot():
    """Glide the butterfly to centre, then fade in the launch banner."""
    import asyncio
    win["butterfly"].state = "glide_in"
    async def _after_glide():
        await asyncio.sleep(3.8)   # butterfly glide duration
        win["banner"].state = "shown"
    asyncio.create_task(_after_glide())


@win.on("butterfly.glide")
def on_butterfly_glide():
    # TODO: implement 'butterfly.glide'
    print("butterfly.glide fired")


@win.on("banner.show")
def on_banner_show():
    # TODO: implement 'banner.show'
    print("banner.show fired")


@win.on("butterfly1.click")
def on_butterfly1_click():
    # TODO: implement 'butterfly1.click'
    print("butterfly1.click fired")


@win.on("butterfly3.click")
def on_butterfly3_click():
    # TODO: implement 'butterfly3.click'
    print("butterfly3.click fired")


@win.on("bluemorphosrc.click")
def on_bluemorphosrc_click():
    # TODO: implement 'bluemorphosrc.click'
    print("bluemorphosrc.click fired")
