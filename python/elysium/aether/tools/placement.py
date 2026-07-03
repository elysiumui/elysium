"""placement.* tools: add / move / resize / list / read placements."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="placement.add",
    description="Create a new placement on the canvas. `kind` is one of "
                "the catalog entries (Button, Card, Mesh3D, PBRSphere, "
                "Image, Label, Slider, Toggle, Shape, Region, ...).",
    input_schema={
        "type": "object",
        "properties": {
            "kind":  {"type": "string"},
            "x":     {"type": "number"},
            "y":     {"type": "number"},
            "w":     {"type": "number"},
            "h":     {"type": "number"},
            "name":  {"type": "string"},
            "props": {"type": "object"},
        },
        "required": ["kind", "x", "y", "w", "h"],
    },
)
def placement_add(session, kind: str, x: float, y: float,
                   w: float, h: float, name: str = "",
                   props: dict | None = None) -> dict:
    designer = session.designer
    P = session.designer_models.Placement
    name = name or designer._assign_name(kind)
    p = P(kind=kind, x=float(x), y=float(y), w=float(w), h=float(h),
          name=name, props=dict(props or {}))
    designer.placements.append(p)
    designer.sel_kind, designer.sel_idx = "placement", len(designer.placements) - 1
    return {"placement_id": session.id_for(p),
            "index": len(designer.placements) - 1,
            "name": p.name}


@register_tool(
    name="placement.remove",
    description="Delete a placement by id.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.DESTRUCTIVE,
    requires_confirmation="destructive",
)
def placement_remove(session, id: str) -> dict:
    p = session.lookup(id)
    designer = session.designer
    designer.placements.remove(p)
    return {"removed": id}


@register_tool(
    name="placement.move",
    description="Translate a placement to absolute coordinates.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"},
                                   "x":  {"type": "number"},
                                   "y":  {"type": "number"}},
                   "required": ["id", "x", "y"]},
)
def placement_move(session, id: str, x: float, y: float) -> dict:
    p = session.lookup(id)
    p.x, p.y = float(x), float(y)
    return {"x": p.x, "y": p.y}


@register_tool(
    name="placement.resize",
    description="Resize a placement to (w, h).",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"},
                                   "w":  {"type": "number"},
                                   "h":  {"type": "number"}},
                   "required": ["id", "w", "h"]},
)
def placement_resize(session, id: str, w: float, h: float) -> dict:
    p = session.lookup(id)
    p.w, p.h = float(w), float(h)
    return {"w": p.w, "h": p.h}


@register_tool(
    name="placement.rename",
    description="Rename a placement.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"},
                                   "name": {"type": "string"}},
                   "required": ["id", "name"]},
)
def placement_rename(session, id: str, name: str) -> dict:
    p = session.lookup(id)
    p.name = name
    return {"name": p.name}


@register_tool(
    name="placement.select",
    description="Select a placement by id (so subsequent keyboard nudges, "
                "Properties-panel edits, etc. target it). Pass id='' to "
                "deselect everything.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
)
def placement_select(session, id: str) -> dict:
    d = session.designer
    if not id:
        d.sel_kind, d.sel_idx, d.sel_set = "none", -1, set()
        return {"selected": None}
    p = session.lookup(id)
    idx = d.placements.index(p)
    d.sel_kind, d.sel_idx, d.sel_set = "placement", idx, {idx}
    return {"selected": {"id": session.id_for(p), "name": p.name,
                          "kind": p.kind, "idx": idx}}


@register_tool(
    name="placement.set_property",
    description="Set an arbitrary property on a placement. Use this for "
                "things like color_fill, font_size, label, image_path, "
                "or any kind-specific field.",
    input_schema={"type": "object",
                   "properties": {"id":    {"type": "string"},
                                   "key":   {"type": "string"},
                                   "value": {}},
                   "required": ["id", "key", "value"]},
)
def placement_set_property(session, id: str, key: str, value) -> dict:
    p = session.lookup(id)
    # Color / coordinate fields are declared as tuples on the Placement
    # dataclass; the bridge ships them across as JSON arrays. Convert
    # incoming lists for known tuple-typed fields so downstream code (cache
    # keys, normalisation, save round-trip) doesn't trip on `unhashable
    # type: 'list'`.
    if isinstance(value, list) and any(
        key.startswith(s) for s in
        ("color_", "fill", "stroke", "gradient_", "pbr_emissive",
         "texture_tint")):
        value = tuple(value)
    if hasattr(p, key):
        setattr(p, key, value)
    else:
        p.props = dict(p.props or {})
        p.props[key] = value
    return {"set": {key: value}}


@register_tool(
    name="placement.duplicate",
    description="Clone a placement with an optional offset.",
    input_schema={"type": "object",
                   "properties": {"id":  {"type": "string"},
                                   "dx":  {"type": "number"},
                                   "dy":  {"type": "number"}},
                   "required": ["id"]},
)
def placement_duplicate(session, id: str, dx: float = 24,
                         dy: float = 24) -> dict:
    designer = session.designer
    p = session.lookup(id)
    from dataclasses import replace
    new = replace(p, x=p.x + dx, y=p.y + dy,
                  name=designer._assign_name(p.kind),
                  props=dict(p.props or {}))
    designer.placements.append(new)
    return {"placement_id": session.id_for(new), "name": new.name}


@register_tool(
    name="placement.bring_forward",
    description="Move a placement up one Z order.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
)
def placement_bring_forward(session, id: str) -> dict:
    designer = session.designer
    p = session.lookup(id)
    i = designer.placements.index(p)
    if i + 1 < len(designer.placements):
        designer.placements[i], designer.placements[i + 1] = \
            designer.placements[i + 1], designer.placements[i]
    return {"index": designer.placements.index(p)}


@register_tool(
    name="placement.send_backward",
    description="Move a placement down one Z order.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
)
def placement_send_backward(session, id: str) -> dict:
    designer = session.designer
    p = session.lookup(id)
    i = designer.placements.index(p)
    if i > 0:
        designer.placements[i], designer.placements[i - 1] = \
            designer.placements[i - 1], designer.placements[i]
    return {"index": designer.placements.index(p)}


@register_tool(
    name="placement.list",
    description="List every placement on the canvas with id / kind / "
                "name / bounds. Read-only: call this after changes to "
                "verify state.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def placement_list(session) -> dict:
    out = []
    for p in session.designer.placements:
        out.append({
            "id":   session.id_for(p),
            "kind": p.kind,
            "name": p.name,
            "x": p.x, "y": p.y, "w": p.w, "h": p.h,
        })
    return {"placements": out, "count": len(out)}


@register_tool(
    name="placement.read",
    description="Get the full property dump for one placement.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def placement_read(session, id: str) -> dict:
    p = session.lookup(id)
    return p.to_json() if hasattr(p, "to_json") else dict(p.__dict__)
