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
                "neutral. Use to revert before restarting a texturing "
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
