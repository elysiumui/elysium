"""Preset — the saved configuration of a brush.

A preset is a small JSON dict referencing an Engine (by ID) + the
parameter values the user wants. Presets are first-class files on disk;
adding 50 new presets is dropping 50 JSON files into the library dir,
no code change required.

Schema:
    {
      "id":            "elysium.ink.fineliner",       # stable ID
      "name":          "Fineliner",                    # display name
      "engine":        "RoundStamp",                   # references engine.ID
      "params":        {"size": 6, "flow": 0.85, ...}, # engine.PARAM_SCHEMA
      "color_mode":    "active",                       # "active"|"fixed"|"image"
      "fixed_color":   [0, 0, 0, 255],                 # only when color_mode=fixed
      "thumbnail":     "thumbs/ink_fineliner.png",     # optional, relative to preset's dir
      "category":      "Ink / Liners",                 # hierarchy path; "A / B / C"
      "tags":          ["ink", "line", "thin"],
      "source":        "builtin",                      # "builtin"|"imported:abr"|"user"
      "imported_from": "",                             # path of the .abr / .sut
      "created_t":     1715000000.0,                   # unix epoch
      "last_used_t":   1715200000.0,
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from pathlib import Path
from typing import Any


@dataclass
class Preset:
    id: str
    name: str
    engine: str
    params: dict = field(default_factory=dict)
    color_mode: str = "active"
    fixed_color: tuple[int, int, int, int] = (0, 0, 0, 255)
    thumbnail: str = ""
    category: str = "Misc"
    tags: list[str] = field(default_factory=list)
    source: str = "user"
    imported_from: str = ""
    created_t: float = field(default_factory=time.time)
    last_used_t: float = 0.0
    # G-Brush Phase E — input-driven dynamics. Each key maps a stroke
    # input ("pressure" | "tilt" | "velocity") + a target param
    # ("size" | "opacity" | "spacing") to a 4-point bezier curve in
    # input-space. Stored as a flat dict keyed "<input>_<target>"
    # → list of 4 (x, y) pairs with x in [0,1] (input value) and y
    # being a multiplier on the base param (typically [0,2]).
    # Renderer integration is the Phase F+ ticket; Studio Phase E only
    # authors + persists.
    dynamics: dict = field(default_factory=dict)
    # Path on disk (set by the library walker — not serialized).
    _path: str = ""

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict. The leading-underscore
        `_path` field is omitted so reloads from disk don't pin a
        stale on-disk location into the JSON itself."""
        d = {
            "id": self.id,
            "name": self.name,
            "engine": self.engine,
            "params": dict(self.params),
            "color_mode": self.color_mode,
            "fixed_color": list(self.fixed_color),
            "thumbnail": self.thumbnail,
            "category": self.category,
            "tags": list(self.tags),
            "source": self.source,
            "imported_from": self.imported_from,
            "created_t": self.created_t,
            "last_used_t": self.last_used_t,
            "dynamics": {k: [list(pt) for pt in v]
                          for k, v in (self.dynamics or {}).items()},
        }
        return d

    @classmethod
    def from_dict(cls, d: dict, path: str = "") -> "Preset":
        """Tolerant loader — unknown fields are ignored, missing fields
        fall back to dataclass defaults so old preset files survive
        schema additions."""
        dyn_raw = d.get("dynamics", {}) or {}
        dynamics: dict = {}
        if isinstance(dyn_raw, dict):
            for k, v in dyn_raw.items():
                if not isinstance(v, list): continue
                pts = []
                for pt in v:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        pts.append((float(pt[0]), float(pt[1])))
                if pts: dynamics[str(k)] = pts
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "Unnamed")),
            engine=str(d.get("engine", "RoundStamp")),
            params=dict(d.get("params", {})),
            color_mode=str(d.get("color_mode", "active")),
            fixed_color=tuple(d.get("fixed_color", (0, 0, 0, 255))),
            thumbnail=str(d.get("thumbnail", "")),
            category=str(d.get("category", "Misc")),
            tags=list(d.get("tags", [])),
            source=str(d.get("source", "user")),
            imported_from=str(d.get("imported_from", "")),
            created_t=float(d.get("created_t", time.time())),
            last_used_t=float(d.get("last_used_t", 0.0)),
            dynamics=dynamics,
            _path=path,
        )


def load_preset(path: str | Path) -> Preset | None:
    p = Path(path)
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None
    # JSON file that isn't a preset dict (e.g. favorites.json which is
    # a top-level list) → silently skip so the library walker can
    # crawl a directory mixing presets + sidecar config files.
    if not isinstance(d, dict):
        return None
    if "engine" not in d or "id" not in d:
        return None
    return Preset.from_dict(d, path=str(p))


def save_preset(preset: Preset, path: str | Path | None = None) -> Path:
    """Write a preset JSON to disk. If `path` is omitted, uses the
    preset's existing `_path` (so save-in-place works); otherwise the
    new path is recorded so subsequent saves go there too."""
    dst = Path(path) if path else Path(preset._path)
    if not dst:
        raise ValueError("Preset has no path — pass one explicitly")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(preset.to_dict(), indent=2))
    preset._path = str(dst)
    return dst
