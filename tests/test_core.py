"""elysium.core — the shared NaN-safe clamp.

Regression cover for the QA priority report's cross-cutting finding: the
`min(max(v, lo), hi)` idiom returns NaN unchanged, so a NaN silently escaped
every clamp in the codebase and surfaced a frame later somewhere unrelated.
"""
from __future__ import annotations

import math

from elysium.core import clamp

NAN = float("nan")
INF = float("inf")


def test_clamp_constrains_to_bounds():
    assert clamp(5.0, 0.0, 1.0) == 1.0
    assert clamp(-5.0, 0.0, 1.0) == 0.0
    assert clamp(0.5, 0.0, 1.0) == 0.5
    # The bounds themselves are inclusive.
    assert clamp(0.0, 0.0, 1.0) == 0.0
    assert clamp(1.0, 0.0, 1.0) == 1.0


def test_clamp_is_nan_safe():
    """The whole reason this helper exists."""
    assert math.isnan(min(max(NAN, 0.0), 1.0))   # the idiom it replaces
    assert clamp(NAN, 0.0, 1.0) == 0.0           # ...and the fix


def test_clamp_handles_infinities():
    assert clamp(INF, 0.0, 1.0) == 1.0
    assert clamp(-INF, 0.0, 1.0) == 0.0


def test_clamp_with_inverted_bounds_returns_lo():
    # Degenerate input shouldn't hand back an out-of-range `hi`.
    assert clamp(5.0, 1.0, 0.0) == 1.0
    assert clamp(-5.0, 1.0, 0.0) == 1.0
