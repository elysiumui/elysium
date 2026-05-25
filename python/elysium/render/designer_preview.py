"""Faithful preview render for a live Designer state.

The skin-document compiler (``paint_skin_png``) only knows
``path / image / text`` nodes — anything richer (``Mesh3D``,
``PBRSphere``, framework components, the materials + textures applied
to them) collapses to a purple rounded placeholder.

This module walks the **Designer's actual placement list**, dispatching
each placement through its appropriate render path (real PBR for
meshes, component paint for shipped widgets, image decode for raster
layers, etc.) into a fresh offscreen ``SkiaLayer``, then encodes PNG.

Used by the Aether bridge's ``/snapshot`` endpoint so external tools
(this Claude Code session, an IDE plugin, a CI screenshot diff) see the
same canvas the developer sees.
"""
from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path
from typing import Any


def paint_designer_png(designer) -> bytes:
    """Render the Designer's live placement state to a PNG matching the
    declared window_doc size. Skips Designer chrome — this is the
    skin frame, not the editor frame."""
    from elysium._native import _native as _n

    w = int(getattr(designer.window_doc, "w", 800))
    h = int(getattr(designer.window_doc, "h", 600))
    layer = _n.SkiaLayer(w, h)

    bg = tuple(getattr(designer.window_doc, "bg_color", (0, 0, 0, 0)))
    layer.clear(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0,
                 (bg[3] / 255.0) if len(bg) >= 4 else 1.0)

    dl = _n.DisplayList()
    for p in designer.placements:
        if getattr(p, "is_hotspot", False):
            continue
        _paint_placement(dl, p, designer)
    layer.execute(dl)
    return layer.encode_png()


# ---------------------------------------------------------------------------
# Per-placement dispatch.
# ---------------------------------------------------------------------------

def _paint_placement(dl, p, designer) -> None:
    # Apply runtime animation transform if any (so the user sees the
    # current frame of the playing timeline, not just the resting pose).
    ax = p.x + getattr(p, "_t_dx", 0.0)
    ay = p.y + getattr(p, "_t_dy", 0.0)
    alpha = getattr(p, "_t_opacity", 1.0)
    if alpha <= 0.01: return     # fully transparent placements skip

    kind = p.kind
    if kind == "Mesh3D":
        _paint_mesh3d(dl, p, ax, ay, alpha)
        # Composite the placement's PaintMask overlay (if any) on top of
        # the rendered mesh, the same way Designer._paint_one_placement
        # does in the live window — without this the snapshot doesn't
        # reflect mesh.transfer_wing_from_reference / brush strokes.
        try:
            masks = getattr(designer, "paint_masks", None) or {}
            mask = masks.get(id(p))
            if mask is not None and mask.buf[..., 3].any():
                import hashlib, tempfile, pathlib
                from PIL import Image as _PIL
                cache_dir = pathlib.Path(tempfile.gettempdir()) / "elysium-aether-snap"
                cache_dir.mkdir(exist_ok=True)
                key = hashlib.md5(mask.buf.tobytes()).hexdigest()[:14]
                pm_path = cache_dir / f"pm-{key}.png"
                if not pm_path.is_file():
                    _PIL.fromarray(mask.buf, mode="RGBA").save(pm_path)
                dl.draw_image_file(str(pm_path), ax, ay, p.w, p.h)
        except Exception:
            pass
    elif kind == "PBRSphere":
        _paint_pbr_sphere(dl, p, ax, ay, alpha)
    elif kind == "Shape":
        _paint_shape(dl, p, ax, ay, alpha)
    elif kind == "Image" and getattr(p, "image_path", ""):
        dl.draw_image_file(p.image_path, ax, ay, p.w, p.h)
    elif kind == "Label":
        _paint_label(dl, p, ax, ay, alpha)
    elif kind == "Button":
        _paint_button(dl, p, ax, ay, alpha)
    else:
        # Generic widget placeholder — keep the old fallback look so
        # the user sees *something* with the right bounds.
        dl.fill_path(_round_d(ax, ay, p.w, p.h, 8),
                      _alpha_color((91, 63, 245, 255), alpha))


# --- Mesh3D ---------------------------------------------------------------

_MESH_CACHE: dict[str, str] = {}


