#!/usr/bin/env python3
"""Bump the Elysium release version everywhere it must stay in lockstep.

Usage:  python scripts/bump-version.py X.Y.Z

The framework version lives in THREE places that must always agree, or the
published wheel and the compiled-in native ``__version__`` desync (this bit us
once: 1.1.3 shipped a 1.1.2-stamped ``.so``). This bumps all three atomically:

  * pyproject.toml               -> the wheel / distribution version
  * elysium-native/Cargo.toml    -> the Rust workspace version, which the native
                                    module exposes as ``_n.__version__``
  * python/elysium/__init__.py   -> the source-tree fallback literal

CI enforces the invariant from two sides: ``build.yml`` fails if pyproject and
the Rust workspace disagree, and ``release-library.yml`` installs the published
wheel and asserts ``elysium.__version__`` == the tag. This script is how you
avoid tripping either. After running it, update CHANGELOG.md and follow
RELEASING.md.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _replace_once(rel: str, pattern: str, repl: str, label: str) -> None:
    path = ROOT / rel
    text = path.read_text()
    new, n = re.subn(pattern, repl, text, count=1)
    if n != 1:
        raise SystemExit(f"error: {rel}: expected exactly 1 {label} match, got {n}")
    path.write_text(new)
    print(f"  {rel}: {label} updated")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        raise SystemExit("usage: python scripts/bump-version.py X.Y.Z")
    v = sys.argv[1]
    # pyproject: the first top-level `version = "..."` is [project].version.
    _replace_once("pyproject.toml",
                  r'(?m)^(version\s*=\s*)"[^"]+"', rf'\g<1>"{v}"', "wheel version")
    # Cargo: the first `version = "..."` is [workspace.package].version.
    _replace_once("elysium-native/Cargo.toml",
                  r'(?m)^(version\s*=\s*)"[^"]+"', rf'\g<1>"{v}"', "Rust workspace version")
    # __init__: the source-tree fallback literal in the version block.
    _replace_once("python/elysium/__init__.py",
                  r'(getattr\(_nmod, "__version__", None\) or )"[^"]+"',
                  rf'\g<1>"{v}"', "source fallback")
    print(f"\nBumped to {v}. Next: update CHANGELOG.md, run the tests, then RELEASING.md.")


if __name__ == "__main__":
    main()
