"""Designer redesign A1 — Studio design tokens, themes, and the UI-font hook."""
from __future__ import annotations

import pytest

from elysium import theme as T


@pytest.fixture(autouse=True)
def _restore_theme():
    yield
    # Don't leak Studio's font/theme into other tests' golden renders.
    T.set_ui_font("")
    T.set_theme(T.light())


# --- new tokens -------------------------------------------------------------

def test_theme_has_spacing_state_and_font_tokens():
    t = T.dark()
    assert (t.space_xs, t.space_sm, t.space_md, t.space_lg, t.space_xl) == (4.0, 8.0, 12.0, 16.0, 24.0)
    assert t.opacity_disabled == 0.40 and 0.0 < t.opacity_hover < 1.0
    assert isinstance(t.font_family, str)


# --- Studio themes ----------------------------------------------------------

def test_studio_dark_palette():
    t = T.studio_dark()
    assert t.name == "Studio Dark" and t.is_dark
    assert t.surface == (0x1B, 0x1E, 0x24, 0xFF)
    assert t.surface_variant == (0x2A, 0x2F, 0x39, 0xFF)
    assert t.edge == (0x2C, 0x32, 0x3C, 0xFF)
    assert t.radius_medium == 8.0           # crisp Studio geometry
    assert t.font_family == "Inter"


def test_studio_light_palette():
    t = T.studio_light()
    assert t.name == "Studio Light" and not t.is_dark
    assert t.surface == (0xF6, 0xF8, 0xFB, 0xFF)
    assert t.radius_medium == 8.0


def test_all_builtins_construct():
    for f in (T.light, T.dark, T.oled, T.midnight_glass, T.frost,
              T.studio_dark, T.studio_light):
        assert isinstance(f(), T.Theme)


def test_set_theme_recolors():
    T.set_theme(T.studio_dark())
    assert T.current_theme().name == "Studio Dark"


# --- font hook --------------------------------------------------------------

def test_set_ui_font_family_returns_true():
    assert T.set_ui_font("Helvetica Neue") is True
    assert T.set_ui_font("") is True          # clear preference


def test_register_missing_font_file_is_graceful():
    # A non-existent .ttf path must not raise and must report failure.
    assert T.set_ui_font("/no/such/font.ttf") is False


def test_button_studio_finish_renders_all_variants():
    # The Studio button finish (tight shadow + hairline edge + subtle sheen)
    # must render for every variant under the studio theme without error.
    from elysium.components import Button
    from elysium._native import _native as n
    T.set_theme(T.studio_dark())
    for variant in ("solid", "outline", "ghost", "glass", "danger"):
        dl = n.DisplayList()
        dl.clear(0.1, 0.11, 0.14, 1.0)
        b = Button(x=12, y=12, w=120, h=36, label="OK", variant=variant)
        b._hover_t = 0.5
        b.paint(dl)
        layer = n.SkiaLayer(150, 64)
        layer.execute(dl)
        assert bytes(layer.encode_png())[:4] == b"\x89PNG"


def test_set_theme_applies_font_without_error():
    # studio_dark carries font_family="Inter"; applying it must be a no-op-safe
    # best-effort that never raises even if Inter isn't installed.
    T.set_theme(T.studio_dark())
    # rendering text under the studio theme still works (font falls back).
    from elysium._native import _native as n
    layer = n.SkiaLayer(80, 32)
    layer.clear(0, 0, 0, 0)
    layer.draw_text("Aa", 6, 22, 16, (232, 235, 240, 255))
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