# Substrings (case-insensitive) that mark a sub-mesh as a "flap-able"
# rigged part. Imported models can use any of these in their part names
# — `Wing_Left`, `fin_R`, `Tail`, `LeftFlap`, etc. — and the generic
# flap helper will animate them. Extend this list (or pass an override
# at call time) to support new rigging conventions.
_FLAP_PART_KEYWORDS: tuple[str, ...] = (
    "wing", "fin", "limb", "ear", "tail", "flap",
)


def _flap_imported_parts(mesh, flap_radians: float, body_eps: float = 0.04,
                          part_keywords: tuple[str, ...] | None = None):
    """Flap the butterfly's wings.

    Two code paths:

    * RIG-DRIVEN — if the mesh carries `vert_part_ids` + `part_names` +
      `part_pivots` (the .3ds loader populates these from the named
      ``Wing_Left`` / ``Wing_Right`` / ``Body`` sub-meshes), rotate each
      wing's vertices around its actual rig pivot. Body verts stay put.

    * PROCEDURAL FALLBACK — for unrigged meshes, partition by
      ``x`` against ``body_eps`` and rotate the two halves around the
      mesh's body axis (auto-detected as the largest non-X extent).
    """
    if abs(flap_radians) < 1e-4: return mesh
    import numpy as np
    from elysium.render.pbr import Mesh
    v = mesh.verts.copy()

    if (mesh.vert_part_ids is not None and mesh.part_names is not None
            and mesh.part_pivots is not None):
        # Rig-driven path. Each wing rotates around its own pivot in
        # the plane spanned by the X axis (wing-span) and the camera-out
        # axis (the smallest of Y/Z by mesh extent). The X axis is the
        # natural hinge direction for wings.
        names = [n.lower() for n in mesh.part_names]
        # Pick the arc axis (the one the wing-tip dips into during flap).
        # Body-axis = the long one of Y/Z (where the body lives), arc-axis
        # = the perpendicular one. For a .3ds Z-up→Y-up swapped butterfly
        # the body runs along Y, arc plane is XZ.
        span_y = float(v[:, 1].max() - v[:, 1].min())
        span_z = float(v[:, 2].max() - v[:, 2].min())
        arc_axis = 2 if span_y >= span_z else 1
        for pid, name in enumerate(names):
            _kw = part_keywords if part_keywords is not None else _FLAP_PART_KEYWORDS
            if not any(k in name for k in _kw):
                continue                # body and other parts stay still
            mask = (mesh.vert_part_ids == pid)
            if not mask.any():
                continue
            sign = +1.0 if "left" in name else -1.0
            a = sign * flap_radians
            c, s = float(np.cos(a)), float(np.sin(a))
            pivot = mesh.part_pivots[pid]
            # Translate to pivot, rotate in (X, arc_axis) plane, translate back.
            px = v[mask, 0] - pivot[0]
            pa = v[mask, arc_axis] - pivot[arc_axis]
            v[mask, 0]        = pivot[0] + c * px + s * pa
            v[mask, arc_axis] = pivot[arc_axis] + (-s) * px + c * pa
    else:
        # Procedural fallback.
        span_y = float(v[:, 1].max() - v[:, 1].min())
        span_z = float(v[:, 2].max() - v[:, 2].min())
        body_axis = 1 if span_y >= span_z else 2
        arc_axis  = 2 if body_axis == 1 else 1
        is_l = v[:, 0] < -body_eps
        is_r = v[:, 0] > +body_eps
        for mask, sign in ((is_l, +1.0), (is_r, -1.0)):
            if not mask.any(): continue
            a = sign * flap_radians
            c, s = float(np.cos(a)), float(np.sin(a))
            x   = v[mask, 0]
            arc = v[mask, arc_axis]
            v[mask, 0]        = c * x + s * arc
            v[mask, arc_axis] = -s * x + c * arc

    return Mesh(verts=v.astype(mesh.verts.dtype),
                faces=mesh.faces.copy(),
                face_mats=(mesh.face_mats.copy() if mesh.face_mats is not None
                            else None),
                vert_uvs=(mesh.vert_uvs.copy() if mesh.vert_uvs is not None
                            else None),
                vert_part_ids=(mesh.vert_part_ids.copy()
                                if mesh.vert_part_ids is not None else None),
                part_names=(list(mesh.part_names)
                              if mesh.part_names is not None else None),
                part_pivots=(mesh.part_pivots.copy()
                              if mesh.part_pivots is not None else None))


