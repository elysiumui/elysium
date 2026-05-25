"""Public brush API.

This package is the Phase A foundation for the Procreate + CSP hybrid
brush system. See ``docs/brush-palette-plan.md`` for the full design.

The public surface is intentionally small:

* ``register_engine`` / ``get_engine`` / ``list_engines`` — the engine
  registry. Each ``engines/<name>.py`` module calls ``register_engine``
  at import time.
* ``library()`` — singleton Library that walks the on-disk preset
  directories and indexes everything for fast lookup + search.
* ``Preset`` / ``load_preset`` / ``save_preset`` — preset record IO.
* ``user_brushes_dir`` / ``builtin_brushes_dir`` — path resolution.

Importing this module triggers a side-effect: every engine in
``engines/`` is imported so its ``register_engine(...)`` call fires.
That way callers can ``from elysium import brush`` and immediately
have all engines available without needing to know their names.
"""
from __future__ import annotations

from .engine import (
    BrushEngine,
    ParamSpec,
    get_engine,
    list_engines,
    register_engine,
    apply_dynamics,
)
from .preset import Preset, load_preset, save_preset
from .library import (
    Library,
    library,
    reload_with_skin,
    user_brushes_dir,
    builtin_brushes_dir,
    ensure_user_dir_seeded,
)
from .importers import (
    import_brush_file,
    save_imported_presets,
    is_brush_file,
)
from .elybrush import write_elybrush, read_elybrush

# Import every engine module so it registers itself. This must run
# BEFORE any code calls `list_engines()` so the registry is populated.
# Each module is idempotent — re-importing is safe (last-write-wins on
# the ID).
from .engines import round_stamp as _round_stamp  # noqa: F401
from .engines import wet_mix as _wet_mix          # noqa: F401
from .engines import bristle as _bristle          # noqa: F401
from .engines import airbrush as _airbrush        # noqa: F401
from .engines import pattern as _pattern          # noqa: F401
from .engines import texture as _texture          # noqa: F401


__all__ = [
    "BrushEngine", "ParamSpec",
    "register_engine", "get_engine", "list_engines", "apply_dynamics",
    "Preset", "load_preset", "save_preset",
    "Library", "library", "reload_with_skin",
    "user_brushes_dir", "builtin_brushes_dir", "ensure_user_dir_seeded",
    "import_brush_file", "save_imported_presets", "is_brush_file",
    "write_elybrush", "read_elybrush",
]
