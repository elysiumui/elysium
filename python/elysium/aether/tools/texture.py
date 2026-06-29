"""texture.*: extract, apply, paint."""
from __future__ import annotations

from pathlib import Path
from builtins import id as _obj_id   # module-level alias so functions whose
                                      # first arg is `id: str` (placement id)
                                      # can still call the builtin `id(obj)`.

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="texture.extract_from_image",
    description="Crop/clean an image into a seamless tile in the user's "
                "texture library at ~/.elysium/textures/. Pass `crop` as "
                "[x, y, w, h] in source-image pixel coords to extract just "
                "that region. `saturation` and `contrast` are signed deltas "
                "in [-1, 1] applied before tiling.",
    input_schema={"type": "object",
                   "properties": {"src":        {"type": "string"},
                                   "name":       {"type": "string"},
                                   "seamless":   {"type": "boolean"},
                                   "crop":       {"type": "array",
                                                   "items": {"type": "number"},
                                                   "minItems": 4,
                                                   "maxItems": 4},
                                   "saturation": {"type": "number"},
                                   "contrast":   {"type": "number"}},
                   "required": ["src", "name"]},
)
def texture_extract(session, src: str, name: str,
                     seamless: bool = True,
                     crop: list | None = None,
                     saturation: float = 0.0,
                     contrast: float = 0.0) -> dict:
    from elysium.render import texture as tex
    crop_rect = tuple(int(v) for v in crop) if crop and len(crop) == 4 else None
    out, _ = tex.extract_from_file(
        src, name=name, crop_rect=crop_rect,
        saturation=float(saturation), contrast=float(contrast),
        tile=bool(seamless))
    return {"path": str(out), "name": name, "crop": list(crop_rect or [])}


@register_tool(
    name="texture.apply_layer",
    description="Add a texture layer to a placement (multi-layer stack).",
    input_schema={"type": "object",
                   "properties": {"id":      {"type": "string"},
                                   "path":    {"type": "string"},
                                   "scale":   {"type": "number"},
                                   "tint":    {"type": "array"},
                                   "opacity": {"type": "number"},
                                   "blend":   {"type": "string"}},
                   "required": ["id", "path"]},
)
def texture_apply_layer(session, id: str, path: str,
                         scale: float = 1.0, tint: list | None = None,
                         opacity: float = 1.0, blend: str = "normal") -> dict:
    p = session.lookup(id)
    layer = {"path": path, "scale": float(scale), "offset_x": 0.0,
              "offset_y": 0.0, "rotation": 0.0, "opacity": float(opacity),
              "blend": blend}
    if tint: layer["tint"] = list(tint)
    p.texture_layers = list(p.texture_layers or [])
    p.texture_layers.append(layer)
    cache = getattr(session.designer, "_texture_cache", None)
    if cache: cache.clear()
    return {"layer_index": len(p.texture_layers) - 1}


