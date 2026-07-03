"""Tier-2 Phase-6: native OS integration (capability-gated)."""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import elysium.native as native


# --- capability matrix ------------------------------------------------------

def test_capabilities_shape():
    caps = native.capabilities()
    for key in ("single_instance", "notifications", "tray",
                "global_hotkeys", "power_events"):
        assert key in caps and isinstance(caps[key], bool)
    # These are guaranteed everywhere.
    assert caps["single_instance"] and caps["notifications"] and caps["power_events"]


def test_is_supported():
    assert native.is_supported("single_instance") is True
    assert native.is_supported("nonexistent") is False


# --- single instance --------------------------------------------------------

def test_single_instance_idempotent_in_process():
    app_id = "dev.elysium.test.singleinstance.A"
    assert native.single_instance(app_id) is True
    assert native.single_instance(app_id) is True   # same process keeps it


def test_single_instance_excludes_other_process():
    app_id = "dev.elysium.test.singleinstance.B"
    # A child process grabs the lock and holds it while we try to acquire.
    child = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import elysium.native as native, time, sys
            ok = native.single_instance({app_id!r})
            print("ACQUIRED" if ok else "DENIED", flush=True)
            time.sleep(3)
        """)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        line = child.stdout.readline().strip()
        assert line == "ACQUIRED"
        # While the child holds it, we must be denied.
        assert native.single_instance(app_id) is False
    finally:
        child.terminate()
        child.wait(timeout=5)


# --- notifications (capability only; don't spam the desktop) ----------------

def test_notify_is_callable_and_returns_bool(monkeypatch):
    called = {}
    from elysium._native import _native as _n
    monkeypatch.setattr(_n, "notify", lambda t, b, a: called.setdefault("args", (t, b, a)) or True)
    assert native.notify("Title", "Body", "App") is True
    assert called["args"] == ("Title", "Body", "App")


# --- tray dispatch (deterministic via monkeypatched events) -----------------

def test_tray_poll_dispatches_to_handler(monkeypatch):
    fired = []
    tray = native.Tray("MyApp", [("open", "Open"), ("quit", "Quit")])
    tray.on("quit", lambda: fired.append("quit"))
    from elysium._native import _native as _n
    events = iter(["quit", None])
    monkeypatch.setattr(_n, "tray_poll", lambda: next(events, None))
    assert tray.poll() == "quit"
    assert fired == ["quit"]
    assert tray.poll() is None


def test_tray_poll_safe_when_empty():
    tray = native.Tray("MyApp", [("x", "X")])
    # No tray created, no events → None, no crash.
    assert tray.poll() is None


# --- global hotkey dispatch -------------------------------------------------

def test_hotkeys_register_and_dispatch(monkeypatch):
    from elysium._native import _native as _n
    monkeypatch.setattr(_n, "hotkey_register", lambda mods, key: 4242)
    fired = []
    keys = native.HotKeys()
    hk = keys.register(native.CTRL | native.SHIFT, "KeyR", lambda: fired.append("reload"))
    assert hk == 4242
    events = iter([4242, None])
    monkeypatch.setattr(_n, "hotkey_poll", lambda: next(events, None))
    assert keys.poll() == 4242
    assert fired == ["reload"]


def test_hotkey_poll_safe_when_empty():
    keys = native.HotKeys()
    assert keys.poll() is None
