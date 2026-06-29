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


# ---------------------------------------------------------------------------
# Semantic accessibility: roles, nodes, live regions, focus rings.
# ---------------------------------------------------------------------------

class Role:
    """Accessibility roles (accesskit-aligned names) a component reports so
    screen readers describe it correctly."""
    BUTTON = "button"
    TOGGLE_BUTTON = "toggleButton"
    CHECK_BOX = "checkBox"
    RADIO_BUTTON = "radioButton"
    SWITCH = "switch"
    SLIDER = "slider"
    TEXT_INPUT = "textInput"
    LABEL = "label"
    LINK = "link"
    HEADING = "heading"
    IMAGE = "image"
    LIST = "list"
    LIST_ITEM = "listItem"
    MENU = "menu"
    MENU_BAR = "menuBar"
    MENU_ITEM = "menuItem"
    TAB = "tab"
    TAB_LIST = "tabList"
    TAB_PANEL = "tabPanel"
    TOOLBAR = "toolbar"
    DIALOG = "dialog"
    GROUP = "group"
    STATUS = "status"
    PROGRESS_INDICATOR = "progressIndicator"
    TREE = "tree"
    TREE_ITEM = "treeItem"
    TABLE = "table"
    ROW = "row"
    CELL = "cell"
    COLUMN_HEADER = "columnHeader"
    COMBO_BOX = "comboBox"


@dataclass
class AccessibleNode:
    """A semantic description of a widget for the accessibility tree (the shape
    the accesskit bridge consumes). Build one per widget; ``None`` fields are
    omitted from :meth:`to_dict`."""
    role: str = Role.GROUP
    label: str = ""
    value: str | None = None
    description: str = ""
    focusable: bool = False
    focused: bool = False
    disabled: bool = False
    checked: bool | None = None
    expanded: bool | None = None
    bounds: tuple[float, float, float, float] | None = None
    row_index: int | None = None
    col_index: int | None = None
    col_header: str | None = None
    children: list | None = None

    def to_dict(self) -> dict:
        out: dict = {"role": self.role}
        if self.label:
            out["label"] = self.label
        if self.value is not None:
            out["value"] = self.value
        if self.description:
            out["description"] = self.description
        if self.focusable:
            out["focusable"] = True
        if self.focused:
            out["focused"] = True
        if self.disabled:
            out["disabled"] = True
        if self.checked is not None:
            out["checked"] = self.checked
        if self.expanded is not None:
            out["expanded"] = self.expanded
        if self.bounds is not None:
            out["bounds"] = list(self.bounds)
        if self.row_index is not None:
            out["row_index"] = self.row_index
        if self.col_index is not None:
            out["col_index"] = self.col_index
        if self.col_header:
            out["col_header"] = self.col_header
        if self.children:
            out["children"] = [c.to_dict() if isinstance(c, AccessibleNode)
                               else c for c in self.children]
        return out


@dataclass
class Announcer:
    """A live-region announcer: queues text for a screen reader (``polite`` by
    default, ``assertive`` to interrupt). Route :meth:`set_sink` to the accesskit
    bridge in a real app; the in-memory log makes it testable."""
    _log: list | None = None
    _sink: Callable[[dict], None] | None = None

    def __post_init__(self) -> None:
        if self._log is None:
            self._log = []

    def set_sink(self, fn: Callable[[dict], None] | None) -> None:
        self._sink = fn

    def announce(self, text: str, assertive: bool = False) -> None:
        msg = {"text": text, "live": "assertive" if assertive else "polite"}
        self._log.append(msg)
        if self._sink is not None:
            self._sink(msg)

    def messages(self) -> list:
        return [m["text"] for m in self._log]

    def last(self) -> str | None:
        return self._log[-1]["text"] if self._log else None

    def clear(self) -> None:
        self._log.clear()


_ANNOUNCER = Announcer()


def announcer() -> Announcer:
    """The process-wide default announcer."""
    return _ANNOUNCER


def announce(text: str, assertive: bool = False) -> None:
    """Announce via the default :func:`announcer`."""
    _ANNOUNCER.announce(text, assertive)


def focus_ring_style(prefs: A11yPrefs | None = None) -> tuple:
    """``(stroke_width, inflate, alpha)`` for a focus ring — thicker and fully
    opaque under high-contrast so keyboard focus is unmistakable."""
    p = prefs or current()
    if p.high_contrast or p.increase_contrast:
        return (2.5, 3.0, 1.0)
    return (1.5, 2.0, 0.75)


def _ring_path(x: float, y: float, w: float, h: float, r: float) -> str:
    return (f"M {x + r} {y} L {x + w - r} {y} Q {x + w} {y} {x + w} {y + r} "
            f"L {x + w} {y + h - r} Q {x + w} {y + h} {x + w - r} {y + h} "
            f"L {x + r} {y + h} Q {x} {y + h} {x} {y + h - r} "
            f"L {x} {y + r} Q {x} {y} {x + r} {y} Z")


def paint_focus_ring(dl, x: float, y: float, w: float, h: float, color,
                     radius: float = 6.0, prefs: A11yPrefs | None = None) -> None:
    """Draw a consistent keyboard-focus ring around ``(x, y, w, h)``, honouring
    high-contrast prefs."""
    from elysium.theme import with_alpha
    width, inflate, alpha = focus_ring_style(prefs)
    dl.stroke_path(
        _ring_path(x - inflate, y - inflate, w + 2 * inflate, h + 2 * inflate,
                   radius + inflate),
        with_alpha(color, alpha), width)


__all__ = [
    "A11yPrefs", "current", "subscribe", "variant_for",
    "Role", "AccessibleNode", "Announcer", "announcer", "announce",
    "focus_ring_style", "paint_focus_ring",
]
