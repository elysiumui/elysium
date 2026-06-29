"""Designer A3 — the bundled-SVG icon loader.

Redesigned glyphs ship as `<kind>.svg` under
``elysium-designer/assets/icons/`` and override the hand-drawn painters at
import. These tests pin the loader contract: it parses the bundled art, the
overridden painters render through the real pipeline, and a malformed file
never blanks an icon (falls back to the original painter).
"""
from __future__ import annotations

import importlib.util
import sys

import pytest


@pytest.fixture(scope="module")
def designer():
    sys.path.insert(0, "elysium-designer")
    spec = importlib.util.spec_from_file_location(
        "elysium_designer_main_icons", "elysium-designer/__main__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["elysium_designer_main_icons"] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def test_bundled_svg_icons_loaded(designer):
    # All 42 redesigned glyphs are bundled and replace the hand-drawn painters.
    assert designer._SVG_ICONS_LOADED >= 42


def test_loaded_icon_renders_through_real_pipeline(designer):
    from elysium import theme as T
    from elysium._native import _native as n

    T.set_theme(T.studio_dark())
    t = T.current_theme()
    for kind in ("tool_select", "tb_save", "vp_shaded", "tool_gizmo"):
        dl = n.DisplayList()
        dl.clear(0.1, 0.11, 0.14, 1.0)
        designer._draw_toolbox_icon(dl, kind, 8, 8, 42, 42, t)
        layer = n.SkiaLayer(58, 58)
        layer.execute(dl)
        assert bytes(layer.encode_png())[:4] == b"\x89PNG"
    T.set_theme(T.light())


def test_parser_handles_duotone_and_circles(designer):
    # currentColor fill + stroke with opacities, plus a stand-alone circle.
    svg = (
        '<svg viewBox="0 0 48 48"><path d="M 8 8 H 40 V 40 H 8 Z" '
        'fill="currentColor" fill-opacity="0.3"></path>'
        '<path d="M 8 8 H 40" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-opacity="1"></path>'
        '<circle cx="24" cy="24" r="6" fill="currentColor"></circle></svg>'
    )
    ops = designer._parse_svg_icon_ops(svg)
    modes = [o[0] for o in ops]
    assert modes.count("fill") == 2 and modes.count("stroke") == 1
    # the duotone fill carries the 0.3 alpha, the stroke its 1.6 width
    fill = next(o for o in ops if o[0] == "fill")
    stroke = next(o for o in ops if o[0] == "stroke")
    assert abs(fill[2] - 0.3) < 1e-6
    assert abs(stroke[3] - 1.6) < 1e-6


def test_malformed_svg_yields_no_ops(designer):
    assert designer._parse_svg_icon_ops("not xml at all <") == []
    assert designer._parse_svg_icon_ops("<svg></svg>") == []


def test_studio_chrome_renders(designer):
    # The flat Studio chrome (module-level, self-contained) renders without
    # error through the real pipeline for both Studio palettes.
    from elysium import theme as T
    from elysium._native import _native as n

    for theme_factory in (T.studio_dark, T.studio_light):
        dl = n.DisplayList()
        designer._paint_studio_chrome(dl, theme_factory())
        layer = n.SkiaLayer(designer.WIDTH, designer.HEIGHT)
        layer.execute(dl)
        assert bytes(layer.encode_png())[:4] == b"\x89PNG"
