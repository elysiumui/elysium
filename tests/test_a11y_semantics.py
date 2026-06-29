"""Tier 7 Phase 3 — semantic a11y: roles, nodes, live regions, focus rings."""
from __future__ import annotations

from elysium import theme as T
from elysium.accessibility import (
    Role, AccessibleNode, Announcer, announcer, announce,
    focus_ring_style, paint_focus_ring, A11yPrefs,
)


# --- AccessibleNode --------------------------------------------------------

def test_node_to_dict_omits_none_and_defaults():
    n = AccessibleNode(role=Role.BUTTON, label="Save", focusable=True)
    d = n.to_dict()
    assert d == {"role": "button", "label": "Save", "focusable": True}
    assert "checked" not in d and "value" not in d


def test_node_checkbox_and_value():
    n = AccessibleNode(role=Role.CHECK_BOX, label="Wrap", checked=True,
                       focusable=True, focused=True)
    d = n.to_dict()
    assert d["role"] == "checkBox" and d["checked"] is True
    assert d["focused"] is True


def test_node_table_associations_and_children():
    cell = AccessibleNode(role=Role.CELL, label="42", row_index=2,
                          col_index=1, col_header="Age")
    row = AccessibleNode(role=Role.ROW, children=[cell])
    table = AccessibleNode(role=Role.TABLE, label="People", children=[row])
    d = table.to_dict()
    assert d["role"] == "table"
    cd = d["children"][0]["children"][0]
    assert cd["row_index"] == 2 and cd["col_index"] == 1
    assert cd["col_header"] == "Age"


# --- Announcer (live regions) ----------------------------------------------

def test_announcer_polite_and_assertive():
    a = Announcer()
    a.announce("Saved")
    a.announce("Error!", assertive=True)
    assert a._log[0]["live"] == "polite"
    assert a._log[1]["live"] == "assertive"
    assert a.messages() == ["Saved", "Error!"]
    assert a.last() == "Error!"


def test_announcer_sink_receives_messages():
    got = []
    a = Announcer()
    a.set_sink(got.append)
    a.announce("Hello")
    assert got and got[0]["text"] == "Hello"
    a.clear()
    assert a.messages() == []


def test_default_announce_uses_singleton():
    announcer().clear()
    announce("Ready")
    assert announcer().last() == "Ready"
    announcer().clear()


# --- focus ring ------------------------------------------------------------

def test_focus_ring_thicker_under_high_contrast():
    normal = focus_ring_style(A11yPrefs(high_contrast=False))
    hc = focus_ring_style(A11yPrefs(high_contrast=True))
    assert hc[0] > normal[0]      # wider stroke
    assert hc[2] == 1.0           # fully opaque


def test_paint_focus_ring_renders():
    from elysium._native import _native as n
    T.set_theme(T.studio_dark())
    t = T.current_theme()
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    paint_focus_ring(dl, 20, 20, 120, 36, t.primary, radius=8,
                     prefs=A11yPrefs(high_contrast=True))
    layer = n.SkiaLayer(180, 80)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
    T.set_theme(T.light())
