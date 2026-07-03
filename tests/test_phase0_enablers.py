"""Tier-2 Phase-0: native input/window/lifecycle enablers (smoke).

These assert the PyO3 surface added in Phase 0 exists and has the right
shape. Real input arrives only from the OS event loop, so behavior here is
limited to defaults + the synchronous flags (input-block, owner/modal kwargs).
"""
from __future__ import annotations

import elysium as ely


def _app_window(**kw):
    app = ely.App(title="t", identifier="dev.test.tier2.phase0")
    return app, app.window(initial_size=(400, 300), **kw)


def test_scroll_poll_defaults_to_zero():
    _, w = _app_window()
    assert w.poll_scroll_delta() == (0.0, 0.0, False)


def test_lifecycle_poll_defaults_to_none():
    _, w = _app_window()
    assert w.poll_lifecycle_event() is None


def test_window_id_is_unique_and_stable():
    app, w = _app_window()
    wid = w.id
    assert isinstance(wid, int) and wid >= 1
    assert w.id == wid  # stable
    w2 = app.window(initial_size=(100, 100))
    assert w2.id != wid


def test_input_block_flag_round_trips():
    _, w = _app_window()
    assert w.input_blocked is False
    w.set_input_blocked(True)
    assert w.input_blocked is True
    w.set_input_blocked(False)
    assert w.input_blocked is False


def test_owner_and_modal_kwargs_accepted():
    app, parent = _app_window()
    child = app.window(initial_size=(200, 150), owner_id=parent.id, modal=True)
    assert child.id != parent.id
