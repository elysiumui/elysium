"""mesh.*: 3D import, camera, render."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="mesh.import",
    description="Import a .obj / .gltf / .glb and add it as a Mesh3D "
                "placement.",
    input_schema={"type": "object",
                   "properties": {"path": {"type": "string"},
                                   "x":{"type":"number"},"y":{"type":"number"},
                                   "w":{"type":"number"},"h":{"type":"number"}},
                   "required": ["path"]},
)
def mesh_import(session, path: str, x: float = 100, y: float = 100,
                 w: float = 300, h: float = 300) -> dict:
    designer = session.designer
    P = session.designer_models.Placement
    p = P(kind="Mesh3D", x=x, y=y, w=w, h=h,
          name=designer._assign_name("Mesh3D"))
    p.mesh_kind = f"file:{path}"
    designer.placements.append(p)
    return {"placement_id": session.id_for(p)}


@register_tool(
    name="mesh.import_3d",
    description="Import a 3D model file (.3ds / .obj / .gltf / .glb / .fbx): "
                "the same one-action flow as File → Import 3D Model… in the "
                "Designer. Parses the file, registers it in the mesh library "
                "under its filename stem, and adds a Mesh3D placement centered "
                "on the canvas. Returns the new placement's id, the mesh "
                "library name, and the triangle / vertex counts so the caller "
                "can confirm the import succeeded.",
    input_schema={"type": "object",
                   "properties": {"path": {"type": "string"},
                                   "w": {"type": "number"},
                                   "h": {"type": "number"}},
                   "required": ["path"]},
)
def mesh_import_3d(session, path: str,
                    w: float = 400.0, h: float = 400.0) -> dict:
    """One-shot equivalent of the GUI's File → Import 3D Model… menu item.
    Centres the placement in the App Window doc and picks a sensible camera
    distance for an imported (unit-normalized) mesh."""
    from pathlib import Path as _Path
    from elysium.render import pbr as _pbr
    designer = session.designer
    src = _Path(path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"3D model not found: {src}")
    mesh = _pbr.import_mesh_from_file(src)
    name = src.stem
    # Store the placement with `mesh_kind = "file:<abs path>"` so the
    # render path loads straight from disk every time and doesn't
    # depend on the in-memory MESH_LIBRARY (which gets wiped whenever
    # elysium.render.pbr is hot-reloaded: that used to silently
    # downgrade imported butterflies to a Sphere fallback).
    abs_path = str(src.resolve())
    mesh_kind = f"file:{abs_path}"
    # Also cache the parsed mesh in MESH_LIBRARY under the file stem +
    # the file: key, so synchronous lookups during the same session
    # skip the re-parse cost.
    _pbr.MESH_LIBRARY[name] = lambda m=mesh: m
    _pbr.MESH_LIBRARY[mesh_kind] = lambda m=mesh: m
    P = session.designer_models.Placement
    win = designer.window_doc
    placement = P(
        kind="Mesh3D",
        x=(win.w - w) / 2.0, y=(win.h - h) / 2.0,
        w=float(w), h=float(h),
        name=designer._assign_name(name) if hasattr(designer, "_assign_name") else name,
        props={},
        mesh_kind=mesh_kind,
    )
    # Imported meshes are normalized to a unit cube; pull the camera in.
    placement.mesh_dist = 1.2
    designer.placements.append(placement)
    designer.menu_status = (f"Imported {name} ({len(mesh.faces)} tris, "
                             f"{len(mesh.verts)} verts)")
    return {"placement_id": session.id_for(placement),
            "mesh_name": name,
            "tris": int(len(mesh.faces)),
            "verts": int(len(mesh.verts)),
            "parts": list(mesh.part_names) if mesh.part_names else None}


@register_tool(
    name="mesh.register_from_file",
    description="Load a .3ds / .obj / .gltf / .glb / .fbx and register it "
                "in the MESH_LIBRARY under `name` *without* creating a new "
                "placement. Use this on launch when a saved .esk references "
                "a named mesh (e.g. 'butterfly') that the fresh process has "
                "not yet loaded: calling this rebinds the name so the "
                "existing Mesh3D placement starts rendering again.",
    input_schema={"type": "object",
                   "properties": {"path": {"type": "string"},
                                   "name": {"type": "string"}},
                   "required": ["path", "name"]},
)
def mesh_register_from_file(session, path: str, name: str) -> dict:
    from pathlib import Path as _Path
    from elysium.render import pbr as _pbr
    src = _Path(path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"3D model not found: {src}")
    mesh = _pbr.import_mesh_from_file(src)
    _pbr.MESH_LIBRARY[name] = (lambda m=mesh: m)
    # Flush mesh caches so the renderer picks up the new binding next frame.
    designer = session.designer
    for cache_attr in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache"):
        c = getattr(designer, cache_attr, None)
        if c: c.clear()
    return {"name": name,
            "tris": int(len(mesh.faces)),
            "verts": int(len(mesh.verts)),
            "parts": list(mesh.part_names) if mesh.part_names else None}


@register_tool(
    name="mesh.uv_unwrap",
    description="Re-generate the UV coordinates of a Mesh3D's underlying "
                "mesh using a projection scheme. Modes:\n"
                "  - 'planar'      : flatten from a viewing axis (yaw,pitch); "
                "                    front-facing surface gets a [0,1]² mapping.\n"
                "  - 'planar_xy'   : project along +Z onto XY plane.\n"
                "  - 'cylindrical' : wrap around the Y axis (u=angle, v=height).\n"
                "  - 'spherical'   : wrap around origin (u=longitude, v=latitude).\n"
                "Mutates the cached mesh object's `vert_uvs` in place. Does NOT "
                "alter vertices, faces, normals, rigging, or part ids: the "
                "model's geometry stays identical. Returns the new per-part UV "
                "bbox so callers can re-render or rebuild atlases against it.",
    input_schema={
        "type": "object",
        "properties": {
            "id":    {"type": "string"},
            "mode":  {"type": "string"},
            "yaw":   {"type": "number"},
            "pitch": {"type": "number"},
        },
        "required": ["id", "mode"],
    },
)
def mesh_uv_unwrap(session, id: str, mode: str,
                    yaw: float = 0.0, pitch: float = 0.0) -> dict:
    """Re-compute mesh UVs from a projection. Geometry untouched."""
    import math
    import numpy as _np
    from elysium.render import pbr as _pbr
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"mesh.uv_unwrap: kind={p.kind!r} (need Mesh3D)")
    # Pull the mesh the same way the renderer does.
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
    v = mesh.verts.astype(_np.float32)
    n = v.shape[0]
    mode = mode.lower()
    if mode in ("planar", "planar_xy", "camera"):
        if mode == "planar_xy":
            ax_u = _np.array([1.0, 0.0, 0.0], dtype=_np.float32)
            ax_v = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
        else:
            cy, sy = math.cos(yaw), math.sin(yaw)
            cp, sp = math.cos(pitch), math.sin(pitch)
            # Camera-look direction.
            look = _np.array([-cp * sy, -sp, -cp * cy], dtype=_np.float32)
            up   = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
            right = _np.cross(look, up); right /= max(_np.linalg.norm(right), 1e-8)
            up_real = _np.cross(right, look)
            ax_u, ax_v = right, up_real
        u = v @ ax_u
        w = v @ ax_v
        u = (u - u.min()) / max(u.max() - u.min(), 1e-6)
        w = (w - w.min()) / max(w.max() - w.min(), 1e-6)
        uvs = _np.stack([u, w], axis=-1)
    elif mode == "cylindrical":
        # u = atan2(z, x) / 2π; v = (y - ymin) / (ymax - ymin)
        u = (_np.arctan2(v[:, 2], v[:, 0]) + math.pi) / (2.0 * math.pi)
        h = v[:, 1]
        w = (h - h.min()) / max(h.max() - h.min(), 1e-6)
        uvs = _np.stack([u, w], axis=-1)
    elif mode == "spherical":
        L = _np.linalg.norm(v, axis=-1) + 1e-8
        u = (_np.arctan2(v[:, 2], v[:, 0]) + math.pi) / (2.0 * math.pi)
        w = _np.arccos(_np.clip(v[:, 1] / L, -1.0, 1.0)) / math.pi
        uvs = _np.stack([u, w], axis=-1)
    else:
        raise ValueError(f"unknown uv_unwrap mode: {mode!r}")
    mesh.vert_uvs = uvs.astype(_np.float32)
    # Rebind in MESH_LIBRARY so subsequent renders see the new UVs.
    if not p.mesh_kind.startswith("file:"):
        _pbr.MESH_LIBRARY[p.mesh_kind] = (lambda m=mesh: m)
    # Flush mesh caches so the next paint re-renders with the new UVs.
    designer = session.designer
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache"):
        c = getattr(designer, ca, None)
        if c: c.clear()
    # Report new per-part UV bbox.
    parts_out = []
    if mesh.part_names and mesh.vert_part_ids is not None:
        for pid, name in enumerate(mesh.part_names):
            m = (mesh.vert_part_ids == pid)
            if not m.any(): continue
            puv = uvs[m]
            parts_out.append({
                "name": name,
                "umin": float(puv[:, 0].min()), "vmin": float(puv[:, 1].min()),
                "umax": float(puv[:, 0].max()), "vmax": float(puv[:, 1].max()),
            })
    return {"mode": mode, "yaw": yaw, "pitch": pitch,
            "verts": int(n), "parts": parts_out}


@register_tool(
    name="material.project_photo",
    description="'Projection painting': bake a photo onto the mesh from a "
                "camera angle (yaw, pitch, dist), then save the result as a "
                "UV-aligned albedo atlas and bind it. For each mesh vertex, "
                "the camera maps it to a screen-space point in the photo; "
                "that pixel becomes the color at the vertex's UV. Triangle "
                "interior pixels in the atlas are filled by rasterising the "
                "UV triangles with bilinear-sampled photo colors. Geometry "
                "untouched. The current camera angle on the placement "
                "(mesh_yaw/mesh_pitch) is used by default.",
    input_schema={
        "type": "object",
        "properties": {
            "id":    {"type": "string"},
            "src":   {"type": "string"},
            "name":  {"type": "string"},
            "yaw":   {"type": "number"},
            "pitch": {"type": "number"},
            "dist":  {"type": "number"},
            "size":  {"type": "integer"},
            "fit":   {"type": "string"},     # 'tight' | 'opaque' | 'full'
        },
        "required": ["id", "src", "name"],
    },
)
def material_project_photo(session, id: str, src: str, name: str,
                            yaw: float | None = None,
                            pitch: float | None = None,
                            dist: float | None = None,
                            size: int = 2048,
                            fit: str = "opaque") -> dict:
    """Per-PIXEL projection painting (Substance/Mari-style).

    For every pixel in the UV atlas we:
      1. Find which mesh triangle owns that atlas pixel.
      2. Recover the 3D position on that triangle via barycentric coords
         of the UV-space position inside the UV-space triangle.
      3. Project that 3D point through a virtual camera to a photo pixel.
      4. Bilinear-sample the photo at that pixel and write it.

    Crucially this is NOT per-vertex color interpolation: each atlas
    pixel reads a real photo pixel through the geometry, so when the
    placement is later rendered from the same camera angle, the on-
    screen result matches the photo at pixel resolution (limited only
    by the atlas dimension)."""
    import math
    import numpy as _np
    from PIL import Image as _PIL
    from elysium.render import pbr as _pbr
    from elysium.render import texture as _tex
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"material.project_photo: kind={p.kind!r} (need Mesh3D)")
    yaw   = float(yaw   if yaw   is not None else getattr(p, "mesh_yaw",   0.4))
    pitch = float(pitch if pitch is not None else getattr(p, "mesh_pitch", 0.25))
    dist  = float(dist  if dist  is not None else
                   getattr(p, "mesh_dist", None) or 3.5)
    photo = _np.array(_PIL.open(src).convert("RGBA"), dtype=_np.uint8)
    pH, pW = photo.shape[:2]
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    cp_, sp_ = math.cos(pitch), math.sin(pitch)
    cam_pos = _np.array([dist * cp_ * sy_, dist * sp_, dist * cp_ * cy_],
                          dtype=_np.float32)
    look = -cam_pos / max(_np.linalg.norm(cam_pos), 1e-8)
    up_w = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
    right = _np.cross(look, up_w); right /= max(_np.linalg.norm(right), 1e-8)
    up = _np.cross(right, look)
    fov = math.radians(38.0)
    f = 1.0 / math.tan(fov * 0.5)
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
    if mesh.vert_uvs is None:
        raise ValueError("mesh has no UVs: call mesh.uv_unwrap first")
    verts = mesh.verts.astype(_np.float32)
    uvs   = mesh.vert_uvs.astype(_np.float32)
    faces = mesh.faces
    # Photo-pixel coords of the "fit" frame: a [0,1]² rectangle that the
    # camera's NDC maps into. Opaque fit shrinks to the photo's opaque
    # bbox; full uses the whole image; tight expands isotropically.
    op = photo[..., 3] > 200
    if op.any():
        ys_, xs_ = _np.where(op)
        ox0, oy0 = float(xs_.min()), float(ys_.min())
        ox1, oy1 = float(xs_.max() + 1), float(ys_.max() + 1)
    else:
        ox0, oy0, ox1, oy1 = 0.0, 0.0, float(pW), float(pH)
    if fit == "full":
        fx0, fy0, fx1, fy1 = 0.0, 0.0, float(pW), float(pH)
    else:                          # 'opaque' (default) / 'tight'
        fx0, fy0, fx1, fy1 = ox0, oy0, ox1, oy1
    atlas  = _np.zeros((size, size, 4), dtype=_np.uint8)
    # Optional second buffer to track best-projection per atlas pixel
    # via "smallest cos(angle) to look direction": front-facing fragments
    # win over edge-on ones to suppress projection stretching.
    best_dot = _np.full((size, size), -2.0, dtype=_np.float32)
    inv_size = 1.0 / float(size - 1)
    # Pre-compute face normals (in world space, identity transform).
    face_v0 = verts[faces[:, 0]]
    face_v1 = verts[faces[:, 1]]
    face_v2 = verts[faces[:, 2]]
    e1 = face_v1 - face_v0
    e2 = face_v2 - face_v0
    face_n = _np.cross(e1, e2)
    fn_len = _np.linalg.norm(face_n, axis=-1, keepdims=True)
    face_n = face_n / _np.maximum(fn_len, 1e-8)
    for fi in range(len(faces)):
        tri = faces[fi]
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]
        # UV triangle in atlas pixel space (V-flipped for 3DS convention).
        up0 = _np.array([uv0[0] * (size - 1), (1.0 - uv0[1]) * (size - 1)], dtype=_np.float32)
        up1 = _np.array([uv1[0] * (size - 1), (1.0 - uv1[1]) * (size - 1)], dtype=_np.float32)
        up2 = _np.array([uv2[0] * (size - 1), (1.0 - uv2[1]) * (size - 1)], dtype=_np.float32)
        x0i = max(0, int(min(up0[0], up1[0], up2[0])))
        x1i = min(size - 1, int(max(up0[0], up1[0], up2[0])) + 1)
        y0i = max(0, int(min(up0[1], up1[1], up2[1])))
        y1i = min(size - 1, int(max(up0[1], up1[1], up2[1])) + 1)
        if x1i <= x0i or y1i <= y0i: continue
        ys2, xs2 = _np.mgrid[y0i:y1i, x0i:x1i].astype(_np.float32)
        denom = (up1[1] - up2[1]) * (up0[0] - up2[0]) + (up2[0] - up1[0]) * (up0[1] - up2[1])
        if abs(denom) < 1e-6: continue
        w0 = ((up1[1] - up2[1]) * (xs2 - up2[0]) + (up2[0] - up1[0]) * (ys2 - up2[1])) / denom
        w1 = ((up2[1] - up0[1]) * (xs2 - up2[0]) + (up0[0] - up2[0]) * (ys2 - up2[1])) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any(): continue
        # 3D position per atlas-pixel from barycentric weights.
        P = (w0[..., None] * v0[None, None, :]
              + w1[..., None] * v1[None, None, :]
              + w2[..., None] * v2[None, None, :])
        # Project to camera plane.
        rel = P - cam_pos[None, None, :]
        z = (rel * look[None, None, :]).sum(axis=-1)
        x = (rel * right[None, None, :]).sum(axis=-1)
        y = (rel * up[None, None, :]).sum(axis=-1)
        in_front = z > 1e-4
        valid = inside & in_front
        if not valid.any(): continue
        inv_z = 1.0 / _np.where(_np.abs(z) > 1e-4, z, 1e-4)
        ndc_x = x * f * inv_z      # -1..1
        ndc_y = y * f * inv_z
        # Map NDC [-1,1] → photo pixel coords within the fit-frame.
        u_norm = (ndc_x + 1.0) * 0.5
        v_norm = (ndc_y + 1.0) * 0.5
        u_norm = _np.clip(u_norm, 0.0, 1.0)
        v_norm = _np.clip(v_norm, 0.0, 1.0)
        photo_x = fx0 + u_norm * (fx1 - fx0)
        photo_y = fy1 - v_norm * (fy1 - fy0)   # flip y: NDC up vs image down
        # Bilinear sample.
        px0 = _np.clip(_np.floor(photo_x).astype(_np.int32), 0, pW - 1)
        px1c = _np.clip(px0 + 1, 0, pW - 1)
        py0 = _np.clip(_np.floor(photo_y).astype(_np.int32), 0, pH - 1)
        py1c = _np.clip(py0 + 1, 0, pH - 1)
        fx = (photo_x - px0).astype(_np.float32)[..., None]
        fy = (photo_y - py0).astype(_np.float32)[..., None]
        c00 = photo[py0, px0,  :].astype(_np.float32)
        c10 = photo[py0, px1c, :].astype(_np.float32)
        c01 = photo[py1c, px0, :].astype(_np.float32)
        c11 = photo[py1c, px1c,:].astype(_np.float32)
        c0_ = c00 * (1 - fx) + c10 * fx
        c1_ = c01 * (1 - fx) + c11 * fx
        sampled = (c0_ * (1 - fy) + c1_ * fy).astype(_np.uint8)
        # Depth/normal test: prefer the most front-facing projection.
        dot = abs(float(face_n[fi] @ look))    # 1 = face-on; 0 = edge-on
        sub_best = best_dot[y0i:y1i, x0i:x1i]
        sub_atlas = atlas[y0i:y1i, x0i:x1i]
        write = valid & (dot > sub_best)
        if not write.any(): continue
        sub_atlas[write, :3] = sampled[write, :3]
        sub_atlas[write,  3] = 255
        sub_best[write] = dot
        atlas[y0i:y1i, x0i:x1i] = sub_atlas
        best_dot[y0i:y1i, x0i:x1i] = sub_best
    _tex.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    out_path = _tex.LIBRARY_DIR / f"{safe}.png"
    _PIL.fromarray(atlas).save(out_path)
    p.pbr_albedo_map = str(out_path)
    designer = session.designer
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache", "_texture_cache"):
        c = getattr(designer, ca, None)
        if c: c.clear()
    return {"path": str(out_path), "size": [size, size],
            "yaw": yaw, "pitch": pitch, "dist": dist,
            "faces_baked": int(len(faces)),
            "fit": fit, "frame": [fx0, fy0, fx1, fy1]}


@register_tool(
    name="material.project_per_part",
    description="Per-part proportional projection painting. Aligns each "
                "named mesh part to a caller-supplied photo bbox, then for "
                "every atlas pixel inside that part: finds its 3D position "
                "via barycentric coords, normalises that position within "
                "the part's 3D screen-space bbox (x,y from a given camera "
                "view), and samples the photo at the equivalent normalized "
                "position inside the part's photo bbox. Result: the top 1% "
                "of the mesh's left wing samples the top 1% of the photo's "
                "left wing, and so on: every section of every wing/body "
                "lines up proportionally to its counterpart in the reference.\n\n"
                "`part_photo_bboxes` maps mesh part name -> {x,y,w,h} in "
                "source-image pixel coords. Defaults supplied for parts "
                "that look like wing/body using a simple symmetric split "
                "of the photo's opaque bbox (left half = first wing-named "
                "part, right half = second wing-named part, central "
                "vertical strip = body-named part). When the photo's wing "
                "is mirrored relative to the mesh's wing (head-on view "
                "swap), pass `flip_h_for=[part_names]` to mirror that "
                "part's photo sampling horizontally. Auto-binds the baked "
                "atlas as the placement's albedo. Geometry untouched.",
    input_schema={
        "type": "object",
        "properties": {
            "id":               {"type": "string"},
            "src":              {"type": "string"},
            "name":             {"type": "string"},
            "yaw":              {"type": "number"},
            "pitch":            {"type": "number"},
            "size":             {"type": "integer"},
            "part_photo_bboxes": {"type": "object"},
            "flip_h_for":       {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "src", "name"],
    },
)
def material_project_per_part(session, id: str, src: str, name: str,
                                yaw: float = 0.0, pitch: float = 0.0,
                                size: int = 2048,
                                part_photo_bboxes: dict | None = None,
                                flip_h_for: list | None = None) -> dict:
    """Wing-to-wing proportional pixel projection."""
    import math
    import numpy as _np
    from PIL import Image as _PIL
    from elysium.render import pbr as _pbr
    from elysium.render import texture as _tex
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"project_per_part: kind={p.kind!r} (need Mesh3D)")
    photo = _np.array(_PIL.open(src).convert("RGBA"), dtype=_np.uint8)
    pH, pW = photo.shape[:2]
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
    if mesh.vert_uvs is None:
        raise ValueError("mesh has no UVs: call mesh.uv_unwrap first")
    if mesh.part_names is None or mesh.vert_part_ids is None:
        raise ValueError("mesh has no part_names/vert_part_ids: project_per_part needs a rigged mesh")
    # Camera basis (so x/y projection picks 'screen-space' axes).
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    cp_, sp_ = math.cos(pitch), math.sin(pitch)
    look = _np.array([-cp_ * sy_, -sp_, -cp_ * cy_], dtype=_np.float32)
    up_w = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)
    right = _np.cross(look, up_w); right /= max(_np.linalg.norm(right), 1e-8)
    up = _np.cross(right, look)
    verts = mesh.verts.astype(_np.float32)
    uvs   = mesh.vert_uvs.astype(_np.float32)
    faces = mesh.faces
    # Project vertices to camera-aligned (x_screen, y_screen).
    # For pixel position WITHIN a part bbox we only need 2D.
    v2d = _np.stack([verts @ right, verts @ up], axis=-1)
    # Auto-default photo bboxes from opaque-bbox split if none supplied.
    if part_photo_bboxes is None:
        part_photo_bboxes = {}
    if not part_photo_bboxes:
        op = photo[..., 3] > 200
        ys, xs = _np.where(op)
        if len(xs):
            ox0, oy0 = int(xs.min()), int(ys.min())
            ox1, oy1 = int(xs.max()), int(ys.max())
            mid_x = (ox0 + ox1) // 2
            wing_names = [n for n in mesh.part_names if "wing" in n.lower()]
            if len(wing_names) >= 2:
                part_photo_bboxes[wing_names[0]] = {
                    "x": ox0, "y": oy0, "w": mid_x - ox0, "h": oy1 - oy0}
                part_photo_bboxes[wing_names[1]] = {
                    "x": mid_x, "y": oy0, "w": ox1 - mid_x, "h": oy1 - oy0}
            for n in mesh.part_names:
                if "body" in n.lower():
                    cx_band = max(20, (ox1 - ox0) // 16)
                    part_photo_bboxes[n] = {
                        "x": mid_x - cx_band // 2, "y": oy0,
                        "w": cx_band, "h": oy1 - oy0}
    flip_h_for_set = set(flip_h_for or [])
    # Precompute per-part screen-space bbox.
    part_bbox_2d: dict = {}
    for pid, pname in enumerate(mesh.part_names):
        mask = (mesh.vert_part_ids == pid)
        if not mask.any(): continue
        pv = v2d[mask]
        part_bbox_2d[pid] = (float(pv[:, 0].min()), float(pv[:, 0].max()),
                              float(pv[:, 1].min()), float(pv[:, 1].max()),
                              pname)
    atlas = _np.zeros((size, size, 4), dtype=_np.uint8)
    written = _np.zeros((size, size), dtype=bool)
    # Per-face: assume all verts share a part id (true for the .3ds loader).
    for fi in range(len(faces)):
        tri = faces[fi]
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        pid = int(mesh.vert_part_ids[i0])
        if pid not in part_bbox_2d: continue
        pxmin, pxmax, pymin, pymax, pname = part_bbox_2d[pid]
        pbox = part_photo_bboxes.get(pname)
        if not pbox: continue
        v3d_x = v2d[[i0, i1, i2], 0]
        v3d_y = v2d[[i0, i1, i2], 1]
        # Rasterise UV triangle.
        uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]
        up0 = _np.array([uv0[0] * (size - 1), (1.0 - uv0[1]) * (size - 1)], dtype=_np.float32)
        up1 = _np.array([uv1[0] * (size - 1), (1.0 - uv1[1]) * (size - 1)], dtype=_np.float32)
        up2 = _np.array([uv2[0] * (size - 1), (1.0 - uv2[1]) * (size - 1)], dtype=_np.float32)
        x0i = max(0, int(min(up0[0], up1[0], up2[0])))
        x1i = min(size - 1, int(max(up0[0], up1[0], up2[0])) + 1)
        y0i = max(0, int(min(up0[1], up1[1], up2[1])))
        y1i = min(size - 1, int(max(up0[1], up1[1], up2[1])) + 1)
        if x1i <= x0i or y1i <= y0i: continue
        ys2, xs2 = _np.mgrid[y0i:y1i, x0i:x1i].astype(_np.float32)
        denom = (up1[1] - up2[1]) * (up0[0] - up2[0]) + (up2[0] - up1[0]) * (up0[1] - up2[1])
        if abs(denom) < 1e-6: continue
        w0 = ((up1[1] - up2[1]) * (xs2 - up2[0]) + (up2[0] - up1[0]) * (ys2 - up2[1])) / denom
        w1 = ((up2[1] - up0[1]) * (xs2 - up2[0]) + (up0[0] - up2[0]) * (ys2 - up2[1])) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any(): continue
        # 3D screen-space x/y per atlas-pixel.
        Px = w0 * v3d_x[0] + w1 * v3d_x[1] + w2 * v3d_x[2]
        Py = w0 * v3d_y[0] + w1 * v3d_y[1] + w2 * v3d_y[2]
        # Normalized position within the part's screen-space bbox.
        dx = pxmax - pxmin; dy = pymax - pymin
        if dx < 1e-6 or dy < 1e-6: continue
        vx = (Px - pxmin) / dx
        vy = (Py - pymin) / dy
        if pname in flip_h_for_set:
            vx = 1.0 - vx
        vx = _np.clip(vx, 0.0, 1.0); vy = _np.clip(vy, 0.0, 1.0)
        # Map to photo pixel coords. Photo Y is inverted (top of part = top of
        # wing visually = photo y near pbox.y, which is the top of the photo bbox).
        photo_x = pbox["x"] + vx * pbox["w"]
        # Vertex-space y increases UP; photo y increases DOWN. v=1 (top of part)
        # should map to the top edge of the photo bbox.
        photo_y = pbox["y"] + (1.0 - vy) * pbox["h"]
        # Bilinear sample.
        px0 = _np.clip(_np.floor(photo_x).astype(_np.int32), 0, pW - 1)
        px1c = _np.clip(px0 + 1, 0, pW - 1)
        py0 = _np.clip(_np.floor(photo_y).astype(_np.int32), 0, pH - 1)
        py1c = _np.clip(py0 + 1, 0, pH - 1)
        fx = (photo_x - px0).astype(_np.float32)[..., None]
        fy = (photo_y - py0).astype(_np.float32)[..., None]
        c00 = photo[py0, px0,  :].astype(_np.float32)
        c10 = photo[py0, px1c, :].astype(_np.float32)
        c01 = photo[py1c, px0, :].astype(_np.float32)
        c11 = photo[py1c, px1c,:].astype(_np.float32)
        c0_ = c00 * (1 - fx) + c10 * fx
        c1_ = c01 * (1 - fx) + c11 * fx
        sampled = (c0_ * (1 - fy) + c1_ * fy).astype(_np.uint8)
        sub_atlas = atlas[y0i:y1i, x0i:x1i]
        sub_written = written[y0i:y1i, x0i:x1i]
        write = inside & (~sub_written)
        if not write.any(): continue
        sub_atlas[write, :3] = sampled[write, :3]
        sub_atlas[write,  3] = 255
        sub_written[write] = True
        atlas[y0i:y1i, x0i:x1i] = sub_atlas
        written[y0i:y1i, x0i:x1i] = sub_written
    _tex.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    out_path = _tex.LIBRARY_DIR / f"{safe}.png"
    _PIL.fromarray(atlas).save(out_path)
    p.pbr_albedo_map = str(out_path)
    designer = session.designer
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache", "_texture_cache"):
        c = getattr(designer, ca, None)
        if c: c.clear()
    return {"path": str(out_path), "size": [size, size],
            "yaw": yaw, "pitch": pitch,
            "parts": {n: part_photo_bboxes.get(n) for n in mesh.part_names},
            "faces_baked": int(len(faces))}


@register_tool(
    name="mesh.read_render_bbox",
    description="Return the tight bbox (in placement-bbox local pixels) "
                "of where the rendered Mesh3D actually occupies space: "
                "i.e. the alpha-bbox of the cached mesh PNG, scaled into "
                "the placement bbox. Lets a caller stamp paint exactly "
                "onto the visible mesh region (e.g. the butterfly's "
                "wings + body) instead of guessing in empty bbox space.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ, undoable=False,
)
def mesh_read_render_bbox(session, id: str) -> dict:
    """Find where the rendered mesh lives inside the placement bbox.

    Strategy: grab the most recent cached PNG bytes (or trigger a fresh
    render and wait briefly), decode, find the alpha-bbox, and scale
    into placement-local px coords.
    """
    from PIL import Image as _PIL
    import io, time
    import numpy as _np
    designer = session.designer
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"mesh.read_render_bbox only supports Mesh3D, got {p.kind!r}")
    # Try to pull bytes from the byte cache the live renderer uses.
    cache = getattr(designer, "_mesh_bytes_cache", {}) or {}
    blob = None
    img_w = img_h = None
    # Find any cached blob keyed for this placement's mesh kind.
    for k, v in cache.items():
        if not v: continue
        # k tuple starts with mesh_kind; v is (bytes, w, h)
        if k[0] == p.mesh_kind:
            blob, img_w, img_h = v
            break
    if blob is None:
        # Force a synchronous-ish render by calling _mesh_render_bytes
        # and polling briefly.
        designer._mesh_render_bytes(p)
        for _ in range(40):
            time.sleep(0.05)
            for k, v in (cache or {}).items():
                if v and k[0] == p.mesh_kind:
                    blob, img_w, img_h = v; break
            if blob is not None: break
    if blob is None:
        return {"render_bbox": None,
                "reason": "no mesh bytes in cache yet (try again after a render)"}
    arr = _np.frombuffer(blob, dtype=_np.uint8).reshape(img_h, img_w, 4)
    a = arr[..., 3]
    ys, xs = _np.where(a > 8)
    if len(xs) == 0:
        return {"render_bbox": None, "reason": "mesh render is fully transparent"}
    img_x0, img_x1 = int(xs.min()), int(xs.max())
    img_y0, img_y1 = int(ys.min()), int(ys.max())
    # Scale the mesh-image bbox into placement-bbox local pixel coords.
    sx = p.w / float(img_w)
    sy = p.h / float(img_h)
    bx0 = img_x0 * sx
    by0 = img_y0 * sy
    bx1 = (img_x1 + 1) * sx
    by1 = (img_y1 + 1) * sy
    return {"render_bbox": {"xmin": float(bx0), "ymin": float(by0),
                              "xmax": float(bx1), "ymax": float(by1),
                              "w": float(bx1 - bx0), "h": float(by1 - by0),
                              "cx": float((bx0 + bx1) / 2.0),
                              "cy": float((by0 + by1) / 2.0)},
            "image_size": [int(img_w), int(img_h)],
            "placement_size": [float(p.w), float(p.h)],
            "image_bbox":   {"xmin": img_x0, "ymin": img_y0,
                              "xmax": img_x1, "ymax": img_y1}}


@register_tool(
    name="mesh.read_part_render_bbox",
    description="Return the screen-pixel bbox of EACH named sub-mesh part "
                "(Wing_Left, Wing_Right, Body, …) inside the placement's "
                "rendered output. Projects every vertex of every part "
                "through the placement's current camera (mesh_yaw / "
                "mesh_pitch / mesh_dist), maps NDC into the rendered "
                "image, then scales into placement-bbox local pixels. "
                "Lets a caller crop the reference photo to the EXACT "
                "pixel dimensions of a model's wing region before "
                "applying: the basis for pixel-perfect transfer.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ, undoable=False,
)
def mesh_read_part_render_bbox(session, id: str) -> dict:
    import math
    import numpy as _np
    from elysium.render import pbr as _pbr
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError(f"read_part_render_bbox: kind={p.kind!r} (need Mesh3D)")
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        mesh = _pbr.MESH_LIBRARY[p.mesh_kind]()
    if mesh.part_names is None or mesh.vert_part_ids is None:
        return {"parts": [], "reason": "mesh has no parts"}
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
    fov = math.radians(38.0)
    f = 1.0 / math.tan(fov * 0.5)
    verts = mesh.verts.astype(_np.float32)
    rel = verts - cam_pos
    z = rel @ look
    x = rel @ right
    y = rel @ up
    inv_z = 1.0 / _np.where(_np.abs(z) > 1e-4, z, 1e-4)
    ndc_x = x * f * inv_z
    ndc_y = y * f * inv_z
    # NDC → placement-local pixels.
    px = (ndc_x + 1.0) * 0.5 * p.w
    py = (1.0 - (ndc_y + 1.0) * 0.5) * p.h    # NDC y-up vs image y-down
    parts: list = []
    for pid, name in enumerate(mesh.part_names):
        mask = (mesh.vert_part_ids == pid)
        if not mask.any(): continue
        xs = px[mask]; ys = py[mask]
        parts.append({"name": name,
                        "xmin": float(xs.min()), "ymin": float(ys.min()),
                        "xmax": float(xs.max()), "ymax": float(ys.max()),
                        "w":    float(xs.max() - xs.min()),
                        "h":    float(ys.max() - ys.min()),
                        "cx":   float((xs.min() + xs.max()) / 2.0),
                        "cy":   float((ys.min() + ys.max()) / 2.0)})
    return {"parts": parts,
            "placement_size": [float(p.w), float(p.h)],
            "camera": {"yaw": yaw, "pitch": pitch, "dist": dist}}


@register_tool(
    name="mesh.read_parts",
    description="List the named sub-meshes inside a Mesh3D placement's "
                "imported model (e.g. for the butterfly .3ds: Wing_Right, "
                "Wing_Left, Body) along with their vertex counts. Returns "
                "an empty list for procedural meshes that weren't imported "
                "from a file.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def mesh_read_parts(session, id: str) -> dict:
    from elysium.render import pbr as _pbr
    p = session.lookup(id)
    if not getattr(p, "mesh_kind", None):
        return {"parts": []}
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        factory = _pbr.MESH_LIBRARY.get(p.mesh_kind)
        if not factory:
            return {"parts": []}
        mesh = factory()
    if not mesh.part_names:
        return {"parts": []}
    import numpy as _np
    out = []
    for pid, name in enumerate(mesh.part_names):
        n = int((mesh.vert_part_ids == pid).sum())
        out.append({"name": name, "id": pid, "verts": n})
    return {"parts": out}


@register_tool(
    name="mesh.read_uv_bbox",
    description="Report the UV bounding box (umin, vmin, umax, vmax) for "
                "each sub-mesh of a Mesh3D placement. UV coords are in "
                "[0,1] and indicate which region of an albedo texture a "
                "part samples: essential for picking a photo crop that "
                "lands on the correct anatomy at the right size.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def mesh_read_uv_bbox(session, id: str) -> dict:
    from elysium.render import pbr as _pbr
    import numpy as _np
    p = session.lookup(id)
    if not getattr(p, "mesh_kind", None):
        return {"parts": []}
    if p.mesh_kind.startswith("file:"):
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
    else:
        factory = _pbr.MESH_LIBRARY.get(p.mesh_kind)
        if not factory:
            return {"parts": []}
        mesh = factory()
    if mesh.vert_uvs is None or mesh.vert_part_ids is None or not mesh.part_names:
        return {"parts": []}
    out = []
    overall_u_min, overall_u_max = 1.0, 0.0
    overall_v_min, overall_v_max = 1.0, 0.0
    for pid, name in enumerate(mesh.part_names):
        mask = (mesh.vert_part_ids == pid)
        if not mask.any():
            continue
        uvs = mesh.vert_uvs[mask]
        u_min, u_max = float(uvs[:, 0].min()), float(uvs[:, 0].max())
        v_min, v_max = float(uvs[:, 1].min()), float(uvs[:, 1].max())
        out.append({"name": name,
                     "umin": u_min, "vmin": v_min,
                     "umax": u_max, "vmax": v_max,
                     "uvw":  u_max - u_min, "uvh":  v_max - v_min,
                     "aspect": ((u_max - u_min) / (v_max - v_min))
                                if v_max > v_min else 0.0})
        overall_u_min = min(overall_u_min, u_min)
        overall_u_max = max(overall_u_max, u_max)
        overall_v_min = min(overall_v_min, v_min)
        overall_v_max = max(overall_v_max, v_max)
    return {"parts": out,
            "overall": {"umin": overall_u_min, "vmin": overall_v_min,
                         "umax": overall_u_max, "vmax": overall_v_max}}


@register_tool(
    name="mesh.set_camera",
    description="Set yaw / pitch / distance for a Mesh3D placement.",
    input_schema={"type": "object",
                   "properties": {"id":{"type":"string"},
                                   "yaw":{"type":"number"},
                                   "pitch":{"type":"number"},
                                   "dist":{"type":"number"}},
                   "required": ["id"]},
)
def mesh_set_camera(session, id: str, yaw: float | None = None,
                     pitch: float | None = None,
                     dist: float | None = None) -> dict:
    p = session.lookup(id)
    if yaw   is not None: p.mesh_yaw   = float(yaw)
    if pitch is not None: p.mesh_pitch = float(pitch)
    if dist  is not None: p.mesh_dist  = float(dist)
    cache = getattr(session.designer, "_mesh_cache", None)
    if cache: cache.clear()
    return {"yaw": p.mesh_yaw, "pitch": p.mesh_pitch}


@register_tool(
    name="mesh.toggle_wireframe",
    description="Toggle wireframe rendering on a Mesh3D placement.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
)
def mesh_toggle_wireframe(session, id: str) -> dict:
    p = session.lookup(id)
    p.mesh_wireframe = not p.mesh_wireframe
    cache = getattr(session.designer, "_mesh_cache", None)
    if cache: cache.clear()
    return {"wireframe": p.mesh_wireframe}


@register_tool(
    name="mesh.render_final",
    description="Path-traced 'Render Final' for the selected mesh; saves "
                "to .elysium/renders/. Returns the absolute output path.",
    input_schema={"type": "object",
                   "properties": {"id":{"type":"string"},
                                   "samples":{"type":"integer"},
                                   "max_bounces":{"type":"integer"},
                                   "denoise":{"type":"boolean"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,        # writes to disk but not to the project
    undoable=False,
)
def mesh_render_final(session, id: str, samples: int = 12,
                       max_bounces: int = 3, denoise: bool = True) -> dict:
    designer = session.designer
    p = session.lookup(id)
    # Reuse the Designer's worker path so caching + studio resolution
    # behaves identically to clicking ● Render Final.
    designer.sel_kind, designer.sel_idx = "placement", designer.placements.index(p)
    designer._render_final_selected()
    return {"queued": True, "placement_id": id}


# ──────────────────────────────────────────────────────────────────────
#   ObjectMapper / PixelSelector: hybrid render-then-mask pipeline
#   (see user's design doc 2026-05-17). The CPU ray-tracer in
#   elysium.render.pbr already produces per-pixel face_idx; this layer
#   exposes that as on-demand binary masks + screen-space pixel lists
#   in CANVAS coordinates so the agent can lasso accurately.
# ──────────────────────────────────────────────────────────────────────

def _build_mesh_for_placement(p):
    """Materialise the same Mesh/MeshObject ``_mesh_render_bytes`` would
    build for this placement, including the per-part wing-flap rig and
    any face_mats assignment. Materials are left as the cheap default
    since the mapper only needs hits, not shading."""
    from elysium.render import pbr as _pbr
    if p.mesh_kind.startswith("file:"):
        from elysium.render.designer_preview import _flap_imported_wings
        mesh = _pbr.import_mesh_from_file(p.mesh_kind.split(":", 1)[1])
        mesh = _flap_imported_wings(mesh, getattr(p, "mesh_flap", 0.0))
    else:
        # MESH_LIBRARY keys are CamelCase ("Butterfly") but some saved
        # placements have lowercased mesh_kind ("butterfly"). The live
        # render path tolerates this via a cache hit; we look it up
        # case-insensitively so a fresh build doesn't KeyError.
        lib = _pbr.MESH_LIBRARY
        factory = lib.get(p.mesh_kind)
        if factory is None:
            for k, v in lib.items():
                if k.lower() == p.mesh_kind.lower():
                    factory = v; break
        if factory is None:
            raise KeyError(f"mesh_kind {p.mesh_kind!r} not in MESH_LIBRARY "
                            f"(have {list(lib.keys())})")
        mesh = factory()
        if (getattr(mesh, "part_names", None)
                and any("wing" in n.lower() for n in mesh.part_names)):
            from elysium.render.designer_preview import _flap_imported_wings
            mesh = _flap_imported_wings(mesh, getattr(p, "mesh_flap", 0.0))
    obj = _pbr.MeshObject(mesh=mesh, materials=[_pbr.Material()])
    return mesh, obj


def _canvas_xy_for_image_pixel(p, img_x: float, img_y: float,
                                 img_w: int, img_h: int) -> tuple[float, float]:
    """Map a pixel in the placement's rendered image (img_w × img_h)
    to its painted location on the Designer canvas. Matches the
    ``dl.draw_image_bytes(rgba, img_w, img_h, ax, ay, p.w, p.h)``
    stretch used by ``_paint_one_placement``, INCLUDING the live
    animation transform (``_t_dx`` / ``_t_dy``): without this offset
    the lasso lands where the placement WOULD be at rest, but the
    visible mesh has flown 50 px up because of the looping animation.
    """
    ax = float(p.x) + float(getattr(p, "_t_dx", 0.0))
    ay = float(p.y) + float(getattr(p, "_t_dy", 0.0))
    cx = ax + (img_x / max(img_w - 1, 1)) * float(p.w)
    cy = ay + (img_y / max(img_h - 1, 1)) * float(p.h)
    return (cx, cy)


def _cached_visible_alpha_mask(p) -> tuple:
    """Pull the SAME RGBA bytes the Designer is currently painting onto
    the canvas for this placement and return ``(alpha_mask, w, h)``.
    This is the source of truth for *what the user sees*; falls back to
    None when the cache is empty (e.g. just after a flush)."""
    import numpy as _np
    from elysium.render import designer_preview as _dp
    import hashlib as _hl
    # Match designer_preview's cache key exactly.
    key = (p.mesh_kind, p.pbr_preset, p.pbr_metallic, p.pbr_roughness,
            p.pbr_clearcoat, p.pbr_clearcoat_roughness,
            getattr(p, "pbr_albedo_map", ""),
            getattr(p, "mesh_yaw", 0.4),
            getattr(p, "mesh_pitch", 0.25),
            getattr(p, "mesh_flap", 0.0),
            int(p.w), int(p.h))
    h = _hl.md5(repr(key).encode()).hexdigest()[:14]
    path = _dp._MESH_CACHE.get(h)
    if not path:
        return None
    from pathlib import Path as _P
    if not _P(path).is_file():
        return None
    from PIL import Image as _PIL
    img = _PIL.open(path).convert("RGBA")
    arr = _np.asarray(img)
    return arr[..., 3], int(img.width), int(img.height)


@register_tool(
    name="mesh.render_part_mask",
    description="Render the named sub-mesh part of a Mesh3D placement to "
                "a binary mask sized at the placement's on-canvas pixel "
                "dimensions (p.w × p.h). The mask is what the user sees "
                "- byte-for-byte identical camera + projection as the "
                "real PBR render: so any pixel that's '1' on the mask "
                "is a pixel the user sees coloured by that part on the "
                "checkerboard canvas. Returns the PNG path + pixel count "
                "+ canvas-space bbox of the part.\n\n"
                "Pass `parts=[]` (omit `part`) to get the union mask for "
                "the whole mesh.",
    input_schema={
        "type": "object",
        "properties": {
            "id":     {"type": "string"},
            "part":   {"type": "string"},
            "parts":  {"type": "array", "items": {"type": "string"}},
            "render_scale": {"type": "number"},
            "out":    {"type": "string"},
        },
        "required": ["id"],
    },
    side_effect=SideEffect.READ,
    undoable=False,
)
def mesh_render_part_mask(session, id: str,
                           part: str | None = None,
                           parts: list | None = None,
                           render_scale: float = 1.0,
                           out: str = "") -> dict:
    import numpy as _np
    from PIL import Image as _PIL
    from pathlib import Path as _Path
    from elysium.render import pbr as _pbr
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError("mesh.render_part_mask is Mesh3D-only")
    mesh, obj = _build_mesh_for_placement(p)
    # Render at the placement's canvas size (scaled), so each mask pixel
    # corresponds exactly to one canvas pixel inside the placement.
    rw = max(8, int(round(float(p.w) * render_scale)))
    rh = max(8, int(round(float(p.h) * render_scale)))
    yaw   = float(getattr(p, "mesh_yaw",   0.4))
    pitch = float(getattr(p, "mesh_pitch", 0.25))
    dist  = float(getattr(p, "mesh_dist", None) or 3.5)
    face_idx, part_id = _pbr.render_mesh_partmap(
        rw, rh, obj, cam_dist=dist, cam_yaw=yaw, cam_pitch=pitch)
    if getattr(p, "mesh_flip_y", False):
        face_idx = face_idx[::-1, :].copy()
        part_id  = part_id[::-1, :].copy()
    # Per-pixel material id (derived from face_mats). For meshes with no
    # part_names but with face_mats (the procedural butterfly), this is
    # the only way to isolate "just the wings" vs body+antennae.
    mat_id = _np.full((rh, rw), -1, dtype=_np.int32)
    if mesh.face_mats is not None:
        hit = face_idx >= 0
        if hit.any():
            mat_id[hit] = mesh.face_mats[face_idx[hit]].astype(_np.int32)
    # Full silhouette = any face-hit (works even when the mesh has no
    # vert_part_ids / part_names: `part_id` would be all -1 there).
    full_hit = (face_idx >= 0)
    # Build the requested mask.
    want = []
    if part: want.append(part)
    if parts: want.extend(parts)
    if not want:
        m = full_hit.astype(_np.uint8) * 255
        chosen_parts = list(mesh.part_names or [])
    elif mesh.part_names is not None and all(n in mesh.part_names for n in want):
        ids = [mesh.part_names.index(n) for n in want]
        m = _np.isin(part_id, ids).astype(_np.uint8) * 255
        chosen_parts = want
    else:
        # Material-aware fallback for meshes without named parts but
        # with face_mats. For the procedural butterfly the convention is
        # mat 0=forewing, 1=hindwing, 2=body, 3=head: so "wing" names
        # restrict to mats {0,1} and exclude antennae/body, which would
        # otherwise pull the silhouette out to the placement edges.
        if not full_hit.any():
            m = _np.zeros((rh, rw), dtype=_np.uint8)
        else:
            xs_grid = _np.arange(rw)[None, :]
            ys_all, xs_all = _np.where(full_hit)
            cx_split = int((xs_all.min() + xs_all.max()) / 2)
            keep = _np.zeros_like(full_hit)
            for nm in want:
                lo = nm.lower()
                # Material gate.
                if "wing" in lo:    mat_mask = _np.isin(mat_id, [0, 1])
                elif "body" in lo:  mat_mask = (mat_id == 2)
                elif "head" in lo or "antenna" in lo:
                                    mat_mask = (mat_id == 3)
                else:               mat_mask = full_hit
                base = full_hit & mat_mask
                # Side gate.
                if   "left"  in lo: side = (xs_grid <= cx_split)
                elif "right" in lo: side = (xs_grid >  cx_split)
                else:               side = _np.ones_like(full_hit)
                keep |= base & side
            m = keep.astype(_np.uint8) * 255
        chosen_parts = want
    pix_count = int((m > 0).sum())
    # Canvas-space bbox of the mask's '1' pixels.
    canvas_bbox = None
    if pix_count > 0:
        ys, xs = _np.where(m > 0)
        x0_c, y0_c = _canvas_xy_for_image_pixel(p, float(xs.min()),
                                                   float(ys.min()), rw, rh)
        x1_c, y1_c = _canvas_xy_for_image_pixel(p, float(xs.max()),
                                                   float(ys.max()), rw, rh)
        canvas_bbox = [x0_c, y0_c, x1_c, y1_c]
    # Save PNG.
    cache_dir = _Path.home() / ".elysium" / "object_masks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not out:
        tag = "+".join(want) if want else "all"
        out_path = cache_dir / f"{id}_{tag}_{rw}x{rh}.png"
    else:
        out_path = _Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    _PIL.fromarray(m, mode="L").save(out_path)
    return {
        "path":        str(out_path),
        "w":           rw,
        "h":           rh,
        "pixels":      pix_count,
        "canvas_bbox": canvas_bbox,
        "parts":       chosen_parts,
        "placement":   {"x": float(p.x), "y": float(p.y),
                         "w": float(p.w), "h": float(p.h)},
    }


@register_tool(
    name="mesh.world_to_screen",
    description="Project a world-space (x, y, z) point through a Mesh3D "
                "placement's camera and return the resulting CANVAS "
                "(x, y) pixel: i.e. the same coordinate space as the "
                "Designer's drag-drop placements. Useful for putting a "
                "marker on a known model vertex (wing tip, antenna, "
                "etc.).",
    input_schema={
        "type": "object",
        "properties": {
            "id":    {"type": "string"},
            "point": {"type": "array", "items": {"type": "number"},
                      "minItems": 3, "maxItems": 3},
        },
        "required": ["id", "point"],
    },
    side_effect=SideEffect.READ, undoable=False,
)
def mesh_world_to_screen(session, id: str, point: list) -> dict:
    from elysium.render import pbr as _pbr
    p = session.lookup(id)
    yaw   = float(getattr(p, "mesh_yaw",   0.4))
    pitch = float(getattr(p, "mesh_pitch", 0.25))
    dist  = float(getattr(p, "mesh_dist", None) or 3.5)
    # Render-space pixel coordinates use the placement's canvas size so
    # 1 render pixel = 1 canvas pixel (no rescale).
    rw, rh = int(round(p.w)), int(round(p.h))
    ix, iy, depth = _pbr.world_to_screen_xy(
        tuple(point), rw, rh, cam_dist=dist, cam_yaw=yaw, cam_pitch=pitch)
    if getattr(p, "mesh_flip_y", False):
        iy = (rh - 1) - iy
    cx, cy = _canvas_xy_for_image_pixel(p, ix, iy, rw, rh)
    return {"canvas": [cx, cy], "image": [ix, iy], "depth": depth,
            "behind_camera": depth <= 0.0}


@register_tool(
    name="mesh.lasso_tip_pct",
    description="Pixel-accurate lasso of the top N % of a Mesh3D "
                "placement's named part, ordered tip-first.\n\n"
                "Algorithm: render the part to a binary mask at the "
                "placement's canvas resolution (so each mask pixel maps "
                "1:1 to a canvas pixel), pick the wing tip as the "
                "extreme corner of the mask (auto-detected from the "
                "part name unless `anchor` is given), sort every mask "
                "pixel by Euclidean distance to the tip, take the top "
                "N %. Returns the ordered list of CANVAS-space (x, y) "
                "pixels plus the tip + its canvas coordinate.\n\n"
                "Optionally builds a marching-ants Shape placement that "
                "outlines those pixels (set `create_overlay=True`).",
    input_schema={
        "type": "object",
        "properties": {
            "id":             {"type": "string"},
            "part":           {"type": "string"},
            "pct":            {"type": "number"},
            "anchor":         {"type": "string",
                                "enum": ["auto", "top_left", "top_right",
                                          "bottom_left", "bottom_right",
                                          "top", "bottom"]},
            "create_overlay": {"type": "boolean"},
            "overlay_name":   {"type": "string"},
            "color":          {"type": "array", "items": {"type": "number"}},
            "max_points":     {"type": "integer"},
            "n_target":       {"type": "integer",
                                "description": "If > 0, override pct: "
                                "lasso exactly this many pixels."},
        },
        "required": ["id", "part"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_lasso_tip_pct(session, id: str, part: str,
                        pct: float = 1.0,
                        anchor: str = "auto",
                        create_overlay: bool = True,
                        overlay_name: str = "lasso_tip",
                        color: list | None = None,
                        max_points: int = 400,
                        n_target: int = 0) -> dict:
    import numpy as _np
    from PIL import Image as _PIL
    from elysium.render import pbr as _pbr
    designer = session.designer
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError("mesh.lasso_tip_pct is Mesh3D-only")
    rw_p, rh_p = max(8, int(round(p.w))), max(8, int(round(p.h)))
    yaw   = float(getattr(p, "mesh_yaw",   0.4))
    pitch = float(getattr(p, "mesh_pitch", 0.25))
    dist  = float(getattr(p, "mesh_dist", None) or 3.5)
    # ALWAYS build a fresh partmap: this is the only way to get
    # per-pixel part_id / mat_id needed to isolate Wing_Left from
    # Wing_Right / Body / antennae. The cached visible alpha is used
    # only as a SILHOUETTE GATE (so we never lasso a pixel the user
    # can't see on screen).
    mesh, obj = _build_mesh_for_placement(p)
    face_idx, part_id = _pbr.render_mesh_partmap(
        rw_p, rh_p, obj, cam_dist=dist, cam_yaw=yaw, cam_pitch=pitch)
    if getattr(p, "mesh_flip_y", False):
        part_id  = part_id[::-1, :].copy()
        face_idx = face_idx[::-1, :].copy()
    rw, rh = rw_p, rh_p
    mat_id = _np.full((rh, rw), -1, dtype=_np.int32)
    if mesh.face_mats is not None:
        hit_ = face_idx >= 0
        if hit_.any():
            mat_id[hit_] = mesh.face_mats[face_idx[hit_]].astype(_np.int32)
    full = (face_idx >= 0)
    source = "partmap"
    # Silhouette gate from cached visible alpha (if any). Resize cache
    # to placement-pixel resolution and intersect with `full` so the
    # mask only keeps pixels the user actually sees.
    cached = _cached_visible_alpha_mask(p)
    if cached is not None:
        c_alpha, cw, ch = cached
        if (cw, ch) != (rw, rh):
            try:
                from PIL import Image as _PIL
                _img = _PIL.fromarray(c_alpha, mode="L").resize(
                    (rw, rh), _PIL.NEAREST)
                c_alpha = _np.asarray(_img)
            except Exception:
                c_alpha = None
        if c_alpha is not None:
            visible = c_alpha > 0
            full = full & visible
            source = "partmap+visible_gate"
    if not full.any():
        return {"points": [], "reason": "no mesh pixels visible",
                "mask_source": source}
    # Build the requested mask. Prefer rigged-mesh part_id when it's
    # available; otherwise (procedural / cached path) use a side split.
    if (mesh is not None and mesh.part_names is not None
            and part in mesh.part_names and part_id is not None):
        pid = mesh.part_names.index(part)
        mask = (part_id == pid)
    else:
        lo = part.lower()
        # Material gate only applies in fresh-partmap mode.
        if mat_id is not None:
            if "wing" in lo:   mat_gate = _np.isin(mat_id, [0, 1])
            elif "body" in lo: mat_gate = (mat_id == 2)
            elif "head" in lo or "antenna" in lo:
                               mat_gate = (mat_id == 3)
            else:              mat_gate = full
            base = full & mat_gate
        else:
            base = full   # cached alpha is the whole visible silhouette
        if not base.any():
            return {"points": [], "reason": f"no pixels for gate ({lo})",
                    "mask_source": source}
        ys_all, xs_all = _np.where(base)
        cx_split = int((xs_all.min() + xs_all.max()) / 2)
        if   "left"  in lo: mask = base & (_np.arange(rw)[None, :] <= cx_split)
        elif "right" in lo: mask = base & (_np.arange(rw)[None, :] >  cx_split)
        else:               mask = base
    if not mask.any():
        return {"points": [], "reason": "no pixels: part fully occluded"}
    ys, xs = _np.where(mask)
    # Auto-pick the tip corner from the part name unless the caller said.
    if anchor == "auto":
        nm = part.lower()
        if "left" in nm:        anchor = "top_left"
        elif "right" in nm:     anchor = "top_right"
        else:                   anchor = "top"
    h, w = mask.shape
    if   anchor == "top_left":     tip_yx = (ys.min(), xs[ys == ys.min()].min())
    elif anchor == "top_right":    tip_yx = (ys.min(), xs[ys == ys.min()].max())
    elif anchor == "bottom_left":  tip_yx = (ys.max(), xs[ys == ys.max()].min())
    elif anchor == "bottom_right": tip_yx = (ys.max(), xs[ys == ys.max()].max())
    elif anchor == "top":          tip_yx = (ys.min(), int(_np.mean(xs[ys == ys.min()])))
    elif anchor == "bottom":       tip_yx = (ys.max(), int(_np.mean(xs[ys == ys.max()])))
    else:                          tip_yx = (ys.min(), xs[ys == ys.min()].min())
    # Re-anchor: snap the tip to the most extreme pixel along the wing's
    # outward direction (the corner that visually reads as 'the tip').
    # For "top_left" this is the pixel with min(y + x); for "top_right"
    # min(y - x); etc.: this stops us picking the middle of the top row.
    yx = _np.column_stack([ys, xs]).astype(_np.float32)
    if   anchor == "top_left":     score = yx[:, 0] + yx[:, 1]
    elif anchor == "top_right":    score = yx[:, 0] - yx[:, 1]
    elif anchor == "bottom_left":  score = -yx[:, 0] + yx[:, 1]
    elif anchor == "bottom_right": score = -yx[:, 0] - yx[:, 1]
    elif anchor == "top":          score = yx[:, 0]
    elif anchor == "bottom":       score = -yx[:, 0]
    else:                          score = yx[:, 0] + yx[:, 1]
    best = int(_np.argmin(score))
    tip_yx = (int(yx[best, 0]), int(yx[best, 1]))
    # Distance from tip → sort ascending → keep top N %.
    tip_arr = _np.array(tip_yx, dtype=_np.float32)
    dist_to_tip = _np.linalg.norm(yx - tip_arr, axis=1)
    n_total = int(mask.sum())
    # `n_target` overrides pct when set: useful for matching another
    # lasso's exact pixel count regardless of percentage drift.
    n_keep = (int(n_target) if n_target and n_target > 0
              else max(1, int(round(n_total * (pct / 100.0)))))
    n_keep = max(1, min(n_keep, n_total))
    order = _np.argsort(dist_to_tip, kind="stable")[:n_keep]
    selected = yx[order].astype(_np.int32)        # (n_keep, 2) as (y, x)
    # Convert to CANVAS coords, sub-pixel precision.
    canvas_pts = []
    for (yy, xx) in selected:
        cx_, cy_ = _canvas_xy_for_image_pixel(p, float(xx), float(yy), rw, rh)
        canvas_pts.append((cx_, cy_))
    tip_canvas = _canvas_xy_for_image_pixel(
        p, float(tip_yx[1]), float(tip_yx[0]), rw, rh)
    overlay_id = None
    if create_overlay and canvas_pts:
        # Build a CONVEX-HULL-LIKE outline of the selected pixels so the
        # marching-ants ring is a single closed loop instead of N tiny
        # dots. For pixel-count ≤ ~12 we just emit all points as the
        # polygon. For larger sets we compute a per-angle-bin outer
        # perimeter so the polygon hugs the visible cluster.
        pts = _np.array(canvas_pts, dtype=_np.float64)
        cx_avg = float(pts[:, 0].mean()); cy_avg = float(pts[:, 1].mean())
        if len(pts) <= 12:
            ord_pts = pts.tolist()
        else:
            ang = _np.arctan2(pts[:, 1] - cy_avg, pts[:, 0] - cx_avg)
            r   = _np.linalg.norm(pts - _np.array([cx_avg, cy_avg]), axis=1)
            # Bin by angle, take farthest in each bin.
            N_BINS = 36
            bin_idx = ((ang + _np.pi) / (2 * _np.pi) * N_BINS).astype(_np.int32)
            bin_idx = _np.clip(bin_idx, 0, N_BINS - 1)
            outline = []
            for b in range(N_BINS):
                m = bin_idx == b
                if not m.any(): continue
                local_r = r[m]
                local_p = pts[m]
                idx = int(_np.argmax(local_r))
                outline.append(tuple(local_p[idx]))
            if outline:
                # Sort by angle so the polygon walks ccw.
                outline.sort(key=lambda q: _np.arctan2(q[1] - cy_avg,
                                                        q[0] - cx_avg))
                ord_pts = [list(q) for q in outline]
            else:
                ord_pts = pts.tolist()
        # Translate to placement-local for the Shape placement.
        if ord_pts:
            xs2 = [pt[0] for pt in ord_pts]; ys2 = [pt[1] for pt in ord_pts]
            x0 = min(xs2); y0 = min(ys2)
            local_pts = [(pt[0] - x0, pt[1] - y0) for pt in ord_pts]
            P = session.designer_models.Placement
            cc = list(int(c) for c in (color or [255, 220, 0, 255]))
            fill_col = (cc[0], cc[1], cc[2], 60)
            sh = P(kind="Shape", x=x0, y=y0,
                    w=max(2.0, max(xs2) - x0),
                    h=max(2.0, max(ys2) - y0),
                    name=overlay_name,
                    shape="polygon",
                    points=local_pts,
                    path_d="",
                    fill=tuple(fill_col),
                    stroke=tuple(cc),
                    stroke_w=2.0)
            sh.is_lasso = True
            designer.placements.append(sh)
            overlay_id = session.id_for(sh)
    # Truncate the returned point list so the JSON stays manageable.
    out_pts = [list(pt) for pt in canvas_pts[:max_points]]
    return {
        "points":     out_pts,
        "n_points":   len(canvas_pts),
        "n_total":    n_total,
        "n_kept":     n_keep,
        "tip_canvas": list(tip_canvas),
        "tip_image":  [int(tip_yx[1]), int(tip_yx[0])],
        "anchor":     anchor,
        "overlay_id": overlay_id,
        "render_size": [rw, rh],
        "mask_source": source,
        "placement":  {"x": float(p.x), "y": float(p.y),
                        "w": float(p.w), "h": float(p.h)},
    }


# ──────────────────────────────────────────────────────────────────────
# image.lasso_left_wing_tip_pct: Image-placement counterpart of
# mesh.lasso_tip_pct. The reference photo doesn't have a 3D part rig,
# so we recover the "left wing" via an alpha + non-white silhouette
# pass on the source pixels, find the upper-outer tip, and lasso the
# top N% closest to it.
# ──────────────────────────────────────────────────────────────────────

def _photo_left_wing_pixels(ref_placement):
    """Return ``(left_yx, src_w, src_h, butterfly_mask)`` for an Image
    placement: ``left_yx`` is an ``(N, 2)`` int array of *source-image*
    ``(y, x)`` coordinates that belong to the viewer-left half of the
    silhouette."""
    import numpy as _np
    from PIL import Image as _PIL
    src = _np.asarray(_PIL.open(ref_placement.image_path).convert("RGBA"))
    H, W = src.shape[:2]
    non_white = ~((src[..., 0] > 235) & (src[..., 1] > 235)
                   & (src[..., 2] > 235))
    butterfly = non_white & (src[..., 3] > 8)
    if not butterfly.any():
        return (_np.empty((0, 2), dtype=_np.int32), W, H, butterfly)
    ys, xs = _np.where(butterfly)
    xmid = (xs.min() + xs.max()) // 2
    keep = xs <= xmid
    left_yx = _np.column_stack([ys[keep], xs[keep]]).astype(_np.int32)
    return left_yx, W, H, butterfly


@register_tool(
    name="image.lasso_left_wing_tip_pct",
    description="Pixel-accurate lasso on the upper-outer tip of an "
                "Image placement's left wing: the Image counterpart of "
                "mesh.lasso_tip_pct. Algorithm: alpha + non-white "
                "silhouette pass on the source photo, split at the "
                "horizontal midpoint to isolate the left wing, find the "
                "upper-outer corner (min y+x), sort by Euclidean "
                "distance to that tip, take the top N % closest pixels, "
                "map them into canvas coords using the placement's "
                "current size, optionally emit a marching-ants Shape "
                "overlay.",
    input_schema={
        "type": "object",
        "properties": {
            "id":             {"type": "string"},
            "pct":            {"type": "number"},
            "side":           {"type": "string",
                                "enum": ["left", "right"]},
            "create_overlay": {"type": "boolean"},
            "overlay_name":   {"type": "string"},
            "color":          {"type": "array", "items": {"type": "number"}},
            "max_points":     {"type": "integer"},
            "n_target":       {"type": "integer"},
        },
        "required": ["id"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def image_lasso_left_wing_tip_pct(session, id: str,
                                    pct: float = 1.0,
                                    side: str = "left",
                                    create_overlay: bool = True,
                                    overlay_name: str = "lasso_image_tip",
                                    color: list | None = None,
                                    max_points: int = 400,
                                    n_target: int = 0) -> dict:
    import numpy as _np
    from PIL import Image as _PIL
    designer = session.designer
    p = session.lookup(id)
    if p.kind != "Image":
        raise ValueError("image.lasso_left_wing_tip_pct is Image-only")
    # Rasterise the source at exact placement-canvas size so each mask
    # pixel = one canvas pixel. That way 1% picks 1% of CANVAS-visible
    # wing pixels (not source pixels), making the count directly
    # comparable to mesh.lasso_tip_pct on a same-area mesh wing.
    src_img = _PIL.open(p.image_path).convert("RGBA")
    cw = max(8, int(round(float(p.w))))
    ch = max(8, int(round(float(p.h))))
    arr = _np.asarray(src_img.resize((cw, ch), _PIL.NEAREST))
    H, W = arr.shape[:2]
    non_white = ~((arr[..., 0] > 235) & (arr[..., 1] > 235)
                   & (arr[..., 2] > 235))
    butterfly = non_white & (arr[..., 3] > 8)
    if not butterfly.any():
        return {"points": [], "reason": "no silhouette at canvas resolution"}
    ys, xs = _np.where(butterfly)
    xmid = (xs.min() + xs.max()) // 2
    if side == "left":
        keep = xs <= xmid
    else:
        keep = xs > xmid
    side_yx = _np.column_stack([ys[keep], xs[keep]]).astype(_np.float32)
    n_total = int(side_yx.shape[0])
    if n_total == 0:
        return {"points": [], "reason": f"no pixels for side={side}"}
    if side == "left":
        score = side_yx[:, 0] + side_yx[:, 1]
    else:
        score = side_yx[:, 0] - side_yx[:, 1]
    tip_idx = int(_np.argmin(score))
    tip_yx = (float(side_yx[tip_idx, 0]), float(side_yx[tip_idx, 1]))
    dist = _np.linalg.norm(side_yx - _np.array(tip_yx, dtype=_np.float32),
                            axis=1)
    # `n_target` overrides pct when set: useful for matching another
    # lasso's exact pixel count regardless of percentage drift.
    n_keep = (int(n_target) if n_target and n_target > 0
              else max(1, int(round(n_total * (pct / 100.0)))))
    n_keep = max(1, min(n_keep, n_total))
    order = _np.argsort(dist, kind="stable")[:n_keep]
    sel = side_yx[order].astype(_np.int32)
    # Apply runtime placement transform exactly as the Designer paints.
    ax = float(p.x) + float(getattr(p, "_t_dx", 0.0))
    ay = float(p.y) + float(getattr(p, "_t_dy", 0.0))
    canvas_pts = [(ax + float(xx), ay + float(yy)) for (yy, xx) in sel]
    tip_canvas = (ax + tip_yx[1], ay + tip_yx[0])
    overlay_id = None
    if create_overlay and canvas_pts:
        # Convex-hull-ish polygon (same trick as mesh.lasso_tip_pct).
        import numpy as _np2
        pts = _np2.array(canvas_pts, dtype=_np2.float64)
        cx_avg = float(pts[:, 0].mean()); cy_avg = float(pts[:, 1].mean())
        if len(pts) <= 12:
            ord_pts = pts.tolist()
        else:
            ang = _np2.arctan2(pts[:, 1] - cy_avg, pts[:, 0] - cx_avg)
            r   = _np2.linalg.norm(pts - _np2.array([cx_avg, cy_avg]), axis=1)
            N_BINS = 36
            bin_idx = ((ang + _np2.pi) / (2 * _np2.pi) * N_BINS).astype(_np2.int32)
            bin_idx = _np2.clip(bin_idx, 0, N_BINS - 1)
            outline = []
            for b in range(N_BINS):
                m = bin_idx == b
                if not m.any(): continue
                local_p = pts[m]; local_r = r[m]
                outline.append(tuple(local_p[int(_np2.argmax(local_r))]))
            if outline:
                outline.sort(key=lambda q: _np2.arctan2(q[1] - cy_avg,
                                                        q[0] - cx_avg))
                ord_pts = [list(q) for q in outline]
            else:
                ord_pts = pts.tolist()
        if ord_pts:
            xs2 = [pt[0] for pt in ord_pts]; ys2 = [pt[1] for pt in ord_pts]
            x0 = min(xs2); y0 = min(ys2)
            local_pts = [(pt[0] - x0, pt[1] - y0) for pt in ord_pts]
            P = session.designer_models.Placement
            cc = list(int(c) for c in (color or [255, 80, 80, 255]))
            fill_col = (cc[0], cc[1], cc[2], 60)
            sh = P(kind="Shape", x=x0, y=y0,
                    w=max(2.0, max(xs2) - x0),
                    h=max(2.0, max(ys2) - y0),
                    name=overlay_name,
                    shape="polygon",
                    points=local_pts,
                    path_d="",
                    fill=tuple(fill_col),
                    stroke=tuple(cc),
                    stroke_w=2.0)
            sh.is_lasso = True
            designer.placements.append(sh)
            overlay_id = session.id_for(sh)
    out_pts = [list(pt) for pt in canvas_pts[:max_points]]
    return {
        "points":     out_pts,
        "n_points":   len(canvas_pts),
        "n_total":    n_total,
        "n_kept":     n_keep,
        "tip_canvas": list(tip_canvas),
        "tip_src":    [int(tip_yx[1]), int(tip_yx[0])],
        "side":       side,
        "src_size":   [W, H],
        "overlay_id": overlay_id,
        "placement":  {"x": float(p.x), "y": float(p.y),
                        "w": float(p.w), "h": float(p.h)},
    }


@register_tool(
    name="mesh.transfer_wing_from_reference",
    description="Pattern-preserving transfer of a reference Image's wing "
                "onto a Mesh3D placement's wing. The source wing's bbox "
                "is cropped from the reference photo and image-warped to "
                "the model wing's bbox (preserving spatial pattern), then "
                "each model wing pixel reads its color from the warped "
                "crop at its bbox-local position. Painted into the "
                "placement's PaintMask so the result composites over the "
                "mesh immediately.\n\n"
                "method='bbox_warp' (default): image-warps the source "
                "crop so stripes/spots stay in the right place even when "
                "the wings have different shapes.\n"
                "method='sweep'     : legacy zig-zag row-major copy "
                "(loses pattern; only useful as a comparison baseline).\n\n"
                "n_regions controls progress reporting (and the row "
                "subdivision used in 'sweep' mode); bbox_warp samples "
                "every pixel from the warped image, independent of "
                "n_regions.\n\n"
                "clear_mask=True wipes the previous PaintMask first so "
                "successive transfers don't bleed through.",
    input_schema={
        "type": "object",
        "properties": {
            "model_id":   {"type": "string"},
            "ref_id":     {"type": "string"},
            "model_part": {"type": "string"},
            "side":       {"type": "string", "enum": ["left", "right"]},
            "n_regions":  {"type": "integer"},
            "method":     {"type": "string",
                            "enum": ["landmark", "regions", "polar",
                                      "flow", "tps", "bbox_warp", "sweep"]},
            "clear_mask": {"type": "boolean"},
            "flip_h":     {"type": "boolean",
                            "description": "Mirror the source crop "
                            "horizontally before warping (use when the "
                            "model wing tip points outward in the "
                            "opposite direction)."},
            "landmarks":  {"type": "array",
                            "description": "Paired landmark points for "
                            "method='landmark'. Each entry: {src:[x,y], "
                            "tgt:[x,y]} in source-photo and canvas pixel "
                            "coords respectively.",
                            "items": {"type": "object"}},
            "paint_only_empty": {"type": "boolean",
                            "description": "Skip pixels where the "
                            "PaintMask already has alpha>0: i.e. only "
                            "fill the gaps left by a previous transfer. "
                            "Pair with clear_mask=false to layer."},
        },
        "required": ["model_id", "ref_id"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_transfer_wing_from_reference(session,
                                       model_id: str, ref_id: str,
                                       model_part: str = "Wing_Left",
                                       side: str = "left",
                                       n_regions: int = 100,
                                       method: str = "tps",
                                       clear_mask: bool = True,
                                       flip_h: bool = False,
                                       landmarks: list | None = None,
                                       paint_only_empty: bool = False) -> dict:
    import math
    import numpy as _np
    from PIL import Image as _PIL
    from builtins import id as _obj_id
    designer = session.designer
    p_model = session.lookup(model_id)
    p_ref   = session.lookup(ref_id)
    if p_model.kind != "Mesh3D":
        raise ValueError("model_id must be a Mesh3D placement")
    if p_ref.kind != "Image":
        raise ValueError("ref_id must be an Image placement")
    # ----- model wing pixels (placement-local) ----------------------------
    mesh, obj = _build_mesh_for_placement(p_model)
    rw = max(8, int(round(float(p_model.w))))
    rh = max(8, int(round(float(p_model.h))))
    yaw   = float(getattr(p_model, "mesh_yaw",   0.4))
    pitch = float(getattr(p_model, "mesh_pitch", 0.25))
    dist  = float(getattr(p_model, "mesh_dist", None) or 3.5)
    from elysium.render import pbr as _pbr
    face_idx, part_id = _pbr.render_mesh_partmap(
        rw, rh, obj, cam_dist=dist, cam_yaw=yaw, cam_pitch=pitch)
    if getattr(p_model, "mesh_flip_y", False):
        face_idx = face_idx[::-1, :].copy()
        part_id  = part_id[::-1, :].copy()
    if mesh.part_names and model_part in mesh.part_names:
        pid = mesh.part_names.index(model_part)
        model_mask = (part_id == pid)
    else:
        full = face_idx >= 0
        ys_all, xs_all = _np.where(full)
        cx_split = int((xs_all.min() + xs_all.max()) / 2)
        xs_grid = _np.arange(rw)[None, :]
        if side == "left": model_mask = full & (xs_grid <= cx_split)
        else:              model_mask = full & (xs_grid >  cx_split)
    model_ys, model_xs = _np.where(model_mask)
    if len(model_ys) == 0:
        return {"transferred_pixels": 0,
                "reason": "no model wing pixels"}
    N_model = int(len(model_ys))
    # ----- reference wing pixels at canvas resolution ---------------------
    cw = max(8, int(round(float(p_ref.w))))
    ch = max(8, int(round(float(p_ref.h))))
    src_full = _np.asarray(_PIL.open(p_ref.image_path).convert("RGBA")
                            .resize((cw, ch), _PIL.NEAREST))
    non_white = ~((src_full[..., 0] > 235) & (src_full[..., 1] > 235)
                   & (src_full[..., 2] > 235))
    butterfly = non_white & (src_full[..., 3] > 8)
    if not butterfly.any():
        return {"transferred_pixels": 0,
                "reason": "reference photo has no silhouette"}
    ys, xs = _np.where(butterfly)
    xmid = (xs.min() + xs.max()) // 2
    keep = (xs <= xmid) if side == "left" else (xs > xmid)
    ref_ys = ys[keep]; ref_xs = xs[keep]
    N_ref = int(len(ref_ys))
    if N_ref == 0:
        return {"transferred_pixels": 0,
                "reason": f"no reference pixels for side={side}"}
    # ----- get / create PaintMask -----------------------------------------
    masks = getattr(designer, "paint_masks", None)
    if masks is None:
        designer.paint_masks = {}; masks = designer.paint_masks
    from elysium.render.texture import PaintMask
    pm_key = _obj_id(p_model)
    pw = max(1, int(round(float(p_model.w))))
    ph = max(1, int(round(float(p_model.h))))
    mask_obj = masks.get(pm_key)
    if mask_obj is None or mask_obj.w != pw or mask_obj.h != ph:
        mask_obj = PaintMask(pw, ph)
        masks[pm_key] = mask_obj
    if clear_mask:
        mask_obj.buf[:] = 0
    # If paint_only_empty, snapshot the pre-paint state once here and
    # restore those pixels at the very end of the function. Cleaner
    # than threading the flag into every per-branch write site.
    _pre_alpha = None; _pre_rgb = None
    if paint_only_empty:
        _pre_alpha = mask_obj.buf[..., 3].copy()
        _pre_rgb   = mask_obj.buf[..., :3].copy()
    transferred = 0
    region_summaries = []
    _tps_fallback_reason = None
    if method == "tps":
        try:
            # === TPS attempt begins (falls back to bbox_warp on failure) ===
            # Hybrid v3: enhanced multi-keypoint TPS with bbox-warp fallback.
            # Pipeline:
            #   1. Build target-wing and source-wing masks
            #   2. Sample MATCHED keypoints via arc-length contour walk
            #      anchored at tip+base, plus radial-distance-binned
            #      interior points (so source ↔ target correspondence is
            #      semantic, not bbox-uniform)
            #   3. Solve inverse TPS (target → source) per coord via RBF
            #      with a small smoothing regulariser
            #   4. Dense forward-warp with bicubic resampling
            #   5. Composite into PaintMask gated by the source silhouette
            #
            # If any step fails (singular TPS, too few keypoints, etc.) the
            # function falls through to the bbox_warp branch so the user
            # still gets a usable result instead of a transparent wing.
            try:
                from scipy.interpolate import RBFInterpolator as _RBF
                from scipy.ndimage import map_coordinates as _map_coords
                from skimage.measure import find_contours as _find_contours
            except Exception as e:
                raise RuntimeError(
                    f"tps method needs scipy+skimage ({e}); install in the venv")
            tgt_mask = model_mask.astype(bool)
            src_mask = _np.zeros_like(butterfly, dtype=bool)
            src_mask[ref_ys, ref_xs] = True
    
            def _strong_kpts(mask_2d, side_local,
                              n_contour: int = 18, n_interior: int = 14):
                """Arc-length contour resample + radial-distance interior bins.
                Output starts with tip + base (anchors), then n_contour
                arc-length boundary samples beginning AT the tip (rolled
                so both wings start at the same anatomical landmark),
                then n_interior points binned by normalized distance from
                base. Order is deterministic for fixed mask geometry."""
                ys_, xs_ = _np.where(mask_2d)
                if len(ys_) < 16:
                    return None
                # 1. Tip + base (side-aware).
                if side_local == "left":
                    tip_score, base_score = ys_ + xs_, -xs_
                else:
                    tip_score, base_score = ys_ - xs_, xs_
                tip_idx  = int(_np.argmin(tip_score))
                base_idx = int(_np.argmin(base_score))
                tip  = _np.array([xs_[tip_idx],  ys_[tip_idx]],  dtype=_np.float64)
                base = _np.array([xs_[base_idx], ys_[base_idx]], dtype=_np.float64)
                # 2. Arc-length boundary walk (skimage.find_contours returns
                #    pixel-precise ordered contour vertices, CCW for a
                #    foreground blob: so neighbouring vertices stay
                #    spatially adjacent and we can integrate arc length).
                contours = _find_contours(mask_2d.astype(_np.uint8), level=0.5)
                if not contours:
                    return None
                contour = max(contours, key=lambda c: len(c))   # longest
                if len(contour) < 8:
                    return None
                # contour is (y, x); convert to (x, y) and integrate length.
                contour_xy = contour[:, ::-1]
                diffs = _np.diff(contour_xy, axis=0)
                seg_len = _np.hypot(diffs[:, 0], diffs[:, 1])
                arc = _np.concatenate([[0.0], _np.cumsum(seg_len)])
                total = float(arc[-1])
                if total < 4.0:
                    return None
                # Find arc-length position of the tip on the contour →
                # roll the contour so tip is at arc-length 0. Same trick
                # for both wings → matched starts.
                tip_vert_idx = int(_np.argmin(
                    _np.hypot(contour_xy[:, 0] - tip[0],
                              contour_xy[:, 1] - tip[1])))
                rolled_arc = (arc - arc[tip_vert_idx]) % total
                order = _np.argsort(rolled_arc)
                rolled_arc = rolled_arc[order]
                rolled_xy  = contour_xy[order]
                sample_at  = _np.linspace(0, total, n_contour, endpoint=False)
                sample_idx = _np.searchsorted(rolled_arc, sample_at)
                sample_idx = _np.clip(sample_idx, 0, len(rolled_xy) - 1)
                contour_pts = rolled_xy[sample_idx].astype(_np.float64)
                # 3. Interior points binned by normalized distance-from-base.
                #    For each radial bin take the point closest to the bin's
                #    target radius AND closest to the line tip→base for
                #    repeatability.
                dx = xs_.astype(_np.float64) - base[0]
                dy = ys_.astype(_np.float64) - base[1]
                d  = _np.hypot(dx, dy)
                d_max = float(d.max())
                interior_pts = []
                if d_max > 1e-3 and n_interior > 0:
                    tip_dir = tip - base
                    tip_dir = tip_dir / max(_np.linalg.norm(tip_dir), 1e-6)
                    # Bins at r/d_max ∈ [0.2 .. 0.85].
                    for fr in _np.linspace(0.2, 0.85, n_interior):
                        r_target = fr * d_max
                        # Among points within ±10% of r_target, pick the one
                        # closest to the tip-base line so both wings choose
                        # the same anatomical landmark.
                        band = (d > r_target * 0.9) & (d < r_target * 1.1)
                        if not band.any(): continue
                        pts_dx = dx[band]; pts_dy = dy[band]
                        # Distance from line through base with direction tip_dir.
                        proj = pts_dx * tip_dir[0] + pts_dy * tip_dir[1]
                        perp = _np.abs(pts_dx * tip_dir[1] - pts_dy * tip_dir[0])
                        # Prefer high projection (closer to tip) and small perp.
                        score = perp - 0.3 * proj
                        k = int(_np.argmin(score))
                        band_xs = xs_[band]; band_ys = ys_[band]
                        interior_pts.append([float(band_xs[k]),
                                              float(band_ys[k])])
                inner_arr = (_np.array(interior_pts, dtype=_np.float64)
                              if interior_pts else _np.zeros((0, 2)))
                return _np.vstack([tip[None, :], base[None, :],
                                    contour_pts, inner_arr])
    
            src_kpts = _strong_kpts(src_mask, side)
            tgt_kpts = _strong_kpts(tgt_mask, side)
            if src_kpts is None or tgt_kpts is None or \
                    len(src_kpts) < 6 or len(tgt_kpts) < 6:
                raise RuntimeError("not enough keypoints for TPS")
            # Pair-deduplicate: drop any (src, tgt) pair whose target xy
            # is within ε of another target xy already seen (TPS with
            # smoothing=0 fails on coincident inputs → singular matrix).
            n_match = min(len(src_kpts), len(tgt_kpts))
            src_kpts = src_kpts[:n_match]; tgt_kpts = tgt_kpts[:n_match]
            keep = []
            seen_t = []
            seen_s = []
            for i in range(n_match):
                tk = tgt_kpts[i]; sk = src_kpts[i]
                dup_t = any(abs(tk[0] - q[0]) < 0.5 and abs(tk[1] - q[1]) < 0.5
                             for q in seen_t)
                dup_s = any(abs(sk[0] - q[0]) < 0.5 and abs(sk[1] - q[1]) < 0.5
                             for q in seen_s)
                if not dup_t and not dup_s:
                    seen_t.append(tk); seen_s.append(sk); keep.append(i)
            if len(keep) < 6:
                raise RuntimeError(
                    f"after de-duplication only {len(keep)} unique keypoint pairs; "
                    f"need ≥6 for TPS")
            src_kpts = src_kpts[keep]; tgt_kpts = tgt_kpts[keep]
            n_match = len(keep)
            # Inverse TPS: target_xy → source_xy. A tiny smoothing term
            # keeps the system non-singular if any near-duplicate slipped
            # through the dedupe.
            try:
                rbf_x = _RBF(tgt_kpts, src_kpts[:, 0],
                              kernel="thin_plate_spline", smoothing=1e-3)
                rbf_y = _RBF(tgt_kpts, src_kpts[:, 1],
                              kernel="thin_plate_spline", smoothing=1e-3)
            except Exception as e:
                raise RuntimeError(f"TPS solve failed: {e}")
            ty_min, ty_max = int(model_ys.min()), int(model_ys.max())
            tx_min, tx_max = int(model_xs.min()), int(model_xs.max())
            yy, xx = _np.mgrid[ty_min:ty_max + 1, tx_min:tx_max + 1]
            grid = _np.column_stack([xx.ravel(), yy.ravel()]).astype(_np.float64)
            src_x = rbf_x(grid).reshape(yy.shape)
            src_y = rbf_y(grid).reshape(yy.shape)
            # Clamp sampling coords to source bounds (else map_coordinates
            # with reflect mode could pull in mirror pixels).
            src_x = _np.clip(src_x, 0, src_full.shape[1] - 1)
            src_y = _np.clip(src_y, 0, src_full.shape[0] - 1)
            coords = _np.array([src_y, src_x], dtype=_np.float64)
            warped = _np.zeros((yy.shape[0], yy.shape[1], 4),
                                dtype=_np.uint8)
            for ch in range(3):
                samp = _map_coords(
                    src_full[..., ch].astype(_np.float32), coords,
                    order=3, mode="reflect", prefilter=False)
                warped[..., ch] = _np.clip(samp, 0, 255).astype(_np.uint8)
            # Source butterfly mask gate (warped): pixels mapped from
            # outside the source butterfly stay un-painted so we don't
            # bleed the photo's background onto the wing.
            bf_sampled = _map_coords(
                butterfly.astype(_np.float32), coords,
                order=1, mode="constant", cval=0.0)
            warped_silhouette = bf_sampled > 0.4
            warped[..., 3] = (warped_silhouette.astype(_np.uint8) * 255)
            # 1-px feather around the target wing edge so the seam blends.
            local_x = model_xs - tx_min
            local_y = model_ys - ty_min
            bf_target = warped_silhouette[local_y, local_x]
            in_bounds = ((model_xs >= 0) & (model_xs < pw)
                          & (model_ys >= 0) & (model_ys < ph)
                          & bf_target)
            cols = warped[local_y[in_bounds], local_x[in_bounds]].copy()
            cols[:, 3] = 255
            mask_obj.buf[model_ys[in_bounds],
                         model_xs[in_bounds]] = cols
            transferred = int(in_bounds.sum())
            for r in range(int(n_regions)):
                y0 = r * max(1, yy.shape[0] // max(1, int(n_regions)))
                y1 = yy.shape[0] if r == int(n_regions) - 1 \
                      else min(yy.shape[0],
                                (r + 1) * max(1, yy.shape[0] // max(1, int(n_regions))))
                if r < 5 or r == int(n_regions) - 1:
                    region_summaries.append(
                        {"region": r, "band_y0_local": int(y0),
                          "band_y1_local": int(y1)})
            result_extra = {
                "method":         "tps",
                "n_keypoints":    int(n_match),
                "model_bbox":     [tx_min, ty_min, tx_max, ty_max],
                "warped_size":    [int(yy.shape[1]), int(yy.shape[0])],
            }
        except Exception as _tps_err:
            # TPS solve / mapping failed: log reason, reset mask
            # buffer, and re-run with bbox_warp on the same inputs.
            _tps_fallback_reason = repr(_tps_err)[:300]
            mask_obj.buf[:] = 0
            transferred = 0
            region_summaries = []
            method = "bbox_warp"
    if method == "bbox_warp":
        # Bbox-warp method: preserves the source's spatial pattern.
        # Crop reference around the wing's tight silhouette bbox, warp
        # the crop to the model wing's bbox dimensions, then sample
        # every model wing pixel at its bbox-relative position.
        my_min, my_max = int(model_ys.min()), int(model_ys.max())
        mx_min, mx_max = int(model_xs.min()), int(model_xs.max())
        mbw = mx_max - mx_min + 1
        mbh = my_max - my_min + 1
        sy_min, sy_max = int(ref_ys.min()), int(ref_ys.max())
        sx_min, sx_max = int(ref_xs.min()), int(ref_xs.max())
        src_crop  = src_full[sy_min:sy_max + 1, sx_min:sx_max + 1]
        bf_crop   = butterfly[sy_min:sy_max + 1, sx_min:sx_max + 1]
        crop_pil  = _PIL.fromarray(src_crop, mode="RGBA")
        bf_pil    = _PIL.fromarray(bf_crop.astype(_np.uint8) * 255, mode="L")
        if flip_h:
            crop_pil = crop_pil.transpose(_PIL.FLIP_LEFT_RIGHT)
            bf_pil   = bf_pil.transpose(_PIL.FLIP_LEFT_RIGHT)
        warped    = _np.asarray(crop_pil.resize((mbw, mbh), _PIL.LANCZOS))
        warped_bf = _np.asarray(bf_pil.resize((mbw, mbh), _PIL.NEAREST)) > 0
        # Sample: each model pixel reads from warped at (local_x, local_y).
        local_x = model_xs - mx_min
        local_y = model_ys - my_min
        sampled = warped[local_y, local_x].copy()
        # Where the warped silhouette is empty (source background), skip.
        skip = ~warped_bf[local_y, local_x]
        sampled[..., 3] = _np.where(skip, 0, _np.maximum(sampled[..., 3], 255))
        # Apply pixel-by-pixel to PaintMask.
        in_bounds = ((model_xs >= 0) & (model_xs < pw)
                      & (model_ys >= 0) & (model_ys < ph)
                      & ~skip)
        mask_obj.buf[model_ys[in_bounds], model_xs[in_bounds]] = sampled[in_bounds]
        transferred = int(in_bounds.sum())
        # Region summary: split the warped image horizontally into n
        # bands top-down so progress maps onto wing geometry.
        per_band = max(1, mbh // max(1, int(n_regions)))
        for r in range(int(n_regions)):
            y0 = r * per_band
            y1 = mbh if r == int(n_regions) - 1 else min(mbh, (r + 1) * per_band)
            in_band = (local_y[in_bounds] >= y0) & (local_y[in_bounds] < y1)
            if r < 5 or r == int(n_regions) - 1:
                region_summaries.append(
                    {"region": r, "band_y0_local": int(y0),
                      "band_y1_local": int(y1),
                      "pixels": int(in_band.sum())})
        result_extra = {
            "method":         "bbox_warp",
            "model_bbox":     [mx_min, my_min, mx_max, my_max],
            "src_bbox":       [sx_min, sy_min, sx_max, sy_max],
            "warped_size":    [mbw, mbh],
            "flip_h":         bool(flip_h),
        }
    elif method == "regions":
        # Multi-region radial warping: bbox-warp baseline, then refine
        # each of N radial bands (concentric distance-from-base shells)
        # with its own local affine transform that aligns the band's
        # centroid + scale on source and target. Cheaper than TPS, more
        # locally adaptive than bbox.
        try:
            from scipy.ndimage import map_coordinates as _map_coords
        except Exception as e:
            raise RuntimeError(f"regions method needs scipy ({e})")
        my_min, my_max = int(model_ys.min()), int(model_ys.max())
        mx_min, mx_max = int(model_xs.min()), int(model_xs.max())
        mbw = mx_max - mx_min + 1; mbh = my_max - my_min + 1
        # Get source crop + butterfly mask in source-canvas coords.
        sys_, sxs_ = _np.where(butterfly)
        if side == "left":
            keep_s = sxs_ <= ((sxs_.min() + sxs_.max()) // 2)
        else:
            keep_s = sxs_ > ((sxs_.min() + sxs_.max()) // 2)
        sys_s = sys_[keep_s]; sxs_s = sxs_[keep_s]
        if side == "left":
            t_score = ys_ = model_ys + model_xs
            s_score = sys_s + sxs_s
        else:
            t_score = model_ys - model_xs
            s_score = sys_s - sxs_s
        tgt_tip_xy = (float(model_xs[int(_np.argmin(t_score))]),
                       float(model_ys[int(_np.argmin(t_score))]))
        src_tip_xy = (float(sxs_s[int(_np.argmin(s_score))]),
                       float(sys_s[int(_np.argmin(s_score))]))
        # Base = anatomically-opposite (rightmost-for-left).
        if side == "left":
            tb_score = -model_xs; sb_score = -sxs_s
        else:
            tb_score = model_xs;  sb_score = sxs_s
        tgt_base_xy = (float(model_xs[int(_np.argmin(tb_score))]),
                        float(model_ys[int(_np.argmin(tb_score))]))
        src_base_xy = (float(sxs_s[int(_np.argmin(sb_score))]),
                        float(sys_s[int(_np.argmin(sb_score))]))
        # Distance-from-base for both wings.
        tgt_d = _np.hypot(model_xs - tgt_base_xy[0],
                           model_ys - tgt_base_xy[1])
        src_d = _np.hypot(sxs_s - src_base_xy[0],
                           sys_s - src_base_xy[1])
        tgt_d_max = float(tgt_d.max()); src_d_max = float(src_d.max())
        N_BANDS = 6
        # Build per-target-pixel band index.
        tgt_band = (tgt_d / max(tgt_d_max, 1e-6) * N_BANDS).astype(_np.int64)
        tgt_band = _np.clip(tgt_band, 0, N_BANDS - 1)
        # For each band: compute centroid + scale on source and target,
        # then derive an affine that maps source band → target band.
        result_canvas = _np.zeros((mbh, mbw, 4), dtype=_np.uint8)
        applied = 0
        band_records = []
        for b in range(N_BANDS):
            t_mask_band = (tgt_band == b)
            tg = (tgt_d / max(tgt_d_max, 1e-6) * N_BANDS).astype(_np.int64)
            s_band_mask = ((src_d / max(src_d_max, 1e-6) * N_BANDS).astype(_np.int64) == b)
            if not t_mask_band.any() or not s_band_mask.any():
                continue
            # Centroids + bbox aspect.
            t_cx = float(model_xs[t_mask_band].mean())
            t_cy = float(model_ys[t_mask_band].mean())
            s_cx = float(sxs_s[s_band_mask].mean())
            s_cy = float(sys_s[s_band_mask].mean())
            t_w  = float(model_xs[t_mask_band].max() - model_xs[t_mask_band].min() + 1)
            t_h  = float(model_ys[t_mask_band].max() - model_ys[t_mask_band].min() + 1)
            s_w  = float(sxs_s[s_band_mask].max() - sxs_s[s_band_mask].min() + 1)
            s_h  = float(sys_s[s_band_mask].max() - sys_s[s_band_mask].min() + 1)
            sx = s_w / max(t_w, 1.0)
            sy = s_h / max(t_h, 1.0)
            # For each target pixel in this band, map to source xy and sample.
            ty = model_ys[t_mask_band]
            tx = model_xs[t_mask_band]
            src_x = s_cx + (tx - t_cx) * sx
            src_y = s_cy + (ty - t_cy) * sy
            src_x = _np.clip(src_x, 0, src_full.shape[1] - 1)
            src_y = _np.clip(src_y, 0, src_full.shape[0] - 1)
            coords = _np.array([src_y, src_x], dtype=_np.float64)
            cols = _np.zeros((len(ty), 4), dtype=_np.uint8)
            for ch in range(3):
                samp = _map_coords(
                    src_full[..., ch].astype(_np.float32), coords,
                    order=3, mode="reflect", prefilter=False)
                cols[:, ch] = _np.clip(samp, 0, 255).astype(_np.uint8)
            # Source silhouette gate.
            bf_samp = _map_coords(
                butterfly.astype(_np.float32), coords,
                order=1, mode="constant", cval=0.0)
            keep_b = bf_samp > 0.4
            cols[:, 3] = (keep_b.astype(_np.uint8) * 255)
            in_bounds = ((tx >= 0) & (tx < pw) & (ty >= 0) & (ty < ph) & keep_b)
            mask_obj.buf[ty[in_bounds], tx[in_bounds]] = cols[in_bounds]
            applied += int(in_bounds.sum())
            band_records.append({"band": b, "pixels": int(in_bounds.sum()),
                                  "src_centroid": [s_cx, s_cy],
                                  "tgt_centroid": [t_cx, t_cy],
                                  "scale": [sx, sy]})
        transferred = applied
        result_extra = {
            "method":       "regions",
            "n_bands":      N_BANDS,
            "bands":        band_records,
        }
    elif method == "landmark":
        # Manual-landmark TPS: set via the `landmarks` kwarg as a
        # list of {"src": [x, y], "tgt": [x, y]} pairs. Use this when
        # automatic correspondence (polar / TPS-auto / regions) misses
        # an anatomical feature you can place by eye.
        try:
            from scipy.interpolate import RBFInterpolator as _RBF
            from scipy.ndimage import map_coordinates as _map_coords
        except Exception as e:
            raise RuntimeError(f"landmark method needs scipy ({e})")
        lms = list(landmarks or [])
        if len(lms) < 6:
            raise RuntimeError(
                f"landmark method needs ≥6 paired landmarks; got {len(lms)}")
        tgt_kpts = _np.array([[lm["tgt"][0], lm["tgt"][1]] for lm in lms],
                              dtype=_np.float64)
        # Source landmarks arrive in SOURCE-PHOTO NATIVE pixel coords
        # (e.g. 377 in a 1536-wide photo). Convert to the canvas-rendered
        # src_full coordinate system the TPS will sample from. Without
        # this, every src_x > cw clips to (cw-1) and the whole transfer
        # paints zero pixels (entire wing maps off the source silhouette).
        src_photo = _PIL.open(p_ref.image_path)
        src_pw, src_ph = src_photo.size
        src_kpts = _np.array(
            [[lm["src"][0] / max(src_pw, 1) * cw,
              lm["src"][1] / max(src_ph, 1) * ch] for lm in lms],
            dtype=_np.float64)
        # Inverse TPS: target_xy → source_xy.
        rbf_x = _RBF(tgt_kpts, src_kpts[:, 0],
                      kernel="thin_plate_spline", smoothing=1e-3)
        rbf_y = _RBF(tgt_kpts, src_kpts[:, 1],
                      kernel="thin_plate_spline", smoothing=1e-3)
        ty_min, ty_max = int(model_ys.min()), int(model_ys.max())
        tx_min, tx_max = int(model_xs.min()), int(model_xs.max())
        yy, xx = _np.mgrid[ty_min:ty_max + 1, tx_min:tx_max + 1]
        grid = _np.column_stack([xx.ravel(), yy.ravel()]).astype(_np.float64)
        src_x = rbf_x(grid).reshape(yy.shape)
        src_y = rbf_y(grid).reshape(yy.shape)
        src_x = _np.clip(src_x, 0, src_full.shape[1] - 1)
        src_y = _np.clip(src_y, 0, src_full.shape[0] - 1)
        coords = _np.array([src_y, src_x], dtype=_np.float64)
        warped = _np.zeros((yy.shape[0], yy.shape[1], 4), dtype=_np.uint8)
        for ch in range(3):
            samp = _map_coords(
                src_full[..., ch].astype(_np.float32), coords,
                order=3, mode="reflect", prefilter=False)
            warped[..., ch] = _np.clip(samp, 0, 255).astype(_np.uint8)
        bf_sampled = _map_coords(
            butterfly.astype(_np.float32), coords,
            order=1, mode="constant", cval=0.0)
        warped_silhouette = bf_sampled > 0.4
        warped[..., 3] = warped_silhouette.astype(_np.uint8) * 255
        local_x = model_xs - tx_min
        local_y = model_ys - ty_min
        bf_target = warped_silhouette[local_y, local_x]
        in_bounds = ((model_xs >= 0) & (model_xs < pw)
                      & (model_ys >= 0) & (model_ys < ph)
                      & bf_target)
        cols = warped[local_y[in_bounds], local_x[in_bounds]].copy()
        cols[:, 3] = 255
        mask_obj.buf[model_ys[in_bounds], model_xs[in_bounds]] = cols
        transferred = int(in_bounds.sum())
        result_extra = {
            "method":      "landmark",
            "n_landmarks": int(len(lms)),
            "warped_size": [int(yy.shape[1]), int(yy.shape[0])],
        }
    elif method == "polar":
        # Polar reparameterisation around the wing tip.
        # For every model wing pixel compute (r/r_max(θ), θ) relative
        # to the model wing's tip; sample the source at the SAME
        # (r/r_max_source(θ), θ) relative to the source wing's tip.
        # r_max(θ) is the silhouette's outer radius along angle θ, so
        # we collapse each wing into the same normalized polar shell
        # and a band at "halfway between wing tip and wing root" maps
        # to its anatomical equivalent regardless of wing shape.
        try:
            from scipy.ndimage import map_coordinates as _map_coords
        except Exception as e:
            raise RuntimeError(f"polar method needs scipy ({e})")
        # Pick tip and body-anchor as before (side-aware).
        ys, xs = _np.where(model_mask)
        if side == "left":
            tip_score = ys + xs;   base_score = -xs
        else:
            tip_score = ys - xs;   base_score = xs
        tip_idx  = int(_np.argmin(tip_score))
        base_idx = int(_np.argmin(base_score))
        tgt_tip   = (float(xs[tip_idx]),  float(ys[tip_idx]))
        tgt_base  = (float(xs[base_idx]), float(ys[base_idx]))
        ref_butterfly = butterfly
        sys_, sxs_ = _np.where(ref_butterfly)
        if side == "left":
            keep_src = sxs_ <= ((sxs_.min() + sxs_.max()) // 2)
        else:
            keep_src = sxs_ >  ((sxs_.min() + sxs_.max()) // 2)
        sys_s, sxs_s = sys_[keep_src], sxs_[keep_src]
        if side == "left":
            stip_score = sys_s + sxs_s;   sbase_score = -sxs_s
        else:
            stip_score = sys_s - sxs_s;   sbase_score = sxs_s
        s_tip_idx  = int(_np.argmin(stip_score))
        s_base_idx = int(_np.argmin(sbase_score))
        src_tip   = (float(sxs_s[s_tip_idx]),  float(sys_s[s_tip_idx]))
        src_base  = (float(sxs_s[s_base_idx]), float(sys_s[s_base_idx]))

        # Build r_max(θ) tables for both wings: discretise θ into N_BINS
        # bins, store the max distance-from-tip of any silhouette pixel
        # whose angle falls in that bin.
        N_BINS = 360
        def _rmax_table(ys_arr, xs_arr, tip_xy):
            dx = xs_arr.astype(_np.float64) - tip_xy[0]
            dy = ys_arr.astype(_np.float64) - tip_xy[1]
            r  = _np.hypot(dx, dy)
            th = _np.arctan2(dy, dx)        # [-π, π]
            bin_idx = _np.clip(
                ((th + _np.pi) / (2 * _np.pi) * N_BINS).astype(_np.int64),
                0, N_BINS - 1)
            table = _np.zeros(N_BINS, dtype=_np.float64)
            _np.maximum.at(table, bin_idx, r)
            # Smooth small gaps with a 5-bin running max so isolated
            # bins with no samples don't read 0.
            for _ in range(2):
                table = _np.maximum.reduce(
                    [table,
                      _np.roll(table, 1), _np.roll(table, -1),
                      _np.roll(table, 2), _np.roll(table, -2)])
            return table

        tgt_rmax = _rmax_table(ys, xs, tgt_tip)
        src_rmax = _rmax_table(sys_s, sxs_s, src_tip)

        # Also need the angle from each wing's tip → root to define a
        # rotational alignment. Map both tip→root vectors to angle 0
        # so the wings agree on "which way is body-side".
        tgt_root_ang = math.atan2(tgt_base[1] - tgt_tip[1],
                                    tgt_base[0] - tgt_tip[0])
        src_root_ang = math.atan2(src_base[1] - src_tip[1],
                                    src_base[0] - src_tip[0])

        # For each target pixel, compute its (r_norm, θ_norm), translate
        # to source coords, sample source bicubic.
        my_min, my_max = int(ys.min()), int(ys.max())
        mx_min, mx_max = int(xs.min()), int(xs.max())
        mbw = mx_max - mx_min + 1
        mbh = my_max - my_min + 1
        yy_g, xx_g = _np.mgrid[my_min:my_max + 1, mx_min:mx_max + 1]
        dx = xx_g.astype(_np.float64) - tgt_tip[0]
        dy = yy_g.astype(_np.float64) - tgt_tip[1]
        r  = _np.hypot(dx, dy)
        th = _np.arctan2(dy, dx)
        # θ relative to the wing's tip→root direction.
        th_norm = (th - tgt_root_ang)
        # Normalise to source θ space.
        th_src = th_norm + src_root_ang
        # Wrap to [-π, π].
        th_src = (th_src + _np.pi) % (2 * _np.pi) - _np.pi
        # Look up r_max(θ) on both sides.
        bin_t = _np.clip(
            ((th + _np.pi) / (2 * _np.pi) * N_BINS).astype(_np.int64),
            0, N_BINS - 1)
        bin_s = _np.clip(
            ((th_src + _np.pi) / (2 * _np.pi) * N_BINS).astype(_np.int64),
            0, N_BINS - 1)
        r_max_t = tgt_rmax[bin_t]
        r_max_s = src_rmax[bin_s]
        r_norm = _np.where(r_max_t > 1e-6, r / r_max_t, 0.0)
        r_src  = r_norm * r_max_s
        src_x = src_tip[0] + r_src * _np.cos(th_src)
        src_y = src_tip[1] + r_src * _np.sin(th_src)
        src_x = _np.clip(src_x, 0, src_full.shape[1] - 1)
        src_y = _np.clip(src_y, 0, src_full.shape[0] - 1)

        coords = _np.array([src_y, src_x], dtype=_np.float64)
        refined = _np.zeros((mbh, mbw, 4), dtype=_np.uint8)
        for ch in range(3):
            samp = _map_coords(
                src_full[..., ch].astype(_np.float32), coords,
                order=3, mode="reflect", prefilter=False)
            refined[..., ch] = _np.clip(samp, 0, 255).astype(_np.uint8)
        # Source silhouette gate at the polar-mapped coords so we only
        # accept color from inside the source butterfly.
        bf_sampled = _map_coords(
            butterfly.astype(_np.float32), coords,
            order=1, mode="constant", cval=0.0)
        warped_silhouette = bf_sampled > 0.4
        refined[..., 3] = warped_silhouette.astype(_np.uint8) * 255
        # Composite gated by the target wing silhouette.
        local_x = model_xs - mx_min
        local_y = model_ys - my_min
        bf_target = warped_silhouette[local_y, local_x]
        in_bounds = ((model_xs >= 0) & (model_xs < pw)
                      & (model_ys >= 0) & (model_ys < ph)
                      & bf_target)
        cols = refined[local_y[in_bounds], local_x[in_bounds]].copy()
        cols[:, 3] = 255
        mask_obj.buf[model_ys[in_bounds], model_xs[in_bounds]] = cols
        transferred = int(in_bounds.sum())
        result_extra = {
            "method":       "polar",
            "tgt_tip":      [tgt_tip[0], tgt_tip[1]],
            "src_tip":      [src_tip[0], src_tip[1]],
            "warped_size":  [mbw, mbh],
            "n_bins":       N_BINS,
        }
    elif method == "flow":
        # bbox-warp base + Farneback dense optical flow refinement.
        # The alignment target is each wing's "distance-from-silhouette-
        # edge" scalar field: that's the one signal that exists on
        # both wings and shares semantic meaning (iridescent bands in
        # the Blue Morpho roughly follow iso-distance contours), so
        # aligning these fields locks the source's bands onto the
        # model wing's distance-equivalent positions.
        try:
            from scipy.ndimage import distance_transform_edt as _edt
        except Exception as e:
            raise RuntimeError(f"flow method needs scipy ({e})")
        # Lazy cv2 import (only required for this method).
        _have_cv2 = False
        try:
            import cv2 as _cv2
            _have_cv2 = True
        except Exception:
            from skimage.registration import optical_flow_ilk as _skflow

        my_min, my_max = int(model_ys.min()), int(model_ys.max())
        mx_min, mx_max = int(model_xs.min()), int(model_xs.max())
        mbw = mx_max - mx_min + 1; mbh = my_max - my_min + 1
        sy_min, sy_max = int(ref_ys.min()), int(ref_ys.max())
        sx_min, sx_max = int(ref_xs.min()), int(ref_xs.max())
        # ---- bbox-warp base ------------------------------------------
        src_crop  = src_full[sy_min:sy_max + 1, sx_min:sx_max + 1]
        bf_crop   = butterfly[sy_min:sy_max + 1, sx_min:sx_max + 1]
        crop_pil  = _PIL.fromarray(src_crop, mode="RGBA")
        bf_pil    = _PIL.fromarray(bf_crop.astype(_np.uint8) * 255, mode="L")
        if flip_h:
            crop_pil = crop_pil.transpose(_PIL.FLIP_LEFT_RIGHT)
            bf_pil   = bf_pil.transpose(_PIL.FLIP_LEFT_RIGHT)
        base_rgba = _np.asarray(crop_pil.resize((mbw, mbh), _PIL.LANCZOS)).copy()
        base_bf   = (_np.asarray(bf_pil.resize((mbw, mbh), _PIL.NEAREST)) > 0)
        # ---- tight target wing mask in bbox coords -------------------
        tgt_bbox = model_mask[my_min:my_max + 1, mx_min:mx_max + 1].astype(bool)
        # ---- distance fields (normalized) ----------------------------
        src_dt = _edt(base_bf).astype(_np.float32)
        tgt_dt = _edt(tgt_bbox).astype(_np.float32)
        if src_dt.max() > 0: src_dt /= src_dt.max()
        if tgt_dt.max() > 0: tgt_dt /= tgt_dt.max()
        # ---- compute dense flow: source-dt → target-dt ---------------
        if _have_cv2:
            flow = _cv2.calcOpticalFlowFarneback(
                src_dt, tgt_dt, None,
                pyr_scale=0.5, levels=4, winsize=15,
                iterations=5, poly_n=5, poly_sigma=1.2, flags=0)
            # cv2 flow shape: (H, W, 2) = (dx, dy).
            flow_y = flow[..., 1]; flow_x = flow[..., 0]
        else:
            flow = _skflow(src_dt, tgt_dt, radius=7, num_warp=5,
                            gaussian=True)
            flow_y = flow[0]; flow_x = flow[1]
        # ---- remap the bbox-warped color using the flow -------------
        yy, xx = _np.mgrid[0:mbh, 0:mbw].astype(_np.float32)
        map_y = _np.clip(yy + flow_y, 0, mbh - 1)
        map_x = _np.clip(xx + flow_x, 0, mbw - 1)
        coords = _np.array([map_y, map_x])
        refined = _np.zeros((mbh, mbw, 4), dtype=_np.uint8)
        from scipy.ndimage import map_coordinates as _map_coords
        for ch in range(3):
            samp = _map_coords(
                base_rgba[..., ch].astype(_np.float32), coords,
                order=3, mode="reflect", prefilter=False)
            refined[..., ch] = _np.clip(samp, 0, 255).astype(_np.uint8)
        # Source silhouette gate (warped along with the flow).
        bf_warped = _map_coords(
            base_bf.astype(_np.float32), coords,
            order=1, mode="constant", cval=0.0) > 0.4
        refined[..., 3] = bf_warped.astype(_np.uint8) * 255
        # ---- composite into PaintMask --------------------------------
        local_x = model_xs - mx_min
        local_y = model_ys - my_min
        bf_target = bf_warped[local_y, local_x]
        in_bounds = ((model_xs >= 0) & (model_xs < pw)
                      & (model_ys >= 0) & (model_ys < ph)
                      & bf_target)
        cols = refined[local_y[in_bounds], local_x[in_bounds]].copy()
        cols[:, 3] = 255
        mask_obj.buf[model_ys[in_bounds], model_xs[in_bounds]] = cols
        transferred = int(in_bounds.sum())
        # Flow magnitude stats so we can see how much it actually moved.
        mag = _np.sqrt(flow_x ** 2 + flow_y ** 2)
        result_extra = {
            "method":              "flow",
            "engine":              "cv2.Farneback" if _have_cv2 else "skimage.ilk",
            "warped_size":         [mbw, mbh],
            "flow_max_pixels":     float(mag.max()),
            "flow_mean_pixels":    float(mag.mean()),
            "model_bbox":          [mx_min, my_min, mx_max, my_max],
        }
    elif method == "sweep":
        # Legacy 'sweep' method: zig-zag row-major. Pattern is lost.
        sort_idx = _np.lexsort((model_xs, model_ys))
        model_ys = model_ys[sort_idx]; model_xs = model_xs[sort_idx]
        sort_idx = _np.lexsort((ref_xs, ref_ys))
        ref_ys = ref_ys[sort_idx]; ref_xs = ref_xs[sort_idx]
        if N_ref == N_model:
            ref_colors = src_full[ref_ys, ref_xs]
        else:
            sample = _np.linspace(0, N_ref - 1, N_model).astype(_np.int64)
            ref_colors = src_full[ref_ys[sample], ref_xs[sample]]
        chunk = max(1, N_model // max(1, int(n_regions)))
        for r in range(int(n_regions)):
            i0 = r * chunk
            i1 = N_model if r == int(n_regions) - 1 else min(N_model, (r + 1) * chunk)
            if i0 >= N_model: break
            my = model_ys[i0:i1]; mx = model_xs[i0:i1]
            cols = ref_colors[i0:i1].copy()
            cols[:, 3] = _np.maximum(cols[:, 3], 255)
            in_bounds = (mx >= 0) & (mx < pw) & (my >= 0) & (my < ph)
            mask_obj.buf[my[in_bounds], mx[in_bounds]] = cols[in_bounds]
            transferred += int(in_bounds.sum())
            if r < 5 or r == int(n_regions) - 1:
                region_summaries.append(
                    {"region": r, "i0": int(i0), "i1": int(i1),
                      "pixels": int(in_bounds.sum())})
        result_extra = {"method": "sweep", "chunk_size": int(chunk)}
    # ----- flush caches so next paint pulls the updated mask --------------
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache",
                "_paint_mask_files", "_paint_mask_png_cache"):
        c = getattr(designer, ca, None)
        if c is not None:
            try: c.clear()
            except Exception: pass
    if hasattr(designer, "_brush_dirty"):
        designer._brush_dirty.add(pm_key)
    # paint_only_empty restoration: overwrite any pixel that was already
    # painted before this call back to its pre-paint state. Net effect:
    # this transfer's new color only lands in pixels that were
    # previously empty. Useful for layering: e.g. bbox-warp first to
    # fill the bulk, then landmark TPS to fill the gaps.
    preserved_overwrites = 0
    if paint_only_empty and _pre_alpha is not None:
        keep = _pre_alpha > 0
        # Count how many pixels we "rescued" (would have been overwritten).
        preserved_overwrites = int((keep & (mask_obj.buf[..., 3] > 0)
                                     & ((mask_obj.buf[..., :3] != _pre_rgb).any(axis=-1))).sum())
        mask_obj.buf[keep, :3] = _pre_rgb[keep]
        mask_obj.buf[keep, 3]  = _pre_alpha[keep]
        # New pixels = currently filled minus previously filled.
        new_pixels = int(((mask_obj.buf[..., 3] > 0) & ~keep).sum())
        transferred = new_pixels   # report only the newly-painted count
    out = {
        "transferred_pixels": transferred,
        "n_regions":          int(n_regions),
        "model_wing_pixels":  N_model,
        "ref_wing_pixels":    N_ref,
        "regions_sample":     region_summaries,
    }
    out.update(result_extra)
    if paint_only_empty:
        out["paint_only_empty"]    = True
        out["preserved_overwrites"] = preserved_overwrites
    if _tps_fallback_reason is not None:
        out["method"] = "tps→bbox_warp_fallback"
        out["tps_fallback_reason"] = _tps_fallback_reason
    return out


# ──────────────────────────────────────────────────────────────────────
#   UV-space bake + normal-map pipeline for PBR-driven iridescence.
# ──────────────────────────────────────────────────────────────────────

@register_tool(
    name="mesh.bake_paint_mask_to_uv_albedo",
    description="Back-project a placement's screen-space PaintMask into "
                "UV space and bind the result as the named sub-mesh "
                "part's `albedo` map (per-part material slot). Uses the "
                "same ray-trace pass as the renderer so each canvas "
                "pixel maps to the exact mesh UV the renderer would "
                "sample from that pixel.\n\n"
                "After baking the tool optionally clears the PaintMask "
                "(default ON) so PBR shading takes over from the screen-"
                "space overlay: that's what lets `mesh.generate_normal_"
                "map_from_albedo` actually catch light through the PBR "
                "shader on subsequent renders. Saves the UV-mapped PNG "
                "under ``~/.elysium/textures/<placement>_<part>_baked.png``.",
    input_schema={
        "type": "object",
        "properties": {
            "id":          {"type": "string"},
            "part":        {"type": "string"},
            "uv_w":        {"type": "integer"},
            "uv_h":        {"type": "integer"},
            "clear_mask":  {"type": "boolean"},
            "out":         {"type": "string"},
        },
        "required": ["id", "part"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_bake_paint_mask_to_uv_albedo(session, id: str, part: str,
                                        uv_w: int = 1024, uv_h: int = 1024,
                                        clear_mask: bool = True,
                                        out: str = "") -> dict:
    import numpy as _np
    from PIL import Image as _PIL
    from pathlib import Path as _Path
    from builtins import id as _obj_id
    from elysium.render import pbr as _pbr
    designer = session.designer
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError("bake_paint_mask_to_uv_albedo is Mesh3D-only")
    pm = (getattr(designer, "paint_masks", None) or {}).get(_obj_id(p))
    if pm is None or not pm.buf[..., 3].any():
        raise RuntimeError("placement has no PaintMask painted (nothing to bake)")
    mesh, obj = _build_mesh_for_placement(p)
    if mesh.vert_uvs is None:
        raise RuntimeError(f"mesh has no UVs; can't bake a UV-space albedo")
    if mesh.part_names is None or part not in mesh.part_names:
        raise KeyError(f"unknown part {part!r}; have {mesh.part_names}")
    pid = mesh.part_names.index(part)
    rw, rh = max(8, int(round(float(p.w)))), max(8, int(round(float(p.h))))
    yaw   = float(getattr(p, "mesh_yaw",   0.4))
    pitch = float(getattr(p, "mesh_pitch", 0.25))
    dist  = float(getattr(p, "mesh_dist", None) or 3.5)
    face_idx, part_id, uv_xy = _pbr.render_mesh_uvmap(
        rw, rh, obj, cam_dist=dist, cam_yaw=yaw, cam_pitch=pitch)
    if getattr(p, "mesh_flip_y", False):
        face_idx = face_idx[::-1, :].copy()
        part_id  = part_id[::-1, :].copy()
        uv_xy    = uv_xy[::-1, :, :].copy()
    in_part = (part_id == pid)
    ys, xs = _np.where(in_part)
    if len(ys) == 0:
        raise RuntimeError(f"no rendered pixels for part {part!r}")
    # The PaintMask is sized to int(p.w) × int(p.h) (see PaintMask
    # construction in _ensure_brush_mask). The partmap/uvmap is also
    # rendered at the same nominal dims via round(p.w), round(p.h), so
    # both grids match.
    pw, ph = pm.w, pm.h
    in_bounds = (xs >= 0) & (xs < pw) & (ys >= 0) & (ys < ph)
    ys = ys[in_bounds]; xs = xs[in_bounds]
    # Only bake pixels where the PaintMask has paint (alpha > 0).
    mask_rgba = pm.buf[ys, xs]
    has_paint = mask_rgba[:, 3] > 0
    ys = ys[has_paint]; xs = xs[has_paint]
    mask_rgba = mask_rgba[has_paint]
    if len(ys) == 0:
        raise RuntimeError("PaintMask has no painted pixels in this part")
    uvs = uv_xy[ys, xs]
    # Convert (u, v) ∈ [0, 1] → UV-texture pixel (col=u*(W-1), row=(1-v)*(H-1)).
    u = _np.clip(uvs[:, 0], 0.0, 1.0)
    v = _np.clip(uvs[:, 1], 0.0, 1.0)
    uw = max(8, int(uv_w)); uh = max(8, int(uv_h))
    uc = (u * (uw - 1)).astype(_np.int64)
    # Use v directly (not 1-v): the PBR sampler in this codebase reads
    # texture row = v * (H-1): confirmed by checking
    # _sample_material_textures + the mesh's existing wing albedo
    # binding. Flipping V here produces a black wing because the chart
    # lands on transparent rows of the baked PNG.
    ur = (v * (uh - 1)).astype(_np.int64)
    # Build the UV texture: start transparent, then stamp paint at each
    # UV pixel. Where the mesh's UV unwrap maps two canvas pixels onto
    # the same UV pixel, the second write wins (it's a baking choice,
    # not an artefact).
    uv_tex = _np.zeros((uh, uw, 4), dtype=_np.uint8)
    uv_tex[ur, uc] = mask_rgba
    # Fill EVERY transparent UV pixel with the nearest stamped pixel's
    # color. We don't know which parts of the UV chart for this part
    # the renderer will sample, so we fill the whole texture and let
    # the renderer pull what it needs. Distance-transform with
    # return_indices=True gives us a 'nearest filled' lookup table for
    # every transparent pixel; cheap to evaluate (~1 ms at 1024²).
    from scipy.ndimage import distance_transform_edt as _edt
    have_paint = uv_tex[..., 3] > 0
    if not have_paint.any():
        raise RuntimeError("no UV pixels were stamped")
    _, (yy_idx, xx_idx) = _edt(~have_paint, return_indices=True)
    for c in range(3):
        ch = uv_tex[..., c]
        ch_filled = ch[yy_idx, xx_idx]
        ch[~have_paint] = ch_filled[~have_paint]
    uv_tex[..., 3] = 255   # whole texture opaque after fill
    # Save to disk.
    if out:
        out_path = _Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        textures_dir = _Path.home() / ".elysium" / "textures"
        textures_dir.mkdir(parents=True, exist_ok=True)
        out_path = textures_dir / f"{id}_{part}_baked.png"
    _PIL.fromarray(uv_tex, mode="RGBA").save(out_path)
    # Bind as per-part texture (slot=albedo) so the renderer samples
    # this for the named part.
    parts_tex = dict(getattr(p, "mesh_part_textures", None) or {})
    parts_tex[part] = str(out_path)
    p.mesh_part_textures = parts_tex
    if clear_mask:
        pm.buf[:] = 0
    # Bust caches so the next render uses the new texture.
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache",
                "_paint_mask_files", "_paint_mask_png_cache"):
        c = getattr(designer, ca, None)
        if c is not None:
            try: c.clear()
            except Exception: pass
    try:
        from elysium.render import pbr as _pbr2
        if hasattr(_pbr2, "_TEX_CACHE"):
            _pbr2._TEX_CACHE.clear()
    except Exception: pass
    return {
        "path":         str(out_path),
        "uv_size":      [uw, uh],
        "n_bakes":      int(len(ys)),
        "part":         part,
        "filled_pixels": int((~have_paint).sum()),
        "placement":    id,
    }


@register_tool(
    name="mesh.generate_normal_map_from_albedo",
    description="Generate a tangent-space normal map from a placement's "
                "UV-mapped albedo texture (the one currently bound for "
                "the named part) by running a Sobel gradient on the "
                "albedo's luminance, then bind it via "
                "material.set_part_texture(slot=\"normal\"). Use after "
                "`mesh.bake_paint_mask_to_uv_albedo` so the normal map "
                "is derived from the just-baked Blue Morpho color, "
                "giving the PBR shader something to catch light off "
                "(iridescence).",
    input_schema={
        "type": "object",
        "properties": {
            "id":         {"type": "string"},
            "part":       {"type": "string"},
            "strength":   {"type": "number"},
            "out":        {"type": "string"},
        },
        "required": ["id", "part"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_generate_normal_map_from_albedo(session, id: str, part: str,
                                           strength: float = 4.0,
                                           out: str = "") -> dict:
    import numpy as _np
    from PIL import Image as _PIL
    from pathlib import Path as _Path
    from scipy.ndimage import sobel as _sobel
    p = session.lookup(id)
    if p.kind != "Mesh3D":
        raise ValueError("generate_normal_map_from_albedo is Mesh3D-only")
    parts_tex = getattr(p, "mesh_part_textures", None) or {}
    albedo_path = parts_tex.get(part)
    if not albedo_path:
        albedo_path = getattr(p, "pbr_albedo_map", "") or getattr(p, "texture_path", "")
    if not albedo_path or not _Path(albedo_path).is_file():
        raise RuntimeError(
            f"no albedo texture bound for part {part!r} (looked at "
            f"mesh_part_textures + pbr_albedo_map); bake one first")
    img = _np.asarray(_PIL.open(albedo_path).convert("RGBA"), dtype=_np.float32)
    # Luminance for gradient magnitude.
    lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    # Sobel gradients.
    gx = _sobel(lum, axis=1, mode="reflect") / 255.0
    gy = _sobel(lum, axis=0, mode="reflect") / 255.0
    s = float(strength)
    # Tangent-space normal: (-gx, -gy, 1/strength) normalized.
    nx = -gx * s
    ny = -gy * s
    nz = _np.ones_like(nx)
    norm = _np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= norm; ny /= norm; nz /= norm
    # Encode 0..1 then 0..255.
    rgb = _np.stack([
        ((nx * 0.5 + 0.5) * 255).clip(0, 255),
        ((ny * 0.5 + 0.5) * 255).clip(0, 255),
        ((nz * 0.5 + 0.5) * 255).clip(0, 255),
    ], axis=-1).astype(_np.uint8)
    # Preserve the source's alpha so the normal map masks to wing.
    alpha = (img[..., 3]).astype(_np.uint8)
    rgba = _np.concatenate([rgb, alpha[..., None]], axis=-1)
    if out:
        out_path = _Path(out)
    else:
        out_path = _Path(albedo_path).with_name(
            _Path(albedo_path).stem + "_normal.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _PIL.fromarray(rgba, mode="RGBA").save(out_path)
    # The framework's PBR material has a `normal_map` slot reached
    # through `pbr_normal_map_map` on Placement (per the existing
    # field_map in material.set_texture). For per-part overrides we
    # use mesh_part_textures[part] with a slot-specific key: but the
    # current MeshObject build path only honours albedo overrides per
    # part. To get the normal map into the actual render we bind it
    # via the whole-placement `pbr_normal_map` field too; the .3ds
    # Monarch shares one normal map across the wings so this is fine.
    try:
        p.pbr_normal_map = str(out_path)
    except Exception:
        pass
    # Bust caches so the next render uses the new normal map.
    for ca in ("_mesh_cache", "_mesh_bytes_cache", "_pbr_cache",
                "_paint_mask_files", "_paint_mask_png_cache"):
        c = getattr(session.designer, ca, None)
        if c is not None:
            try: c.clear()
            except Exception: pass
    try:
        from elysium.render import pbr as _pbr2
        if hasattr(_pbr2, "_TEX_CACHE"):
            _pbr2._TEX_CACHE.clear()
    except Exception: pass
    return {
        "path":      str(out_path),
        "size":      [rgba.shape[1], rgba.shape[0]],
        "strength":  s,
        "part":      part,
    }


@register_tool(
    name="mesh.transfer_polar_with_normal_map",
    description="One-shot pipeline: run polar transfer for Wing_Left, "
                "bake the PaintMask into a UV-space albedo for the "
                "part, then generate + bind a Sobel-derived normal map "
                "so the wing catches light through the PBR shader. "
                "This is the full path from a reference photo to a "
                "PBR-lit iridescent wing in one menu click.",
    input_schema={
        "type": "object",
        "properties": {
            "model_id":   {"type": "string"},
            "ref_id":     {"type": "string"},
            "part":       {"type": "string"},
            "side":       {"type": "string", "enum": ["left", "right"]},
            "uv_w":       {"type": "integer"},
            "uv_h":       {"type": "integer"},
            "strength":   {"type": "number"},
        },
        "required": ["model_id", "ref_id"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_transfer_polar_with_normal_map(session,
                                          model_id: str, ref_id: str,
                                          part: str = "Wing_Left",
                                          side: str = "left",
                                          uv_w: int = 1024,
                                          uv_h: int = 1024,
                                          strength: float = 4.0) -> dict:
    out = {}
    out["polar"]  = mesh_transfer_wing_from_reference(
        session=session, model_id=model_id, ref_id=ref_id,
        model_part=part, side=side, n_regions=100, method="polar",
        clear_mask=True)
    out["bake"]   = mesh_bake_paint_mask_to_uv_albedo(
        session=session, id=model_id, part=part,
        uv_w=uv_w, uv_h=uv_h, clear_mask=True)
    out["normal"] = mesh_generate_normal_map_from_albedo(
        session=session, id=model_id, part=part, strength=strength)
    return out


# ──────────────────────────────────────────────────────────────────────
# Manual landmark workflow: save / load JSON presets + a thin wrapper
# that runs the landmark TPS transfer end-to-end.
# ──────────────────────────────────────────────────────────────────────

_LANDMARK_DIR = "~/.elysium/landmarks"

def _landmark_dir():
    from pathlib import Path
    p = Path(_LANDMARK_DIR).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


@register_tool(
    name="mesh.save_landmarks",
    description="Persist a list of paired source/target landmarks as a "
                "JSON preset under ~/.elysium/landmarks/<name>.json so "
                "the manual landmark transfer can be replayed across "
                "sessions / wings / models.",
    input_schema={
        "type": "object",
        "properties": {
            "name":      {"type": "string"},
            "landmarks": {"type": "array", "items": {"type": "object"}},
            "meta":      {"type": "object"},
        },
        "required": ["name", "landmarks"],
    },
)
def mesh_save_landmarks(session, name: str, landmarks: list,
                         meta: dict | None = None) -> dict:
    import json
    path = _landmark_dir() / f"{name}.json"
    payload = {"name": name,
               "landmarks": [
                   {"src": list(lm["src"]), "tgt": list(lm["tgt"]),
                    "label": lm.get("label", "")}
                   for lm in landmarks],
               "meta": meta or {}}
    path.write_text(json.dumps(payload, indent=2))
    return {"path": str(path), "n": len(payload["landmarks"])}


@register_tool(
    name="mesh.load_landmarks",
    description="Read a landmark preset saved by mesh.save_landmarks.",
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    side_effect=SideEffect.READ, undoable=False,
)
def mesh_load_landmarks(session, name: str) -> dict:
    import json
    path = _landmark_dir() / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no landmark preset {name!r} at {path}")
    return json.loads(path.read_text())


@register_tool(
    name="mesh.list_landmark_presets",
    description="List all saved landmark presets under ~/.elysium/landmarks.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ, undoable=False,
)
def mesh_list_landmark_presets(session) -> dict:
    import json
    out = []
    for p in sorted(_landmark_dir().glob("*.json")):
        try:
            data = json.loads(p.read_text())
            out.append({"name": p.stem, "n": len(data.get("landmarks", [])),
                         "meta": data.get("meta", {})})
        except Exception as e:
            out.append({"name": p.stem, "error": repr(e)[:120]})
    return {"presets": out, "dir": str(_landmark_dir())}


@register_tool(
    name="mesh.transfer_landmark_with_normal_map",
    description="One-shot pipeline using manually placed landmarks: "
                "run TPS transfer driven by the supplied landmark "
                "pairs, bake the result to a UV-space albedo for the "
                "named part, then generate + bind a normal map for "
                "PBR-driven iridescence under the studio lighting.",
    input_schema={
        "type": "object",
        "properties": {
            "model_id":   {"type": "string"},
            "ref_id":     {"type": "string"},
            "part":       {"type": "string"},
            "side":       {"type": "string", "enum": ["left", "right"]},
            "landmarks":  {"type": "array", "items": {"type": "object"}},
            "uv_w":       {"type": "integer"},
            "uv_h":       {"type": "integer"},
            "strength":   {"type": "number"},
        },
        "required": ["model_id", "ref_id", "landmarks"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_transfer_landmark_with_normal_map(session,
                                             model_id: str, ref_id: str,
                                             landmarks: list,
                                             part: str = "Wing_Left",
                                             side: str = "left",
                                             uv_w: int = 1024,
                                             uv_h: int = 1024,
                                             strength: float = 4.0) -> dict:
    out = {}
    out["landmark"] = mesh_transfer_wing_from_reference(
        session=session, model_id=model_id, ref_id=ref_id,
        model_part=part, side=side, n_regions=100, method="landmark",
        clear_mask=True, landmarks=landmarks)
    out["bake"]   = mesh_bake_paint_mask_to_uv_albedo(
        session=session, id=model_id, part=part,
        uv_w=uv_w, uv_h=uv_h, clear_mask=True)
    out["normal"] = mesh_generate_normal_map_from_albedo(
        session=session, id=model_id, part=part, strength=strength)
    return out


@register_tool(
    name="mesh.transfer_bbox_then_landmark_gaps",
    description="Layered transfer: run bbox_warp first (fills the bulk "
                "of the wing with the source pattern's overall layout), "
                "then run landmark TPS in `paint_only_empty` mode to "
                "fill only the gaps bbox_warp left transparent (where "
                "the source butterfly silhouette didn't cover the warped "
                "bbox), then bake to a UV-space albedo and generate a "
                "normal map for PBR-driven iridescence.\n\n"
                "Needs ≥6 paired landmarks. Use this when the bbox-warp "
                "baseline looks good for the wing's central pattern "
                "but leaves anatomical regions (wing tip / outer rim / "
                "inner cell) uncovered.",
    input_schema={
        "type": "object",
        "properties": {
            "model_id":  {"type": "string"},
            "ref_id":    {"type": "string"},
            "part":      {"type": "string"},
            "side":      {"type": "string", "enum": ["left", "right"]},
            "landmarks": {"type": "array", "items": {"type": "object"}},
            "uv_w":      {"type": "integer"},
            "uv_h":      {"type": "integer"},
            "strength":  {"type": "number"},
        },
        "required": ["model_id", "ref_id", "landmarks"],
    },
    side_effect=SideEffect.WRITE, undoable=False,
)
def mesh_transfer_bbox_then_landmark_gaps(session,
                                            model_id: str, ref_id: str,
                                            landmarks: list,
                                            part: str = "Wing_Left",
                                            side: str = "left",
                                            uv_w: int = 1024,
                                            uv_h: int = 1024,
                                            strength: float = 4.0) -> dict:
    if len(landmarks) < 6:
        raise RuntimeError(
            f"need ≥6 paired landmarks for the landmark gap-fill step; "
            f"got {len(landmarks)}")
    out: dict = {}
    out["bbox"]     = mesh_transfer_wing_from_reference(
        session=session, model_id=model_id, ref_id=ref_id,
        model_part=part, side=side, n_regions=100,
        method="bbox_warp", clear_mask=True)
    out["landmark_gaps"] = mesh_transfer_wing_from_reference(
        session=session, model_id=model_id, ref_id=ref_id,
        model_part=part, side=side, n_regions=100,
        method="landmark", clear_mask=False,
        paint_only_empty=True, landmarks=landmarks)
    out["bake"]   = mesh_bake_paint_mask_to_uv_albedo(
        session=session, id=model_id, part=part,
        uv_w=uv_w, uv_h=uv_h, clear_mask=True)
    out["normal"] = mesh_generate_normal_map_from_albedo(
        session=session, id=model_id, part=part, strength=strength)
    return out


# ---------------------------------------------------------------------------
# Phase 1m: generic bridge-tool aliases.
#
# The wing-named bridge tools above keep their original IDs so any saved
# scripts / Aether transcripts / external automation continues to work.
# Each gets a generic alias under a part-targeted name so the
# user-facing tool catalog (which the AI agent reads) doesn't expose the
# butterfly demo's vocabulary. Aliases are thin `dataclasses.replace`
# clones of the original Tool: same function pointer, just a new name +
# trimmed-down description noting the generic naming.
# ---------------------------------------------------------------------------

def _add_generic_alias(old_name: str, new_name: str,
                        new_description: str | None = None) -> None:
    """Look up `old_name` in the global REGISTRY and add a clone of it
    under `new_name`. Silently skipped if the original isn't registered
    (e.g. a partial-import dev-reload state)."""
    from dataclasses import replace as _replace
    from . import REGISTRY as _reg
    orig = _reg.get(old_name)
    if orig is None:
        return
    _reg.add(_replace(
        orig,
        name=new_name,
        description=new_description or orig.description,
    ))


_PHASE_1M_ALIASES: list[tuple[str, str, str]] = [
    # (old_wing_name, new_generic_name, optional_new_description)
    (
        "mesh.transfer_wing_from_reference",
        "mesh.transfer_part_from_reference",
        "Pattern-preserving transfer of a reference Image's pixels onto a "
        "Mesh3D placement's named part (e.g. a left/right surface pair). "
        "Method options: bbox_warp / sweep / tps / flow / polar / "
        "regions / landmark.",
    ),
    (
        "image.lasso_left_wing_tip_pct",
        "image.lasso_corner_pct",
        "Lasso the top N%% of an Image's specified corner so the lasso "
        "polygon can drive a downstream landmark / transfer step.",
    ),
]

for _old, _new, _desc in _PHASE_1M_ALIASES:
    _add_generic_alias(_old, _new, _desc)
