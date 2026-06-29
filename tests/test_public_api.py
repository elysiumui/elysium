"""Public-API surface lock — operationalizes strict semver (1.0+).

Every public Elysium module declares an ``__all__``; this snapshots the union
into ``tests/_api_surface.json`` and fails if the live surface drifts. A
failure is a signal, not a bug: if the change is intentional, regenerate with
``UPDATE_API_SURFACE=1 pytest tests/test_public_api.py`` and record it in
``CHANGELOG.md`` (and, if it removes/renames anything, follow the deprecation
path in ``docs/guides/api-stability.md``).
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

# Every module that is part of the committed public API.
PUBLIC_MODULES = [
    "elysium",
    "elysium.components",
    "elysium.components.dataentry",
    "elysium.components.scroll",
    "elysium.components.virtual",
    "elysium.components.completer",
    "elysium.components.daterange",
    "elysium.components.dashboard",
    "elysium.layout",
    "elysium.theme",
    "elysium.anim",
    "elysium.reactive",
    "elysium.input",
    "elysium.text",
    "elysium.text.richtext",
    "elysium.dialogs",
    "elysium.modelview",
    "elysium.modelview.grid",
    "elysium.concurrency",
    "elysium.windowing",
    "elysium.native",
    "elysium.i18n",
    "elysium.locale",
    "elysium.settings",
    "elysium.dnd",
    "elysium.testing",
    "elysium.focus",
    "elysium.accessibility",
    "elysium.shell",
    "elysium.graphics",
    "elysium.charts",
    "elysium.commands",
    "elysium.styling",
]

_SNAPSHOT = Path(__file__).parent / "_api_surface.json"


def _live_surface() -> dict[str, list[str]]:
    surface: dict[str, list[str]] = {}
    for name in PUBLIC_MODULES:
        mod = importlib.import_module(name)
        exported = getattr(mod, "__all__", None)
        assert exported is not None, f"{name} must define __all__ (it is public)"
        surface[name] = sorted(exported)
    return surface


def test_every_public_module_declares_all():
    for name in PUBLIC_MODULES:
        mod = importlib.import_module(name)
        assert hasattr(mod, "__all__"), f"{name} is public but has no __all__"


def test_no_private_names_exported():
    for name in PUBLIC_MODULES:
        mod = importlib.import_module(name)
        for sym in getattr(mod, "__all__", []):
            assert not sym.startswith("_") or sym == "__version__", (
                f"{name}.__all__ exports private name {sym!r}")


def test_exported_names_are_resolvable():
    for name in PUBLIC_MODULES:
        mod = importlib.import_module(name)
        for sym in getattr(mod, "__all__", []):
            assert hasattr(mod, sym), f"{name}.__all__ lists {sym!r} but it isn't defined"


def test_public_surface_matches_snapshot():
    live = _live_surface()
    if os.environ.get("UPDATE_API_SURFACE") == "1":
        _SNAPSHOT.write_text(json.dumps(live, indent=2, sort_keys=True) + "\n")
        pytest.skip("regenerated API surface snapshot")
    assert _SNAPSHOT.exists(), (
        "tests/_api_surface.json missing — run UPDATE_API_SURFACE=1 pytest "
        "tests/test_public_api.py to create it")
    locked = json.loads(_SNAPSHOT.read_text())

    # Per-module diff for a readable failure.
    drift: list[str] = []
    for name in PUBLIC_MODULES:
        want = locked.get(name, [])
        got = live.get(name, [])
        added = sorted(set(got) - set(want))
        removed = sorted(set(want) - set(got))
        if added or removed:
            drift.append(f"{name}: +{added} -{removed}")
    assert not drift, (
        "Public API surface changed:\n  " + "\n  ".join(drift) +
        "\n\nIf intentional: UPDATE_API_SURFACE=1 pytest tests/test_public_api.py"
        " + add a CHANGELOG entry (removals/renames need the deprecation path).")
