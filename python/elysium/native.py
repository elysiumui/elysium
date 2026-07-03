"""Native OS integration — Tier-2 Qt parity (QSystemTrayIcon, QShortcut /
global hotkeys, notifications, single-instance).

A capability-gated wrapper over the native layer. Features that aren't
available on a platform degrade gracefully and are reported by
:func:`capabilities` — per the project's GTK-free Linux stance, system tray and
global hotkeys are macOS/Windows-only, while notifications work everywhere
(native on macOS/Windows, ``notify-send`` on Linux) and single-instance is
pure-Python-friendly everywhere.

    import elysium.native as native
    if not native.single_instance("dev.example.app"):
        sys.exit("already running")
    native.notify("Build finished", "All tests passed")

    tray = native.Tray("MyApp", [("open", "Open"), ("quit", "Quit")])
    tray.on("quit", lambda: app.quit())
    tray.create()                 # call on the main thread during setup
    # each frame: tray.poll()

    keys = native.HotKeys()
    keys.register(native.CTRL | native.SHIFT, "KeyR", on_reload)
    # each frame: keys.poll()
"""
from __future__ import annotations

from typing import Any, Callable, Optional

try:
    from elysium._native import _native as _n
except Exception:  # pragma: no cover - native ext always present in practice
    _n = None  # type: ignore[assignment]

# Modifier bits (match elysium.input).
SHIFT, CTRL, ALT, META = 1, 2, 4, 8


def capabilities() -> dict[str, bool]:
    """Map of native feature → supported on this platform."""
    if _n is None or not hasattr(_n, "capabilities"):
        return {}
    try:
        return dict(_n.capabilities())
    except Exception:
        return {}


def is_supported(feature: str) -> bool:
    return capabilities().get(feature, False)


def single_instance(app_id: str) -> bool:
    """Return True if this is the first running instance for ``app_id`` (or it
    already holds the lock); False if another instance is running. If the
    native lock is unavailable, returns True so the app still starts."""
    if _n is None or not hasattr(_n, "single_instance"):
        return True
    try:
        return bool(_n.single_instance(app_id))
    except Exception:
        return True


def notify(title: str, body: str = "", app_name: str = "Elysium") -> bool:
    """Show an OS notification (best-effort). Native on macOS/Windows,
    ``notify-send`` on Linux. Returns True on success."""
    if _n is None or not hasattr(_n, "notify"):
        return False
    try:
        return bool(_n.notify(title, body, app_name))
    except Exception:
        return False


class Tray:
    """A system-tray icon with a context menu. Construct with ``(id, label)``
    items, wire ``on(id, handler)`` callbacks, call :meth:`create` on the main
    thread during setup, then :meth:`poll` each frame to dispatch clicks."""

    def __init__(self, tooltip: str = "",
                 items: Optional[list[tuple[str, str]]] = None) -> None:
        self.tooltip = tooltip
        self.items = list(items or [])
        self._handlers: dict[str, Callable[[], None]] = {}
        self.created = False

    @property
    def supported(self) -> bool:
        return is_supported("tray")

    def on(self, item_id: str, handler: Callable[[], None]) -> "Tray":
        self._handlers[item_id] = handler
        return self

    def create(self) -> bool:
        if _n is None or not hasattr(_n, "tray_create"):
            return False
        try:
            self.created = bool(_n.tray_create(self.tooltip, self.items))
        except Exception:
            self.created = False
        return self.created

    def poll(self) -> Optional[str]:
        """Dispatch any pending menu click to its handler; returns the id."""
        if _n is None or not hasattr(_n, "tray_poll"):
            return None
        try:
            item_id = _n.tray_poll()
        except Exception:
            return None
        if item_id is not None:
            h = self._handlers.get(item_id)
            if h is not None:
                try: h()
                except Exception: pass
        return item_id


class HotKeys:
    """System-wide global hotkeys. ``register(mods, key, handler)`` then
    :meth:`poll` each frame to dispatch fired hotkeys to their handlers."""

    def __init__(self) -> None:
        self._handlers: dict[int, Callable[[], None]] = {}

    @property
    def supported(self) -> bool:
        return is_supported("global_hotkeys")

    def register(self, mods: int, key: str,
                 handler: Optional[Callable[[], None]] = None) -> int:
        """Register a hotkey; returns its non-zero id (0 = failed/unsupported)."""
        if _n is None or not hasattr(_n, "hotkey_register"):
            return 0
        try:
            hk_id = int(_n.hotkey_register(mods, key))
        except Exception:
            return 0
        if hk_id and handler is not None:
            self._handlers[hk_id] = handler
        return hk_id

    def poll(self) -> Optional[int]:
        """Dispatch any fired hotkey to its handler; returns the hotkey id."""
        if _n is None or not hasattr(_n, "hotkey_poll"):
            return None
        try:
            hk_id = _n.hotkey_poll()
        except Exception:
            return None
        if hk_id is not None:
            h = self._handlers.get(hk_id)
            if h is not None:
                try: h()
                except Exception: pass
        return hk_id


__all__ = [
    "capabilities", "is_supported", "single_instance", "notify",
    "Tray", "HotKeys", "SHIFT", "CTRL", "ALT", "META",
]
