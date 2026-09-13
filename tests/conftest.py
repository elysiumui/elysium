"""Shared pytest helpers for the Elysium test-suite.

The native extension (``elysium._native._native``) is built by maturin and is
absent on a fresh checkout. ``import elysium`` still succeeds without it and
sets ``elysium._NATIVE_AVAILABLE = False``; a module-scope
``from elysium._native import _native`` in a test file does not, and turns the
whole file into a collection error. Tests that need the extension must
therefore

* import it inside the test body (or a fixture), never at module scope, and
* be guarded so they skip, not fail, when the extension is not built.

The guard is the registered ``native`` marker; marked items are skipped by the
``pytest_collection_modifyitems`` hook below when the extension is absent::

    pytestmark = pytest.mark.native        # whole module

    @pytest.mark.native                    # or per test
    def test_x():
        from elysium._native import _native as n
        ...

``native_only`` is the same marker under the name several files already use
for their local ``skipif`` copy (``tests/test_phase1.py``, ``test_phase2.py``,
``test_butterfly.py``), so those can drop the copy and write
``pytestmark = pytest.mark.native`` when convenient.

Do NOT ``from conftest import ...`` in a test module: ``tests/snapshots/`` has
its own rootless ``conftest.py`` and pytest registers both under the module
name ``conftest``, so whichever loaded last wins and the import fails in a
full-suite run. Use the marker (no import needed) or a fixture instead.
"""
from __future__ import annotations

import pytest

NATIVE_SKIP_REASON = "native extension not built"


def native_available() -> bool:
    """True when the compiled ``elysium._native`` extension imported."""
    import elysium

    return bool(getattr(elysium, "_NATIVE_AVAILABLE", False))


#: Marker for tests that need the compiled extension; equal to ``pytest.mark.native``.
native_only = pytest.mark.native


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "native: test needs the compiled elysium._native extension "
        "(skipped when it is not built)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if native_available():
        return
    skip = pytest.mark.skip(reason=NATIVE_SKIP_REASON)
    for item in items:
        if item.get_closest_marker("native") is not None:
            item.add_marker(skip)
