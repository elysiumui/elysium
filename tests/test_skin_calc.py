"""Tests for the ``calc(...)`` preprocessor in
``elysium.skin.load_skin`` (spec §6.5).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from elysium.skin import (
    CalcExpressionError,
    _document_has_calc,
    _eval_calc_expression,
    _resolve_calc_in_tree,
)


# ---------------------------------------------------------------------------
# Expression evaluator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("1 + 2",          3.0),
        ("100 - 4",        96.0),
        ("3 * 4",          12.0),
        ("10 / 4",         2.5),
        ("800 - 116 - 320", 364.0),    # spec §6.5 example minus the `%`
        ("(2 + 3) * 4",    20.0),
        (" 1.5 + 2.5 ",    4.0),
        ("1e2 + 1",        101.0),
        (".5 * 4",         2.0),
        ("-3 + 5",         2.0),       # unary minus inside parser
    ],
)
def test_eval_calc_expression_arithmetic(expr, expected):
    assert _eval_calc_expression(expr) == pytest.approx(expected)


@pytest.mark.parametrize(
    "bad",
    [
        "100%",               # percent placeholder not yet supported
        "foo + 1",            # identifier
        "1 + a",              # identifier
        "__import__('os')",   # injection attempt
        "1; 2",               # semicolon
        "1 ** 2",             # disallowed operator
        "1 // 2",             # floor-div (two-char operator)
        "1 & 2",              # bitwise
        "",                   # empty
    ],
)
def test_eval_calc_expression_rejects_non_arithmetic(bad):
    with pytest.raises(CalcExpressionError):
        _eval_calc_expression(bad)


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def test_resolve_calc_in_tree_replaces_strings():
    tree = {
        "root": {
            "size": {"w": "calc(800 - 116 - 320)", "h": 480},
            "children": [
                {"type": "path", "x": "calc(10 + 5)", "y": 7},
                {"type": "text", "value": "hello, world",
                 "font_size": "calc( 12 + 4 )"},
            ],
        },
        "id": "literal-string-is-passthrough",
    }
    _resolve_calc_in_tree(tree)
    assert tree["root"]["size"]["w"] == 364.0
    assert tree["root"]["size"]["h"] == 480     # untouched literal
    assert tree["root"]["children"][0]["x"] == 15.0
    assert tree["root"]["children"][1]["font_size"] == 16.0
    # Non-calc strings stay strings.
    assert tree["root"]["children"][1]["value"] == "hello, world"
    assert tree["id"] == "literal-string-is-passthrough"


def test_resolve_calc_handles_lists_of_calcs():
    tree = {"stops": ["calc(1 + 1)", "calc(2 * 2)", 9, "name"]}
    _resolve_calc_in_tree(tree)
    assert tree["stops"] == [2.0, 4.0, 9, "name"]


def test_resolve_calc_raises_on_malformed_expression():
    tree = {"x": "calc(foo + 1)"}
    with pytest.raises(CalcExpressionError):
        _resolve_calc_in_tree(tree)


def test_document_has_calc_detects_calc():
    assert _document_has_calc({"x": "calc(1 + 1)"})
    assert _document_has_calc({"a": {"b": ["x", "calc(0)"]}})
    assert not _document_has_calc({"x": 12, "y": "hello"})
    assert not _document_has_calc("plain string")


# ---------------------------------------------------------------------------
# End-to-end: stage_with_calc_resolved rewrites document.json
# ---------------------------------------------------------------------------


def test_stage_with_calc_resolved_rewrites_disk(tmp_path):
    """`_stage_with_calc_resolved` produces a temp bundle whose
    document.json no longer contains any ``calc(...)`` strings."""
    from elysium.skin import _stage_with_calc_resolved

    src = tmp_path / "demo.esk"
    src.mkdir()
    (src / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "id": "x", "name": "demo", "version": "0.1.0",
    }))
    (src / "document.json").write_text(json.dumps({
        "root": {
            "type": "scene", "id": "root",
            "size": {"w": "calc(800 - 320)", "h": 480},
            "children": [],
        },
    }))
    staged = _stage_with_calc_resolved(src, None)
    assert staged is not None
    new_doc = json.loads((staged / "document.json").read_text())
    assert new_doc["root"]["size"]["w"] == 480.0
    # No calc(...) string survives.
    text = (staged / "document.json").read_text()
    assert "calc(" not in text


def test_stage_with_calc_resolved_skips_when_no_calc(tmp_path):
    """Fast-path: if document.json has no calc(...), the staging
    function returns None so the loader uses the original bundle in
    place (no extra IO)."""
    from elysium.skin import _stage_with_calc_resolved

    src = tmp_path / "demo.esk"
    src.mkdir()
    (src / "document.json").write_text(json.dumps({
        "root": {"type": "scene", "id": "r",
                 "size": {"w": 100, "h": 100}, "children": []},
    }))
    assert _stage_with_calc_resolved(src, None) is None


def test_stage_with_calc_resolved_uses_variant_override(tmp_path):
    """When ``variant_doc_text`` is provided, it replaces the default
    document before calc resolution runs."""
    from elysium.skin import _stage_with_calc_resolved

    src = tmp_path / "demo.esk"
    src.mkdir()
    (src / "document.json").write_text(json.dumps({
        "root": {"type": "scene", "id": "default",
                 "size": {"w": 100, "h": 100}, "children": []},
    }))
    variant_text = json.dumps({
        "root": {"type": "scene", "id": "hc",
                 "size": {"w": "calc(50 + 50)", "h": 100}, "children": []},
    })
    staged = _stage_with_calc_resolved(src, variant_text)
    assert staged is not None
    doc = json.loads((staged / "document.json").read_text())
    assert doc["root"]["id"] == "hc"
    assert doc["root"]["size"]["w"] == 100.0
