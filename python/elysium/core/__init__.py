"""elysium.core — small numeric primitives shared across the framework.

Currently just `clamp`, which exists because the obvious idiom is quietly
wrong for NaN:

    min(max(v, lo), hi)     # -> nan when v is nan

Every comparison against NaN is False, so both `min` and `max` fall through
and hand the NaN straight back. A NaN that survives a clamp goes on to poison
whatever it feeds — a zoom factor, a scroll offset, a device coordinate — and
usually only surfaces a frame later as an `OverflowError` or a blank widget,
far from the code that produced it.
"""
from __future__ import annotations

import math

__all__ = ["clamp"]


def clamp(v: float, lo: float, hi: float) -> float:
    """Constrain `v` to `[lo, hi]`, treating NaN as `lo`.

    `lo` is the "identity" end for every caller in this codebase (a zoom
    snaps to `min_zoom`, a ratio to `0.0`, a progress value to the start),
    so mapping NaN there degrades gracefully instead of propagating.

        >>> clamp(5.0, 0.0, 1.0)
        1.0
        >>> clamp(float("nan"), 0.0, 1.0)
        0.0

    If `hi < lo` the bounds are treated as inverted and `lo` wins, which
    keeps the result inside the caller's intended range rather than
    silently returning an out-of-range `hi`.
    """
    if math.isnan(v) or hi < lo:
        return lo
    # ±inf needs no special case — it clamps by ordinary comparison.
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