# Back-compat alias — the helper used to be wing-specific (it was
# written for the butterfly demo). Phase 1n generic-ised the name to
# `_flap_imported_parts`; keep the old binding so any code that still
# imports it (or saved hot-reload state) keeps working.
_flap_imported_wings = _flap_imported_parts


def _part_is_flappable(part_names, keywords: tuple[str, ...] | None = None) -> bool:
    """True when ANY of the mesh's named parts matches one of the
    `_FLAP_PART_KEYWORDS` substrings (case-insensitive). Generic-ised
    in Phase 1n from the old hard-coded `"wing" in n.lower()` check so
    any imported rigged mesh (wings / fins / limbs / ears / tails /
    flaps) lights up the flap animation path."""
    if not part_names:
        return False
    _kw = keywords if keywords is not None else _FLAP_PART_KEYWORDS
    for n in part_names:
        ln = n.lower()
        if any(k in ln for k in _kw):
            return True
    return False


def _paint_mesh3d(dl, p, ax: float, ay: float, alpha: float) -> None:
    """Path-trace / render the Mesh3D placement through pbr.render_mesh
    and stamp the resulting bytes into the display list."""
    try:
        from elysium.render import pbr as pbr_engine
    except Exception:
        dl.fill_path(_round_d(ax, ay, p.w, p.h, 4),
                      _alpha_color((90, 90, 110, 255), alpha))
        return
    _parts_tex = getattr(p, "mesh_part_textures", None) or {}
    key = (p.mesh_kind, p.pbr_preset, p.pbr_metallic, p.pbr_roughness,
            p.pbr_clearcoat, p.pbr_clearcoat_roughness,
            getattr(p, "pbr_albedo_map", ""),
            getattr(p, "mesh_yaw", 0.4), getattr(p, "mesh_pitch", 0.25),
            getattr(p, "mesh_flap", 0.0),
            int(p.w), int(p.h),
            bool(getattr(p, "mesh_flip_y", False)),
            tuple(sorted(_parts_tex.items())),
            getattr(p, "pbr_normal_map", ""))
    h = hashlib.md5(repr(key).encode()).hexdigest()[:14]
    cached = _MESH_CACHE.get(h)
    if cached and Path(cached).is_file():
        dl.draw_image_file(cached, ax, ay, p.w, p.h)
        return

    # First-time render — go through the framework. Heavy but cached.
    # Generic mesh path: either an external file or a MESH_LIBRARY name.
    # A texture is always applied as `mat.albedo_map` on the existing
    # geometry — it must never swap the mesh itself.
    try:
        if p.mesh_kind.startswith("file:"):
            # Imported mesh (.obj / .gltf / .glb / .3ds).
            mesh_path = p.mesh_kind.split(":", 1)[1]
            mesh = pbr_engine.import_mesh_from_file(mesh_path)
            mesh = _flap_imported_parts(
                mesh, getattr(p, "mesh_flap", 0.0))
            from dataclasses import replace
            mat = (replace(pbr_engine.PRESETS[p.pbr_preset])
                    if p.pbr_preset in pbr_engine.PRESETS
                    else pbr_engine.Material(base_color=(1.0, 1.0, 1.0),
                                              metallic=0.0,
                                              roughness=0.55))
            mat.metallic = p.pbr_metallic
            mat.roughness = p.pbr_roughness
            mat.specular = p.pbr_specular
            mat.clear_coat = p.pbr_clearcoat
            mat.clear_coat_roughness = p.pbr_clearcoat_roughness
            # Honour pbr_use_color_fill on the file: branch too — without
            # this, an imported .3ds is forever stuck on the preset (or
            # white) base color and the color_fill setting is ignored.
            _use_cf = (getattr(p, "pbr_use_color_fill", False)
                        and getattr(p, "color_fill", None)
                        and p.color_fill[3] > 0)
            if _use_cf:
                mat.base_color = (p.color_fill[0]/255.0,
                                    p.color_fill[1]/255.0,
                                    p.color_fill[2]/255.0)
            albedo = (getattr(p, "pbr_albedo_map", "")
                       or getattr(p, "texture_path", ""))
            if albedo: mat.albedo_map = albedo
            # Per-part textures for the imported mesh (Monarch .3ds
            # has named parts Wing_Left / Wing_Right / Body).
            part_textures = dict(getattr(p, "mesh_part_textures", {}) or {})
            if (mesh.vert_part_ids is not None and mesh.part_names
                    and part_textures):
                import numpy as _np2
                from dataclasses import replace as _rep
                mats = []
                for pid, name in enumerate(mesh.part_names):
                    mi = pbr_engine.Material(
                        base_color=(1.0, 1.0, 1.0),
                        metallic=0.0, roughness=0.55)
                    mi.metallic = p.pbr_metallic
                    mi.roughness = p.pbr_roughness
                    mi.specular = p.pbr_specular
                    mi.clear_coat = p.pbr_clearcoat
                    mi.clear_coat_roughness = p.pbr_clearcoat_roughness
                    if _use_cf:
                        mi.base_color = mat.base_color
                    tex = part_textures.get(name, albedo)
                    if tex:
                        mi.albedo_map = tex
                    nrm = getattr(p, "pbr_normal_map", "")
                    if nrm:
                        mi.normal_map = nrm
                    mats.append(mi)
                face_part = mesh.vert_part_ids[mesh.faces[:, 0]].astype(_np2.int32)
                mesh = _rep(mesh, face_mats=face_part)
                obj = pbr_engine.MeshObject(mesh=mesh, materials=mats)
            else:
                nrm = getattr(p, "pbr_normal_map", "")
                if nrm:
                    mat.normal_map = nrm
                obj = pbr_engine.MeshObject(mesh=mesh, materials=[mat])
        else:
            # Case-insensitive lookup: saved skins sometimes have
            # `mesh_kind` lowercased ("butterfly") while the library
            # keys are CamelCase. Falling back to Sphere silently
            # rendered a sphere over the user's butterfly — match the
            # key by name regardless of case.
            _lib = pbr_engine.MESH_LIBRARY
            _factory = _lib.get(p.mesh_kind)
            if _factory is None:
                for _k, _v in _lib.items():
                    if _k.lower() == p.mesh_kind.lower():
                        _factory = _v; break
            mesh = (_factory or _lib["Sphere"])()
            # Generic flap: any rigged mesh exposing "wing" parts flaps.
            if (getattr(mesh, "part_names", None)
                    and _part_is_flappable(mesh.part_names)):
                mesh = _flap_imported_parts(
                    mesh, getattr(p, "mesh_flap", 0.0))
            from dataclasses import replace
            mat = (replace(pbr_engine.PRESETS[p.pbr_preset])
                    if p.pbr_preset in pbr_engine.PRESETS
                    else pbr_engine.Material())
            mat.metallic = p.pbr_metallic
            mat.roughness = p.pbr_roughness
            mat.specular = p.pbr_specular
            mat.clear_coat = p.pbr_clearcoat
            mat.clear_coat_roughness = p.pbr_clearcoat_roughness
            albedo = (getattr(p, "pbr_albedo_map", "")
                       or getattr(p, "texture_path", ""))
            if albedo: mat.albedo_map = albedo
            # Per-part textures (Wing_Left ↦ baked Blue Morpho albedo
            # etc.) — must match the live Designer's _mesh_render_bytes
            # path or /snapshot will diverge from the on-screen render.
            part_textures = dict(getattr(p, "mesh_part_textures", {}) or {})
            if (mesh.vert_part_ids is not None and mesh.part_names
                    and part_textures):
                import numpy as _np2
                from dataclasses import replace as _rep
                mats = []
                for pid, name in enumerate(mesh.part_names):
                    mi = pbr_engine.Material()
                    mi.metallic = p.pbr_metallic
                    mi.roughness = p.pbr_roughness
                    mi.specular = p.pbr_specular
                    mi.clear_coat = p.pbr_clearcoat
                    mi.clear_coat_roughness = p.pbr_clearcoat_roughness
                    tex = part_textures.get(name, albedo)
                    if tex:
                        mi.albedo_map = tex
                    # Normal map: prefer per-part if set, else global.
                    nrm = getattr(p, "pbr_normal_map", "")
                    if nrm:
                        mi.normal_map = nrm
                    mats.append(mi)
                face_part = mesh.vert_part_ids[mesh.faces[:, 0]].astype(_np2.int32)
                mesh = _rep(mesh, face_mats=face_part)
                obj = pbr_engine.MeshObject(mesh=mesh, materials=mats)
            else:
                # Global normal map (no per-part rig) — bind whole-mat.
                nrm = getattr(p, "pbr_normal_map", "")
                if nrm:
                    mat.normal_map = nrm
                obj = pbr_engine.MeshObject(mesh=mesh, materials=[mat])
        # Studio lookup from the window_doc if accessible.
        studio_name = getattr(p, "_studio_override", None)
        env = pbr_engine.to_environment(
            pbr_engine.STUDIOS.get(studio_name or "Default Soft Studio",
                                     pbr_engine.STUDIOS["Default Soft Studio"]))
        size = min(384, max(64, int(min(p.w, p.h))))
        rgba = pbr_engine.render_mesh(
            size, size, obj, env,
            cam_yaw=getattr(p, "mesh_yaw", 0.4),
            cam_pitch=getattr(p, "mesh_pitch", 0.25),
            cam_dist=getattr(p, "mesh_dist", 3.5),
            transparent_bg=True)
        # Per-placement Y flip (mirrors what `_mesh_render_bytes` does
        # in the live Designer paint path; without this the snapshot
        # would diverge from the live window — the .3ds Monarch lives
        # head-down in object space and needs flip_y=True to read
        # head-up).
        if bool(getattr(p, "mesh_flip_y", False)):
            import numpy as _np
            arr = _np.frombuffer(rgba, dtype=_np.uint8).reshape(size, size, 4)
            rgba = bytes(arr[::-1, :, :].copy())
        png = pbr_engine.rgba_to_png(rgba, size, size)
        cache_dir = Path(tempfile.gettempdir()) / "elysium-aether-snap"
        cache_dir.mkdir(exist_ok=True)
        out = cache_dir / f"mesh-{h}.png"
        out.write_bytes(png)
        _MESH_CACHE[h] = str(out)
        dl.draw_image_file(str(out), ax, ay, p.w, p.h)
    except Exception as e:
        # Render failed — show a labelled red rect so the user knows
        # something's off rather than silently lying.
        dl.fill_path(_round_d(ax, ay, p.w, p.h, 4),
                      (255, 80, 80, int(255 * alpha)))
        dl.draw_text(f"render_mesh: {type(e).__name__}",
                      ax + 8, ay + 16, 10, (255, 255, 255, 220))


