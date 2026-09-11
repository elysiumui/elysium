"""material.*: PBR material setup on Mesh3D / PBRSphere placements."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="material.set",
    description="Apply a material to a Mesh3D / PBRSphere placement. "
                "Either pick a `preset` from the material library or "
                "pass individual params.",
    input_schema={
        "type": "object",
        "properties": {
            "id":              {"type": "string"},
            "preset":          {"type": "string"},
            "metallic":        {"type": "number"},
            "roughness":       {"type": "number"},
            "specular":        {"type": "number"},
            "clear_coat":      {"type": "number"},
            "clear_coat_roughness": {"type": "number"},
            "anisotropy":      {"type": "number"},
        },
        "required": ["id"],
    },
)
def material_set(session, id: str, preset: str | None = None,
                  metallic: float | None = None,
                  roughness: float | None = None,
                  specular: float | None = None,
                  clear_coat: float | None = None,
                  clear_coat_roughness: float | None = None,
                  anisotropy: float | None = None) -> dict:
    p = session.lookup(id)
    if preset is not None: p.pbr_preset = preset
    if metallic is not None: p.pbr_metallic = float(metallic)
    if roughness is not None: p.pbr_roughness = float(roughness)
    if specular is not None: p.pbr_specular = float(specular)
    if clear_coat is not None: p.pbr_clearcoat = float(clear_coat)
    if clear_coat_roughness is not None: p.pbr_clearcoat_roughness = float(clear_coat_roughness)
    if anisotropy is not None: p.pbr_anisotropy = float(anisotropy)
    cache = getattr(session.designer, "_mesh_cache", None)
    if cache: cache.clear()
    return {"applied": True}


@register_tool(
    name="material.set_texture",
    description="Bind an image as a material texture map. `slot` is "
                "albedo / metallic_rough / normal / ao / emissive.",
    input_schema={
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "slot": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["id", "slot", "path"],
    },
)
def material_set_texture(session, id: str, slot: str, path: str) -> dict:
    p = session.lookup(id)
    field_map = {
        "albedo":         "pbr_albedo_map",
        "metallic_rough": "pbr_metallic_rough_map",
        "normal":         "pbr_normal_map",
        "ao":             "pbr_ao_map",
        "emissive":       "pbr_emissive_map",
    }
    field = field_map.get(slot)
    if field is None:
        raise ValueError(f"unknown slot {slot}; one of {list(field_map)}")
    setattr(p, field, path)
    # Flush every render-cache the Designer might be using so the
    # texture change shows on the next paint.
    for cache_attr in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache"):
        cache = getattr(session.designer, cache_attr, None)
        if cache: cache.clear()
    return {"slot": slot, "path": path}


@register_tool(
    name="material.set_part_texture",
    description="Bind an albedo texture to ONE named sub-mesh of a Mesh3D "
                "placement (use mesh.read_parts to discover names). Lets a "
                "user re-skin the wings and the body of an imported model "
                "with different tiles. Pass an empty path to clear the "
                "binding for that part.",
    input_schema={
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "part": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["id", "part", "path"],
    },
)
def material_set_part_texture(session, id: str, part: str, path: str) -> dict:
    p = session.lookup(id)
    parts = dict(getattr(p, "mesh_part_textures", None) or {})
    if path:
        parts[part] = path
    else:
        parts.pop(part, None)
    p.mesh_part_textures = parts
    for cache_attr in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache"):
        cache = getattr(session.designer, cache_attr, None)
        if cache: cache.clear()
    return {"part": part, "path": path, "all_parts": parts}


@register_tool(
    name="material.clear",
    description="Wipe every material customization on a placement so it "
                "renders as the bare imported model. Clears: all PBR "
                "texture slots (albedo / metallic_rough / normal / ao / "
                "emissive), all per-part textures, the texture-layer "
                "stack, the painted PaintMask, and resets PBR knobs to "
                "neutral. Removes authored material slots and their owned images. Use to revert before restarting a texturing "
                "workflow from scratch.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.DESTRUCTIVE,
)
def material_clear(session, id: str) -> dict:
    p = session.lookup(id)
    designer = session.designer
    cleared: list = []
    if "materials3d" in getattr(p, "props", {}):
        p.props.pop("materials3d")
        cleared.append("materials3d")
    # PBR texture slots: empty path = no binding.
    for slot in ("albedo", "metallic_rough", "normal", "ao", "emissive"):
        field = "pbr_" + slot + "_map"
        if getattr(p, field, ""):
            setattr(p, field, "")
            cleared.append(slot)
    # Per-part textures.
    if getattr(p, "mesh_part_textures", None):
        p.mesh_part_textures = {}
        cleared.append("mesh_part_textures")
    # Layer stack.
    if getattr(p, "texture_layers", None):
        p.texture_layers = []
        cleared.append("texture_layers")
    if getattr(p, "texture_path", ""):
        p.texture_path = ""
        cleared.append("texture_path")
    # PaintMask overlay.
    masks = getattr(designer, "paint_masks", {}) or {}
    builtin_id = __import__("builtins").id
    m = masks.get(builtin_id(p))
    if m is not None:
        if hasattr(m, "clear"): m.clear()
        else:
            import numpy as _np
            m.buf = _np.zeros_like(m.buf)
        cleared.append("paint_mask")
    # Reset PBR knobs to neutral defaults.
    p.pbr_metallic = 0.0
    p.pbr_roughness = 0.6
    p.pbr_specular = 0.3
    p.pbr_clearcoat = 0.0
    p.pbr_clearcoat_roughness = 0.05
    p.pbr_use_color_fill = True
    # Flush every cache so the next frame starts from disk again.
    try:
        from elysium.render import pbr as _pbr
        if hasattr(_pbr, "_TEX_CACHE"):
            _pbr._TEX_CACHE.clear()
    except Exception: pass
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache",
                "_texture_cache", "_paint_mask_files",
                "_paint_mask_png_cache", "_brush_dirty"):
        c = getattr(designer, ca, None)
        if c:
            try: c.clear()
            except Exception: pass
    return {"cleared": cleared, "placement": id}


@register_tool(
    name="material.read",
    description="Read a placement's material parameters.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def material_read(session, id: str) -> dict:
    p = session.lookup(id)
    return {
        "preset":      getattr(p, "pbr_preset", ""),
        "metallic":    getattr(p, "pbr_metallic", 0.0),
        "roughness":   getattr(p, "pbr_roughness", 0.5),
        "specular":    getattr(p, "pbr_specular", 0.5),
        "clear_coat":  getattr(p, "pbr_clearcoat", 0.0),
        "clear_coat_roughness": getattr(p, "pbr_clearcoat_roughness", 0.0),
    }


_SLOT_VALUES = {"type":"object", "additionalProperties":False, "properties":{
    **{key:{"type":"number", "minimum":0, "maximum":1} for key in ('metallic','roughness','specular','clear_coat','clear_coat_roughness')},
    **{key:{"type":"array","items":{"type":"number","minimum":0,"maximum":maximum},"minItems":3,"maxItems":3} for key,maximum in [('base_color',1),('emissive',64)]},
}}


@register_tool(name="material.slots_get", description="Read stable object-local material slots and source face-to-slot assignments. Null parameters inherit the existing object material.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"}},"required":["id"]}, side_effect=SideEffect.READ, undoable=False)
def slots_get(session, id):
    from ...render import mesh_materials
    return mesh_materials.read(session.lookup(id))


@register_tool(name="material.slot_add", description="Add a named material slot with linear RGB surface parameters. Existing face assignments and object material are preserved. At most 64 slots per object.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"},"name":{"type":"string"},"values":_SLOT_VALUES},"required":["id"]})
def slot_add(session, id, name="Material", values=None):
    from ...render import mesh_materials
    return mesh_materials.add(session.lookup(id), name, values)


@register_tool(name="material.slot_update", description="Rename a stable material slot or update linear RGB surface parameters. Explicit parameters replace inherited object binding for this slot; other slots and assignments stay unchanged.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"},"slot_id":{"type":"string"},"name":{"type":"string"},"values":_SLOT_VALUES},"required":["id","slot_id"]})
def slot_update(session, id, slot_id, name=None, values=None):
    from ...render import mesh_materials
    return mesh_materials.update(session.lookup(id), slot_id, name=name, values=values)


@register_tool(name="material.faces_assign", description="Assign the selected stable source face identities to an existing material slot. Geometry, UVs, normals and other face assignments are preserved; validates the retained modifier stack before publication.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"},"slot_id":{"type":"string"},"face_ids":{"type":"array","items":{"type":"string"},"minItems":1,"uniqueItems":True}},"required":["id","slot_id","face_ids"]})
def faces_assign(session, id, slot_id, face_ids):
    from ...render import mesh_materials
    return mesh_materials.assign(session.lookup(id), face_ids, slot_id)


@register_tool(name="material.slot_remove", description="Remove an unused material slot; used slots and the last slot reject. Reindexes later face indices while preserving their stable slot identities and appearance.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"},"slot_id":{"type":"string"}},"required":["id","slot_id"]})
def slot_remove(session, id, slot_id):
    from ...render import mesh_materials
    return mesh_materials.remove(session.lookup(id), slot_id)


@register_tool(name="material.slot_image_set", description="Import a single PNG/JPEG (at most 2048x2048, 16 MiB) as this material slot's owned image for base_color (default), roughness, metallic, normal or metallic_roughness. Stored in the editable project and native export; Base color uses sRGB RGB; roughness/metallic use linear red-channel data; normal uses linear RGB tangent-space directions at strength 1; metallic_roughness uses linear G=roughness and B=metallic. Individual scalar maps override their packed channel. Closest sampling, repeat UVs, opaque surface; color/scalar images multiply their matching surface values; normal images alter shading without editing geometry. Empty path clears the image override. Other surfaces and source attributes remain unchanged.", input_schema={"type":"object","additionalProperties":False,"properties":{"id":{"type":"string"},"slot_id":{"type":"string"},"path":{"type":"string"},"channel":{"enum":["base_color","roughness","metallic","normal","metallic_roughness"]}},"required":["id","slot_id","path"]})
def slot_image_set(session, id, slot_id, path, channel="base_color"):
    from ...render import mesh_materials
    return mesh_materials.set_image(session.lookup(id), slot_id, path, channel)


_GRAPH_TARGET = {"id":{"type":"string"},"slot_id":{"type":"string"}}
_GRAPH_NODE = {**_GRAPH_TARGET,"node_id":{"type":"string"}}

def _graph_change(session,id,slot_id,operation,*args,**kwargs):
    from ...render import material_graph,mesh_materials
    p=session.lookup(id)
    graph=mesh_materials.graph_read(p,slot_id)['graph']
    graph=getattr(material_graph,operation)(graph,*args,**kwargs)
    node_id=None
    if isinstance(graph,tuple):graph,node_id=graph
    mesh_materials.graph_set(p,slot_id,graph)
    result=mesh_materials.graph_read(p,slot_id)
    if node_id:result['node_id']=node_id
    return result


@register_tool(name="material.color_graph_get",description="Read the retained color graph and evaluated linear RGB output for a material slot. Null output keeps surface fields.",input_schema={"type":"object","additionalProperties":False,"properties":_GRAPH_TARGET,"required":["id","slot_id"]},side_effect=SideEffect.READ,undoable=False)
def color_graph_get(session,id,slot_id):
    from ...render import mesh_materials
    return mesh_materials.graph_read(session.lookup(id),slot_id)


@register_tool(name="material.color_node_add",description="Add a persistent Color, Value, Add, Multiply or Mix node (maximum 64). Values must be from 0 to 1; computed results are clamped to that range. Missing A/B inputs default to zero/one. New nodes do not change the surface until an output is chosen.",input_schema={"type":"object","additionalProperties":False,"properties":{**_GRAPH_TARGET,"kind":{"enum":["Color","Value","Add","Multiply","Mix"]}},"required":["id","slot_id","kind"]})
def color_node_add(session,id,slot_id,kind):
    return _graph_change(session,id,slot_id,'add',kind)


@register_tool(name="material.color_node_update",description="Edit a color node's name/value or replace its input links. Color value is linear RGB; Value and Mix factor are scalars from 0 to 1. Inputs map a/b to current node IDs. Missing nodes, cycles, invalid kinds and values reject atomically, including disconnected nodes.",input_schema={"type":"object","additionalProperties":False,"properties":{**_GRAPH_NODE,"name":{"type":"string"},"value":{"anyOf":[{"type":"number"},{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3}]},"inputs":{"type":"object","additionalProperties":False,"properties":{"a":{"type":"string"},"b":{"type":"string"}}}},"required":["id","slot_id","node_id"]})
def color_node_update(session,id,slot_id,node_id,name=None,value=None,inputs=None):
    return _graph_change(session,id,slot_id,'update',node_id,name=name,value=value,inputs=inputs)


@register_tool(name="material.color_output_set",description="Use a node's evaluated linear RGB as this slot's base color, before its image multiplier. A Value output broadcasts to RGB. Null node_id clears the graph output and restores surface fields.",input_schema={"type":"object","additionalProperties":False,"properties":{**_GRAPH_TARGET,"node_id":{"type":["string","null"]}},"required":["id","slot_id","node_id"]})
def color_output_set(session,id,slot_id,node_id):
    return _graph_change(session,id,slot_id,'output',node_id)


@register_tool(name="material.color_node_remove",description="Remove a node and its referencing links. Missing inputs revert to zero/one; removing the output restores surface fields. Other source geometry and material data stay unchanged.",input_schema={"type":"object","additionalProperties":False,"properties":_GRAPH_NODE,"required":["id","slot_id","node_id"]})
def color_node_remove(session,id,slot_id,node_id):
    return _graph_change(session,id,slot_id,'remove',node_id)
