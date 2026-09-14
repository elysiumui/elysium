"""Tier 7 Phase 3 — semantic a11y: roles, nodes, live regions, focus rings."""
from __future__ import annotations

import math

import pytest

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


@pytest.mark.native
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


# --- window.publish_a11y_tree strictness -----------------------------------
#
# The native bridge validates the flat node list before anything reaches the
# OS adapter. A malformed tree raises ValueError and the previously published
# tree stays live, so one bad frame cannot blank the screen reader.

def _a11y_window():
    import elysium as ely
    app = ely.App(title="a11y", identifier="dev.test.a11y.strict")
    return app.window(initial_size=(200, 100))


def _node(nid, **overrides):
    node = {"id": nid, "role": "button", "bounds": (0.0, 0.0, 10.0, 10.0),
            "children": []}
    node.update(overrides)
    return node


def _valid_tree():
    return [_node(1, role="window", children=[2]), _node(2, label="Save")]


def _deep_chain(depth):
    return ([_node(i, children=[i + 1]) for i in range(1, depth)]
            + [_node(depth)])


@pytest.mark.native
def test_publish_a11y_tree_accepts_well_formed_tree_and_hit_tests():
    win = _a11y_window()
    win.publish_a11y_tree(1, _valid_tree())
    assert win.a11y_hit(5.0, 5.0) == 2
    assert win.a11y_hit(50.0, 50.0) is None


@pytest.mark.native
@pytest.mark.parametrize("root, nodes, message", [
    pytest.param(1, [_node(1, children=[2, 2]), _node(2)],
                 "Repeated or cyclic", id="duplicate-child"),
    pytest.param(1, [_node(1, children=[2]), _node(2, children=[1])],
                 "Repeated or cyclic", id="cycle"),
    pytest.param(1, [_node(1, children=[9])],
                 "Missing accessibility node 9", id="missing-child"),
    pytest.param(7, [_node(1)],
                 "Missing accessibility node 7", id="missing-root"),
    pytest.param(1, [_node(1), _node(1)],
                 "Duplicate accessibility node 1", id="duplicate-id"),
    pytest.param(1, [_node(1), _node(2)],
                 "must belong to the root tree", id="orphan"),
    pytest.param(1, _deep_chain(130),
                 "too deep", id="depth-over-128"),
    pytest.param(1, [_node(1, bounds=(0.0, 0.0, -1.0, 5.0))],
                 "Invalid accessibility bounds", id="negative-size"),
    pytest.param(1, [_node(1, bounds=(math.nan, 0.0, 1.0, 5.0))],
                 "Invalid accessibility bounds", id="non-finite-bounds"),
    pytest.param(1, [{"role": "button"}],
                 "requires id", id="missing-id"),
    pytest.param(1, [{"id": 1}],
                 "requires role", id="missing-role"),
    pytest.param(2**64 - 1, [_node(2**64 - 1)],
                 "Invalid or duplicate accessibility identity", id="reserved-id"),
])
def test_publish_a11y_tree_rejects_malformed_trees(root, nodes, message):
    win = _a11y_window()
    win.publish_a11y_tree(1, _valid_tree())
    with pytest.raises(ValueError, match=message):
        win.publish_a11y_tree(root, nodes)
    # The last good tree is still what assistive tech sees.
    assert win.a11y_hit(5.0, 5.0) == 2


@pytest.mark.native
def test_publish_a11y_tree_depth_limit_is_inclusive():
    win = _a11y_window()
    win.publish_a11y_tree(1, _deep_chain(129))   # root at depth 0, leaf at 128
    assert win.a11y_hit(5.0, 5.0) == 129
