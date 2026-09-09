"""Public model-space transforms; independent from canvas coordinates."""

from ...render import scene
from ..types import SideEffect
from . import register_tool

_VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


@register_tool(
    name="scene.transform_set",
    description="Set mesh location in meters, XYZ Euler rotation in degrees, scale or local pivot in Y-up model space.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "transform": {
                "type": "object",
                "additionalProperties": False,
                "properties": {k: _VECTOR for k in scene.DEFAULT},
            },
        },
        "required": ["id", "transform"],
    },
)
def transform_set(session, id, transform):
    return {"placement_id": id, "transform": scene.update(session.lookup(id), transform)}


@register_tool(
    name="scene.transform_get",
    description="Read authored model-space mesh transform and matrix.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    side_effect=SideEffect.READ,
)
def transform_get(session, id):
    p = session.lookup(id)
    return {"placement_id": id, "transform": scene.transform(p), "matrix": scene.matrix(p).tolist()}
