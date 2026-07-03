"""Tier-1 Phase-0 native enablers: text shaping, clipboard, IME plumbing.

These exercise the new `_native` free functions and `PyWindow` methods that
the Python text-editing / dialog layers build on (caret geometry, hit-testing,
clipboard, IME preedit). All are surface-free or non-blocking so they run in
headless CI without a live event loop.
"""
from __future__ import annotations

import os
import sys

import pytest


def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")

# The system clipboard needs a display server; headless Linux CI (no DISPLAY /
# WAYLAND_DISPLAY) has none, so the X11 clipboard backend times out.
needs_display = pytest.mark.skipif(
    sys.platform.startswith("linux")
    and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="clipboard requires a display server",
)

SZ = 16.0


# --- Text shaping -----------------------------------------------------------

@native_only
def test_caret_x_monotonic_and_bounded():
    from elysium._native import _native as _n
    s = "hello world"
    n = len(s)
    assert _n.text_caret_x(s, SZ, 0) == 0.0
    prev = 0.0
    for i in range(1, n + 1):
        x = _n.text_caret_x(s, SZ, i)
        assert x >= prev
        prev = x
    width = _n.measure_text_run(s, SZ)[0]
    assert abs(_n.text_caret_x(s, SZ, n) - width) < 0.5
    # Over-long index clamps to the end (no exception).
    assert abs(_n.text_caret_x(s, SZ, n + 50) - width) < 0.5


@native_only
def test_hit_index_round_trips_caret():
    from elysium._native import _native as _n
    s = "Editable"
    n = len(s)
    for i in range(n + 1):
        x = _n.text_caret_x(s, SZ, i)
        probe = x if i == n else x + 0.5
        hit = _n.text_hit_index(s, SZ, probe)
        assert abs(hit - i) <= 1
    assert _n.text_hit_index(s, SZ, -100.0) == 0
    assert _n.text_hit_index(s, SZ, 100_000.0) == n


@native_only
def test_empty_string_is_safe():
    from elysium._native import _native as _n
    assert _n.text_caret_x("", SZ, 0) == 0.0
    assert _n.text_hit_index("", SZ, 25.0) == 0
    w, asc, desc = _n.measure_text_run("", SZ)
    assert w == 0.0 and asc >= 0.0 and desc >= 0.0


@native_only
def test_font_vmetrics_positive():
    from elysium._native import _native as _n
    asc, desc, lh = _n.font_vmetrics(SZ)
    assert asc > 0 and desc > 0 and lh > 0
    assert lh >= asc + desc - 1.0


@native_only
def test_cjk_codepoint_indexing():
    """Indices are Python-str codepoints, so CJK (BMP) lines up with len()."""
    from elysium._native import _native as _n
    s = "日本語ABC"  # 6 codepoints
    assert len(s) == 6
    width = _n.measure_text_run(s, SZ)[0]
    assert abs(_n.text_caret_x(s, SZ, 6) - width) < 0.5
    assert _n.text_caret_x(s, SZ, 3) < width  # before "A"


# --- Clipboard + IME (window-bound) -----------------------------------------

@native_only
@needs_display
def test_clipboard_round_trip_unicode():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.clip")
    w = app.window(transparent=True, title_bar=False, initial_size=(200, 120))
    sample = "Elysium • Tier1 • 日本語 • café"
    w._native.set_clipboard_text(sample)
    assert w._native.get_clipboard_text() == sample


@native_only
def test_ime_plumbing_present_and_nonblocking():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.ime")
    w = app.window(transparent=True, title_bar=False, initial_size=(200, 120))
    # No composition in flight → empty preedit.
    assert w._native.preedit() == ""
    # Requests are queued for the (not-yet-running) loop; must not raise.
    w._native.set_ime_allowed(True)
    w._native.set_ime_cursor_area(10.0, 20.0, 2.0, 18.0)
