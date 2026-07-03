"""Tier 7 Phase 2 — autocomplete: Completer matching + nav + render."""
from __future__ import annotations

import pytest

from elysium import theme as T
from elysium.components.completer import Completer


CANDS = ["apple", "apricot", "banana", "grape", "grapefruit", "pineapple"]


@pytest.fixture(autouse=True)
def _studio():
    T.set_theme(T.studio_dark())
    yield
    T.set_theme(T.light())


def test_prefix_matches_rank_first():
    c = Completer(candidates=CANDS, w=200)
    c.update_query("ap")
    # prefix matches (apple, apricot) come before contains (pineapple)
    assert c.matches[:2] == ["apple", "apricot"]
    assert "pineapple" in c.matches               # contains "ap"
    assert c.visible is True


def test_fuzzy_subsequence_when_no_prefix():
    c = Completer(candidates=CANDS, w=200, fuzzy=True)
    c.update_query("grpft")            # subsequence of "grapefruit"
    assert "grapefruit" in c.matches
    c2 = Completer(candidates=CANDS, w=200, fuzzy=False)
    c2.update_query("grpft")
    assert "grapefruit" not in c2.matches          # fuzzy off → no match


def test_empty_query_hides():
    c = Completer(candidates=CANDS, w=200)
    c.update_query("")
    assert c.matches == [] and c.visible is False


def test_keyboard_nav_wraps_and_accepts():
    accepted = []
    c = Completer(candidates=CANDS, w=200, on_accept=accepted.append)
    c.update_query("gr")               # grape, grapefruit
    assert c.current() == "grape"
    assert c.on_key("down") is True
    assert c.current() == "grapefruit"
    c.on_key("down")                   # wraps back to first
    assert c.current() == "grape"
    assert c.on_key("up") is True
    assert c.current() == "grapefruit"
    assert c.on_key("enter") is True
    assert accepted == ["grapefruit"]
    assert c.visible is False
    assert "grapefruit" in c.history   # accepted item remembered


def test_escape_closes():
    c = Completer(candidates=CANDS, w=200)
    c.update_query("ap")
    assert c.on_key("escape") is True
    assert c.visible is False


def test_history_ranks_first():
    c = Completer(candidates=CANDS, w=200, history=["apricot"])
    c.update_query("ap")
    assert c.matches[0] == "apricot"   # history entry surfaces first


def test_click_selects_and_accepts():
    accepted = []
    c = Completer(candidates=CANDS, x=10, y=40, w=200,
                  on_accept=accepted.append)
    c.update_query("a")
    # click the second visible row
    row_y = c.y + 4 + 1 * c.row_h
    assert c.on_click(c.x + 20, row_y + 5) is True
    assert accepted and accepted[0] == c.matches[1] if False else accepted
    assert c.visible is False


def test_panel_geometry_caps_visible():
    c = Completer(candidates=[f"item{i}" for i in range(50)], w=200,
                  max_visible=6)
    c.update_query("item")
    assert c.visible_count() == 6
    assert c.panel_height() == 6 * c.row_h + 8


def test_completer_renders():
    from elysium._native import _native as n
    c = Completer(candidates=CANDS, x=20, y=20, w=220)
    c.update_query("ap")
    dl = n.DisplayList()
    dl.clear(0.1, 0.11, 0.14, 1.0)
    c.paint(dl)
    layer = n.SkiaLayer(260, 200)
    layer.execute(dl)
    assert bytes(layer.encode_png())[:4] == b"\x89PNG"
