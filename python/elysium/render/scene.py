"""Authored meter-space transforms and a shared, depth-tested scene preview.

Designer uses right-handed +Y up. Object Euler angles are XYZ degrees;
local matrices are T(location) T(pivot) Rz Ry Rx S T(-pivot).
Canvas layout coordinates and per-placement preview cameras are unrelated.
"""

from copy import deepcopy

import numpy as np

from . import mesh_document, pbr

DEFAULT = {
    "location": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "pivot": [0.0, 0.0, 0.0],
}


def transform(placement):
    raw = placement.props.get("transform3d", {})
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT):
        raise ValueError("Invalid transform3d fields")
    result = deepcopy(DEFAULT)
    for name, value in raw.items():
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError(f"{name} requires three finite numbers")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v)
            for v in value
        ):
            raise ValueError(f"{name} requires three finite numbers")
        result[name] = [float(v) for v in value]
    if any(abs(v) < 1e-8 for v in result["scale"]):
        raise ValueError("Scale must be nonzero on every axis")
    return result


def update(placement, values):
    if placement.kind != "Mesh3D":
        raise ValueError("3D transforms require a mesh object")
    if not isinstance(values, dict) or set(values) - set(DEFAULT):
        raise ValueError("Unknown transform field")
    candidate = deepcopy(placement)
    candidate.props["transform3d"] = {**transform(placement), **values}
    checked = transform(candidate)
    placement.props["transform3d"] = checked
    return deepcopy(checked)


def matrix(placement):
    values = transform(placement)
    linear = pbr._euler_rot(*np.radians(values["rotation"])).astype(np.float64) @ np.diag(
        values["scale"]
    )
    pivot = np.asarray(values["pivot"])
    result = np.eye(4)
    result[:3, :3] = linear
    result[:3, 3] = np.asarray(values["location"]) + pivot - linear @ pivot
    return result


def compose(placements):
    """Flatten only for rendering; authored geometry/attributes stay independent."""
    verts, faces, face_objects = [], [], []
    count = 0
    for i, p in enumerate(placements):
        if p.kind != "Mesh3D" or not getattr(p, "visible", True):
            continue
        mesh = mesh_document.resolve(p.mesh_kind)
        m = matrix(p)
        verts.append(mesh.verts @ m[:3, :3].T + m[:3, 3])
        face_indices = mesh.faces[:, ::-1] if np.linalg.det(m[:3, :3]) < 0 else mesh.faces
        faces.append(face_indices + count)
        face_objects.extend([i] * len(mesh.faces))
        count += len(mesh.verts)
    if not verts:
        return None, np.empty(0, dtype=np.int32)
    # Neutral solid viewport material; this does not edit authored materials.
    mesh = pbr.Mesh(np.concatenate(verts).astype(np.float32), np.concatenate(faces))
    return pbr.MeshObject(
        mesh, [pbr.Material(base_color=(0.45, 0.45, 0.45), metallic=0.0, roughness=0.8)]
    ), np.asarray(face_objects, dtype=np.int32)


def frame(placements, aspect=1.0):
    obj, _ = compose(placements)
    if obj is None:
        return [0.0, 0.0, 0.0], 10.0
    lo, hi = obj.mesh.verts.min(axis=0), obj.mesh.verts.max(axis=0)
    radius = max(float(np.linalg.norm(hi - lo)) / 2, 0.1)
    half_fov = np.arctan(np.tan(np.radians(38) / 2) * min(aspect, 1.0))
    return ((lo + hi) / 2).tolist(), float(radius / np.sin(half_fov) * 1.1)


def render(
    placements, width, height, *, target=(0.0, 0.0, 0.0), distance=10.0, yaw=0.65, pitch=0.4
):
    obj, face_objects = compose(placements)
    ids = np.full((height, width), -1, dtype=np.int32)
    if obj is None:
        # Empty geometry still needs camera rays for the world grid.
        obj = pbr.MeshObject(
            pbr.Mesh(
                np.array([[0.0, -1e6, 0.0], [1.0, -1e6, 0.0], [0.0, -1e6, 1.0]], dtype=np.float32),
                np.array([[0, 1, 2]]),
            ),
            [pbr.Material()],
        )
        face_objects = np.array([-1], dtype=np.int32)
    hits = {}
    rgba = pbr.render_mesh(
        width,
        height,
        obj,
        pbr.to_environment(pbr.STUDIOS["Default Soft Studio"]),
        cam_dist=distance,
        cam_yaw=yaw,
        cam_pitch=pitch,
        cam_target=target,
        transparent_bg=True,
        hit_output=hits,
    )
    faces = hits["face_index"]
    mask = faces >= 0
    ids[mask] = face_objects[faces[mask]]
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).copy()
    background = pixels[:, :, 3] == 0
    pixels[background] = (48, 49, 52, 255)
    # Solid modeling shading is neutral, independent of material-preview studios.
    if mask.any():
        triangles = obj.mesh.verts[obj.mesh.faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
        light = np.array([0.2, 0.8, 1.0])
        light /= np.linalg.norm(light)
        gray = np.clip(
            145 * (0.65 + 0.35 * np.maximum(normals[faces[mask]] @ light, 0)), 0, 255
        ).astype(np.uint8)
        pixels[mask, :3] = gray[:, None]
    ro, rd = hits["ray_origin"], hits["ray_direction"]
    with np.errstate(divide="ignore", invalid="ignore"):
        plane_t = -ro[:, :, 1] / rd[:, :, 1]
        points = ro + rd * plane_t[:, :, None]
    visible = (plane_t > 0) & (faces < 0) & np.isfinite(plane_t)
    # World-space footprint of roughly one pixel, growing with distance.
    footprint = np.maximum(plane_t * np.tan(np.radians(38) / 2) * 2 / height, 0.001)
    x, z = points[:, :, 0], points[:, :, 2]
    finite_x, finite_z = np.where(visible, x, 0), np.where(visible, z, 0)
    line = np.minimum(np.abs(finite_x - np.round(finite_x)), np.abs(finite_z - np.round(finite_z)))
    strength = (
        np.clip(1 - line / footprint, 0, 1)
        * np.clip(1 - plane_t / (distance * 5), 0, 1)
        * np.clip(1 - footprint * 3, 0, 1)
    )
    strength = np.where(visible, strength, 0)
    pixels[:, :, :3] = (
        pixels[:, :, :3] * (1 - strength[:, :, None])
        + np.array([85, 86, 89]) * strength[:, :, None]
    ).astype(np.uint8)
    for coordinate, color in ((z, (150, 65, 65)), (x, (65, 100, 170))):
        axis = visible & (np.abs(coordinate) < footprint)
        pixels[axis, :3] = color
    return pixels.tobytes(), ids
