"""Brush library — walks the on-disk preset directories and builds a
fast in-memory index keyed by id, category, and full-text search.

Per-Q2 of the redesign-plan answers: presets live USER-GLOBAL at
``~/Library/Application Support/Elysium/brushes/`` (macOS) with optional
per-skin overrides at ``<skin>/brushes/``. Both directories are walked
at startup AND on demand (hot-reload of brushes works without restart).

Builtin presets ship inside the package at
``python/elysium/brush/builtin/`` — copied into the user-global dir on
first launch so the user can edit them without modifying the source.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from .preset import Preset, load_preset


# ---- directory resolution ---------------------------------------------------

def user_brushes_dir() -> Path:
    """OS-specific user brush directory. Returns the path even when
    the directory doesn't exist yet — callers are expected to mkdir."""
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Elysium" / "brushes"
    if sysname == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Elysium" / "brushes"
        return Path.home() / "AppData" / "Roaming" / "Elysium" / "brushes"
    # Linux + everything else → XDG.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "elysium" / "brushes"


def builtin_brushes_dir() -> Path:
    """Directory inside the installed package containing the starter
    presets. These get copied into ``user_brushes_dir()`` on first
    launch so the user can edit them without touching the source."""
    return Path(__file__).resolve().parent / "builtin"


# ---- bootstrap (copy builtins into user dir on first launch) ---------------

def ensure_user_dir_seeded() -> Path:
    """Create the user brush directory if missing AND copy every
    builtin preset into it on first launch. Returns the user dir.

    Re-running this does NOT clobber files that already exist —
    `shutil.copy2` is invoked only when the destination is missing,
    so user edits to a seeded builtin survive subsequent launches."""
    user = user_brushes_dir()
    user.mkdir(parents=True, exist_ok=True)
    built = builtin_brushes_dir()
    if not built.is_dir():
        return user
    # Seed every preset JSON + every thumbnail PNG. Two extensions
    # cover the entire shipped builtin tree; explicit extension list
    # protects against accidentally seeding stray editor files
    # (.DS_Store, .swp, etc.) that may have landed in the package
    # tree during development.
    import json as _json
    for ext in ("*.json", "*.png"):
        for src in built.rglob(ext):
            try:
                rel = src.relative_to(built)
            except ValueError:
                continue
            dst = user / rel
            if dst.exists():
                # For JSON presets, additively patch metadata fields
                # that the user copy is missing (e.g. when a new
                # builtin field like `thumbnail` ships in a Designer
                # update). User edits to existing fields are
                # preserved — we never overwrite values, only fill
                # in keys that don't exist yet.
                if ext == "*.json":
                    try:
                        user_data = _json.loads(dst.read_text())
                        built_data = _json.loads(src.read_text())
                        if isinstance(user_data, dict) and isinstance(built_data, dict):
                            changed = False
                            for k in ("thumbnail",):
                                if k not in user_data and k in built_data:
                                    user_data[k] = built_data[k]
                                    changed = True
                            if changed:
                                dst.write_text(_json.dumps(user_data, indent=2))
                    except Exception:
                        pass
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass
    return user


# ---- library index ---------------------------------------------------------

