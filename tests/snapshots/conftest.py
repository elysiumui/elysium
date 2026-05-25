"""Per-platform golden-image conftest.

Goldens live at `tests/snapshots/<platform>/...`. Setting
`UPDATE_GOLDENS=1` in the environment causes tests that produce an
`.actual.png` sibling to copy it over the missing/stale golden, so a
runner on a new platform can self-populate on its first run.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

PLATFORM_DIR = Path(__file__).parent / sys.platform


def pytest_collection_modifyitems(config, items):
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def update_goldens_if_requested():
    yield
    if os.environ.get("UPDATE_GOLDENS") != "1":
        return
    for actual in PLATFORM_DIR.glob("*.actual.png"):
        golden = actual.with_name(actual.name.replace(".actual.png", ".png"))
        shutil.copy2(actual, golden)
        print(f"updated golden: {golden.relative_to(Path.cwd())}",
              file=sys.stderr)
