"""Visual regression tests — render with Skia, compare to golden PNG."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")
SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / sys.platform


def _render_hero(width: int = 800, height: int = 560) -> bytes:
    """The spec's Phase 0 hero card: indigo→coral gradient, rounded, shadowed."""
    import elysium as ely
    layer = ely.SkiaLayer(width, height)
    layer.clear(0.055, 0.043, 0.102, 1.0)
    pad = min(width, height) * 0.08
    card_w = width - 2 * pad
    card_h = height - 2 * pad
    layer.draw_gradient_card(
        pad, pad, card_w, card_h,
        24.0,
        (0x5B, 0x3F, 0xF5, 0xFF),
        (0xFF, 0x5C, 0x8A, 0xFF),
        40.0, (0.0, 12.0), (0, 0, 0, 0x7F),
    )
    cx = width / 2.0
    cy = height - pad - card_h * 0.18
    layer.draw_filled_circle(cx, cy, min(card_w, card_h) * 0.05, (0xFA, 0xF7, 0xFF, 0xFF))
    return bytes(layer.encode_png())


@native_only
def test_hero_card_round_trip():
    """Skia produces a non-trivial PNG of the right dimensions."""
    png = _render_hero(800, 560)
    assert png.startswith(b"\x89PNG\r\n\x1a\n"), "PNG header"
    assert len(png) > 5000, "PNG should have real content"


def _render_hero_glass(width: int = 800, height: int = 560) -> bytes:
    """Hero card + frosted-glass overlay panel (spec §4.4 frosted_glass)."""
    import elysium as ely
    layer = ely.SkiaLayer(width, height)
    layer.clear(0.055, 0.043, 0.102, 1.0)
    layer.draw_gradient_card(
        50.0, 50.0, 700.0, 460.0, 24.0,
        (0x5B, 0x3F, 0xF5, 0xFF), (0xFF, 0x5C, 0x8A, 0xFF),
        40.0, (0.0, 12.0), (0, 0, 0, 0x7F),
    )
    layer.draw_frosted_panel(
        220.0, 350.0, 360.0, 130.0,
        20.0, 24.0,
        (0xFA, 0xF7, 0xFF, 0x40),
        (0xFA, 0xF7, 0xFF, 0x80),
    )
    layer.draw_filled_circle(400.0, 415.0, 26.0, (0xFA, 0xF7, 0xFF, 0xFF))
    return bytes(layer.encode_png())


@native_only
def test_hero_glass_round_trip():
    png = _render_hero_glass(800, 560)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 5000


def _render_shaped_window(width: int = 800, height: int = 560) -> bytes:
    """The 'break the rectangle' shaped-window milestone: alpha-0 background
    with the gradient card + frosted panel floating on it. What the OS
    desktop sees through a `transparent=True, title_bar=False` Elysium window.
    """
    import elysium as ely
    layer = ely.SkiaLayer(width, height)
    layer.clear(0.0, 0.0, 0.0, 0.0)
    layer.draw_gradient_card(
        50.0, 50.0, 700.0, 460.0, 32.0,
        (0x5B, 0x3F, 0xF5, 0xFF), (0xFF, 0x5C, 0x8A, 0xFF),
        40.0, (0.0, 12.0), (0, 0, 0, 0x7F),
    )
    layer.draw_frosted_panel(
        220.0, 350.0, 360.0, 130.0, 28.0, 28.0,
        (0xFA, 0xF7, 0xFF, 0x44), (0xFA, 0xF7, 0xFF, 0x88),
    )
    layer.draw_filled_circle(400.0, 415.0, 26.0, (0xFA, 0xF7, 0xFF, 0xFF))
    return bytes(layer.encode_png())


@native_only
def test_shaped_window_has_transparent_corners():
    """The shaped window's PNG should have a fully-transparent top-left
    pixel — that's the alpha-0 area the OS lets the desktop show through."""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(_render_shaped_window(800, 560)))
    # Top-left pixel should be transparent (alpha 0).
    px = img.convert("RGBA").getpixel((0, 0))
    assert px[3] == 0, f"expected alpha 0 at (0,0), got {px}"
    # Center pixel should be opaque (inside the card).
    px = img.convert("RGBA").getpixel((400, 280))
    assert px[3] == 255, f"expected alpha 255 at center, got {px}"


@native_only
@pytest.mark.skipif(not (SNAPSHOT_DIR / "shaped_window.png").exists(),
                    reason=f"no golden at {SNAPSHOT_DIR / 'shaped_window.png'}")
def test_shaped_window_matches_golden():
    png = _render_shaped_window(800, 560)
    golden = (SNAPSHOT_DIR / "shaped_window.png").read_bytes()
    if hashlib.sha256(png).hexdigest() != hashlib.sha256(golden).hexdigest():
        diff = SNAPSHOT_DIR / "shaped_window.actual.png"
        diff.write_bytes(png)
        pytest.fail(f"shaped_window differs from golden; actual at {diff}")


@native_only
@pytest.mark.skipif(not (SNAPSHOT_DIR / "hero_glass.png").exists(),
                    reason=f"no golden at {SNAPSHOT_DIR / 'hero_glass.png'}")
def test_hero_glass_matches_golden():
    png = _render_hero_glass(800, 560)
    golden = (SNAPSHOT_DIR / "hero_glass.png").read_bytes()
    if hashlib.sha256(png).hexdigest() != hashlib.sha256(golden).hexdigest():
        diff = SNAPSHOT_DIR / "hero_glass.actual.png"
        diff.write_bytes(png)
        pytest.fail(f"hero_glass differs from golden; actual at {diff}")


@native_only
@pytest.mark.skipif(not (SNAPSHOT_DIR / "hero_card.png").exists(),
                    reason=f"no golden at {SNAPSHOT_DIR / 'hero_card.png'}")
def test_hero_card_matches_golden():
    """Pixel-diff the rendered card against the golden snapshot.

    On a deterministic GPU/CPU stack the SHA256 should match byte-for-byte.
    If we ever cross hardware vendors we'll switch to a perceptual diff.
    """
    png = _render_hero(800, 560)
    golden = (SNAPSHOT_DIR / "hero_card.png").read_bytes()
    actual_hash = hashlib.sha256(png).hexdigest()
    golden_hash = hashlib.sha256(golden).hexdigest()
    if actual_hash != golden_hash:
        diff_path = SNAPSHOT_DIR / "hero_card.actual.png"
        diff_path.write_bytes(png)
        pytest.fail(
            f"hero card differs from golden\n"
            f"  golden sha256: {golden_hash}\n"
            f"  actual sha256: {actual_hash}\n"
            f"  actual saved to: {diff_path}"
        )
