"""brush.*: paintbrush palette & texture-stamp ("texture slurp") tools.

Lets the agent (and, by extension, anything driving the Designer's
bridge) pick a small *tileable* RGBA tile and paint with it using the
existing Brush tool: same workflow as: slurp a swatch from a photo,
stash it in the palette, then drag the brush across the canvas to lay
that tile down with a soft-edged circular stamp.
"""
from __future__ import annotations

from pathlib import Path

from . import register_tool
from ..types import SideEffect


def _load_rgba(path: str):
    from PIL import Image as _PILImage
    import numpy as _np
    im = _PILImage.open(path).convert("RGBA")
    return _np.array(im, dtype=_np.uint8)


def _set_active(designer, tile, name: str, scale: float,
                  auto_radius: bool = True) -> None:
    """Make `tile` the brush's active stamp. When auto_radius=True (the
    default) also size the brush footprint to match the tile so a
    slurped Npx swatch paints an N-px brush: preserving the user's
    intent that pattern size on the model = pattern size on the source."""
    import numpy as _np
    # Force opaque alpha on the active tile so paint is additive only.
    if tile is not None and tile.shape[-1] == 4:
        # Don't mutate the palette entry; copy if any alpha < 255.
        if (tile[..., 3] != 255).any():
            tile = tile.copy()
            tile[..., 3] = 255
    designer.brush_texture = tile
    designer.brush_texture_name = name
    designer.brush_texture_scale = float(scale)
    if tile is not None:
        if auto_radius:
            h, w = tile.shape[:2]
            designer.brush_radius = float(max(1, max(w, h) // 2))
        designer.menu_status = (f"Brush texture set · {name} · "
                                  f"{tile.shape[1]}×{tile.shape[0]}px · "
                                  f"radius={designer.brush_radius:g}")
    else:
        designer.menu_status = "Brush texture cleared (solid color)"


@register_tool(
    name="brush.set_texture",
    description="Activate a tileable RGBA tile as the current Brush stamp. "
                "Either pass `name` (a tile already in the designer's brush "
                "palette / texture library at ~/.elysium/textures/) or `path` "
                "(absolute file path). Once set, the Brush tool paints with "
                "that texture instead of `brush_color`; switch back to solid "
                "color with brush.clear_texture. `scale` (default 1.0) "
                "stretches the tile in placement-pixel units: 0.5 = pattern "
                "twice as dense, 2.0 = pattern twice as large.",
    input_schema={"type": "object",
                   "properties": {"name":  {"type": "string"},
                                   "path":  {"type": "string"},
                                   "scale": {"type": "number"}}},
)
def brush_set_texture(session, name: str = "", path: str = "",
                       scale: float = 1.0) -> dict:
    designer = session.designer
    tile = None
    src_name = name or Path(path).stem if path else name
    if name and name in getattr(designer, "brush_palette", {}):
        tile = designer.brush_palette[name]
    elif path:
        tile = _load_rgba(path)
    elif name:
        # Try the library on disk.
        from elysium.render import texture as tex
        for fp in tex.list_library():
            if fp.stem == name:
                tile = _load_rgba(str(fp))
                break
    if tile is None:
        raise FileNotFoundError(
            f"brush.set_texture: no tile found for name={name!r} path={path!r}")
    _set_active(designer, tile, src_name, scale)
    return {"name": src_name,
            "w": int(tile.shape[1]), "h": int(tile.shape[0]),
            "scale": float(scale)}


@register_tool(
    name="brush.clear_texture",
    description="Return the Brush tool to solid-color mode (paints with "
                "`brush_color` again).",
    input_schema={"type": "object", "properties": {}},
)
def brush_clear_texture(session) -> dict:
    _set_active(session.designer, None, "", 1.0)
    return {"cleared": True}


@register_tool(
    name="brush.slurp",
    description="Eyedropper a tileable swatch out of a source image and stash "
                "it in the brush palette under `name`. `crop` is "
                "[x, y, w, h] in source-image pixel coords; omit to use the "
                "whole image. If `seamless` is true (default) the tile is "
                "feathered/wrapped so it tiles without seams. The new tile "
                "is also set as the active brush stamp so the very next "
                "brush stroke uses it.",
    input_schema={"type": "object",
                   "properties": {"src":      {"type": "string"},
                                   "name":     {"type": "string"},
                                   "crop":     {"type": "array",
                                                 "items": {"type": "number"},
                                                 "minItems": 4, "maxItems": 4},
                                   "seamless": {"type": "boolean"},
                                   "scale":    {"type": "number"},
                                   "save":     {"type": "boolean"}},
                   "required": ["src", "name"]},
)
def brush_slurp(session, src: str, name: str,
                 crop: list | None = None,
                 seamless: bool = True,
                 scale: float = 1.0,
                 save: bool = True) -> dict:
    """Cut a region out of `src` (in pixel coords) and register it as a
    named brush stamp.

    Critical invariants for the "paint colors and patterns onto the
    model without changing its shape" workflow:

    1. The slurped tile is forced FULLY OPAQUE: alpha set to 255
       across the whole crop. The brush must never paint with the
       source's alpha (which would let transparent-source pixels
       erase the underlying model).
    2. The brush's stamp radius is auto-set to half the tile's
       largest side, so a 3×3-px slurp paints a ~3-px brush footprint
       and a 50×50-px slurp paints a ~50-px footprint. The user can
       still adjust afterwards via brush.set_params.
    3. brush_texture_scale is reset to 1.0 so the tile is sampled at
       its native pixel size (no implicit upscale)."""
    import numpy as _np
    from elysium.render import texture as tex
    designer = session.designer
    crop_rect = tuple(int(v) for v in crop) if crop and len(crop) == 4 else None
    out_path, _ = tex.extract_from_file(
        src, name=name, crop_rect=crop_rect, tile=bool(seamless),
        saturation=0.0, contrast=0.0)
    tile = _load_rgba(str(out_path))
    # Force the slurped tile fully opaque: the brush paints additively,
    # never punches holes. If the source had alpha-keyed background,
    # those pixels still carry useful RGB; promote them to alpha=255.
    if tile.shape[-1] == 4:
        tile = tile.copy()
        tile[..., 3] = 255
    pal = getattr(designer, "brush_palette", None)
    if pal is None:
        designer.brush_palette = {}
        pal = designer.brush_palette
    pal[name] = tile
    # Notify the palette panel so an Aether-driven add can land in a
    # pending texture slot. Best-effort: older Designer builds without
    # the hook just ignore the call.
    hook = getattr(designer, "_aether_append_palette_tile", None)
    if callable(hook):
        try:
            hook(name)
        except Exception:
            pass
    # Auto-size the brush footprint to match the slurped tile. Half the
    # max dimension gives a circular stamp that just covers the tile.
    h, w = tile.shape[:2]
    designer.brush_radius = float(max(1, max(w, h) // 2))
    _set_active(designer, tile, name, 1.0)        # native scale
    return {"name": name, "path": str(out_path),
            "w": int(w), "h": int(h),
            "brush_radius": designer.brush_radius,
            "saved": bool(save), "crop": list(crop_rect or [])}


@register_tool(
    name="brush.list_palette",
    description="List every brush swatch the designer has cached this "
                "session (the in-memory palette plus on-disk tiles under "
                "~/.elysium/textures/).",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ, undoable=False,
)
def brush_list_palette(session) -> dict:
    from elysium.render import texture as tex
    designer = session.designer
    pal = getattr(designer, "brush_palette", {}) or {}
    palette = []
    for name, tile in pal.items():
        h, w = tile.shape[:2]
        palette.append({"name": name, "w": int(w), "h": int(h),
                         "in_memory": True})
    library = []
    for fp in tex.list_library():
        library.append({"name": fp.stem, "path": str(fp)})
    return {"palette": palette, "library": library,
            "active": getattr(designer, "brush_texture_name", "")}


@register_tool(
    name="brush.read",
    description="Report the current brush state: tool, radius, opacity, "
                "hardness, solid color, and the active texture stamp (if "
                "any) plus its scale.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ, undoable=False,
)
def brush_read(session) -> dict:
    d = session.designer
    tex = getattr(d, "brush_texture", None)
    return {"tool":      getattr(d, "tool", ""),
            "radius":    float(getattr(d, "brush_radius", 0.0)),
            "opacity":   float(getattr(d, "brush_opacity", 1.0)),
            "hardness":  float(getattr(d, "brush_hardness", 0.5)),
            "color":     list(getattr(d, "brush_color", (0, 0, 0, 255))),
            "texture":   getattr(d, "brush_texture_name", "") or None,
            "tex_scale": float(getattr(d, "brush_texture_scale", 1.0)),
            "tex_size":  ([int(tex.shape[1]), int(tex.shape[0])]
                           if tex is not None else None)}


@register_tool(
    name="brush.stroke",
    description="Lay a brush stroke on a placement's PaintMask using the "
                "currently active brush state (texture if set, otherwise "
                "solid brush_color). Coordinates are in placement-bbox "
                "local pixels: [0,0] = top-left of the bbox. `from` and "
                "`to` define the stroke endpoints; pass equal points for a "
                "single dab. Honours brush_radius, brush_opacity, "
                "brush_hardness, brush_texture_scale. Additive only: no "
                "alpha cutout, never erases the underlying model.",
    input_schema={
        "type": "object",
        "properties": {
            "id":      {"type": "string"},
            "from":    {"type": "array", "items": {"type": "number"},
                         "minItems": 2, "maxItems": 2},
            "to":      {"type": "array", "items": {"type": "number"},
                         "minItems": 2, "maxItems": 2},
            "radius":  {"type": "number"},
            "opacity": {"type": "number"},
        },
        "required": ["id", "from", "to"],
    },
)
def brush_stroke(session, id: str,
                  **kwargs) -> dict:
    # `from` is a Python keyword; receive via kwargs.
    src_pt = kwargs.get("from")
    dst_pt = kwargs.get("to")
    radius = kwargs.get("radius")
    opacity = kwargs.get("opacity")
    if src_pt is None or dst_pt is None:
        raise ValueError("brush.stroke requires `from` and `to`")
    designer = session.designer
    p = session.lookup(id)
    # Lazily build the mask the same way the live Brush tool does.
    mask = designer._get_paint_mask(p)
    x0, y0 = float(src_pt[0]), float(src_pt[1])
    x1, y1 = float(dst_pt[0]), float(dst_pt[1])
    r = float(radius) if radius is not None else float(designer.brush_radius)
    op = float(opacity) if opacity is not None else float(designer.brush_opacity)
    hardness = float(designer.brush_hardness)
    tex = getattr(designer, "brush_texture", None)
    if tex is not None and hasattr(mask, "stroke_texture"):
        scale = float(getattr(designer, "brush_texture_scale", 1.0))
        if x0 == x1 and y0 == y1:
            mask.stamp_texture(x0, y0, r, tex,
                                opacity=op, hardness=hardness, scale=scale)
        else:
            mask.stroke_texture(x0, y0, x1, y1, r, tex,
                                 opacity=op, hardness=hardness, scale=scale)
        mode = f"texture[{getattr(designer, 'brush_texture_name', '')}]"
    else:
        col = tuple(int(c) for c in designer.brush_color)
        if x0 == x1 and y0 == y1:
            mask.stamp(x0, y0, r, col,
                        opacity=op, hardness=hardness, erase=False)
        else:
            mask.stroke(x0, y0, x1, y1, r, col,
                         opacity=op, hardness=hardness, erase=False)
        mode = f"color rgb{col[:3]}"
    # Invalidate caches so the painted mask renders on next frame.
    designer._brush_dirty.add(__import__("builtins").id(p))
    cache = getattr(designer, "_paint_mask_files", None)
    if cache: cache.pop(__import__("builtins").id(p), None)
    cache = getattr(designer, "_paint_mask_png_cache", None)
    if cache: cache.pop(__import__("builtins").id(p), None)
    cache = getattr(designer, "_texture_cache", None)
    if cache:
        for k in list(cache.keys()):
            if k[0] == __import__("builtins").id(p):
                cache.pop(k, None)
    designer.menu_status = (f"Brush stroke · {p.name} · {mode} · "
                              f"r={r:g} · ({x0:.0f},{y0:.0f})→({x1:.0f},{y1:.0f})")
    return {"placement": id, "mode": mode,
            "from": [x0, y0], "to": [x1, y1],
            "radius": r, "opacity": op}


@register_tool(
    name="brush.set_params",
    description="Adjust brush size / opacity / hardness / color without "
                "switching tools. Any omitted field is left alone. `color` "
                "is [r, g, b] or [r, g, b, a] in 0-255.",
    input_schema={"type": "object",
                   "properties": {"radius":   {"type": "number"},
                                   "opacity":  {"type": "number"},
                                   "hardness": {"type": "number"},
                                   "color":    {"type": "array",
                                                 "items": {"type": "number"}},
                                   "scale":    {"type": "number"}}},
)
def brush_set_params(session, radius: float | None = None,
                      opacity: float | None = None,
                      hardness: float | None = None,
                      color: list | None = None,
                      scale: float | None = None) -> dict:
    d = session.designer
    if radius   is not None: d.brush_radius   = float(radius)
    if opacity  is not None: d.brush_opacity  = float(opacity)
    if hardness is not None: d.brush_hardness = float(hardness)
    if scale    is not None: d.brush_texture_scale = float(scale)
    if color and len(color) >= 3:
        c = [int(v) for v in color]
        if len(c) == 3: c.append(255)
        d.brush_color = tuple(c[:4])
    return {"radius": d.brush_radius, "opacity": d.brush_opacity,
            "hardness": d.brush_hardness,
            "color": list(d.brush_color),
            "tex_scale": d.brush_texture_scale}