# --- PBR sphere ----------------------------------------------------------

def _paint_pbr_sphere(dl, p, ax: float, ay: float, alpha: float) -> None:
    try:
        from elysium.render import pbr as pbr_engine
        from dataclasses import replace
        mat = (replace(pbr_engine.PRESETS[p.pbr_preset])
                if p.pbr_preset in pbr_engine.PRESETS
                else pbr_engine.Material())
        mat.metallic = p.pbr_metallic
        mat.roughness = p.pbr_roughness
        env = pbr_engine.to_environment(pbr_engine.STUDIOS["Default Soft Studio"])
        size = min(256, max(64, int(min(p.w, p.h))))
        rgba = pbr_engine.render_sphere(size, size, mat, env)
        png  = pbr_engine.rgba_to_png(rgba, size, size)
        out = Path(tempfile.gettempdir()) / f"elysium-aether-snap/sphere-{id(p):x}.png"
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(png)
        dl.draw_image_file(str(out), ax, ay, p.w, p.h)
    except Exception:
        dl.fill_path(_round_d(ax, ay, p.w, p.h, p.w / 2),
                      (170, 170, 200, int(255 * alpha)))


# --- Shape ---------------------------------------------------------------

def _paint_shape(dl, p, ax: float, ay: float, alpha: float) -> None:
    d = getattr(p, "path_d", "")
    if not d:
        if getattr(p, "shape", "rect") == "ellipse":
            dl.filled_circle(ax + p.w / 2, ay + p.h / 2,
                              min(p.w, p.h) / 2,
                              _alpha_color(p.fill, alpha))
        else:
            dl.fill_path(_round_d(ax, ay, p.w, p.h, 4),
                          _alpha_color(p.fill, alpha))
        return
    # Path is stored relative to the placement's origin; shift it.
    shifted = _translate_path(d, ax, ay)
    dl.fill_path(shifted, _alpha_color(p.fill, alpha))
    if p.stroke and p.stroke[3] > 0 and getattr(p, "stroke_w", 0) > 0:
        dl.stroke_path(shifted, _alpha_color(p.stroke, alpha), p.stroke_w)


