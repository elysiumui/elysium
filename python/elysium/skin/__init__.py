"""Skin loading + variant selection.

Wraps the native loader with a thin Python helper that picks the right
variant subtree based on OS accessibility prefs (reduce-motion,
high-contrast), resolves any ``calc(...)`` arithmetic expressions in
numeric positions, and hands the resulting JSON to the renderer.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# calc(...) preprocessor (spec §6.5)
# ---------------------------------------------------------------------------

# Match `calc(<expr>)` where <expr> is any combination of integers,
# floats, the operators + - * /, parentheses, and whitespace. We refuse
# anything else (no names, no `100%` placeholders, no function calls)
# so the eval is safe.
_CALC_OUTER_RE = re.compile(r"^\s*calc\(\s*(.+?)\s*\)\s*$", re.DOTALL)
_CALC_TOKEN_RE = re.compile(
    r"\s*("
    r"\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?"   # number
    r"|\.\d+(?:[eE][+\-]?\d+)?"          # .5 form
    r"|[+\-*/()]"                        # operators
    r")\s*"
)


class CalcExpressionError(ValueError):
    """Raised when a ``calc(...)`` expression contains anything other
    than numeric literals + arithmetic operators + parentheses. Catches
    typos at load time instead of letting them silently corrupt the
    skin tree."""


def _eval_calc_expression(expr: str) -> float:
    """Evaluate an arithmetic ``calc(...)`` body. Allowed: numbers,
    ``+ - * /``, parentheses, whitespace. Anything else (identifiers,
    ``%``, function calls) raises ``CalcExpressionError``.

    The expression is tokenised, every token validated against the
    allow-list, then re-joined and passed to ``eval`` with an empty
    globals/locals. Restricting tokens this tightly means ``eval`` is
    only ever fed a textbook arithmetic expression and cannot escape.
    """
    tokens: list[str] = []
    pos = 0
    while pos < len(expr):
        m = _CALC_TOKEN_RE.match(expr, pos)
        if m is None:
            raise CalcExpressionError(
                f"calc(): unparseable character at position {pos} in "
                f"{expr!r}")
        tokens.append(m.group(1))
        pos = m.end()
    if not tokens:
        raise CalcExpressionError(f"calc(): empty expression {expr!r}")
    safe = " ".join(tokens)
    try:
        # Empty globals/locals so identifiers can't resolve. The
        # tokeniser already rejected anything but numbers + operators
        # + parens; this is belt + suspenders.
        result = eval(safe, {"__builtins__": {}}, {})
    except Exception as exc:
        raise CalcExpressionError(
            f"calc({expr!r}) evaluation failed: {exc}") from exc
    if not isinstance(result, (int, float)):
        raise CalcExpressionError(
            f"calc({expr!r}) did not produce a number")
    return float(result)


def _resolve_calc_in_tree(node: Any) -> Any:
    """Walk an arbitrary parsed-JSON tree and replace every
    ``"calc(...)"`` string with the evaluated number. Mutates dicts +
    lists in place; returns the (possibly replaced) value so leaf
    callers can reassign.

    Strings that are not ``calc(...)`` are left untouched, so authors
    can keep using string-valued fields (paths, colour hexes, hook
    names) freely.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            node[k] = _resolve_calc_in_tree(v)
        return node
    if isinstance(node, list):
        for i, v in enumerate(node):
            node[i] = _resolve_calc_in_tree(v)
        return node
    if isinstance(node, str):
        m = _CALC_OUTER_RE.match(node)
        if m is not None:
            return _eval_calc_expression(m.group(1))
    return node


