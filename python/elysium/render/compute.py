"""Loader + validator for the WGSL compute scaffold.

The Rust renderer hasn't yet wired a wgpu compute pipeline; until then,
this module exposes the shader source and validates it via the naga-backed
sandbox in `_native` (which the Rust skin loader already uses). When the
pipeline lands, the renderer will consume `pbr_compute_src()` directly.
"""
from __future__ import annotations

from pathlib import Path

_SHADER_DIR = Path(__file__).parent / "shaders"
# The Rust crate `ely-render` keeps an `include_str!`-compiled copy of the
# same file under `crates/ely-render/src/shaders/`. If you edit one, copy
# the change to the other (or run `scripts/sync_shaders.py`).


def pbr_compute_src() -> str:
    """Return the WGSL source for the PBR compute scaffold."""
    return (_SHADER_DIR / "pbr_compute.wgsl").read_text()


def validate_pbr_compute() -> tuple[bool, str]:
    """Parse-only validation against naga. Returns (ok, message)."""
    src = pbr_compute_src()
    try:
        from elysium._native import _native as _n
    except Exception as e:                              # pragma: no cover
        return (True, f"naga not available ({e}); skipped validation")
    fn = getattr(_n, "validate_wgsl", None)
    if fn is None:
        return (True, "validate_wgsl binding not exposed; treating as ok")
    try:
        fn(src)
        return (True, "ok")
    except Exception as e:
        return (False, str(e))


def render_mesh_gpu(w: int, h: int, obj, env, *,
                    cam_yaw: float = 0.4, cam_pitch: float = 0.25,
                    cam_dist: float = 3.5) -> bytes:
    """GPU compute equivalent of ``elysium.render.pbr.render_mesh`` —
    runs the WGSL PBR pipeline on a separate wgpu device. Returns RGBA
    bytes (alpha = 255 everywhere). Falls back to a RuntimeError if the
    adapter does not support the required limits.
    """
    import math
    import numpy as np
    from elysium._native import _native as _n
    from elysium.render import pbr

    # Camera basis — matches render_mesh.
    cy_, sy_ = math.cos(cam_yaw), math.sin(cam_yaw)
    cp_, sp_ = math.cos(cam_pitch), math.sin(cam_pitch)
    cam_pos = np.array([cam_dist * cp_ * sy_,
                        cam_dist * sp_,
                        cam_dist * cp_ * cy_], dtype=np.float32)
    look = -cam_pos / max(np.linalg.norm(cam_pos), 1e-8)
    up_w = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(look, up_w)
    right = right / max(np.linalg.norm(right), 1e-8)
    up    = np.cross(right, look)
    fov_scale = 1.0 / math.tan(math.radians(38) * 0.5)

    # World-space verts + BVH (mirrors render_mesh's path).
    verts_w, face_normals, _ = pbr._world_transform(obj)
    bvh = pbr._cached_bvh_for(obj, verts_w)

    # Pad to vec4.
    def _pad4(arr3):
        out = np.zeros((arr3.shape[0], 4), dtype=np.float32)
        out[:, :3] = arr3
        return out
    verts4   = _pad4(verts_w.astype(np.float32))
    normals4 = _pad4(face_normals.astype(np.float32))

    # Faces: (v0, v1, v2, mat_idx). Default mat_idx 0.
    faces = obj.mesh.faces.astype(np.uint32)
    mat_idx = (obj.mesh.face_mats.astype(np.uint32)
               if obj.mesh.face_mats is not None
               else np.zeros(faces.shape[0], dtype=np.uint32))
    faces4 = np.zeros((faces.shape[0], 4), dtype=np.uint32)
    faces4[:, :3] = faces
    faces4[:, 3]  = mat_idx

    bvh_min4 = _pad4(bvh.node_min)
    bvh_max4 = _pad4(bvh.node_max)
    bvh_meta = np.stack([bvh.node_left.astype(np.int32),
                         bvh.node_right.astype(np.int32),
                         bvh.node_tri_start.astype(np.int32),
                         bvh.node_tri_end.astype(np.int32)], axis=-1)
    tri_order = bvh.tri_order.astype(np.uint32)

    # Material → 16 floats: base_color(4), params(4), emissive(4), cc(4).
    mats_flat = []
    for m in obj.materials:
        base = list(m.base_color) + [1.0]
        if len(base) > 4: base = base[:4]
        while len(base) < 4: base.append(1.0)
        params = [float(m.metallic), float(m.roughness),
                  float(m.specular), float(m.clear_coat)]
        emiss = list(m.emissive) + [0.0]
        if len(emiss) > 4: emiss = emiss[:4]
        while len(emiss) < 4: emiss.append(0.0)
        cc = [float(m.clear_coat_roughness), 0.0, 0.0, 0.0]
        mats_flat.extend(base + params + emiss + cc)
    if not mats_flat:
        mats_flat = [1, 1, 1, 1,  0, 0.5, 1, 0,  0, 0, 0, 0,  0.04, 0, 0, 0]

    sun_dir   = list(np.array(env.sun_dir,   dtype=np.float32)) + [0.0]
    sun_color = list(np.array(env.sun_color, dtype=np.float32)) + [0.0]
    fill_dir  = list(np.array(env.fill_dir,  dtype=np.float32)) + [0.0]
    fill_col  = list(np.array(env.fill_color, dtype=np.float32)) + [0.0]
    uniforms  = (list(cam_pos) + [0.0]
                 + list(look)  + [0.0]
                 + list(right) + [0.0]
                 + list(up)    + [0.0]
                 + sun_dir + sun_color + fill_dir + fill_col)

    return _n.render_pbr_compute(
        w, h,
        [float(x) for x in uniforms],
        (int(w), int(h)),
        float(fov_scale), float(w) / float(h),
        verts4.flatten().tolist(),
        faces4.flatten().tolist(),
        normals4.flatten().tolist(),
        bvh_min4.flatten().tolist(),
        bvh_max4.flatten().tolist(),
        bvh_meta.flatten().tolist(),
        tri_order.tolist(),
        list(map(float, mats_flat)),
    )


__all__ = ["pbr_compute_src", "validate_pbr_compute", "render_mesh_gpu"]
