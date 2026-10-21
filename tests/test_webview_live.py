"""Live ``elysium.webview`` tests against the real platform engine.

Every scenario lives in ``_webview_probe.py`` and runs in its own
process: a crash in native code then fails one test instead of killing
the session, and the macOS application object never leaks between
scenarios (or into the rest of the suite). Scenarios that find no engine
or no WebGL report a skip.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = Path(__file__).with_name("_webview_probe.py")

# Platforms whose engine backend is exercised live in CI.
LIVE_PLATFORMS = ("darwin", "linux", "win32")

pytestmark = pytest.mark.skipif(
    sys.platform not in LIVE_PLATFORMS,
    reason=f"live WebView scenarios are not enabled on {sys.platform}",
)

W, H = 320, 240
RED, BLUE, GREEN = (255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255)


def probe(name: str, timeout: float = 120.0) -> dict:
    env = dict(os.environ, PYTHONFAULTHANDLER="1")
    proc = subprocess.run(
        [sys.executable, str(PROBE), name],
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    assert proc.returncode == 0, (
        f"probe {name!r} exited with {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[-2000:]}\n--- stderr ---\n{proc.stderr[-6000:]}"
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert lines, f"probe {name!r} printed no result\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    result = json.loads(lines[-1])
    if "skip" in result:
        pytest.skip(result["skip"])
    return result


def near(px, expected, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, expected))


def test_reported_crash_repro_returns_the_value():
    assert probe("repro") == {"value": "42"}


def test_evaluate_js_returns_json_values_and_raises_js_errors():
    r = probe("types")
    thrown = r.pop("throw")
    assert r == {
        "1+1": 2, "1.5": 1.5, "'s'": "s", "true": True, "false": False,
        "null": None, "undefined": None,
        "({a:[1,'x',null], b:{c:2.5}})": {"a": [1, "x", None], "b": {"c": 2.5}},
        "[]": [], "-0": 0, "0/0": None, "1/0": None,      # JSON has no NaN/Infinity
    }
    assert isinstance(r["1+1"], int)
    assert thrown[0] == "WebViewJSError" and "boom" in thrown[1], thrown


def test_many_evaluations_release_their_completion_blocks():
    r = probe("many")
    assert r["ok"]
    if sys.platform == "darwin":
        assert r["live_blocks"] == 0


def test_snapshot_returns_the_rendered_page():
    r = probe("snapshot")
    assert r["len"] == W * H * 4
    assert near(r["top"], RED), r["top"]            # top-down rows: red stays on top
    assert near(r["bottom"], BLUE), r["bottom"]
    fw, fh, scale, seq = r["frame"]
    assert (fw, fh) == (round(W * scale), round(H * scale)) and scale >= 1 and seq == 1
    assert near(r["green_bg"], GREEN), r["green_bg"]
    assert r["clear_bg"][3] == 0


def test_snapshot_captures_webgl_content():
    r = probe("webgl")
    assert r["frames_advanced"] > 0, "requestAnimationFrame is not running"
    assert near(r["center"], BLUE), r["center"]


def test_expose_bridge_round_trips():
    r = probe("bridge")
    assert r["done"] is True
    assert r["add"] == 5                    # sync handler
    assert r["mul"] == 20                   # coroutine handler
    assert r["fail"] == "ValueError: nope"  # a raising handler rejects the Promise
    assert r["late"] == "late-ok"           # exposed after the page had loaded


def test_calls_from_a_worker_thread():
    r = probe("worker")
    assert "error" not in r, r.get("error")
    assert r["eval"] == "rgb(255, 0, 0)"
    assert near(r["top"], RED)


def test_paint_never_blocks_and_composites_the_latest_frame():
    r = probe("paint")
    assert r["first"] is False                  # no frame yet: nothing drawn, no wait
    assert r["second"] is True
    assert r["args"] == [True, 10, 20, 160, 120]


def test_load_failure_resize_and_close():
    r = probe("lifecycle")
    assert r["bad_load"] == "WebViewError"
    assert r["good_load"] == "ok"
    assert r["resized"] is True
    assert r["after_close"] == "WebViewError"


@pytest.mark.skipif(sys.platform != "darwin", reason="the NSApplication ordering guard is macOS-only")
def test_app_run_after_main_thread_pumping_raises_clearly():
    r = probe("app_guard")
    assert r == {"raised": "ElysiumError", "mentions_run": True}


@pytest.mark.skipif(
    not os.environ.get("ELYSIUM_RUN_WINDOW_TEST"),
    reason="opens a real App window; set ELYSIUM_RUN_WINDOW_TEST=1 locally",
)
def test_inside_a_running_app():
    r = probe("app")
    assert "error" not in r, r.get("error")
    assert r["eval"] == 2
    assert near(r["top"], RED)
