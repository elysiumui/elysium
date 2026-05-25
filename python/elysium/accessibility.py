"""User-preference plumbing — reduce-motion + high-contrast.

Reads OS-level accessibility prefs and exposes them as ``Signal``-like
flags that themes / animations watch. Skins that ship variant trees
(``variants/reduce_motion.json``, ``variants/high_contrast.json``) get
auto-applied when the corresponding pref is on.

The reads themselves are cheap and cached, but we hook a 1-second
polling timer to catch live changes — every platform has a callback
API, but the call sites differ enough that polling is the simplest
correct option until we wire each one through the native layer.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class A11yPrefs:
    reduce_motion: bool = False
    high_contrast: bool = False
    increase_contrast: bool = False
    reduce_transparency: bool = False
    invert_colors: bool = False


_LOCK = threading.Lock()
_CURRENT = A11yPrefs()
_LISTENERS: list[Callable[[A11yPrefs], None]] = []
_POLLER_STARTED = False


def current() -> A11yPrefs:
    """Snapshot of the latest OS-reported prefs."""
    with _LOCK:
        return A11yPrefs(**_CURRENT.__dict__)


def subscribe(fn: Callable[[A11yPrefs], None]) -> Callable[[], None]:
    """Run ``fn(current_prefs)`` whenever any pref changes. Returns an
    unsubscribe closure."""
    _ensure_poller()
    with _LOCK:
        _LISTENERS.append(fn)
        snapshot = A11yPrefs(**_CURRENT.__dict__)
    fn(snapshot)
    def _unsub() -> None:
        with _LOCK:
            try: _LISTENERS.remove(fn)
            except ValueError: pass
    return _unsub


def variant_for(prefs: A11yPrefs | None = None) -> str | None:
    """Return the variant key the framework should select for the
    current prefs, or None for the default variant. Reduce-motion wins
    over high-contrast when both are on — most apps care more about
    motion sensitivity."""
    p = prefs or current()
    if p.reduce_motion: return "reduce_motion"
    if p.high_contrast or p.increase_contrast: return "high_contrast"
    return None


# ---------------------------------------------------------------------------
# Polling implementation.
# ---------------------------------------------------------------------------

def _ensure_poller() -> None:
    global _POLLER_STARTED
    if _POLLER_STARTED: return
    _POLLER_STARTED = True
    t = threading.Thread(target=_poll_loop, daemon=True, name="elysium-a11y-prefs")
    t.start()


def _poll_loop() -> None:
    while True:
        new = _read_prefs()
        changed = False
        with _LOCK:
            if new != _CURRENT:
                _CURRENT.__dict__.update(new.__dict__)
                listeners = list(_LISTENERS)
                changed = True
            else:
                listeners = []
        if changed:
            # Export the reduce-motion flag for the Rust render-thread
            # animator to pick up (see PyWindow::anim_set_target).
            os.environ["ELYSIUM_REDUCE_MOTION"] = "1" if new.reduce_motion else "0"
            for fn in listeners:
                try: fn(A11yPrefs(**new.__dict__))
                except Exception: pass
        time.sleep(1.0)


def _read_prefs() -> A11yPrefs:
    plat = sys.platform
    if plat == "darwin":   return _read_macos()
    if plat == "win32":    return _read_windows()
    if plat.startswith("linux"): return _read_linux()
    return A11yPrefs()


def _read_macos() -> A11yPrefs:
    """`defaults read com.apple.universalaccess` is what System
    Settings writes to. ``reduceMotion``, ``increaseContrast``,
    ``reduceTransparency`` are the keys we care about."""
    def _bool(domain: str, key: str) -> bool:
        try:
            out = subprocess.check_output(
                ["defaults", "read", domain, key],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip()
        except Exception:
            return False
        return out in {"1", "TRUE", "true", "YES", "yes"}
    return A11yPrefs(
        reduce_motion=_bool("com.apple.universalaccess", "reduceMotion"),
        increase_contrast=_bool("com.apple.universalaccess", "increaseContrast"),
        reduce_transparency=_bool("com.apple.universalaccess", "reduceTransparency"),
        invert_colors=_bool("com.apple.universalaccess", "whiteOnBlack"),
        high_contrast=_bool("com.apple.universalaccess", "increaseContrast"),
    )


def _read_windows() -> A11yPrefs:
    """SystemParametersInfo + SystemInformation queries. We use
    ``ctypes`` to avoid a pywin32 dep; SPI_GETCLIENTAREAANIMATION
    returns the user's animation preference and HIGHCONTRASTW
    surfaces the high-contrast flag."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        SPI_GETCLIENTAREAANIMATION = 0x1042
        anim = wintypes.BOOL()
        user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0,
                                      ctypes.byref(anim), 0)
        reduce_motion = not bool(anim.value)

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT),
                        ("dwFlags", wintypes.DWORD),
                        ("lpszDefaultScheme", wintypes.LPWSTR)]
        SPI_GETHIGHCONTRAST = 0x42
        hc = HIGHCONTRAST(); hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        user32.SystemParametersInfoW(SPI_GETHIGHCONTRAST, hc.cbSize,
                                      ctypes.byref(hc), 0)
        HCF_HIGHCONTRASTON = 0x1
        high_contrast = bool(hc.dwFlags & HCF_HIGHCONTRASTON)
        return A11yPrefs(
            reduce_motion=reduce_motion,
            high_contrast=high_contrast,
            increase_contrast=high_contrast,
        )
    except Exception:
        return A11yPrefs()


def _read_linux() -> A11yPrefs:
    """GNOME stores both flags in gsettings under
    ``org.gnome.desktop.interface``."""
    def _gget(schema: str, key: str) -> str:
        try:
            return subprocess.check_output(
                ["gsettings", "get", schema, key],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip()
        except Exception:
            return ""
    rm = _gget("org.gnome.desktop.interface", "enable-animations")
    hc = _gget("org.gnome.desktop.a11y.interface", "high-contrast")
    return A11yPrefs(
        reduce_motion=(rm == "false"),
        high_contrast=(hc == "true"),
        increase_contrast=(hc == "true"),
    )


__all__ = ["A11yPrefs", "current", "subscribe", "variant_for"]
