"""Tier-3: error / edge-case coverage — malformed input, boundaries, and
graceful degradation, across the public surface.
"""
from __future__ import annotations

import pytest

from elysium.settings import Settings
from elysium.text import IntValidator, DoubleValidator, Mask, Acceptable, Intermediate, Invalid
from elysium.modelview import ItemModel, Column
from elysium.components.scroll import ScrollView
from elysium.components.virtual import visible_window, row_window
from elysium import i18n
import elysium.native as native


# --- settings -------------------------------------------------------------

def test_settings_load_of_garbage_is_graceful(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ this is not valid json ]]")
    s = Settings("garbage", path=p)        # must not raise
    assert s.get("anything", "default") == "default"


def test_settings_missing_file_uses_defaults(tmp_path):
    s = Settings("missing", path=tmp_path / "nope.json",
                 defaults={"theme": "dark"})
    assert s.get("theme") == "dark"
    assert s.get("absent") is None


def test_settings_deep_missing_group(tmp_path):
    s = Settings("deep", path=tmp_path / "s.json")
    assert s.get("a.b.c.d", "fallback") == "fallback"
    assert not s.contains("a.b.c.d")


# --- validators / masks ---------------------------------------------------

def test_int_validator_boundaries():
    v = IntValidator(0, 100).validate
    assert v("50") == Acceptable
    assert v("100") == Acceptable
    assert v("101") == Invalid
    assert v("-1") == Invalid
    assert v("") in (Intermediate, Acceptable)     # empty is a valid prefix
    assert v("abc") == Invalid


def test_double_validator_decimals():
    v = DoubleValidator(0.0, 1.0, decimals=2).validate
    assert v("0.99") == Acceptable
    assert v("1.5") == Invalid
    assert v("0.999") in (Invalid, Intermediate)   # too many decimals


def test_mask_rejects_wrong_shape():
    m = Mask("000-000")
    # A digit-only mask shouldn't accept letters.
    out, _ = m.apply("12a")
    assert "a" not in out


# --- model/view edge cases ------------------------------------------------

def test_itemmodel_heterogeneous_and_none_sort():
    m = ItemModel(rows=[{"k": 3}, {"k": None}, {"k": 1}, {"k": "x"}],
                  columns=[Column("k")])
    m.toggle_sort("k")                       # must not raise on mixed/None
    vals = [m.value(i, "k") for i in range(4)]
    assert vals[-1] is None                  # None sinks to the end


def test_itemmodel_value_out_of_range():
    m = ItemModel(rows=[{"k": 1}], columns=[Column("k")])
    assert m.value(99, "k") is None          # no IndexError
    m.remove_at(99)                          # no-op, no raise


def test_empty_model_view():
    m = ItemModel(rows=[], columns=[Column("k")])
    assert m.row_count() == 0 and m.view() == []
    m.toggle_sort("k")                       # sort of nothing is fine
    assert m.view() == []


# --- scroll / virtual bounds ----------------------------------------------

def test_scroll_clamps_past_content():
    sv = ScrollView(x=0, y=0, w=200, h=200, content_w=200, content_h=400)
    sv.on_scroll(0, 10_000)                  # way past the top
    assert sv.scroll_y == 0.0
    sv.on_scroll(0, -10_000)                 # way past the bottom
    assert sv.scroll_y == sv.max_y()


def test_windowing_helpers_degenerate_inputs():
    assert visible_window(0, 20.0, 300.0, 0.0) == (0, 0, 0.0)     # no items
    assert visible_window(100, 0.0, 300.0, 0.0) == (0, 0, 0.0)    # zero height
    assert row_window(100, 300.0, 0.0, 0) == (0, 0)              # zero row height


# --- i18n / native degradation --------------------------------------------

def test_i18n_missing_catalog_returns_msgid(tmp_path):
    i18n.install("xx", localedir=str(tmp_path))   # no .mo there
    assert i18n.tr("Save") == "Save"               # identity fallback
    i18n.use_translation(__import__("gettext").NullTranslations(), "en")


def test_native_unsupported_feature_is_false():
    assert native.is_supported("totally_made_up_feature") is False
    # Wrappers no-op safely even if a capability is absent.
    tray = native.Tray("x", [("a", "A")])
    assert tray.poll() is None