# --- Label / Button ------------------------------------------------------

def _paint_label(dl, p, ax: float, ay: float, alpha: float) -> None:
    text = str((p.props or {}).get("label", p.name))
    size = float((p.props or {}).get("font_size", 28))
    weight = int((p.props or {}).get("weight", 700))
    family = str((p.props or {}).get("font_family", ""))
    color = _alpha_color((p.props or {}).get("color", (24, 26, 44, 255)),
                          alpha)
    dl.draw_paragraph(text, ax, ay + size, p.w, size, color, 2,
                       family, weight, [])


def _paint_button(dl, p, ax: float, ay: float, alpha: float) -> None:
    dl.fill_path(_round_d(ax, ay, p.w, p.h, 10),
                  _alpha_color((91, 63, 245, 255), alpha))
    label = str((p.props or {}).get("label", p.name))
    dl.draw_paragraph(label, ax, ay + p.h / 2 - 7, p.w, 16,
                       _alpha_color((255, 255, 255, 255), alpha),
                       2, "", 600, [])


# --- helpers ------------------------------------------------------------

def _alpha_color(c, alpha: float) -> tuple:
    if not c: return (0, 0, 0, 0)
    if len(c) == 3:
        return (int(c[0]), int(c[1]), int(c[2]), int(255 * alpha))
    return (int(c[0]), int(c[1]), int(c[2]),
            int(c[3] * alpha) if alpha < 1.0 else int(c[3]))


