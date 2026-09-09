"""Native primitive creation and parameter editing through the public API."""

from __future__ import annotations

from copy import deepcopy

from ...render import mesh_document
from ...render import primitives as geometry
from ..types import SideEffect
from . import register_tool


def _parameter_schema(kind):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            key: {"type": "integer" if integer else "number", "minimum": lower, "maximum": upper}
            for key, (_, lower, upper, integer, _) in geometry.PARAMETERS[kind].items()
        },
    }


@register_tool(
    name="mesh.primitive_create",
    description="Create an independent native Cube, Sphere, Cylinder, Cone, Plane or Torus. "
    "Parameters describe model-space geometry; optional x/y place its canvas view.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"enum": list(geometry.PARAMETERS)},
            "parameters": {"type": "object"},
            "name": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
        },
        "required": ["kind"],
        "allOf": [
            {
                "if": {"properties": {"kind": {"const": kind}}},
                "then": {"properties": {"parameters": _parameter_schema(kind)}},
            }
            for kind in geometry.PARAMETERS
        ],
    },
)
def primitive_create(
    session,
    kind: str,
    parameters: dict | None = None,
    name: str = "",
    x: float | None = None,
    y: float | None = None,
) -> dict:
    # Validate before publishing any placement or consuming a display name.
    mesh, values = geometry.build(kind, parameters)
    d = session.designer
    wx, wy, ww, wh = d._window_rect()
    p = session.designer_models.Placement(
        kind="Mesh3D",
        name=name or d._assign_name(kind),
        x=wx + (ww - 260) / 2 if x is None else x,
        y=wy + (wh - 260) / 2 if y is None else y,
        w=260.0,
        h=260.0,
        props={},
    )
    key = mesh_document.bind(p, mesh, label=kind)
    p.props["primitive"] = {"kind": kind, "parameters": values, "mesh_key": key}
    d.placements.append(p)
    d._select_placement(len(d.placements) - 1)
    return {
        "placement_id": session.id_for(p),
        "name": p.name,
        "parameters": values,
        "vertices": len(mesh.verts),
        "triangles": len(mesh.faces),
    }


@register_tool(
    name="mesh.primitive_update",
    description="Change native primitive dimensions or segments. Regeneration is available "
    "until geometry is edited; it never silently discards later modeling edits.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "parameters": {"type": "object"}},
        "required": ["id", "parameters"],
    },
)
def primitive_update(session, id: str, parameters: dict) -> dict:
    p = session.lookup(id)
    geometry.update(p, parameters)
    for name in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache"):
        cache = getattr(session.designer, name, None)
        if cache is not None:
            cache.clear()
    return {"placement_id": id, **deepcopy(geometry.settings(p))}


@register_tool(
    name="mesh.primitive_parameters",
    description="Read a primitive's editable dimensions and segment counts, or null after conversion.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    side_effect=SideEffect.READ,
)
def primitive_parameters(session, id: str) -> dict:
    return {"placement_id": id, "primitive": deepcopy(geometry.settings(session.lookup(id)))}