class Library:
    """In-memory snapshot of every available preset. Holds two indexes:

    * `by_id` — dict[preset_id, Preset]
    * `by_category` — dict[category_path, list[Preset]] (insertion-ordered)

    Plus a token-based search index so the Library Modal's search box
    filters thousands of presets in O(1) per token.
    """

    def __init__(self) -> None:
        self.by_id: dict[str, Preset] = {}
        self.by_category: dict[str, list[Preset]] = {}
        self._search_index: dict[str, set[str]] = {}

    # ---- public API ----------------------------------------------------

    def all(self) -> list[Preset]:
        return list(self.by_id.values())

    def get(self, preset_id: str) -> Preset | None:
        return self.by_id.get(preset_id)

    def categories(self) -> list[str]:
        return list(self.by_category.keys())

    def search(self, query: str) -> list[Preset]:
        """Tokenise the query, intersect each token's posting list,
        return matching presets in stable order. Empty query → all."""
        q = (query or "").strip().lower()
        if not q:
            return self.all()
        tokens = [tok for tok in q.replace("/", " ").split() if tok]
        if not tokens:
            return self.all()
        hit_ids: set[str] | None = None
        for tok in tokens:
            posting: set[str] = set()
            # Substring match on every token in the index — slower than
            # exact-token, but expected library sizes (< 5k presets)
            # make this trivial.
            for index_tok, ids in self._search_index.items():
                if tok in index_tok:
                    posting |= ids
            if hit_ids is None:
                hit_ids = posting
            else:
                hit_ids &= posting
            if not hit_ids:
                return []
        return [self.by_id[pid] for pid in (hit_ids or [])]

    # ---- loading -------------------------------------------------------

    def load(self, *dirs: Path | str) -> None:
        """Walk each directory recursively, loading every `*.json` as
        a Preset. Later directories override earlier ones by preset ID,
        so the user-global dir overlays builtin defaults and a per-skin
        `brushes/` override beats the user-global one."""
        for d in dirs:
            d = Path(d)
            if not d.is_dir():
                continue
            # Known non-preset filenames at the root of the user dir
            # (sidecar configs the Designer writes alongside presets).
            SKIP_NAMES = {"favorites.json"}
            for p in sorted(d.rglob("*.json")):
                if p.name in SKIP_NAMES:
                    continue
                preset = load_preset(p)
                if preset is None or not preset.id:
                    continue
                self._register(preset)
        self._rebuild_search_index()

    def reload(self, *dirs: Path | str) -> None:
        """Drop the existing index + reload from disk. Use on
        hot-reload of brush files."""
        self.by_id.clear()
        self.by_category.clear()
        self._search_index.clear()
        self.load(*dirs)

    # ---- internal helpers ---------------------------------------------

    def _register(self, preset: Preset) -> None:
        # Last-write-wins per ID (so per-skin overrides shadow user-global).
        if preset.id in self.by_id:
            old = self.by_id[preset.id]
            cat_list = self.by_category.get(old.category) or []
            if old in cat_list:
                cat_list.remove(old)
        self.by_id[preset.id] = preset
        self.by_category.setdefault(preset.category, []).append(preset)

    def _rebuild_search_index(self) -> None:
        idx: dict[str, set[str]] = {}
        for preset in self.by_id.values():
            tokens = self._tokens_for(preset)
            for tok in tokens:
                idx.setdefault(tok, set()).add(preset.id)
        self._search_index = idx

    def _tokens_for(self, preset: Preset) -> set[str]:
        """Flatten name + category path + tags + engine into a
        lowercase token set for the search index."""
        bits: list[str] = []
        bits.extend(preset.name.lower().split())
        bits.extend(preset.category.lower().replace("/", " ").split())
        bits.extend(t.lower() for t in preset.tags)
        bits.append(preset.engine.lower())
        return {b for b in bits if b}


# ---- module-level singleton -------------------------------------------------

_LIBRARY: Library | None = None


def library() -> Library:
    """Lazy singleton. First call seeds the user dir from the package's
    builtin presets and loads everything into the index."""
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = Library()
        user = ensure_user_dir_seeded()
        _LIBRARY.load(user)
    return _LIBRARY


def reload_with_skin(skin_path: Path | str | None) -> Library:
    """Re-walk the user-global dir + the per-skin override dir (if
    present). Called by the Designer when a new .esk is opened so a
    skin-specific brush set takes effect immediately."""
    lib = library()
    dirs: list[Path] = [user_brushes_dir()]
    if skin_path:
        sk = Path(skin_path) / "brushes"
        if sk.is_dir():
            dirs.append(sk)
    lib.reload(*dirs)
    return lib
