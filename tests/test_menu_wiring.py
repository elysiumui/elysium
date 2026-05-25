"""Regression test: every menu action in ``elysium-designer/menus.py``
must have a handler in ``elysium-designer/__main__.py`` — either a
direct ``cmd == "..."`` branch, a tupled ``cmd in (...)`` branch, a
namespace ``ns == "..."`` route, or a ``cmd.startswith(...)`` prefix
route.

Lacking a wiring path means the click silently lands on the
``coming soon`` fallback, which is what happened with File > Open
Skin until this test was added.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGNER_DIR = REPO_ROOT / "elysium-designer"


def _menu_actions() -> set[str]:
    sys.path.insert(0, str(DESIGNER_DIR))
    import menus as M  # type: ignore[import-not-found]
    out = set()
    for _top, items in M.MENUS:
        for it in items:
            label = it[0]
            action = it[1] if len(it) > 1 else ""
            if action and label != "---":
                out.add(action)
    return out


def _dispatcher_coverage() -> tuple[set[str], set[str], set[str]]:
    text = (DESIGNER_DIR / "__main__.py").read_text()
    direct = set(re.findall(r'cmd\s*==\s*"([a-z0-9_.]+)"', text))
    tupled: set[str] = set()
    for m in re.finditer(r'cmd\s+in\s+\(([^)]+)\)', text):
        for s in re.findall(r'"([a-z0-9_.]+)"', m.group(1)):
            tupled.add(s)
    namespace = set(re.findall(r'ns\s*==\s*"([a-z0-9_]+)"', text))
    starts = set(re.findall(r'cmd\.startswith\("([a-z0-9_.]+)"\)', text))
    return direct | tupled, namespace, starts


def test_every_menu_action_has_a_handler():
    actions = _menu_actions()
    direct_or_tupled, namespaces, starts = _dispatcher_coverage()
    unwired = []
    for a in sorted(actions):
        if a in direct_or_tupled:
            continue
        ns = a.split(".", 1)[0]
        if ns in namespaces:
            continue
        if any(a.startswith(s) for s in starts):
            continue
        unwired.append(a)
    assert not unwired, (
        "Menu actions with no dispatcher route — clicking these "
        "falls through to the 'coming soon' branch:\n  "
        + "\n  ".join(unwired))


def test_menu_action_count_is_audit_baseline():
    """Locks the baseline so a developer who *removes* a menu entry
    has to update this test consciously."""
    actions = _menu_actions()
    # Adjust this number deliberately when adding/removing menu items.
    expected = 226
    assert len(actions) == expected, (
        f"Menu action count changed: now {len(actions)}, was {expected}. "
        f"If intentional, update the expected value in this test.")


def test_no_native_dialog_calls_from_dispatch_paths():
    """`_n.open_file_dialog` calls NSOpenPanel.runModal which Cocoa
    pins to the main thread. The Designer's dispatch runs on the
    animation thread, so every native-dialog call from a menu /
    shelf action crashes the bundled .app. They must all go through
    `self._pick_file` (subprocess picker) instead.

    Regression guard: scan the designer module for any direct
    `_n.open_file_dialog(` call. None should remain.
    """
    text = (DESIGNER_DIR / "__main__.py").read_text()
    direct_calls = [
        (i + 1, ln) for i, ln in enumerate(text.splitlines())
        if "_n.open_file_dialog(" in ln
    ]
    assert not direct_calls, (
        "Found native dialog calls — these will crash the bundled "
        ".app when invoked from a menu/shelf:\n  "
        + "\n  ".join(f"line {n}: {l.strip()}" for n, l in direct_calls))
