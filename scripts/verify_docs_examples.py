#!/usr/bin/env python3
"""Verify that every ```python code block in the docs sites compiles.

We extract every fenced ```python block from both `docs/` and `docs-designer/`,
compile each one (without executing it), and report any SyntaxError. This
catches the most common form of doc-rot: a code sample's API drifted but the
prose still references the old signature.

This script does NOT execute the blocks (that would require a window, GPU,
display, etc.). It only runs `compile(src, filename, "exec")`. Blocks tagged
``` ```python no-check ``` ``` are skipped so we can ship aspirational
examples that intentionally don't compile yet.

Run from the repo root:

  python scripts/verify_docs_examples.py

Exits 0 on success, 1 on any compilation failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
ROOTS = (REPO_ROOT / "docs", REPO_ROOT / "docs-designer")

# Match a fenced code block of language python (case-insensitive). Optional
# trailing attribute `no-check` skips the block (escape hatch for samples
# that reference roadmap APIs).
FENCE_RE = re.compile(
    r"```python(?P<attrs>[^\n]*)\n(?P<body>.*?)\n```",
    re.DOTALL,
)


def _iter_blocks(text: str) -> Iterable[tuple[str, str]]:
    for m in FENCE_RE.finditer(text):
        attrs = (m.group("attrs") or "").strip()
        if "no-check" in attrs:
            continue
        yield attrs, m.group("body")


def main(argv: list[str] | None = None) -> int:
    errors: list[tuple[Path, int, SyntaxError]] = []
    block_count = 0
    file_count = 0
    for root in ROOTS:
        if not root.is_dir():
            continue
        for md in sorted(root.rglob("*.md")):
            text = md.read_text()
            file_count += 1
            for attrs, body in _iter_blocks(text):
                block_count += 1
                try:
                    compile(body, str(md), "exec")
                except SyntaxError as exc:
                    errors.append((md, exc.lineno or 0, exc))
    print(
        f"checked {block_count} python block(s) across {file_count} doc files "
        f"under {', '.join(str(r) for r in ROOTS)}"
    )
    if errors:
        print(f"\nFAILED with {len(errors)} compile error(s):")
        for md, line, exc in errors:
            print(f"  {md}:{line}: {exc.msg}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
