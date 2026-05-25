"""Generate `examples/pomodoro/stem.esk/document.json`.

The Pomodoro app used to paint its leaf-cluster stem button entirely in
Python (`_paint_stem` in main.py). Moving the artwork into a tiny `.esk`
makes the cluster editable in the Designer — open `stem.esk` and the
five leaves + centre knob show up as named path nodes you can recolour
or reshape with the standard vector tools.

The cluster is authored at a CANONICAL centre of (100, 100) within a
200×200 canvas, sized to radius=32. Per frame the Pomodoro pushes a
translate + scale onto its DisplayList, extends with this skin's
compiled commands, then pops — so position (which animates as the
clam opens) stays in Python while colours / leaf shape live in the
.esk.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path("/Users/KenleyJacquesLamaute/ElysiumUI/examples/pomodoro/stem.esk/document.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

CX, CY = 100.0, 100.0
R = 32.0          # canonical radius (matches BTN_R in main.py at 1:1 scale)
N_LEAVES = 5


def hex_rgba(rgba: tuple[int, int, int, int]) -> str:
    r, g, b, a = rgba
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def leaf_d(cx: float, cy: float, angle_deg: float,
              length: float, width: float) -> str:
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    px, py = -sa, ca
    tip_x, tip_y = cx + length * ca, cy + length * sa
    half = length * 0.45
    sa_x = cx + half * ca + width * px
    sa_y = cy + half * sa + width * py
    sb_x = cx + half * ca - width * px
    sb_y = cy + half * sa - width * py
    return (f"M {cx} {cy} "
              f"Q {sa_x} {sa_y} {tip_x} {tip_y} "
              f"Q {sb_x} {sb_y} {cx} {cy} Z")


def ellipse_d(cx: float, cy: float, rx: float, ry: float) -> str:
    return (f"M {cx} {cy - ry} "
              f"Q {cx + rx} {cy - ry} {cx + rx} {cy} "
              f"Q {cx + rx} {cy + ry} {cx} {cy + ry} "
              f"Q {cx - rx} {cy + ry} {cx - rx} {cy} "
              f"Q {cx - rx} {cy - ry} {cx} {cy - ry} Z")


def circle_d(cx: float, cy: float, r: float) -> str:
    # Approximate a circle with 4 quadratic bezier segments — same shape
    # `filled_circle` would produce but expressed as an SVG path so it
    # lives in the document tree as an editable node.
    return ellipse_d(cx, cy, r, r)


def path_node(node_id: str, d: str, fill_rgba: tuple[int, int, int, int]) -> dict:
    return {
        "type": "path",
        "id": node_id,
        "d": d,
        "fill": {"type": "color", "value": hex_rgba(fill_rgba)},
    }


def main() -> None:
    children: list[dict] = []

    # 1. Ambient-occlusion shadow under the cluster.
    children.append(path_node(
        "stem-shadow-outer",
        ellipse_d(CX, CY + 5, R * 1.35, R * 0.55),
        (0, 0, 0, 80)))
    children.append(path_node(
        "stem-shadow-inner",
        ellipse_d(CX, CY + 4, R * 1.10, R * 0.42),
        (0, 0, 0, 100)))

    # 2. Five lance-shaped leaves, 4 stacked layers each.
    leaf_len = R * 1.05
    for i in range(N_LEAVES):
        angle = -90.0 + i * (360.0 / N_LEAVES)
        # Back-shadow: shape offset down by 1.2 to ring the leaf in dark.
        children.append(path_node(
            f"leaf-{i}-back",
            leaf_d(CX, CY + 1.2, angle, leaf_len, R * 0.40),
            (20, 44, 12, 230)))
        # Dark olive base — the leaf's underside.
        children.append(path_node(
            f"leaf-{i}-base",
            leaf_d(CX, CY, angle, leaf_len, R * 0.38),
            (44, 92, 26, 255)))
        # Mid-green body.
        children.append(path_node(
            f"leaf-{i}-body",
            leaf_d(CX, CY, angle, leaf_len * 0.92, R * 0.32),
            (84, 154, 48, 255)))
        # Bright crown — narrow specular ridge.
        children.append(path_node(
            f"leaf-{i}-crown",
            leaf_d(CX, CY, angle, leaf_len * 0.82, R * 0.18),
            (152, 212, 80, 250)))
        # Tip highlight.
        a = math.radians(angle)
        tip_x = CX + leaf_len * 0.78 * math.cos(a)
        tip_y = CY + leaf_len * 0.78 * math.sin(a)
        children.append(path_node(
            f"leaf-{i}-tip",
            circle_d(tip_x, tip_y, R * 0.06),
            (210, 240, 150, 220)))

    # 3. Centre stem-root knob — three nested circles + highlight pip.
    children.append(path_node(
        "knob-shadow",
        circle_d(CX, CY + 1, R * 0.30),
        (24, 50, 14, 255)))
    children.append(path_node(
        "knob-body",
        circle_d(CX, CY, R * 0.26),
        (60, 108, 32, 255)))
    children.append(path_node(
        "knob-highlight",
        circle_d(CX - 1.2, CY - 1.6, R * 0.18),
        (120, 178, 60, 240)))
    children.append(path_node(
        "knob-pip",
        circle_d(CX - 2.0, CY - 2.4, R * 0.08),
        (210, 240, 150, 240)))

    doc = {
        "root": {
            "type": "scene",
            "id": "stem-root",
            "size": {"w": 200.0, "h": 200.0},
            "background": {"type": "color", "value": "#00000000"},
            "children": children,
        }
    }

    OUT.write_text(json.dumps(doc, indent=2))
    print(f"wrote {OUT}  ({len(children)} path nodes)")


if __name__ == "__main__":
    main()
