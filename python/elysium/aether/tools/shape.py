"""shape.* tools: draw paths and run boolean ops via the native helpers."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


def _rect_d(x, y, w, h, r=0):
    if r <= 0:
        return f"M {x} {y} L {x+w} {y} L {x+w} {y+h} L {x} {y+h} Z"
    return (f"M {x+r} {y} L {x+w-r} {y} Q {x+w} {y} {x+w} {y+r} "
            f"L {x+w} {y+h-r} Q {x+w} {y+h} {x+w-r} {y+h} "
            f"L {x+r} {y+h} Q {x} {y+h} {x} {y+h-r} "
            f"L {x} {y+r} Q {x} {y} {x+r} {y} Z")


def _ellipse_d(cx, cy, rx, ry):
    return (f"M {cx-rx} {cy} "
            f"Q {cx-rx} {cy-ry} {cx} {cy-ry} "
            f"Q {cx+rx} {cy-ry} {cx+rx} {cy} "
            f"Q {cx+rx} {cy+ry} {cx} {cy+ry} "
            f"Q {cx-rx} {cy+ry} {cx-rx} {cy} Z")


@register_tool(
    name="shape.draw_rect",
    description="Add a rectangle shape placement.",
    input_schema={"type": "object",
                   "properties": {"x": {"type":"number"}, "y": {"type":"number"},
                                   "w": {"type":"number"}, "h": {"type":"number"},
                                   "radius": {"type":"number"},
                                   "fill":   {"type":"array"},
                                   "stroke": {"type":"array"}},
                   "required": ["x","y","w","h"]},
)
def shape_draw_rect(session, x, y, w, h, radius: float = 0,
                     fill=None, stroke=None) -> dict:
    designer = session.designer
    P = session.designer_models.Placement
    p = P(kind="Shape", x=x, y=y, w=w, h=h,
          name=designer._assign_name("Shape"),
          shape="rect", path_d=_rect_d(0, 0, w, h, radius),
          fill=tuple(fill or (120, 110, 240, 255)),
          stroke=tuple(stroke or (0, 0, 0, 0)))
    designer.placements.append(p)
    return {"placement_id": session.id_for(p)}


@register_tool(
    name="shape.draw_ellipse",
    description="Add an ellipse / circle shape.",
    input_schema={"type": "object",
                   "properties": {"cx":{"type":"number"},"cy":{"type":"number"},
                                   "rx":{"type":"number"},"ry":{"type":"number"},
                                   "fill":{"type":"array"}},
                   "required": ["cx","cy","rx","ry"]},
)
def shape_draw_ellipse(session, cx, cy, rx, ry, fill=None) -> dict:
    designer = session.designer
    P = session.designer_models.Placement
    p = P(kind="Shape", x=cx-rx, y=cy-ry, w=rx*2, h=ry*2,
          name=designer._assign_name("Shape"), shape="ellipse",
          path_d=_ellipse_d(rx, ry, rx, ry),
          fill=tuple(fill or (120, 110, 240, 255)))
    designer.placements.append(p)
    return {"placement_id": session.id_for(p)}


@register_tool(
    name="shape.draw_path",
    description="Add a custom SVG-path shape. `d` uses the path mini-"
                "language (M / L / Q / C / Z; no A).",
    input_schema={"type": "object",
                   "properties": {"d":{"type":"string"},
                                   "x":{"type":"number"},"y":{"type":"number"},
                                   "w":{"type":"number"},"h":{"type":"number"},
                                   "fill":{"type":"array"}},
                   "required": ["d","x","y","w","h"]},
)
def shape_draw_path(session, d, x, y, w, h, fill=None) -> dict:
    designer = session.designer
    P = session.designer_models.Placement
    p = P(kind="Shape", x=x, y=y, w=w, h=h,
          name=designer._assign_name("Shape"), shape="path",
          path_d=d, fill=tuple(fill or (120, 110, 240, 255)))
    designer.placements.append(p)
    return {"placement_id": session.id_for(p)}


@register_tool(
    name="shape.boolean_op",
    description="Run a boolean path op on two or more selected shapes. "
                "`op` is union / intersect / subtract / exclude.",
    input_schema={"type": "object",
                   "properties": {"ids":{"type":"array","items":{"type":"string"}},
                                   "op":{"type":"string"}},
                   "required": ["ids","op"]},
)
def shape_boolean_op(session, ids: list[str], op: str) -> dict:
    from elysium._native import _native as _n
    designer = session.designer
    if len(ids) < 2:
        raise ValueError("boolean_op needs >= 2 shapes")
    placements = [session.lookup(i) for i in ids]
    result_d = placements[0].path_d
    for p in placements[1:]:
        result_d = _n.path_op(result_d, p.path_d, op)
    bbox = _n.path_bounds(result_d)
    base = placements[0]
    base.path_d = result_d
    base.x, base.y, base.w, base.h = bbox
    for p in placements[1:]:
        designer.placements.remove(p)
    return {"placement_id": session.id_for(base), "bbox": list(bbox)}
