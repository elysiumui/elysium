"""Tier-2 Phase-5: multi-window depth (owned/modal windows, messaging).

Uses the eager native window stubs (created by app.window without running the
event loop), so ownership/modality/messaging are exercised headlessly.
"""
from __future__ import annotations

import elysium as ely
from elysium.windowing import WindowManager


def _app():
    return ely.App(title="t", identifier="dev.test.tier2.windowing")


def test_modal_child_blocks_owner_input():
    app = _app()
    wm = WindowManager(app)
    owner = wm.open(initial_size=(800, 600))
    assert not owner.input_blocked
    dlg = wm.open(owner=owner, modal=True, initial_size=(300, 200))
    assert owner.input_blocked is True
    assert wm.modal_active and wm.top_modal is dlg
    wm.close(dlg)
    assert owner.input_blocked is False
    assert not wm.modal_active


def test_owner_child_tree_and_cascade_close():
    app = _app()
    wm = WindowManager(app)
    parent = wm.open(initial_size=(800, 600))
    a = wm.open(owner=parent, initial_size=(200, 200))
    b = wm.open(owner=parent, initial_size=(200, 200))
    assert {w.id for w in wm.children(parent)} == {a.id, b.id}
    assert wm.owner_of(a) is parent
    wm.close(parent)               # cascades to a + b
    assert wm.children(parent) == []
    assert wm.owner_of(a) is None  # all untracked now


def test_two_modals_keep_owner_blocked_until_both_close():
    app = _app()
    wm = WindowManager(app)
    owner = wm.open(initial_size=(800, 600))
    m1 = wm.open(owner=owner, modal=True, initial_size=(200, 200))
    m2 = wm.open(owner=owner, modal=True, initial_size=(200, 200))
    assert owner.input_blocked
    wm.close(m1)
    assert owner.input_blocked   # m2 still modal
    wm.close(m2)
    assert not owner.input_blocked


def test_non_modal_child_does_not_block():
    app = _app()
    wm = WindowManager(app)
    owner = wm.open(initial_size=(800, 600))
    wm.open(owner=owner, modal=False, initial_size=(200, 200))
    assert not owner.input_blocked


def test_inter_window_message_delivery():
    app = _app()
    wm = WindowManager(app)
    a = wm.open(initial_size=(400, 300))
    b = wm.open(initial_size=(400, 300))
    got = []
    wm.on_message(b, got.append)
    assert wm.send(b, {"kind": "ping", "from": a.id})
    # Delivered via b's UI dispatcher → drain to run it.
    b.ui_dispatcher().drain()
    assert got == [{"kind": "ping", "from": a.id}]


def test_send_to_untracked_returns_false():
    app = _app()
    wm = WindowManager(app)
    stray = app.window(initial_size=(100, 100))  # not registered
    assert wm.send(stray, "x") is False