def _stage_with_calc_resolved(p: Path,
                              variant_doc_text: str | None
                              ) -> Path | None:
    """Stage a skin bundle into a temp dir, with `document.json`
    rewritten so all ``calc(...)`` strings have been resolved to
    literal numbers. When ``variant_doc_text`` is provided it replaces
    the default document before calc resolution runs.

    Returns the staged path, or None when ``p`` isn't a directory
    bundle (caller falls back to native loader directly)."""
    if not p.is_dir():
        return None
    doc_path = p / "document.json"
    if variant_doc_text is None and not doc_path.is_file():
        # Nothing to rewrite. Skip staging.
        return None
    raw = (variant_doc_text if variant_doc_text is not None
           else doc_path.read_text())
    try:
        doc = json.loads(raw)
    except Exception:
        # Malformed JSON: hand the original off to the native loader
        # so it emits the canonical parse error.
        return None
    if not _document_has_calc(doc) and variant_doc_text is None:
        # Fast path: no rewriting needed.
        return None
    _resolve_calc_in_tree(doc)
    staged = Path(tempfile.mkdtemp(prefix="elysium-skin-calc-"))
    for entry in p.iterdir():
        if entry.is_dir() and entry.name != "variants":
            shutil.copytree(entry, staged / entry.name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        elif entry.is_file() and entry.name != "document.json":
            shutil.copy2(entry, staged / entry.name)
    (staged / "document.json").write_text(json.dumps(doc))
    return staged


def _document_has_calc(node: Any) -> bool:
    """Cheap pre-check: scan the tree for any ``"calc(...)"`` string so
    we can avoid the staging round-trip when no expression is present."""
    if isinstance(node, dict):
        return any(_document_has_calc(v) for v in node.values())
    if isinstance(node, list):
        return any(_document_has_calc(v) for v in node)
    if isinstance(node, str):
        return _CALC_OUTER_RE.match(node) is not None
    return False


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_skin(path: str | Path, *, variant: str | None = None) -> Any:
    """Load a ``.esk`` skin and pick the variant.

    Variant resolution:

    1. If ``variant`` is passed, use it verbatim.
    2. Otherwise read the user's OS prefs via
       ``elysium.accessibility.variant_for()`` — ``"reduce_motion"`` or
       ``"high_contrast"`` when those prefs are on.
    3. Fall back to the default tree at ``document.json``.

    A skin advertises its variants by shipping
    ``variants/<name>.json`` next to ``document.json``; the file replaces
    the document tree when that variant is active.

    Before the document is passed to the native loader, any
    ``"calc(<expr>)"`` strings in numeric positions are resolved to
    their evaluated numbers (spec §6.5). Allowed expression grammar:
    decimal / scientific-notation numbers, ``+ - * /``, parentheses,
    whitespace. Anything else (identifiers, ``%``, function calls)
    raises ``CalcExpressionError`` at load time so authors find typos
    before they corrupt the rendered tree.
    """
    from elysium._native import _native as _n

    p = Path(path)
    if variant is None:
        try:
            from elysium.accessibility import variant_for
            variant = variant_for()
        except Exception:
            variant = None

    variant_doc_text: str | None = None
    if variant and p.is_dir():
        candidate = p / "variants" / f"{variant}.json"
        if candidate.is_file():
            variant_doc_text = candidate.read_text()

    # Spec §6.6: populate the process-wide glyph atlas from
    # `<bundle>/assets/icons/`. IconButton looks up `icon` names in
    # this atlas; the call is a no-op when the directory is missing
    # or the bundle is not a directory (e.g. a packed `.esk` file).
    if p.is_dir():
        icons_dir = p / "assets" / "icons"
        if icons_dir.is_dir():
            try:
                from elysium.components import get_default_atlas
                get_default_atlas().load_from_directory(icons_dir)
            except Exception:
                # An icon-loader failure must never block skin load;
                # IconButton will fall back to text rendering when an
                # atlas entry is missing.
                pass

    staged = _stage_with_calc_resolved(p, variant_doc_text)
    if staged is not None:
        return _n.load_skin(str(staged))
    return _n.load_skin(str(p))


__all__ = ["load_skin", "CalcExpressionError"]
