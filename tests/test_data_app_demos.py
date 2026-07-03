"""Tier 8 Phase 4 — tabular numerals + the two reference-app demos."""
from __future__ import annotations

import importlib.util
import sys

import pytest

from elysium import theme as T


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_ui_font("")
    T.set_theme(T.light())


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --- tabular numerals ------------------------------------------------------

def test_draw_paragraph_accepts_tabular():
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0, 0, 0, 1)
    # positional + keyword forms both work; the param is the new font feature
    dl.draw_paragraph("$1,234.50", 8, 30, 200, 18.0, (232, 235, 240, 255),
                      0, "", 400, [], False, True)
    dl.draw_paragraph("1,000", 8, 60, 200, 18.0, (232, 235, 240, 255),
                      tabular=True)
    layer = n.SkiaLayer(220, 80)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


def test_label_tabular_renders():
    from elysium.components import Label
    from elysium._native import _native as n
    dl = n.DisplayList()
    dl.clear(0, 0, 0, 1)
    Label(x=4, y=4, w=160, h=24, text="$19,540.00", size=20, align="right",
          tabular=True).paint(dl)
    layer = n.SkiaLayer(180, 32)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


# --- reference demos -------------------------------------------------------

def test_storeprofitlens_dashboard_builds_and_paints():
    from elysium._native import _native as n
    mod = _load("spl_dashboard", "examples/storeprofitlens-dashboard/main.py")
    app = mod.build_dashboard(1180, 760)
    assert len(app["cards"]) == 5 and len(app["cost"]) == 5
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    mod.paint_dashboard(dl, app, 1180, 760)
    layer = n.SkiaLayer(1180, 760)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"


def test_variantproof_grid_builds_paints_and_edits():
    from elysium._native import _native as n
    mod = _load("vp_grid", "examples/variantproof-grid/main.py")
    app = mod.build_editor(1180, 720)
    g = app["grid"]
    assert g.frozen_cols == 2
    assert g.dirty_count() >= 3        # seeded pending edits
    assert g.error_count() >= 1        # the duplicate-SKU validation
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    mod.paint_editor(dl, app, 1180, 720)
    layer = n.SkiaLayer(1180, 720)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
