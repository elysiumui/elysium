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
    index = next(i for i, candidate in enumerate(session.designer.placements) if candidate is p)
    return {
        "placement_id": session.id_for(p),
        "transform": scene.transform(p),
        "matrix": scene.matrix(p).tolist(),
        "world_matrix": scene.world_matrices(session.designer.placements)[index].tolist(),
        "parent_id": scene.parent_data(p)[0],
    }


@register_tool(
    name="scene.parent_set",
    description="Parent a mesh/group to a stable scene entity, or detach it. Keep-world preserves visible geometry including shear. Cycles are rejected.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "parent_id": {"type": ["string", "null"]},
            "keep_world": {"type": "boolean"},
        },
        "required": ["id", "parent_id"],
    },
)
def parent_set(session, id, parent_id, keep_world=True):
    child = session.lookup(id)
    parent = None if parent_id is None else session.lookup(parent_id)
    return {
        "placement_id": session.id_for(child),
        "parent": scene.set_parent(
            session.designer.placements, child, parent, keep_world=keep_world
        ),
    }


@register_tool(
    name="scene.transform_apply",
    description="Apply local mesh transforms to editable geometry while preserving UVs, normals, pivots and child world positions.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
)
def transform_apply(session, id):
    p = session.lookup(id)
    scene.apply_transform(session.designer.placements, p)
    return {
        "placement_id": session.id_for(p),
        "mesh_key": p.mesh_kind,
        "transform": scene.transform(p),
    }


@register_tool(
    name="scene.group_create",
    description="Create an empty transform group. Children are attached with scene.parent_set.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def group_create(session, name):
    d = session.designer
    p = session.designer_models.Placement(
        kind="SceneGroup", name=name, x=0, y=0, w=0, h=0, props={}
    )
    d.placements.append(p)
    d._select_placement(len(d.placements) - 1)
    return {"placement_id": session.id_for(p), "name": p.name}


@register_tool(
    name="scene.camera_set",
    description="Set the persistent shared scene camera. Angles are radians; orthographic scale is vertical meters. Enables 3D Scene view.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "camera": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": _VECTOR,
                    "projection": {"enum": ["perspective", "orthographic"]},
                    **{k: {"type": "number"} for k in ("yaw", "pitch", "distance", "ortho_scale")},
                },
            }
        },
        "required": ["camera"],
    },
)
def camera_set(session, camera):
    w = session.designer.window_doc
    w.scene_camera = scene.camera({**w.scene_camera, **camera})
    w.scene_view = True
    return {"camera": w.scene_camera}


@register_tool(
    name="mesh.taper_set",
    description="Set a retained native taper. Start/end XYZ factors apply at minimum/maximum local axis; the axis coordinate is unchanged. Source geometry stays editable.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "taper": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"axis": {"enum": ["x", "y", "z"]}, "start": _VECTOR, "end": _VECTOR},
            },
        },
        "required": ["id", "taper"],
    },
)
def taper_set(session, id, taper):
    from ...render import mesh_edit

    p = session.lookup(id)
    return {"placement_id": session.id_for(p), "taper": mesh_edit.taper_set(p, taper)}


@register_tool(
    name="scene.key_set",
    description="Set or replace a persistent local-transform key at an integer frame (60 fps). Explicit transform values are optional; otherwise capture current pose.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "frame": {"type": "integer", "minimum": 0, "maximum": 360000},
            "transform": {
                "type": "object",
                "additionalProperties": False,
                "properties": {k: _VECTOR for k in scene.DEFAULT},
            },
        },
        "required": ["id", "frame"],
    },
)
def key_set(session, id, frame, transform=None):
    from ...render import scene_animation

    return scene_animation.set_key(session.lookup(id), frame, transform)


@register_tool(
    name="scene.frame_set",
    description="Seek the shared 3D scene to a frame at 60 fps. Evaluates keys and parented objects.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"frame": {"type": "integer", "minimum": 0, "maximum": 360000}},
        "required": ["frame"],
    },
)
def frame_set(session, frame):
    from ...render import scene_animation

    return {"frame": scene_animation.seek(session.designer, frame)}


@register_tool(
    name="mesh.topology_get",
    description="Read durable vertex, edge, polygon and corner identities, UVs and material slots. Legacy triangles are described without mutating the source.",
    input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"}},"required":["id"]},
    side_effect=SideEffect.READ,
)
def topology_get(session,id):
    from ...render import mesh_document, topology
    p=session.lookup(id)
    if p.kind!='Mesh3D': raise ValueError('Topology requires a mesh')
    return {'placement_id':id,'topology':topology.document(mesh_document.resolve(p.mesh_kind)),
            'selection':p.props.get('components3d',{})}


@register_tool(
    name="mesh.components_select",
    description="Select persistent vertex, edge or polygon IDs; additive selection toggles the specified IDs.",
    input_schema={"type":"object","additionalProperties":False,"properties":{
        "id":{"type":"string"},"mode":{"enum":["vertices","edges","faces"]},
        "ids":{"type":"array","items":{"type":"string"}},"additive":{"type":"boolean"}},
        "required":["id","mode","ids"]},
)
def components_select(session,id,mode,ids,additive=False):
    from ...render import topology
    return topology.select(session.lookup(id),mode,ids,additive=additive)


@register_tool(
    name="mesh.components_edit",
    description="Extrude a face region along its averaged normal or extrude_individual faces along their own normals, inset individual planar convex faces by positive distance, or move components in local meters. Inset rejects collapsed offsets. One atomic mesh revision with stable IDs and corner attributes.",
    input_schema={"type":"object","additionalProperties":False,"properties":{
        "id":{"type":"string"},"operation":{"enum":["extrude","extrude_individual","inset","move"]},
        "distance":{"type":"number"},"offset":_VECTOR},"required":["id","operation"]},
)
def components_edit(session,id,operation,distance=1.0,offset=(0.,0.,0.)):
    from ...render import topology
    return topology.edit_selected(session.lookup(id),operation,distance=distance,offset=offset)
