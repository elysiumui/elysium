"""Per-user settings — Tier-2 Qt parity (QSettings).

A small, dependency-free persistence layer for app config: typed get/set with
dotted **groups**, durable atomic writes, an in-memory cache, change
callbacks, and platform-appropriate storage locations. Generalizes the
Designer's hand-rolled ``~/.elysium/designer-prefs.json`` pattern.

    s = Settings("designer")            # ~/.elysium/designer/settings.json
    s.set("window.size", [1200, 800])
    w, h = s.get("window.size", [800, 600])
    with s.group("palette"):
        s.set("recent", ["#ff0000"])    # stored under "palette.recent"
    s.save()                            # or pass autosave=True

Keys are dotted paths into a nested dict, so ``window.size`` and
``window.pos`` share the ``window`` group.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional


def config_dir(app: str) -> Path:
    """Platform-appropriate per-user config directory for ``app``.

    * Linux/BSD: ``$XDG_CONFIG_HOME/elysium/<app>`` (default ``~/.config``)
    * macOS: ``~/Library/Application Support/elysium/<app>``
    * Windows: ``%APPDATA%/elysium/<app>``

    Always rooted under an ``elysium`` namespace so apps don't collide.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        root = Path(base) / "elysium"
    elif _is_macos():
        root = Path.home() / "Library" / "Application Support" / "elysium"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        root = Path(base) / "elysium"
    return root / app


def _is_macos() -> bool:
    import sys
    return sys.platform == "darwin"


class Settings:
    """Persistent per-user key/value store with dotted-key groups."""

    def __init__(self, app: str, *, path: Optional[Path] = None,
                 autosave: bool = False, defaults: Optional[dict] = None) -> None:
        self.app = app
        self.path = Path(path) if path is not None else (config_dir(app) / "settings.json")
        self.autosave = autosave
        self._defaults = dict(defaults or {})
        self._data: dict = {}
        self._group_prefix = ""
        self._on_change: list[Callable[[str, Any], None]] = []
        self.load()

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        try:
            if self.path.is_file():
                self._data = json.loads(self.path.read_text())
        except Exception:
            self._data = {}

    def save(self) -> None:
        """Atomically write to disk (temp file + os.replace) so a crash
        mid-write never corrupts the existing settings."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
            os.replace(tmp, self.path)
        except Exception:
            pass

    # -- key access ---------------------------------------------------------

    def _full_key(self, key: str) -> str:
        return f"{self._group_prefix}{key}" if self._group_prefix else key

    def get(self, key: str, default: Any = None) -> Any:
        full = self._full_key(key)
        node, leaf = self._descend(full, create=False)
        if node is not None and leaf in node:
            return node[leaf]
        # Fall back to construction-time defaults.
        dnode, dleaf = self._descend(full, create=False, data=self._defaults)
        if dnode is not None and dleaf in dnode:
            return dnode[dleaf]
        return default

    def set(self, key: str, value: Any) -> None:
        full = self._full_key(key)
        node, leaf = self._descend(full, create=True)
        if node.get(leaf) == value:
            return
        node[leaf] = value
        for cb in self._on_change:
            try: cb(full, value)
            except Exception: pass
        if self.autosave:
            self.save()

    def contains(self, key: str) -> bool:
        node, leaf = self._descend(self._full_key(key), create=False)
        return node is not None and leaf in node

    def remove(self, key: str) -> None:
        node, leaf = self._descend(self._full_key(key), create=False)
        if node is not None and leaf in node:
            del node[leaf]
            if self.autosave:
                self.save()

    def clear(self) -> None:
        self._data = {}
        if self.autosave:
            self.save()

    def keys(self) -> list[str]:
        """All stored dotted keys (leaves), depth-first."""
        out: list[str] = []

        def walk(d: dict, prefix: str) -> None:
            for k, v in d.items():
                full = f"{prefix}{k}"
                if isinstance(v, dict):
                    walk(v, full + ".")
                else:
                    out.append(full)

        walk(self._data, "")
        return out

    def _descend(self, dotted: str, create: bool, data: Optional[dict] = None):
        """Return ``(parent_dict, leaf_name)`` for a dotted key. With
        ``create=False`` returns ``(None, leaf)`` if a parent is missing."""
        d = self._data if data is None else data
        parts = dotted.split(".")
        for p in parts[:-1]:
            nxt = d.get(p)
            if not isinstance(nxt, dict):
                if not create:
                    return (None, parts[-1])
                nxt = {}
                d[p] = nxt
            d = nxt
        return (d, parts[-1])

    # -- groups -------------------------------------------------------------

    @contextmanager
    def group(self, name: str) -> Iterator["Settings"]:
        """Scope keys under ``name.`` for the duration of the block. Nestable."""
        prev = self._group_prefix
        self._group_prefix = f"{prev}{name}."
        try:
            yield self
        finally:
            self._group_prefix = prev

    # -- change notification ------------------------------------------------

    def on_change(self, fn: Callable[[str, Any], None]) -> None:
        """Register ``fn(full_key, value)`` fired on every ``set`` that
        actually changes a value."""
        self._on_change.append(fn)

    # dict-style sugar
    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return self.contains(key)


__all__ = ["Settings", "config_dir"]