def _round_d(x, y, w, h, r) -> str:
    r = max(0, min(r, w / 2, h / 2))
    if r <= 0:
        return f"M {x} {y} L {x+w} {y} L {x+w} {y+h} L {x} {y+h} Z"
    return (f"M {x+r} {y} L {x+w-r} {y} Q {x+w} {y} {x+w} {y+r} "
            f"L {x+w} {y+h-r} Q {x+w} {y+h} {x+w-r} {y+h} "
            f"L {x+r} {y+h} Q {x} {y+h} {x} {y+h-r} "
            f"L {x} {y+r} Q {x} {y} {x+r} {y} Z")


def _translate_path(d: str, dx: float, dy: float) -> str:
    """Shift every absolute coordinate in an SVG mini-language path by
    (dx, dy). Lowercase relative commands pass through unchanged."""
    out = []
    tokens = d.replace(",", " ").split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in {"M", "L", "T"}:
            out += [tok,
                    str(float(tokens[i + 1]) + dx),
                    str(float(tokens[i + 2]) + dy)]
            i += 3
        elif tok in {"Q", "S"}:
            out += [tok,
                    str(float(tokens[i + 1]) + dx),
                    str(float(tokens[i + 2]) + dy),
                    str(float(tokens[i + 3]) + dx),
                    str(float(tokens[i + 4]) + dy)]
            i += 5
        elif tok == "C":
            out += [tok,
                    str(float(tokens[i + 1]) + dx),
                    str(float(tokens[i + 2]) + dy),
                    str(float(tokens[i + 3]) + dx),
                    str(float(tokens[i + 4]) + dy),
                    str(float(tokens[i + 5]) + dx),
                    str(float(tokens[i + 6]) + dy)]
            i += 7
        elif tok in {"H"}:
            out += [tok, str(float(tokens[i + 1]) + dx)]; i += 2
        elif tok in {"V"}:
            out += [tok, str(float(tokens[i + 1]) + dy)]; i += 2
        elif tok == "Z":
            out.append(tok); i += 1
        else:
            out.append(tok); i += 1
    return " ".join(out)


__all__ = ["paint_designer_png"]