@register_tool(
    name="texture.list_library",
    description="List every texture in the user's local library along with "
                "its pixel dimensions, aspect ratio, and file size.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def texture_list_library(session) -> dict:
    from elysium.render import texture as tex
    from PIL import Image as _PILImage
    out = []
    for path in tex.list_library():
        info = {"path": str(path), "name": path.stem}
        try:
            with _PILImage.open(path) as im:
                info["w"], info["h"] = im.size
                info["aspect"] = (im.size[0] / im.size[1]) if im.size[1] else 0
            info["bytes"] = path.stat().st_size
        except Exception as e:
            info["error"] = str(e)
        out.append(info)
    return {"textures": out, "count": len(out)}


@register_tool(
    name="texture.crop_to_match",
    description="Crop a source image to an arbitrary aspect ratio and "
                "resolution, save to the user's texture library, return the "
                "tile path. Unlike texture.extract_from_image, this preserves "
                "the cropped pixels exactly (no tiling pass) and produces an "
                "output of the requested dimensions. Use it after "
                "mesh.read_uv_bbox to pick a region of the source photo that "
                "matches a sub-mesh's UV bbox aspect ratio. Pass either "
                "`crop` [x,y,w,h] in source-pixel coords, or `crop_norm` "
                "[u_min, v_min, u_max, v_max] in [0,1] coords. If `out_w`/"
                "`out_h` are given, the cropped region is resized to those "
                "dimensions; otherwise the crop's native dimensions are kept.",
    input_schema={
        "type": "object",
        "properties": {
            "src":       {"type": "string"},
            "name":      {"type": "string"},
            "crop":      {"type": "array", "items": {"type": "number"},
                           "minItems": 4, "maxItems": 4},
            "crop_norm": {"type": "array", "items": {"type": "number"},
                           "minItems": 4, "maxItems": 4},
            "out_w":     {"type": "number"},
            "out_h":     {"type": "number"},
        },
        "required": ["src", "name"],
    },
)
def texture_crop_to_match(session, src: str, name: str,
                            crop: list | None = None,
                            crop_norm: list | None = None,
                            out_w: float | None = None,
                            out_h: float | None = None) -> dict:
    from PIL import Image as _PILImage
    from pathlib import Path
    from elysium.render.texture import LIBRARY_DIR
    im = _PILImage.open(src).convert("RGBA")
    sw, sh = im.size
    if crop is not None and len(crop) == 4:
        x, y, w, h = [int(v) for v in crop]
    elif crop_norm is not None and len(crop_norm) == 4:
        u0, v0, u1, v1 = [float(v) for v in crop_norm]
        x = int(round(u0 * sw)); y = int(round(v0 * sh))
        w = int(round((u1 - u0) * sw))
        h = int(round((v1 - v0) * sh))
    else:
        x, y, w, h = 0, 0, sw, sh
    # Clamp.
    x = max(0, min(sw - 1, x)); y = max(0, min(sh - 1, y))
    w = max(1, min(sw - x, w)); h = max(1, min(sh - y, h))
    region = im.crop((x, y, x + w, y + h))
    if out_w and out_h:
        region = region.resize((int(out_w), int(out_h)), _PILImage.LANCZOS)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    out = LIBRARY_DIR / f"{safe}.png"
    i = 1
    while out.exists() and out.stat().st_size > 0 and i < 10000:
        out = LIBRARY_DIR / f"{safe}-{i}.png"
        i += 1
    region.save(out)
    return {"path": str(out), "name": out.stem,
            "src_crop": [x, y, w, h], "out_size": list(region.size)}


@register_tool(
    name="texture.stamp_region",
    description="Stamp a section of a source image onto a placement's "
                "PaintMask at the given target rect (in placement-local "
                "coords [0,0] = top-left of the bbox). Equivalent of using "
                "the Brush tool with a custom image stamp instead of a solid "
                "color: lets a caller build up a complex texture section "
                "by section. Pass `src_crop` [x,y,w,h] in source-pixel "
                "coords (defaults to whole image) and `dst_rect` [x,y,w,h] "
                "in placement-bbox px (defaults to (0,0,placement.w,placement.h)). "
                "`opacity` (0..1) controls blend strength.",
    input_schema={
        "type": "object",
        "properties": {
            "id":       {"type": "string"},
            "src":      {"type": "string"},
            "src_crop": {"type": "array", "items": {"type": "number"},
                         "minItems": 4, "maxItems": 4},
            "dst_rect": {"type": "array", "items": {"type": "number"},
                         "minItems": 4, "maxItems": 4},
            "opacity":  {"type": "number"},
        },
        "required": ["id", "src"],
    },
)
def texture_stamp_region(session, id: str, src: str,
                          src_crop: list | None = None,
                          dst_rect: list | None = None,
                          opacity: float = 1.0) -> dict:
    from PIL import Image as _PILImage
    import numpy as _np
    p = session.lookup(id)
    designer = session.designer
    # Load source.
    src_im = _PILImage.open(src).convert("RGBA")
    sw, sh = src_im.size
    if src_crop and len(src_crop) == 4:
        sx, sy, scw, sch = [int(v) for v in src_crop]
    else:
        sx, sy, scw, sch = 0, 0, sw, sh
    sx = max(0, min(sw - 1, sx)); sy = max(0, min(sh - 1, sy))
    scw = max(1, min(sw - sx, scw)); sch = max(1, min(sh - sy, sch))
    src_im = src_im.crop((sx, sy, sx + scw, sy + sch))
    # Locate or create the placement's PaintMask.
    masks = getattr(designer, "paint_masks", None)
    if masks is None:
        designer.paint_masks = {}
        masks = designer.paint_masks
    mask = masks.get(_obj_id(p))
    pw, ph = int(p.w), int(p.h)
    if mask is None:
        # Lazy import the PaintMask class from the framework: same one
        # the live brush uses.
        try:
            from elysium.render.texture import PaintMask
        except ImportError:
            # Fall back to a dataclass-shaped stand-in: just an RGBA buffer.
            class _PM:
                def __init__(self, w, h):
                    self.buf = _np.zeros((h, w, 4), dtype=_np.uint8)
            PaintMask = _PM
        mask = PaintMask(pw, ph) if PaintMask.__init__.__defaults__ is None \
                else PaintMask(pw, ph)
        masks[_obj_id(p)] = mask
    if dst_rect and len(dst_rect) == 4:
        dx, dy, dw, dh = [int(v) for v in dst_rect]
    else:
        dx, dy, dw, dh = 0, 0, pw, ph
    dx = max(0, min(pw, dx)); dy = max(0, min(ph, dy))
    dw = max(1, min(pw - dx, dw)); dh = max(1, min(ph - dy, dh))
    stamp = src_im.resize((dw, dh), _PILImage.LANCZOS)
    stamp_arr = _np.array(stamp).astype(_np.float32) / 255.0
    if stamp_arr.shape[-1] == 3:
        # Add full alpha.
        a = _np.ones((dh, dw, 1), dtype=_np.float32)
        stamp_arr = _np.concatenate([stamp_arr, a], axis=-1)
    buf = mask.buf.astype(_np.float32) / 255.0
    region = buf[dy:dy+dh, dx:dx+dw, :]
    sa = stamp_arr[..., 3:4] * float(opacity)
    # Source-over alpha blend.
    out_rgb = stamp_arr[..., :3] * sa + region[..., :3] * (1.0 - sa)
    out_a   = sa + region[..., 3:4] * (1.0 - sa)
    region[:] = _np.concatenate([out_rgb, out_a], axis=-1)
    buf[dy:dy+dh, dx:dx+dw, :] = region
    mask.buf = (_np.clip(buf, 0.0, 1.0) * 255.0 + 0.5).astype(_np.uint8)
    # Flag the mask as dirty + flush every caching layer so the canvas
    # writes a fresh mask PNG on the next paint frame.
    if hasattr(designer, "_brush_dirty"):
        designer._brush_dirty.add(_obj_id(p))
    cache = getattr(designer, "_paint_mask_files", None)
    if cache: cache.pop(_obj_id(p), None)
    cache = getattr(designer, "_paint_mask_png_cache", None)
    if cache: cache.pop(_obj_id(p), None)
    cache = getattr(designer, "_texture_cache", None)
    if cache:
        for k in list(cache.keys()):
            if k and k[0] == _obj_id(p):
                cache.pop(k, None)
    return {"placement": id, "dst": [dx, dy, dw, dh],
            "src_crop": [sx, sy, scw, sch], "opacity": float(opacity)}


@register_tool(
    name="texture.assemble_atlas",
    description="Build a single albedo atlas image that aligns regions of a "
                "source photo to a mesh's UV layout. `regions` is a list of "
                "{src_crop:[x,y,w,h], dst_uv_bbox:[umin,vmin,umax,vmax], "
                "flip_v:bool}. For each entry the source crop is extracted "
                "from `src` (in source-image pixel coords), scaled to fit "
                "the destination UV bbox (translated to pixel coords in a "
                "fresh size×size canvas), and pasted in. `flip_v` defaults "
                "to True (matching the .3ds loader's V-flip so on-screen "
                "anatomy is right-side up). Existing destination pixels are "
                "overwritten: paint anatomy from background → foreground "
                "(wings first, body last). Returns the saved atlas path so "
                "it can be bound via material.set_texture.",
    input_schema={
        "type": "object",
        "properties": {
            "src":     {"type": "string"},
            "name":    {"type": "string"},
            "size":    {"type": "integer"},
            "regions": {"type": "array",
                         "items": {"type": "object",
                                    "properties": {
                                        "src_crop":     {"type": "array",
                                                          "items": {"type": "number"},
                                                          "minItems": 4, "maxItems": 4},
                                        "dst_uv_bbox":  {"type": "array",
                                                          "items": {"type": "number"},
                                                          "minItems": 4, "maxItems": 4},
                                        "flip_v":       {"type": "boolean"},
                                    },
                                    "required": ["src_crop", "dst_uv_bbox"]}},
        },
        "required": ["name", "regions"],
    },
)
def texture_assemble_atlas(session, name: str,
                            regions: list, src: str = "",
                            size: int = 1024) -> dict:
    """Compose a UV-aligned albedo atlas from a single source photo."""
    from PIL import Image as _PIL
    from pathlib import Path as _Path
    size = int(size)
    default_src_im = _PIL.open(src).convert("RGBA") if src else None
    atlas = _PIL.new("RGBA", (size, size), (0, 0, 0, 0))
    for r in regions:
        sx, sy, sw, sh = (int(v) for v in r["src_crop"])
        umin, vmin, umax, vmax = (float(v) for v in r["dst_uv_bbox"])
        # Per-region source override: each region can read from its own
        # image. Useful when you've pre-scaled crops per part with
        # texture.crop_to_match and want to glue them onto a single atlas
        # at part-specific UV bboxes.
        if r.get("src"):
            src_im = _PIL.open(r["src"]).convert("RGBA")
        elif default_src_im is not None:
            src_im = default_src_im
        else:
            raise ValueError("assemble_atlas: every region needs `src`, or pass top-level `src`")
        crop = src_im.crop((sx, sy, sx + sw, sy + sh))
        # Optional horizontal mirror: useful when the source photo's wing
        # is oriented the opposite way from the mesh's UV layout (e.g.
        # photo's inner-blue content is on one side of the crop but the
        # mesh's inner-wing UV is on the other).
        if bool(r.get("flip_h", False)):
            crop = crop.transpose(_PIL.FLIP_LEFT_RIGHT)
        # Translate dst UV bbox → atlas pixel rect. V-flip for 3DS-style
        # meshes (where the loader does v = 1 - v); top of texture image
        # is v=1, bottom is v=0.
        flip_v = bool(r.get("flip_v", True))
        if flip_v:
            py0 = int(round(size * (1.0 - vmax)))
            py1 = int(round(size * (1.0 - vmin)))
        else:
            py0 = int(round(size * vmin))
            py1 = int(round(size * vmax))
        px0 = int(round(size * umin))
        px1 = int(round(size * umax))
        dw, dh = max(1, px1 - px0), max(1, py1 - py0)
        scaled = crop.resize((dw, dh), _PIL.LANCZOS)
        if flip_v:
            # Flip the crop vertically too so wing-tip pixels map to the
            # v=vmax edge of the bbox (which after V-flip lands at the
            # smaller-y end of the atlas image: i.e. the "top" visually).
            scaled = scaled.transpose(_PIL.FLIP_TOP_BOTTOM)
        atlas.alpha_composite(scaled, dest=(px0, py0))
    from elysium.render import texture as _tex
    out = _tex.LIBRARY_DIR / f"{name}.png"
    atlas.save(out)
    return {"path": str(out), "size": [size, size],
            "regions": len(regions)}


@register_tool(
    name="texture.clear_paint_mask",
    description="Wipe a placement's PaintMask (the screen-space brush "
                "overlay) back to fully transparent. Equivalent to selecting "
                "the placement, picking the Eraser, and dragging across the "
                "entire bbox: but in one tool call. Use to revert all "
                "freehand painting on a placement before restarting.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
)
def texture_clear_paint_mask(session, id: str) -> dict:
    designer = session.designer
    p = session.lookup(id)
    masks = getattr(designer, "paint_masks", None)
    if masks is None:
        return {"cleared": False, "reason": "no paint_masks dict"}
    m = masks.get(_obj_id(p))
    if m is None:
        return {"cleared": False, "reason": "no mask for this placement"}
    if hasattr(m, "clear"):
        m.clear()
    else:
        import numpy as _np
        m.buf = _np.zeros_like(m.buf)
    if hasattr(designer, "_brush_dirty"):
        designer._brush_dirty.add(_obj_id(p))
    cache = getattr(designer, "_paint_mask_files", None)
    if cache: cache.pop(_obj_id(p), None)
    cache = getattr(designer, "_paint_mask_png_cache", None)
    if cache: cache.pop(_obj_id(p), None)
    designer.menu_status = f"PaintMask cleared on {p.name}"
    return {"cleared": True, "w": int(m.w), "h": int(m.h)}


@register_tool(
    name="texture.read_info",
    description="Inspect an image file on disk. Returns its size, the "
                "tight bounding box of opaque pixels (alpha > 200), and "
                "the tight bbox of pixels matching an optional color "
                "filter so you can pick crops by content instead of "
                "guessing. `color_filter` is one of: 'blue', 'red', "
                "'iridescent', 'dark', or absent (skip). Returns the "
                "centroid of matched pixels too, for easy 'aim here' "
                "stamping.",
    input_schema={
        "type": "object",
        "properties": {
            "path":         {"type": "string"},
            "color_filter": {"type": "string"},
            "alpha_thresh": {"type": "integer"},
        },
        "required": ["path"],
    },
    side_effect=SideEffect.READ, undoable=False,
)
def texture_read_info(path: str,
                       color_filter: str | None = None,
                       alpha_thresh: int = 200) -> dict:
    from PIL import Image as _PIL
    import numpy as _np
    a = _np.array(_PIL.open(path).convert("RGBA"))
    H, W = a.shape[:2]
    out: dict = {"size": [W, H]}
    op = a[..., 3] > int(alpha_thresh)
    if op.any():
        ys, xs = _np.where(op)
        out["opaque_bbox"] = {"xmin": int(xs.min()), "ymin": int(ys.min()),
                                "xmax": int(xs.max()), "ymax": int(ys.max()),
                                "w": int(xs.max() - xs.min() + 1),
                                "h": int(ys.max() - ys.min() + 1)}
    else:
        out["opaque_bbox"] = None
    if color_filter:
        r = a[..., 0].astype(int); g = a[..., 1].astype(int); b = a[..., 2].astype(int)
        cf = color_filter.lower()
        if   cf == "blue":       mask = op & (b > r + 30) & (b > g + 20) & (b > 60)
        elif cf == "red":        mask = op & (r > b + 30) & (r > g + 20) & (r > 60)
        elif cf == "iridescent": mask = op & ((b > r + 20) | (r > b + 20)) & (r + g + b > 200)
        elif cf == "dark":       mask = op & (r + g + b < 90)
        else:                     mask = _np.zeros_like(op)
        ys, xs = _np.where(mask)
        if len(xs):
            out["match"] = {
                "color_filter": cf, "count": int(len(xs)),
                "xmin": int(xs.min()), "ymin": int(ys.min()),
                "xmax": int(xs.max()), "ymax": int(ys.max()),
                "xmean": int(xs.mean()), "ymean": int(ys.mean()),
                "p5_x": int(_np.percentile(xs, 5)), "p95_x": int(_np.percentile(xs, 95)),
                "p5_y": int(_np.percentile(ys, 5)), "p95_y": int(_np.percentile(ys, 95)),
            }
        else:
            out["match"] = {"color_filter": cf, "count": 0}
    return out


@register_tool(
    name="texture.generate_pbr_maps",
    description="Generate a full set of PBR maps (diffuse / albedo, normal, "
                "roughness, displacement) from a single flat photograph. "
                "Diffuse strips baked highlights/shadows via tone-curve "
                "normalisation; normal map comes from luminance gradients "
                "(Sobel) encoded as tangent-space RGB; roughness is the "
                "inverse of local luminance variance (smooth areas = low "
                "roughness); displacement is the photo's luminance. Returns "
                "a dict with one path per generated map.",
    input_schema={
        "type": "object",
        "properties": {
            "src":         {"type": "string"},
            "name":        {"type": "string"},
            "normal_strength":     {"type": "number"},
            "roughness_smoothing": {"type": "number"},
        },
        "required": ["src", "name"],
    },
)
def texture_generate_pbr_maps(session, src: str, name: str,
                                normal_strength: float = 6.0,
                                roughness_smoothing: float = 3.0) -> dict:
    """Decompose a single photo into Color/Normal/Roughness/Displacement."""
    from PIL import Image as _PIL
    from PIL import ImageFilter as _PILFilter
    import numpy as _np
    from elysium.render import texture as _tex
    img = _PIL.open(src).convert("RGBA")
    a = _np.array(img, dtype=_np.uint8)
    rgb = a[..., :3].astype(_np.float32) / 255.0
    alpha = a[..., 3]
    H, W = a.shape[:2]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

    # --- DIFFUSE (Color) -------------------------------------------------
    # Tone-curve normalisation: divide by a heavily blurred luminance to
    # remove baked highlights/shadows, then renormalise. Keeps the pure
    # surface color close to flat.
    blurred = _np.array(img.convert("L").filter(
        _PILFilter.GaussianBlur(radius=max(8, min(W, H) // 16)))) / 255.0
    blurred = _np.maximum(blurred, 0.05)
    norm = lum / blurred
    # Push back to 0-1 via gentle reinhard.
    norm = norm / (1.0 + 0.4 * norm)
    flat_scale = (norm[..., None] / _np.maximum(lum[..., None], 1e-4))
    diffuse = _np.clip(rgb * flat_scale, 0.0, 1.0)
    diffuse_rgba = _np.concatenate([(diffuse * 255).astype(_np.uint8),
                                      alpha[..., None]], axis=-1)

    # --- NORMAL ----------------------------------------------------------
    # Sobel-derived height gradients → tangent-space RGB normal.
    L = (lum * 255).astype(_np.float32)
    gx = _np.zeros_like(L)
    gy = _np.zeros_like(L)
    gx[:, 1:-1] = (L[:, 2:] - L[:, :-2]) * 0.5
    gy[1:-1, :] = (L[2:, :] - L[:-2, :]) * 0.5
    s = max(0.1, float(normal_strength))
    nx = -gx / 128.0 * s
    ny = -gy / 128.0 * s
    nz = _np.ones_like(nx)
    n_len = _np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= n_len; ny /= n_len; nz /= n_len
    nrgb = _np.stack([(nx * 0.5 + 0.5) * 255.0,
                       (ny * 0.5 + 0.5) * 255.0,
                       (nz * 0.5 + 0.5) * 255.0], axis=-1).astype(_np.uint8)
    normal_rgba = _np.concatenate([nrgb, alpha[..., None]], axis=-1)

    # --- ROUGHNESS -------------------------------------------------------
    # Local luminance standard deviation in a small window → high stddev
    # = busier surface = rougher. Inverted then blurred for stability.
    win = max(2, int(roughness_smoothing))
    pad = win
    Lpad = _np.pad(L, pad, mode="edge")
    s_sum = _np.zeros_like(L); s_sq = _np.zeros_like(L); cnt = 0
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            tile = Lpad[pad + dy: pad + dy + H, pad + dx: pad + dx + W]
            s_sum += tile; s_sq += tile * tile; cnt += 1
    mean = s_sum / cnt
    var = _np.maximum(s_sq / cnt - mean * mean, 0)
    stddev = _np.sqrt(var)
    rough = _np.clip(stddev / 32.0, 0.05, 0.95)
    rough_rgb = (_np.stack([rough, rough, rough], axis=-1) * 255).astype(_np.uint8)
    rough_rgba = _np.concatenate([rough_rgb, alpha[..., None]], axis=-1)

    # --- DISPLACEMENT ----------------------------------------------------
    disp = (lum * 255).astype(_np.uint8)
    disp_rgb = _np.stack([disp, disp, disp], axis=-1)
    disp_rgba = _np.concatenate([disp_rgb, alpha[..., None]], axis=-1)

    # Save all four.
    _tex.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    for suffix, arr in (("diffuse", diffuse_rgba),
                          ("normal", normal_rgba),
                          ("roughness", rough_rgba),
                          ("displacement", disp_rgba)):
        path = _tex.LIBRARY_DIR / f"{safe}_{suffix}.png"
        _PIL.fromarray(arr).save(path)
        out[suffix] = str(path)
    return {"name": name, "size": [W, H], "maps": out}


@register_tool(
    name="texture.transfer_section",
    description="Strict 1:1 pixel transfer from a source-image region to a "
                "target placement's PaintMask (screen-space overlay). The "
                "source crop is scaled to EXACTLY the target rect's pixel "
                "dimensions, then copied row-by-row top-down so each pixel "
                "in the source maps to one pixel in the target.\n\n"
                "Use `row_start` / `row_end` (in [0,1] of the section) to "
                "transfer only a partial vertical band: that's the basis "
                "for the progressive top-down workflow: call repeatedly "
                "with row_end stepping from 0→1 and screenshot between "
                "each call to watch the wing fill in section by section.\n\n"
                "The transfer is additive on the PaintMask: existing paint "
                "below it is overwritten only in the band being painted.",
    input_schema={
        "type": "object",
        "properties": {
            "id":         {"type": "string"},
            "src":        {"type": "string"},
            "src_crop":   {"type": "array", "items": {"type": "number"},
                            "minItems": 4, "maxItems": 4},
            "dst_rect":   {"type": "array", "items": {"type": "number"},
                            "minItems": 4, "maxItems": 4},
            "row_start":  {"type": "number"},   # [0,1]
            "row_end":    {"type": "number"},   # [0,1]
            "flip_h":     {"type": "boolean"},
        },
        "required": ["id", "src", "src_crop", "dst_rect"],
    },
)
def texture_transfer_section(session, id: str, src: str,
                               src_crop: list, dst_rect: list,
                               row_start: float = 0.0,
                               row_end: float = 1.0,
                               flip_h: bool = False) -> dict:
    """Pixel-perfect 1:1 transfer from a source crop to a placement's
    PaintMask, optionally restricted to a vertical band."""
    from PIL import Image as _PIL
    import numpy as _np
    designer = session.designer
    p = session.lookup(id)
    sx, sy, sw, sh = (int(v) for v in src_crop)
    dx, dy, dw, dh = (int(v) for v in dst_rect)
    src_im = _PIL.open(src).convert("RGBA")
    src_im = src_im.crop((sx, sy, sx + sw, sy + sh))
    if flip_h:
        src_im = src_im.transpose(_PIL.FLIP_LEFT_RIGHT)
    # Scale to target dimensions: this is where the wings become the
    # same pixel size on both butterflies.
    if (sw, sh) != (dw, dh):
        src_im = src_im.resize((dw, dh), _PIL.LANCZOS)
    scaled = _np.array(src_im, dtype=_np.uint8)
    # Vertical band restriction (top-down progressive paint).
    row_start = max(0.0, min(1.0, float(row_start)))
    row_end   = max(0.0, min(1.0, float(row_end)))
    if row_end <= row_start:
        return {"transferred": 0, "reason": "row_end <= row_start"}
    band_y0 = int(round(row_start * dh))
    band_y1 = int(round(row_end * dh))
    band = scaled[band_y0:band_y1]
    band_h = band.shape[0]
    if band_h <= 0:
        return {"transferred": 0, "reason": "empty band"}
    # Get / create PaintMask.
    masks = getattr(designer, "paint_masks", None)
    if masks is None:
        designer.paint_masks = {}
        masks = designer.paint_masks
    mask = masks.get(_obj_id(p))
    pw, ph = int(p.w), int(p.h)
    if mask is None:
        try:
            from elysium.render.texture import PaintMask
        except ImportError:
            class _PM:
                def __init__(self, w, h):
                    self.buf = _np.zeros((h, w, 4), dtype=_np.uint8)
            PaintMask = _PM
        mask = PaintMask(pw, ph)
        masks[_obj_id(p)] = mask
    # Compute destination band in placement-local coords.
    tgt_y0 = dy + band_y0
    tgt_y1 = dy + band_y1
    tgt_x0 = dx
    tgt_x1 = dx + dw
    # Clip to mask.
    if tgt_x0 < 0: band = band[:, -tgt_x0:]; tgt_x0 = 0
    if tgt_y0 < 0: band = band[-tgt_y0:]; tgt_y0 = 0
    if tgt_x1 > pw: band = band[:, :pw - tgt_x0]; tgt_x1 = pw
    if tgt_y1 > ph: band = band[:ph - tgt_y0]; tgt_y1 = ph
    if band.shape[0] <= 0 or band.shape[1] <= 0:
        return {"transferred": 0, "reason": "clipped to nothing"}
    # Strict pixel copy: straight write into mask.buf at the destination.
    # Force opaque alpha so paint is additive only (cannot erase model).
    band_rgb = band[..., :3]
    h_band, w_band = band_rgb.shape[:2]
    target_slice = mask.buf[tgt_y0:tgt_y0 + h_band, tgt_x0:tgt_x0 + w_band]
    target_slice[..., :3] = band_rgb
    target_slice[..., 3]  = 255
    mask.buf[tgt_y0:tgt_y0 + h_band, tgt_x0:tgt_x0 + w_band] = target_slice
    # Flush caches so the next paint frame re-renders the PaintMask.
    if hasattr(designer, "_brush_dirty"):
        designer._brush_dirty.add(_obj_id(p))
    for ca in ("_paint_mask_files", "_paint_mask_png_cache"):
        c = getattr(designer, ca, None)
        if c: c.pop(_obj_id(p), None)
    designer.menu_status = (f"Transferred {h_band}×{w_band}px section "
                              f"row=[{row_start:.0%}–{row_end:.0%}] → {p.name}")
    return {"transferred": int(h_band * w_band),
            "dst_band": [int(tgt_x0), int(tgt_y0), int(w_band), int(h_band)],
            "src_size": [int(dw), int(dh)],
            "rows": [int(band_y0), int(band_y1)]}


@register_tool(
    name="lasso.wing_perimeter",
    description="Compute the perimeter polygon of a wing's top vertical band, "
                "INSIDE the wing silhouette (not a bbox rectangle). Returns "
                "a Shape placement-ready polygon point list following the "
                "wing outline at rows in [v_start, v_end] of the wing.\n\n"
                "For a Mesh3D placement: projects each face's vertices "
                "through the placement's camera, identifies which faces "
                "fall in the vertical band, then traces the outer edge of "
                "those faces as a polygon: so the lasso hugs the actual "
                "wing perimeter at that altitude.\n\n"
                "For an Image placement: reads the photo's alpha channel "
                "inside `source_bbox` (in source-image pixel coords), "
                "finds opaque pixels in the band, returns left/right "
                "extents per row as a polygon outline in placement-local "
                "canvas pixels (so the polygon is sized to the on-screen "
                "image).\n\n"
                "Optionally CREATES a marching-ants Shape placement with "
                "that polygon when `create_overlay=True`.",
    input_schema={
        "type": "object",
        "properties": {
            "id":            {"type": "string"},
            "part":          {"type": "string"},
            "source_bbox":   {"type": "array", "items": {"type": "number"},
                               "minItems": 4, "maxItems": 4},
            "v_start":       {"type": "number"},
            "v_end":         {"type": "number"},
            "create_overlay":{"type": "boolean"},
            "overlay_name":  {"type": "string"},
            "color":         {"type": "array", "items": {"type": "number"},
                               "minItems": 3, "maxItems": 4},
        },
        "required": ["id"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def lasso_wing_perimeter(session, id: str,
                          part: str = "",
                          source_bbox: list | None = None,
                          v_start: float = 0.0,
                          v_end: float = 0.01,
                          axis: str = "tip",      # "tip" | "y_top" | "y_bottom"
                          create_overlay: bool = False,
                          overlay_name: str = "lasso",
                          color: list | None = None) -> dict:
    import math
    import numpy as _np
    from PIL import Image as _PIL
    from elysium.render import pbr as _pbr
    designer = session.designer
    p = session.lookup(id)
    points: list[tuple[float, float]] = []
    placement_offset = (0.0, 0.0)
    if p.kind == "Mesh3D":
        # Project each vertex of the named part to placement-local pixels.
        if p.mesh_kind.startswith("file:"):
            mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
        else:
            mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
        if mesh.part_names is None:
            raise ValueError("mesh has no part_names")
        pid = None
        for i, n in enumerate(mesh.part_names):
            if n == part: pid = i; break
        if pid is None:
            raise KeyError(f"no part {part!r}; have {mesh.part_names}")
        yaw   = float(getattr(p, "mesh_yaw",   0.4))
        pitch = float(getattr(p, "mesh_pitch", 0.25))
        dist  = float(getattr(p, "mesh_dist", None) or 3.5)
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        cp_, sp_ = math.cos(pitch), math.sin(pitch)
        cam_pos = _np.array([dist * cp_ * sy_, dist * sp_, dist * cp_ * cy_],
                              dtype=_np.float32)
        look = -cam_pos / max(_np.linalg.norm(cam_pos), 1e-8)
        up_w = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
        right = _np.cross(look, up_w); right /= max(_np.linalg.norm(right), 1e-8)
        up = _np.cross(right, look)
        fov = math.radians(38.0); f = 1.0 / math.tan(fov * 0.5)
        verts = mesh.verts.astype(_np.float32)
        rel = verts - cam_pos
        z = rel @ look
        x = rel @ right; y = rel @ up
        inv_z = 1.0 / _np.where(_np.abs(z) > 1e-4, z, 1e-4)
        ndc_x = x * f * inv_z; ndc_y = y * f * inv_z
        px = (ndc_x + 1.0) * 0.5 * p.w
        py = (1.0 - (ndc_y + 1.0) * 0.5) * p.h
        mask = (mesh.vert_part_ids == pid)
        wxs = px[mask]; wys = py[mask]
        if len(wxs) == 0:
            return {"points": [], "reason": "no verts in part"}
        # Choose the "scan axis": the direction we slice the wing along.
        # axis="tip": auto-detect the wing's body→tip direction (outer X
        #   side for left/right wings); "top 1%" = 1% slice closest to
        #   the tip.
        # axis="y_top": classic top-down rows.
        # axis="y_bottom": bottom-up rows.
        if axis == "corner_tip":
            # Wing tip corner: the OUTER-UPPER vertex of the wing.
            # Combines X-extreme (outer) and Y-min (top) into one scan.
            # For Wing_Left (centroid X < body_cx): tip at (min_X, min_Y),
            #   scan = X + Y → min scan = tip.
            # For Wing_Right (centroid X > body_cx): tip at (max_X, min_Y),
            #   scan = -X + Y → min scan = tip.
            cx = float(wxs.mean())
            body_cx = p.w * 0.5
            x_sign = +1.0 if cx < body_cx else -1.0
            scan_pts = px * x_sign + py
            scan_part = scan_pts[mask]
            scan_min, scan_max = float(scan_part.min()), float(scan_part.max())
            band_lo = scan_min
            band_hi = scan_min + v_end * (scan_max - scan_min)
            faces = mesh.faces
            part_face_idx = [i for i in range(len(faces))
                              if mask[int(faces[i][0])]]
            row_extents: list[tuple[float, float, float]] = []
            for fi in part_face_idx:
                i0, i1, i2 = (int(faces[fi][k]) for k in range(3))
                vx = (px[i0], px[i1], px[i2])
                vy = (py[i0], py[i1], py[i2])
                vs = (px[i0] * x_sign + py[i0],
                       px[i1] * x_sign + py[i1],
                       px[i2] * x_sign + py[i2])
                if min(vs) > band_hi: continue
                # Triangle has at least one vertex in [band_lo, band_hi].
                # Sample its rows.
                ymin_f = float(min(vy)); ymax_f = float(max(vy))
                nrows = max(1, int(ymax_f - ymin_f))
                for r in range(nrows + 1):
                    row_y = ymin_f + r
                    if row_y > max(vy) or row_y < min(vy): continue
                    edges = ((0, 1), (1, 2), (2, 0))
                    xs_on_row: list[float] = []
                    for a, b in edges:
                        ya, yb = vy[a], vy[b]
                        if (ya - row_y) * (yb - row_y) > 0: continue
                        if abs(yb - ya) < 1e-6: continue
                        t = (row_y - ya) / (yb - ya)
                        xs_on_row.append(vx[a] + t * (vx[b] - vx[a]))
                    if not xs_on_row: continue
                    # Among xs_on_row, filter those whose (X*x_sign + Y) is in band.
                    in_band_xs = [x_ for x_ in xs_on_row
                                  if band_lo <= (x_ * x_sign + row_y) <= band_hi]
                    if not in_band_xs: continue
                    row_extents.append((row_y, min(in_band_xs), max(in_band_xs)))
            # De-dup by row.
            from collections import defaultdict
            by_row = defaultdict(lambda: (float("inf"), float("-inf")))
            for y_, lo, hi in row_extents:
                k = round(y_)
                cur = by_row[k]
                by_row[k] = (min(cur[0], lo), max(cur[1], hi))
            sorted_rows = sorted(by_row.items())
            for y_, (lo, hi) in sorted_rows:
                points.append((float(lo), float(y_)))
            for y_, (lo, hi) in reversed(sorted_rows):
                points.append((float(hi), float(y_)))
        elif axis == "tip":
            cx = float(wxs.mean())
            # The body's screen X center: use the placement center as
            # proxy (mesh world X=0 maps roughly here).
            body_cx = p.w * 0.5
            # tip is OUTSIDE the body: for Wing_Right (cx > body_cx) the
            # tip sits at MAX x → scan = -x so min(scan) = tip.
            # For Wing_Left (cx < body_cx) tip is at MIN x → scan = +x.
            tip_dir_x = -1.0 if cx > body_cx else +1.0
            # Scan-axis = X going from tip→body.  tip_value (smallest
            # along scan axis) is the wing tip.
            scan = px * tip_dir_x   # along scan axis (positive going away from tip)
            # Tip = MIN of scan (smallest = at tip = our "top")
            scan_part = scan[mask]
            scan_min, scan_max = float(scan_part.min()), float(scan_part.max())
            band_lo = scan_min + v_start * (scan_max - scan_min)
            band_hi = scan_min + v_end   * (scan_max - scan_min)
            # Walk strip-axis = perpendicular to scan = Y.
            faces = mesh.faces
            part_face_idx = [i for i in range(len(faces))
                              if mask[int(faces[i][0])]]
            strip_extents: list[tuple[float, float, float]] = []
            # Sample along Y; for each Y row, find which faces in the
            # tip band intersect, and take their min/max along scan axis
            # within the band.
            row_extents = []
            nrows = max(2, int(round(wys.max() - wys.min())))
            for r in range(nrows + 1):
                row_y = float(wys.min()) + r
                lows: list[float] = []; highs: list[float] = []
                lows_x: list[float] = []; highs_x: list[float] = []
                for fi in part_face_idx:
                    i0, i1, i2 = (int(faces[fi][k]) for k in range(3))
                    v_y = (py[i0], py[i1], py[i2])
                    v_x = (px[i0], px[i1], px[i2])
                    if min(v_y) > row_y or max(v_y) < row_y: continue
                    # Get intersection points with row_y.
                    edges = ((0, 1), (1, 2), (2, 0))
                    xs_on_row: list[float] = []
                    for a, b in edges:
                        ya, yb = v_y[a], v_y[b]
                        if (ya - row_y) * (yb - row_y) > 0: continue
                        if abs(yb - ya) < 1e-6: continue
                        t = (row_y - ya) / (yb - ya)
                        xs_on_row.append(v_x[a] + t * (v_x[b] - v_x[a]))
                    if not xs_on_row: continue
                    # Scan values for those X positions.
                    scan_vals = [x_ * tip_dir_x for x_ in xs_on_row]
                    # Clip the [xmin, xmax] across the row by the band.
                    seg_lo = min(scan_vals); seg_hi = max(scan_vals)
                    clip_lo = max(seg_lo, band_lo); clip_hi = min(seg_hi, band_hi)
                    if clip_hi < clip_lo: continue
                    lows.append(clip_lo); highs.append(clip_hi)
                if lows:
                    row_extents.append((row_y, min(lows), max(highs)))
            # Convert scan-coord back to X for points.
            for y_, lo, hi in row_extents:
                points.append((float(lo * tip_dir_x), float(y_)))
            for y_, lo, hi in reversed(row_extents):
                points.append((float(hi * tip_dir_x), float(y_)))
        else:
            # Original Y-axis slice path.
            ymin, ymax = float(wys.min()), float(wys.max())
            if axis == "y_top":
                band_top = ymin + v_start * (ymax - ymin)
                band_bottom = ymin + v_end * (ymax - ymin)
            else:  # y_bottom
                band_top = ymax - v_end * (ymax - ymin)
                band_bottom = ymax - v_start * (ymax - ymin)
            faces = mesh.faces
            part_face_idx = [i for i in range(len(faces))
                              if mask[int(faces[i][0])]]
            row_extents: list[tuple[float, float, float]] = []
            nrows = max(1, int(round(band_bottom - band_top)))
            for r in range(nrows + 1):
                row_y = band_top + r
                lefts: list[float] = []; rights: list[float] = []
                for fi in part_face_idx:
                    i0, i1, i2 = (int(faces[fi][k]) for k in range(3))
                    v_y = (py[i0], py[i1], py[i2])
                    v_x = (px[i0], px[i1], px[i2])
                    if min(v_y) > row_y or max(v_y) < row_y: continue
                    edges = ((0, 1), (1, 2), (2, 0))
                    xs_on_row: list[float] = []
                    for a, b in edges:
                        ya, yb = v_y[a], v_y[b]
                        if (ya - row_y) * (yb - row_y) > 0: continue
                        if abs(yb - ya) < 1e-6: continue
                        t = (row_y - ya) / (yb - ya)
                        xs_on_row.append(v_x[a] + t * (v_x[b] - v_x[a]))
                    if xs_on_row:
                        lefts.append(min(xs_on_row))
                        rights.append(max(xs_on_row))
                if lefts:
                    row_extents.append((row_y, min(lefts), max(rights)))
            for y_, lx, _rx in row_extents:
                points.append((float(lx), float(y_)))
            for y_, _lx, rx in reversed(row_extents):
                points.append((float(rx), float(y_)))
        placement_offset = (float(p.x), float(p.y))
    elif p.kind == "Image":
        # Identify opaque wing pixels inside source_bbox, in the v band.
        if not source_bbox or len(source_bbox) != 4:
            raise ValueError("source_bbox required for Image placement")
        img_path = getattr(p, "image_path", "")
        if not img_path:
            raise ValueError("Image placement has no image_path")
        photo = _np.array(_PIL.open(img_path).convert("RGBA"), dtype=_np.uint8)
        pH, pW = photo.shape[:2]
        sx, sy, sw, sh = (int(v) for v in source_bbox)
        wing = photo[sy:sy+sh, sx:sx+sw]
        op = wing[..., 3] > 200
        if not op.any():
            return {"points": [], "reason": "no opaque pixels in source_bbox"}
        ys, xs = _np.where(op)
        scale_x = p.w / float(pW)
        scale_y = p.h / float(pH)
        if axis == "tip":
            # The wing's tip = column farthest from the photo's center.
            x_mid = (xs.min() + xs.max()) / 2.0
            photo_mid_x = (pW / 2.0) - sx     # photo center in wing-crop coords
            tip_dir_x = -1.0 if x_mid > photo_mid_x else +1.0
            scan = xs * tip_dir_x
            scan_min, scan_max = float(scan.min()), float(scan.max())
            band_lo = scan_min + v_start * (scan_max - scan_min)
            band_hi = scan_min + v_end   * (scan_max - scan_min)
            # For each Y row in the wing's opaque range, find x-extent
            # of opaque pixels that fall in the tip band.
            row_extents = []
            for r in range(int(ys.min()), int(ys.max()) + 1):
                row_mask = (ys == r)
                if not row_mask.any(): continue
                row_xs_w = xs[row_mask]
                row_scan = row_xs_w * tip_dir_x
                in_band = (row_scan >= band_lo) & (row_scan <= band_hi)
                if not in_band.any(): continue
                xs_in = row_xs_w[in_band]
                l = sx + int(xs_in.min())
                ri = sx + int(xs_in.max())
                abs_row = r + sy
                canvas_y = abs_row * scale_y
                row_extents.append((canvas_y,
                                      l * scale_x,
                                      ri * scale_x))
            for y_, lx, _rx in row_extents:
                points.append((float(lx), float(y_)))
            for y_, _lx, rx in reversed(row_extents):
                points.append((float(rx), float(y_)))
        else:
            # Top 1% rows of wing's opaque content (by Y inside the source_bbox).
            wing_ymin = int(ys.min()); wing_ymax = int(ys.max())
            wing_h = wing_ymax - wing_ymin
            if axis == "y_top":
                band_top    = wing_ymin + v_start * wing_h
                band_bottom = wing_ymin + v_end   * wing_h
            else:
                band_top    = wing_ymax - v_end   * wing_h
                band_bottom = wing_ymax - v_start * wing_h
            row_extents = []
            for r in range(int(band_top), int(band_bottom) + 1):
                row_xs = xs[ys == r]
                if len(row_xs) == 0: continue
                l = sx + int(row_xs.min())
                ri = sx + int(row_xs.max())
                abs_row = r + sy
                canvas_y = abs_row * scale_y
                row_extents.append((canvas_y,
                                      l * scale_x,
                                      ri * scale_x))
            for y_, lx, _rx in row_extents:
                points.append((float(lx), float(y_)))
            for y_, _lx, rx in reversed(row_extents):
                points.append((float(rx), float(y_)))
        placement_offset = (float(p.x), float(p.y))
    else:
        raise ValueError(f"unsupported kind: {p.kind}")
    # Optionally create a visible Shape overlay placement.
    overlay_id = None
    if create_overlay and points:
        # Convert points to absolute canvas coords (Shape placements are
        # absolute), then add a Shape placement with shape="polygon".
        abs_pts = [(placement_offset[0] + x_, placement_offset[1] + y_)
                    for (x_, y_) in points]
        xs_ = [pt[0] for pt in abs_pts]; ys_ = [pt[1] for pt in abs_pts]
        x0 = min(xs_); y0 = min(ys_)
        x1 = max(xs_); y1 = max(ys_)
        local_pts = [(x_ - x0, y_ - y0) for (x_, y_) in abs_pts]
        P = session.designer_models.Placement
        cc = list(int(c) for c in (color or [255, 40, 40, 255]))
        # Semi-transparent fill of the band so a 1–2 px wide region is
        # still visible behind the marching ants.
        fill_col = (cc[0], cc[1], cc[2], 80)
        sh = P(kind="Shape", x=x0, y=y0,
                w=max(2.0, x1 - x0), h=max(2.0, y1 - y0),
                name=overlay_name,
                shape="polygon",
                points=local_pts,
                path_d="",
                fill=tuple(fill_col),
                stroke=tuple(cc),
                stroke_w=3.0)
        # `is_lasso` flag (marching-ants stroke marker) set after
        # construction: Placement's dataclass `__init__` may pre-date
        # the field on a hot-reloaded instance.
        sh.is_lasso = True
        designer.placements.append(sh)
        overlay_id = session.id_for(sh)
    return {"points":      [list(pt) for pt in points],
            "n_points":    len(points),
            "overlay_id":  overlay_id,
            "offset":      list(placement_offset)}


@register_tool(
    name="texture.transfer_uv_band",
    description="Copy a horizontal band of pixels from a source image into "
                "a Mesh3D placement's UV-mapped albedo texture (the texture "
                "that's baked onto the mesh's surface: NOT a screen "
                "overlay).\n\n"
                "Algorithm: identify the named sub-mesh part's UV bbox in "
                "the atlas → compute the atlas pixel rect that corresponds "
                "to the part's [v_start, v_end] vertical band → crop the "
                "source wing region from `src_wing_bbox` → scale it to "
                "the part's render-pixel dimensions (so each source pixel "
                "lands on one render pixel after PBR sampling) → take the "
                "[v_start, v_end] vertical band of the scaled crop → "
                "resample to the atlas-pixel band → write into the atlas "
                "and save. If the placement has no albedo bound yet a "
                "fresh transparent atlas of `size`×`size` is created. The "
                "existing atlas (if any) is preserved in regions outside "
                "this band so consecutive calls accumulate.\n\n"
                "Per-part UV bboxes come from mesh.read_uv_bbox; pixel "
                "dimensions of the part on screen come from "
                "mesh.read_part_render_bbox. Both are needed.",
    input_schema={
        "type": "object",
        "properties": {
            "id":              {"type": "string"},
            "src":             {"type": "string"},
            "src_wing_bbox":   {"type": "array", "items": {"type": "number"},
                                 "minItems": 4, "maxItems": 4},
            "part":            {"type": "string"},
            "v_start":         {"type": "number"},
            "v_end":           {"type": "number"},
            "size":            {"type": "integer"},
            "flip_h":          {"type": "boolean"},
        },
        "required": ["id", "src", "src_wing_bbox", "part"],
    },
)
def texture_transfer_uv_band(session, id: str, src: str,
                              src_wing_bbox: list, part: str,
                              v_start: float = 0.0,
                              v_end: float = 1.0,
                              size: int = 1024,
                              flip_h: bool = False) -> dict:
    from PIL import Image as _PIL
    import numpy as _np
    from elysium.render import pbr as _pbr
    from elysium.render import texture as _tex
    designer = session.designer
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"transfer_uv_band: kind={p.kind!r} (need Mesh3D)")
    # Pull the mesh.
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
    if mesh.vert_uvs is None or mesh.part_names is None:
        raise ValueError("mesh needs UVs + part names: uv_unwrap first")
    # Find the part's UV bbox.
    pid = None
    for i, n in enumerate(mesh.part_names):
        if n == part: pid = i; break
    if pid is None:
        raise KeyError(f"no part named {part!r}; have {mesh.part_names}")
    part_mask = (mesh.vert_part_ids == pid)
    p_uvs = mesh.vert_uvs[part_mask]
    umin, umax = float(p_uvs[:, 0].min()), float(p_uvs[:, 0].max())
    vmin, vmax = float(p_uvs[:, 1].min()), float(p_uvs[:, 1].max())
    # Compute atlas pixel rect for the part's full UV bbox.
    # The renderer uses V-flipped sampling (3DS convention): sample at
    # atlas y = (1 - v) * (H - 1). So part v=vmax is atlas y near top,
    # part v=vmin is atlas y near bottom.
    atlas_x0 = int(round(umin * size))
    atlas_x1 = int(round(umax * size))
    atlas_y0 = int(round((1.0 - vmax) * size))  # top edge of part in atlas
    atlas_y1 = int(round((1.0 - vmin) * size))  # bottom edge
    part_atlas_w = max(1, atlas_x1 - atlas_x0)
    part_atlas_h = max(1, atlas_y1 - atlas_y0)
    # Vertical band restriction in [0,1] of the part. v_start=0 → top
    # of part (highest screen-y region), v_end=1 → bottom of part.
    v_start = max(0.0, min(1.0, float(v_start)))
    v_end   = max(0.0, min(1.0, float(v_end)))
    if v_end <= v_start:
        return {"transferred": 0, "reason": "v_end <= v_start"}
    band_y0 = atlas_y0 + int(round(v_start * part_atlas_h))
    band_y1 = atlas_y0 + int(round(v_end   * part_atlas_h))
    band_atlas_h = max(1, band_y1 - band_y0)
    # Load source crop + scale to part's render pixel size for 1:1 sampling.
    sx, sy, sw, sh = (int(v) for v in src_wing_bbox)
    src_im = _PIL.open(src).convert("RGBA")
    crop = src_im.crop((sx, sy, sx + sw, sy + sh))
    if flip_h:
        crop = crop.transpose(_PIL.FLIP_LEFT_RIGHT)
    # Compute model part's render pixel size from camera projection.
    import math
    yaw   = float(getattr(p, "mesh_yaw",   0.4))
    pitch = float(getattr(p, "mesh_pitch", 0.25))
    dist  = float(getattr(p, "mesh_dist", None) or 3.5)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    cp_, sp_ = math.cos(pitch), math.sin(pitch)
    cam_pos = _np.array([dist * cp_ * sy_, dist * sp_, dist * cp_ * cy_],
                          dtype=_np.float32)
    look = -cam_pos / max(_np.linalg.norm(cam_pos), 1e-8)
    up_w = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
    right = _np.cross(look, up_w); right /= max(_np.linalg.norm(right), 1e-8)
    up = _np.cross(right, look)
    fov = math.radians(38.0); f = 1.0 / math.tan(fov * 0.5)
    pverts = mesh.verts[part_mask]
    rel = pverts - cam_pos
    z = rel @ look
    x = rel @ right; y = rel @ up
    inv_z = 1.0 / _np.where(_np.abs(z) > 1e-4, z, 1e-4)
    ndc_x = x * f * inv_z; ndc_y = y * f * inv_z
    px = (ndc_x + 1.0) * 0.5 * p.w
    py = (1.0 - (ndc_y + 1.0) * 0.5) * p.h
    render_w = max(1, int(px.max() - px.min()))
    render_h = max(1, int(py.max() - py.min()))
    # Scale source crop to part's render pixel size so 1 source pixel = 1 render pixel.
    scaled = crop.resize((render_w, render_h), _PIL.LANCZOS)
    scaled_arr = _np.array(scaled, dtype=_np.uint8)
    # Take vertical band from the scaled crop.
    band_top    = int(round(v_start * render_h))
    band_bottom = int(round(v_end   * render_h))
    band_pixels = scaled_arr[band_top:band_bottom]
    if band_pixels.shape[0] == 0:
        return {"transferred": 0, "reason": "band rounded to zero rows"}
    # Resample this band to fit (band_atlas_h, part_atlas_w).
    band_im = _PIL.fromarray(band_pixels)
    band_im = band_im.resize((part_atlas_w, band_atlas_h), _PIL.LANCZOS)
    band_to_write = _np.array(band_im, dtype=_np.uint8)
    # Open or create albedo atlas.
    cur_path = getattr(p, "pbr_albedo_map", "")
    if cur_path and _PIL.open(cur_path).size == (size, size):
        atlas_im = _PIL.open(cur_path).convert("RGBA")
        atlas = _np.array(atlas_im, dtype=_np.uint8)
    else:
        # Initialise a FRESH atlas with the placement's color_fill so any
        # UV regions we don't paint still render as the bare-model color
        # (instead of black). Incremental band transfers then over-write
        # only the targeted regions.
        fill = getattr(p, "color_fill", None) or (122, 88, 244, 255)
        atlas = _np.zeros((size, size, 4), dtype=_np.uint8)
        atlas[..., 0] = int(fill[0])
        atlas[..., 1] = int(fill[1])
        atlas[..., 2] = int(fill[2])
        atlas[..., 3] = 255
    # Write band into atlas at (atlas_x0..atlas_x1, band_y0..band_y1).
    atlas_y0_clip = max(0, band_y0); atlas_y1_clip = min(size, band_y1)
    atlas_x0_clip = max(0, atlas_x0); atlas_x1_clip = min(size, atlas_x1)
    write_h = atlas_y1_clip - atlas_y0_clip
    write_w = atlas_x1_clip - atlas_x0_clip
    if write_h > 0 and write_w > 0:
        write_band = band_to_write[:write_h, :write_w]
        atlas[atlas_y0_clip:atlas_y0_clip + write_h,
              atlas_x0_clip:atlas_x0_clip + write_w, :3] = write_band[..., :3]
        atlas[atlas_y0_clip:atlas_y0_clip + write_h,
              atlas_x0_clip:atlas_x0_clip + write_w,  3] = 255
    # Save.
    _tex.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    safe = "bm_band_atlas"
    out_path = _tex.LIBRARY_DIR / f"{safe}.png"
    _PIL.fromarray(atlas).save(out_path)
    p.pbr_albedo_map = str(out_path)
    # Flush all caches so the next render reads the new atlas pixels.
    try:
        if hasattr(_pbr, "_TEX_CACHE"): _pbr._TEX_CACHE.clear()
    except Exception: pass
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache", "_texture_cache"):
        c = getattr(designer, ca, None)
        if c: c.clear()
    return {"transferred_atlas_pixels": int(write_h * write_w),
            "part":              part,
            "v_band":            [v_start, v_end],
            "atlas_band_rect":   [atlas_x0_clip, atlas_y0_clip, write_w, write_h],
            "part_render_size":  [render_w, render_h],
            "scaled_band_size":  [band_to_write.shape[1], band_to_write.shape[0]],
            "atlas_path":        str(out_path)}


@register_tool(
    name="texture.flush_caches",
    description="Clear every in-memory texture/mesh cache so the next "
                "render re-reads files from disk. Use after overwriting a "
                "texture in the library: without this, pbr._TEX_CACHE "
                "keeps the stale pixels even though the file changed.",
    input_schema={"type": "object", "properties": {}},
)
def texture_flush_caches(session) -> dict:
    from elysium.render import pbr as _pbr
    n_tex = len(getattr(_pbr, "_TEX_CACHE", {}))
    if hasattr(_pbr, "_TEX_CACHE"):
        _pbr._TEX_CACHE.clear()
    designer = session.designer
    cleared = []
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache",
                "_texture_cache", "_paint_mask_files",
                "_paint_mask_png_cache"):
        c = getattr(designer, ca, None)
        if c:
            cleared.append((ca, len(c)))
            c.clear()
    return {"pbr_tex_cache_cleared": int(n_tex),
            "designer_caches_cleared": cleared}


@register_tool(
    name="texture.delete_from_library",
    description="Delete a texture from the user's library. Pass the tile's "
                "filename stem (e.g. 'bm_wing'). The tile is unlinked from "
                "disk but any placement still referencing it will keep its "
                "current binding string: the next render will hit a missing "
                "file. Bind a different tile via material.set_texture / "
                "material.set_part_texture before deleting.",
    input_schema={"type": "object",
                   "properties": {"name": {"type": "string"}},
                   "required": ["name"]},
)
def texture_delete_from_library(session, name: str) -> dict:
    from elysium.render import texture as tex
    deleted = []
    for path in tex.list_library():
        if path.stem == name:
            path.unlink(missing_ok=True)
            deleted.append(str(path))
    return {"deleted": deleted}


@register_tool(
    name="texture.paint_mask",
    description="Paint a brush stroke onto a placement's PaintMask.",
    input_schema={"type": "object",
                   "properties": {"id":      {"type": "string"},
                                   "from":    {"type": "array"},
                                   "to":      {"type": "array"},
                                   "radius":  {"type": "number"},
                                   "color":   {"type": "array"},
                                   "opacity": {"type": "number"},
                                   "hardness":{"type": "number"},
                                   "erase":   {"type": "boolean"}},
                   "required": ["id","from","to","radius","color"]},
)
def texture_paint_mask(session, id: str, **kwargs) -> dict:
    p = session.lookup(id)
    designer = session.designer
    mask = designer._get_paint_mask(p)
    fx, fy = kwargs["from"]; tx, ty = kwargs["to"]
    mask.stroke(fx, fy, tx, ty, kwargs["radius"], tuple(kwargs["color"]),
                opacity=kwargs.get("opacity", 1.0),
                hardness=kwargs.get("hardness", 0.5),
                erase=bool(kwargs.get("erase", False)))
    designer._brush_dirty.add(id_(p))
    return {"strokes": 1}


def id_(o): return id(o)
