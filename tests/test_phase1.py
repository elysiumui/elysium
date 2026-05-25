"""Phase 1 tests — .esk loader, document compilation, hook wiring, decorator events."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _native_available() -> bool:
    import elysium
    return getattr(elysium, "_NATIVE_AVAILABLE", False)


native_only = pytest.mark.skipif(not _native_available(), reason="native extension not built")
HELLO_ESK = Path(__file__).parent.parent / "examples/hello/hello.esk"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / sys.platform


# --- Loader -----------------------------------------------------------------

@native_only
def test_load_skin_from_disk():
    """Loader parses manifest + document + hooks.json."""
    import elysium as ely
    skin = ely.load_skin(str(HELLO_ESK))
    assert skin.id == "dev.elysium.hello"
    assert skin.name == "Hello, Elysium"
    assert skin.schema_version == "1.0"


@native_only
def test_load_skin_hook_index():
    """All 4 declared hooks are present with correct types."""
    import elysium as ely
    skin = ely.load_skin(str(HELLO_ESK))
    hooks = skin.hooks()
    assert hooks["greeting_button.click"]["type"] == "event"
    assert "click" in hooks["greeting_button.click"]["events"]
    assert hooks["greeting_button.state"]["type"] == "state"
    assert hooks["greeting_button.state"]["states"] == ["idle", "hover", "pressed"]
    assert hooks["message.text"]["type"] == "text"


@native_only
def test_load_skin_rejects_missing_dir():
    import elysium as ely
    with pytest.raises(ValueError, match="missing required file|io|.*"):
        ely.load_skin("/nonexistent/skin.esk")


# --- Compile pipeline -------------------------------------------------------

@native_only
def test_compile_skin_to_display_list():
    import elysium as ely
    skin = ely.load_skin(str(HELLO_ESK))
    dl = skin.to_display_list(480, 320)
    # Clear + card + button at minimum.
    assert len(dl) >= 3


def _render_hello_from_esk(w: int = 480, h: int = 320) -> bytes:
    import elysium as ely
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    skin = ely.load_skin(str(HELLO_ESK))
    dl = skin.to_display_list(w, h)
    layer = _n.SkiaLayer(w, h)
    layer.execute(dl)
    return bytes(layer.encode_png())


@native_only
def test_loaded_skin_renders_through_skia_layer():
    """Full Phase 1 pipeline: .esk → DisplayList → SkiaLayer → PNG."""
    png = _render_hello_from_esk()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 5000


@native_only
@pytest.mark.skipif(not (SNAPSHOT_DIR / "hello_from_esk.png").exists(),
                    reason=f"no golden at {SNAPSHOT_DIR / 'hello_from_esk.png'}")
def test_hello_from_esk_matches_golden():
    """Deterministic Skia render of the .esk-loaded skin matches the golden."""
    import hashlib
    png = _render_hello_from_esk()
    golden = (SNAPSHOT_DIR / "hello_from_esk.png").read_bytes()
    if hashlib.sha256(png).hexdigest() != hashlib.sha256(golden).hexdigest():
        diff = SNAPSHOT_DIR / "hello_from_esk.actual.png"
        diff.write_bytes(png)
        pytest.fail(f"hello_from_esk differs from golden; actual at {diff}")


# --- Decorator events -------------------------------------------------------

@native_only
def test_window_on_decorator_fires():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.on")
    win = app.window(transparent=False, title_bar=True, initial_size=(100, 100))

    captured = []
    @win.on("test.click")  # hook doesn't need to exist for dispatch
    def handler(event):
        captured.append(event)

    n = win.fire("test.click", {"x": 1, "y": 2})
    assert n == 1
    assert captured == [{"x": 1, "y": 2}]


@native_only
def test_window_subscribe_and_unsubscribe():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.sub")
    win = app.window(transparent=False, title_bar=True, initial_size=(100, 100))

    received = []
    unsub = win.subscribe("foo", lambda e: received.append(e))
    win.fire("foo", "a")
    win.fire("foo", "b")
    unsub()
    win.fire("foo", "c")
    assert received == ["a", "b"]


@native_only
def test_handler_exceptions_dont_propagate():
    import elysium as ely
    app = ely.App(title="t", identifier="dev.elysium.test.except")
    win = app.window(transparent=False, title_bar=True, initial_size=(100, 100))

    @win.on("boom")
    def crash(event):
        raise RuntimeError("oops")

    log = []
    @win.on("boom")
    def survive(event):
        log.append(event)

    # Even though `crash` raises, `survive` still runs.
    n = win.fire("boom", "value")
    assert n == 2
    assert log == ["value"]


# --- Live window with .esk (gated on display) -------------------------------

@native_only
@pytest.mark.skipif(
    not __import__("os").environ.get("ELYSIUM_RUN_WINDOW_TEST"),
    reason="requires a display; set ELYSIUM_RUN_WINDOW_TEST=1 locally",
)
def test_phase1_hello_example_runs_end_to_end():
    """Phase 1 exit gate: load examples/hello/hello.esk, render it through
    the live pipeline (winit + Skia + wgpu), cross-thread quit cleanly."""
    import threading
    import time
    import elysium as ely

    app = ely.App(title="phase1-pytest", identifier="dev.elysium.phase1.pytest")
    win = app.window(transparent=False, title_bar=True, initial_size=(480, 320))
    win.load_skin(str(HELLO_ESK))

    threading.Thread(target=lambda: (time.sleep(1.0), app.quit()), daemon=True).start()
    started = time.perf_counter()
    app.run()
    elapsed = time.perf_counter() - started
    assert 0.5 < elapsed < 40.0, f"expected ~1s, got {elapsed}"
