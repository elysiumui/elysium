"""Unified entry point for the brush-file importers.

Dispatches by file extension, returns a list of Presets (one input
file can produce many — a .abr typically contains 10-200 brushes).
Caller is responsible for writing each preset's JSON into the user
library dir + reloading the library index.
"""
from __future__ import annotations

from pathlib import Path

from .preset import Preset, save_preset
from . import abr as _abr
from . import sut as _sut
from . import elybrush as _ely


_KNOWN_EXTS = (".abr", ".sut", ".elybrush", ".elybrush-set")


def is_brush_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _KNOWN_EXTS


def import_brush_file(path: str | Path,
                       assets_dir: str | Path | None = None) -> list[Preset]:
    """Parse `path` and return the Presets it contains. The returned
    Presets are NOT yet on disk — callers should call
    `save_imported_presets()` to actually populate the library.

    Stamp images extracted from .abr/.sut/.elybrush land in
    `assets_dir` (default: a sibling `imported_assets/` folder)."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".abr":
        return _abr.read_abr(p, assets_dir=assets_dir)
    if ext == ".sut":
        return _sut.read_sut(p, assets_dir=assets_dir)
    if ext in (".elybrush", ".elybrush-set"):
        return _ely.read_elybrush(p, extract_to=assets_dir)
    return []


def save_imported_presets(presets: list[Preset],
                           user_dir: Path) -> list[Path]:
    """Write each imported preset as its own JSON file under
    `user_dir/<engine_slug>/<preset_slug>.json`. Returns the list of
    paths written so callers can show "imported N brushes" status."""
    import re
    out: list[Path] = []
    for preset in presets:
        slug = preset.id.split(".", 1)[-1] if "." in preset.id else preset.id
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", slug).strip("_") or "brush"
        # Group imported brushes into a subfolder per source so the
        # user can find / delete a batch easily.
        if preset.imported_from:
            src_name = Path(preset.imported_from).stem
            subdir = re.sub(r"[^A-Za-z0-9]+", "_", src_name).strip("_") or "imported"
            dst_dir = user_dir / "imported" / subdir
        else:
            dst_dir = user_dir
        dst = dst_dir / f"{slug}.json"
        # Avoid collisions if two imports produce the same slug.
        if dst.exists():
            for n in range(2, 9999):
                cand = dst_dir / f"{slug}_{n}.json"
                if not cand.exists():
                    dst = cand
                    break
        try:
            save_preset(preset, dst)
            out.append(dst)
        except Exception:
            continue
    return out
