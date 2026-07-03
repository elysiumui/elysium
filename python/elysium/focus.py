"""Path-aware focus navigation.

Tab order follows document order by default. Arrow keys move spatially
to the nearest neighbour in the requested direction — "nearest" is the
candidate whose centre minimises a weighted distance favouring the
axis of motion (90% perpendicular, 10% parallel).

Skins can override per-hook with::

    "accessible": {
        "directional_focus": {
            "up": "track.prev", "down": "track.next",
            "left": "album",    "right": "track.title"
        }
    }
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


Direction = Literal["up", "down", "left", "right", "next", "prev"]


@dataclass
class FocusNode:
    id: str
    bounds: tuple[float, float, float, float]   # x, y, w, h
    overrides: dict[str, str] | None = None


def next_focus(nodes: list[FocusNode], current: str | None,
                direction: Direction) -> str | None:
    """Return the node id that should receive focus, or None when no
    move applies. ``current`` may be None to seed focus on the first
    node in document order."""
    if not nodes: return None
    by_id = {n.id: n for n in nodes}
    if current is None:
        return nodes[0].id

    cur = by_id.get(current)
    if cur is None:
        return nodes[0].id

    # Per-hook override always wins.
    if cur.overrides and direction in cur.overrides:
        return cur.overrides[direction]

    if direction in ("next", "prev"):
        idx = next((i for i, n in enumerate(nodes) if n.id == current), 0)
        if direction == "next":
            return nodes[(idx + 1) % len(nodes)].id
        return nodes[(idx - 1) % len(nodes)].id

    cx, cy = _centre(cur.bounds)
    best_id: str | None = None
    best_score = float("inf")
    for n in nodes:
        if n.id == current: continue
        nx, ny = _centre(n.bounds)
        if not _in_direction(direction, cx, cy, nx, ny): continue
        score = _score(direction, cx, cy, nx, ny)
        if score < best_score:
            best_score = score
            best_id = n.id
    return best_id


def _centre(b: tuple[float, float, float, float]) -> tuple[float, float]:
    return (b[0] + b[2] * 0.5, b[1] + b[3] * 0.5)


def _in_direction(d: Direction, cx: float, cy: float,
                   nx: float, ny: float) -> bool:
    dx = nx - cx
    dy = ny - cy
    if d == "right": return dx >  abs(dy)
    if d == "left":  return dx < -abs(dy)
    if d == "down":  return dy >  abs(dx)
    if d == "up":    return dy < -abs(dx)
    return False


def _score(d: Direction, cx: float, cy: float,
            nx: float, ny: float) -> float:
    dx = nx - cx
    dy = ny - cy
    # Weighted score — perpendicular distance dominates so the nearest
    # element along the axis of motion wins, but a tied perpendicular
    # distance falls back to the closer one overall.
    if d in ("right", "left"):
        return abs(dx) + abs(dy) * 4.0
    return abs(dy) + abs(dx) * 4.0


__all__ = ["FocusNode", "Direction", "next_focus"]
