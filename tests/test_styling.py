"""Tier 7 Phase 1 — declarative styling: StyleSheet selector resolution."""
from __future__ import annotations

import pytest

from elysium.styling import Selector, StyleSheet


# --- selector parsing ------------------------------------------------------

def test_parse_selector_components():
    s = Selector.parse("Button.primary.lg#save:hover")
    assert s.type == "Button"
    assert s.id == "save"
    assert s.classes == frozenset({"primary", "lg"})
    assert s.states == frozenset({"hover"})


def test_parse_wildcard_and_bare():
    assert Selector.parse("*").type is None
    s = Selector.parse(".danger")
    assert s.type is None and s.classes == frozenset({"danger"})


def test_parse_rejects_unknown_state():
    with pytest.raises(ValueError):
        Selector.parse("Button:wiggle")


def test_specificity_ordering():
    type_only = Selector.parse("Button").specificity
    with_class = Selector.parse("Button.primary").specificity
    with_id = Selector.parse("#save").specificity
    assert with_id > with_class > type_only


# --- resolution ------------------------------------------------------------

def test_resolve_merges_by_specificity():
    sheet = StyleSheet({
        "Button": {"radius": 6, "fill": "base"},
        "Button.primary": {"fill": "iris"},
        "#save": {"radius": 12},
    })
    r = sheet.resolve("Button", id="save", classes=["primary"])
    assert r["fill"] == "iris"     # class beats bare type
    assert r["radius"] == 12       # id beats type


def test_resolve_state_only_when_active():
    sheet = StyleSheet({
        "Button": {"lift": 0},
        "Button:hover": {"lift": 2},
    })
    assert sheet.resolve("Button")["lift"] == 0
    assert sheet.resolve("Button", states=["hover"])["lift"] == 2


def test_resolve_requires_all_classes_present():
    sheet = StyleSheet({"Button.a.b": {"x": 1}})
    assert sheet.resolve("Button", classes=["a"]) == {}        # missing .b
    assert sheet.resolve("Button", classes=["a", "b"]) == {"x": 1}


def test_resolve_type_mismatch_excluded():
    sheet = StyleSheet({"Label": {"x": 1}})
    assert sheet.resolve("Button") == {}


def test_source_order_breaks_ties():
    sheet = StyleSheet({
        ".a": {"v": 1},
        ".b": {"v": 2},
    })
    # both equally specific; later rule (.b) wins for shared property
    assert sheet.resolve("X", classes=["a", "b"])["v"] == 2


def test_add_updates_and_recompiles():
    sheet = StyleSheet({"Button": {"radius": 6}})
    sheet.add("Button:hover", {"radius": 8})
    assert sheet.resolve("Button", states=["hover"])["radius"] == 8


# --- apply -----------------------------------------------------------------

class _Widget:
    style_id = "save"
    style_classes = ("primary",)

    def __init__(self):
        self.radius = 6.0
        self.label = "OK"


def test_apply_writes_known_props_only():
    sheet = StyleSheet({
        "_Widget#save": {"radius": 14, "bogus": 99},
    })
    w = _Widget()
    resolved = sheet.apply(w)
    assert w.radius == 14            # existing attr written
    assert not hasattr(w, "bogus")   # unknown attr skipped
    assert resolved["radius"] == 14


def test_apply_uses_widget_id_and_classes():
    sheet = StyleSheet({"_Widget.primary": {"label": "Primary"}})
    w = _Widget()
    sheet.apply(w)
    assert w.label == "Primary"
