"""OS-level keyboard + mouse end-to-end test.

Launches the `examples/input-probe` window, injects **real OS input** (through
the OS event stack → winit → framework — NOT the framework API, which would
bypass the layer bugs actually live in), and asserts the probe received it.

Injectors, per platform:
  * Linux   — `xdotool` (XTEST), under an X server (Xvfb in CI).
  * Windows — `pywinauto` (`send_keys` / `click_input` = real SendInput).
  * macOS   — not covered (OS injection is gated by TCC accessibility perms
              that hosted runners can't grant); the test skips.

The load-bearing assertion is `kbd_text == "hello"` — text delivered via
`KeyboardInput`. When IME is (wrongly) enabled on Windows, typed text arrives
only via `Ime::Commit` and `kbd_text` comes back empty, so this goes RED — the
exact regression that dead-keyboarded the Designer on Windows. Run manually:

    pip install pywinauto        # Windows
    sudo apt-get install xdotool # Linux (+ run under Xvfb)
    pytest tests/test_os_input.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

TYPED = "hello"
PROBE_TITLE = "Elysium Input Probe"
TARGET_XY = (200, 150)  # the click-target circle, window-logical coords


# --------------------------------------------------------------------------- #
# Probe process management
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _post(port: int, path: str) -> None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST")
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def _wait_ready(port: int, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _get(port)
        if last and last.get("ready"):
            return last
        time.sleep(0.4)
    raise AssertionError(f"probe never became ready (last={last})")


# --------------------------------------------------------------------------- #
# Availability checks — run BEFORE launching the probe, so a normal test job
# (no Xvfb / no injector) skips instead of launching a windowless probe that
# can never become ready.
# --------------------------------------------------------------------------- #
def _require_linux() -> None:
    if not os.environ.get("DISPLAY"):
        pytest.skip("no X DISPLAY (need Xvfb) for xdotool injection")
    if not shutil.which("xdotool"):
        pytest.skip("xdotool not installed")


def _require_windows() -> None:
    try:
        import pywinauto  # noqa: F401
    except ImportError:
        pytest.skip("pywinauto not installed")


REQUIRE = {"linux": _require_linux, "win32": _require_windows}


# --------------------------------------------------------------------------- #
# Injectors
# --------------------------------------------------------------------------- #
def _inject_linux() -> None:
    wid = subprocess.check_output(
        ["xdotool", "search", "--sync", "--name", PROBE_TITLE], text=True
    ).split()[0]
    subprocess.run(["xdotool", "windowactivate", "--sync", wid], check=True)
    subprocess.run(["xdotool", "windowfocus", "--sync", wid], check=True)
    # Keyboard: type into the focused window (delay lets the 60 Hz probe drain).
    subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "40", TYPED],
                   check=True)
    # Mouse: move to the target (window-relative) and left-click.
    subprocess.run(["xdotool", "mousemove", "--window", wid,
                    str(TARGET_XY[0]), str(TARGET_XY[1])], check=True)
    subprocess.run(["xdotool", "click", "1"], check=True)


def _inject_windows() -> None:
    from pywinauto.application import Application
    from pywinauto.keyboard import send_keys
    app = Application(backend="win32").connect(title_re=f".*{PROBE_TITLE}.*", timeout=30)
    win = app.top_window()
    win.set_focus()
    time.sleep(0.5)
    send_keys(TYPED)                                    # real SendInput
    win.click_input(coords=TARGET_XY, button="left")   # real mouse input


INJECTORS = {"linux": _inject_linux, "win32": _inject_windows}


# --------------------------------------------------------------------------- #
# The test
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(sys.platform == "darwin",
                    reason="macOS OS-input injection needs TCC accessibility perms")
def test_os_keyboard_and_mouse_roundtrip():
    plat = "linux" if sys.platform.startswith("linux") else sys.platform
    inject = INJECTORS.get(plat)
    if inject is None:
        pytest.skip(f"no OS injector for platform {plat!r}")
    # Skip (not fail) BEFORE launching the probe when the injector/display is
    # unavailable — e.g. the normal test suite with no Xvfb.
    REQUIRE[plat]()

    port = _free_port()
    env = {**os.environ, "ELYSIUM_PROBE_PORT": str(port)}
    # Capture probe output to a temp file (non-blocking) so we can surface the
    # real crash if it never comes up — e.g. wgpu failing to init under Xvfb.
    log = tempfile.NamedTemporaryFile("w+", suffix=".probe.log", delete=False)
    proc = subprocess.Popen([sys.executable, "-m", "examples.input-probe"],
                            cwd=os.path.dirname(os.path.dirname(__file__)),
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        try:
            _wait_ready(port)
        except AssertionError:
            log.flush()
            with open(log.name) as f:
                print("---- probe output ----\n" + f.read() + "----------------------")
            raise
        _post(port, "/reset")
        inject()

        # Poll for the injected input to land (avoid a race with the 60 Hz drain).
        deadline = time.time() + 10.0
        state: dict = {}
        while time.time() < deadline:
            state = _get(port) or {}
            if state.get("kbd_text") == TYPED and state.get("clicks"):
                break
            time.sleep(0.3)

        # The load-bearing assertion: typed text arrived via KeyboardInput.
        assert state.get("kbd_text") == TYPED, (
            f"keyboard input not delivered via KeyboardInput.text: "
            f"kbd_text={state.get('kbd_text')!r}, all-source text={state.get('text')!r}, "
            f"raw={state.get('raw_events')!r}")

        # Mouse: at least one left-click landed, inside the window bounds.
        clicks = state.get("clicks") or []
        assert clicks, f"no mouse click registered (state={state})"
        c = clicks[-1]
        assert c["x"] is None or 0 <= c["x"] <= 400
        assert c["y"] is None or 0 <= c["y"] <= 300
    finally:
        _post(port, "/quit")
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            os.unlink(log.name)
        except OSError:
            pass
