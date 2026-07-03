"""Phase 2 butterfly tests — DisplayList path ops, mouse-state polling,
butterfly demo geometry, animation interpolation, hover-toggled close
button.

The live window test (clicks + drag) is gated on a display.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")
SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / sys.platform
BUTTERFLY_DIR = Path(__file__).parent.parent / "examples" / "butterfly"


def _import_butterfly():
    sys.path.insert(0, str(BUTTERFLY_DIR))
    import butterfly  # noqa: E402
    return butterfly


# --- DisplayList path commands --------------------------------------------

@native_only
def test_displaylist_path_commands_round_trip():
    """DisplayList can hold fill/stroke/gradient path commands and render
    byte-for-byte identical to direct SkiaLayer calls."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]

    d = "M 100 100 L 200 100 L 200 200 L 100 200 Z"

    # Path A: direct SkiaLayer.
    direct = _n.SkiaLayer(400, 400)
    direct.clear(0, 0, 0, 1)
    direct.fill_path_linear_gradient(d, (100, 100), (200, 200), (255, 0, 0, 255), (0, 0, 255, 255))
    direct.stroke_path(d, (255, 255, 255, 255), 2.0)
    png_direct = bytes(direct.encode_png())

    # Path B: DisplayList → execute.
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    dl.fill_path_linear_gradient(d, (100, 100), (200, 200), (255, 0, 0, 255), (0, 0, 255, 255))
    dl.stroke_path(d, (255, 255, 255, 255), 2.0)
    via_dl = _n.SkiaLayer(400, 400)
    via_dl.execute(dl)
    png_via_dl = bytes(via_dl.encode_png())

    assert png_direct == png_via_dl, "DisplayList rendering must match direct paint"


@native_only
def test_displaylist_transforms():
    """`push_transform` / `pop_transform` apply scale + translate on the canvas."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    dl.push_transform(100, 100)
    dl.fill_path("M 0 0 L 50 0 L 50 50 L 0 50 Z", (255, 0, 0, 255))
    dl.pop_transform()
    layer = _n.SkiaLayer(200, 200)
    layer.execute(dl)
    png = bytes(layer.encode_png())
    assert len(png) > 200, "non-trivial output expected"


# --- Mouse polling (no display needed — just calling getters) -------------

@native_only
def test_window_mouse_state_initial_outside():
    """Before any cursor enters the window, all the polled values are zero/None."""
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.mouse")
    win = app.window(transparent=True, title_bar=False, initial_size=(100, 100))
    assert win.cursor_position is None
    assert win.cursor_inside is False
    assert win.mouse_pressed is False
    assert win.press_count == 0


@native_only
def test_window_set_outer_position_doesnt_throw():
    """set_outer_position queues a request; the actual move happens when
    the OS event loop runs. The call itself must be safe + non-blocking."""
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.pos")
    win = app.window(transparent=True, title_bar=False, initial_size=(100, 100))
    win.set_outer_position(100, 200)
    win.set_outer_position(-50, 0)  # Negative coords allowed (multi-monitor).


# --- Butterfly geometry ---------------------------------------------------

@native_only
def test_butterfly_renders_to_displaylist():
    """The butterfly module accepts both SkiaLayer and DisplayList as target."""
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    butterfly = _import_butterfly()
    dl = _n.DisplayList()
    dl.clear(0, 0, 0, 1)
    butterfly.draw(dl, 900, 720, flap_t=1.0, scale=1.0)
    # Should produce a meaningful number of commands (wings + body + veins).
    assert len(dl) >= 50, f"expected >= 50 commands, got {len(dl)}"


@native_only
@pytest.mark.parametrize("flap_t", [0.0, 0.3, 0.6, 1.0])
def test_butterfly_animates_without_error(flap_t):
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    butterfly = _import_butterfly()
    layer = _n.SkiaLayer(900, 720)
    layer.clear(0, 0, 0, 1)
    butterfly.draw(layer, 900, 720, flap_t=flap_t, scale=1.0)
    png = bytes(layer.encode_png())
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 5000


@native_only
@pytest.mark.skipif(not (SNAPSHOT_DIR / "butterfly_open.png").exists(),
                    reason=f"no golden at {SNAPSHOT_DIR / 'butterfly_open.png'}")
def test_butterfly_open_matches_golden():
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    butterfly = _import_butterfly()
    layer = _n.SkiaLayer(900, 720)
    layer.clear(0, 0, 0, 0)
    butterfly.draw(layer, 900, 720, flap_t=1.0, scale=1.0)
    actual = bytes(layer.encode_png())
    golden = (SNAPSHOT_DIR / "butterfly_open.png").read_bytes()
    if hashlib.sha256(actual).hexdigest() != hashlib.sha256(golden).hexdigest():
        (SNAPSHOT_DIR / "butterfly_open.actual.png").write_bytes(actual)
        pytest.fail(f"butterfly_open differs from golden; actual saved")


# --- Live window: click-on-close-area hit-tests (no display needed) -------

@native_only
def test_close_button_hit_test_geometry():
    """The IconCloseButton component hit-tests its own circular region.
    The butterfly bbox helper in the demo module agrees."""
    sys.path.insert(0, str(BUTTERFLY_DIR))
    import main as demo  # type: ignore  # noqa: E402
    from elysium.components import IconCloseButton

    btn = IconCloseButton(x=100, y=100, w=28, h=28)
    cx, cy = btn.x + btn.w / 2, btn.y + btn.h / 2

    # Exact center hits.
    assert btn.hit_test(cx, cy)
    # Outside the (radius + slop) padding doesn't.
    assert not btn.hit_test(cx + 40, cy)
    # The demo's butterfly-bbox helper is independent.
    assert demo.point_in_butterfly(demo.WIDTH // 2, demo.HEIGHT // 2)
    assert not demo.point_in_butterfly(-100, -100)


@native_only
@pytest.mark.skipif(
    not __import__("os").environ.get("ELYSIUM_RUN_WINDOW_TEST"),
    reason="requires a display; set ELYSIUM_RUN_WINDOW_TEST=1 locally",
)
def test_butterfly_live_runs():
    """Phase 2 gate: the butterfly app opens, animates for ~1.5s, exits."""
    import threading
    import time
    import elysium as ely
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    butterfly = _import_butterfly()

    app = ely.App(title="butterfly-pytest", identifier="dev.elysium.butterfly.pytest")
    win = app.window(transparent=True, title_bar=False, initial_size=(900, 720))

    def animator():
        start = time.perf_counter()
        while True:
            t = (time.perf_counter() - start) * 3.0
            phase = t % 1.0
            flap_t = 1.0 - abs(1.0 - 2.0 * phase)
            dl = _n.DisplayList()
            dl.clear(0, 0, 0, 0)
            butterfly.draw(dl, 900, 720, flap_t=flap_t, scale=1.0)
            try:
                win.publish_display_list(dl)
            except Exception:
                return
            time.sleep(1.0 / 60.0)

    threading.Thread(target=animator, daemon=True).start()
    threading.Thread(target=lambda: (time.sleep(1.5), app.quit()), daemon=True).start()

    started = time.perf_counter()
    app.run()
    elapsed = time.perf_counter() - started
    assert 0.8 < elapsed < 40.0, f"expected ~1.5s, got {elapsed}"
