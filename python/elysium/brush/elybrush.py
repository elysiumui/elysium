"""Native .elybrush format — a zip archive containing:

  preset.json     — the Preset.to_dict() serialization
  thumbnail.png   — optional preview tile (raw RGBA PNG)
  stamp.png       — optional brush-tip image referenced by params["pattern_path"]

The single-file `.elybrush` is the share-friendly unit. Multiple
brushes pack into `.elybrush-set` zips (a zip-of-zips), which the
importer auto-recurses into.

This format is fully under our control — schema lives here, no
backward-compatibility burden, and any field the Preset dataclass
gains automatically survives a round-trip without changes to this
module.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from .preset import Preset


def write_elybrush(preset: Preset, dst: str | Path,
                    stamp_image_path: str | Path | None = None,
                    thumbnail_path: str | Path | None = None) -> Path:
    """Pack a Preset (plus optional stamp + thumbnail images) into a
    single `.elybrush` archive at `dst`. Returns the written path."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("preset.json", json.dumps(preset.to_dict(), indent=2))
        if stamp_image_path:
            sp = Path(stamp_image_path)
            if sp.is_file():
                zf.write(sp, arcname="stamp.png")
        if thumbnail_path:
            tp = Path(thumbnail_path)
            if tp.is_file():
                zf.write(tp, arcname="thumbnail.png")
    return dst


def read_elybrush(src: str | Path,
                    extract_to: str | Path | None = None) -> list[Preset]:
    """Read a `.elybrush` (single preset) or `.elybrush-set` (zip of
    multiple `.elybrush`). Extracts any stamp/thumbnail images into
    `extract_to` (defaults to a sibling `assets/` dir of the source)
    and rewrites preset.params["pattern_path"] to point at the
    extracted file. Returns the list of Presets ready to register
    with the Library."""
    src = Path(src)
    if not src.is_file():
        return []
    target_dir = Path(extract_to) if extract_to else (src.parent / "elybrush_assets")
    target_dir.mkdir(parents=True, exist_ok=True)
    out: list[Preset] = []
    with zipfile.ZipFile(src, "r") as zf:
        names = zf.namelist()
        # Set archive: zip-of-zips. Each inner .elybrush gets read
        # recursively.
        if any(n.endswith(".elybrush") for n in names):
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                for n in names:
                    if not n.endswith(".elybrush"):
                        continue
                    extracted = td_path / Path(n).name
                    extracted.write_bytes(zf.read(n))
                    out.extend(read_elybrush(extracted, extract_to=target_dir))
            return out
        # Single preset.
        if "preset.json" not in names:
            return []
        data = json.loads(zf.read("preset.json").decode("utf-8"))
        preset = Preset.from_dict(data)
        # Extract stamp.png if present + rewrite pattern_path.
        if "stamp.png" in names:
            stamp_dst = target_dir / f"{preset.id.replace('.', '_')}_stamp.png"
            stamp_dst.write_bytes(zf.read("stamp.png"))
            preset.params["pattern_path"] = str(stamp_dst)
        if "thumbnail.png" in names:
            thumb_dst = target_dir / f"{preset.id.replace('.', '_')}_thumb.png"
            thumb_dst.write_bytes(zf.read("thumbnail.png"))
            preset.thumbnail = str(thumb_dst)
        # Mark as imported so the source field is honest.
        if preset.source == "user" or not preset.source:
            preset.source = f"imported:elybrush:{src.name}"
        out.append(preset)
    return out
