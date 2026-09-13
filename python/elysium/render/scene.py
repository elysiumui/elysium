"""Authored meter-space transforms and a shared, depth-tested scene preview.

Designer uses right-handed +Y up. Object Euler angles are XYZ degrees;
local matrices are T(location) T(pivot) Rz Ry Rx S T(-pivot).
Canvas layout coordinates and per-placement preview cameras are unrelated.
"""

import math
from copy import deepcopy

import numpy as np

from . import mesh_document, mesh_edit, pbr

DEFAULT = {
    "location": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "pivot": [0.0, 0.0, 0.0],
}

# Object-level coordinate spaces (lower-case; mesh.components_transform keeps
# its capitalised Global/Local/Parent enum).
SPACES = ("local", "parent", "world")
_AXES = {"X": 0, "Y": 1, "Z": 2}

CAMERA_DEFAULT = {
    "target": [0.0, 0.0, 0.0],
    "distance": 10.0,
    "yaw": 0.65,
    "pitch": 0.4,
    "projection": "perspective",
    "ortho_scale": 7.0,
}

# Axis view presets as (yaw, pitch) for pbr.render_mesh's orbit camera:
# the camera sits at +Z/-Z/+X/-X/+Y/-Y. Screen axes: front X right, Y up;
# right -Z right; top X right, -Z up (Blender numpad views under
# Designer = (Blender X, Blender Z, -Blender Y)).
VIEW_PRESETS = {
    "front": (0.0, 0.0),
    "back": (math.pi, 0.0),
    "right": (math.pi / 2, 0.0),
    "left": (-math.pi / 2, 0.0),
    "top": (0.0, math.pi / 2),
    "bottom": (0.0, -math.pi / 2),
}


def shading_mode(value="solid"):
    if value not in ("solid", "material", "checker"):
        raise ValueError("Shading must be solid, material or checker")
    return value


def camera(values=None):
    values = {} if values is None else values
    if not isinstance(values, dict) or set(values) - set(CAMERA_DEFAULT):
        raise ValueError("Unknown scene camera fields")
    checked = deepcopy(CAMERA_DEFAULT)
    checked.update(values)
    if checked["projection"] not in ("perspective", "orthographic"):
        raise ValueError("Camera projection must be perspective or orthographic")
    target = checked["target"]
    if not isinstance(target, (list, tuple)) or len(target) != 3:
        raise ValueError("Camera target requires three numbers")
    for v in [*target, *(checked[k] for k in ("distance", "yaw", "pitch", "ortho_scale"))]:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v):
            raise ValueError("Camera values must be finite numbers")
    if checked["distance"] <= 0 or checked["ortho_scale"] <= 0:
        raise ValueError("Camera distance and orthographic scale must be positive")
    return deepcopy(checked)


def transform(placement):
    raw = (getattr(placement, "props", None) or {}).get("transform3d", {})
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
    if placement.kind not in ("Mesh3D", "SceneGroup"):
        raise ValueError("3D transforms require a mesh object or scene group")
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


def euler_degrees(rotation):
    """Inverse of pbr._euler_rot (R = Rz Ry Rx) as XYZ degrees."""
    R = np.asarray(rotation, dtype=np.float64)
    hyp = math.hypot(R[2, 1], R[2, 2])
    if hyp < 1e-9:  # Gimbal lock: fold everything into Y and Z.
        x, y, z = 0.0, math.atan2(-R[2, 0], hyp), math.atan2(-R[0, 1], R[1, 1])
    else:
        x, y, z = math.atan2(R[2, 1], R[2, 2]), math.atan2(-R[2, 0], hyp), math.atan2(R[1, 0], R[0, 0])
    return [float(v) for v in np.degrees([x, y, z])]


def decompose_linear(linear):
    """Split a 3x3 linear part into (rotation, scale); shear is rejected."""
    linear = np.asarray(linear, dtype=np.float64)
    scale = np.linalg.norm(linear, axis=0)
    if not np.isfinite(scale).all() or (scale < 1e-12).any():
        raise ValueError("Transform is degenerate")
    rotation = linear / scale
    if np.linalg.det(rotation) < 0:
        scale = scale * [-1.0, 1.0, 1.0]
        rotation = rotation * [-1.0, 1.0, 1.0]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6):
        raise ValueError("Transform would introduce shear; use local space or apply transforms first")
    return rotation, [float(v) for v in scale]


def _index(placements, placement):
    index = next((i for i, p in enumerate(placements) if p is placement), None)
    if index is None:
        raise ValueError("Object must belong to this scene")
    return index


def parent_matrix(placements, placement):
    """World matrix of the object's parent frame including the parent inverse."""
    index = _index(placements, placement)
    return world_matrices(placements)[index] @ np.linalg.inv(matrix(placement))


def _linear(values):
    return pbr._euler_rot(*np.radians(values["rotation"])).astype(np.float64) @ np.diag(values["scale"])


def describe(placements, placement, space="local"):
    """Read the transform in local, parent (origin position) or world terms.

    ``location`` is always the position of the object's local origin in the
    chosen space; rotation/scale/pivot are local unless space is world.
    """
    if space not in SPACES:
        raise ValueError("Space must be local, parent or world")
    values = transform(placement)
    if space == "local":
        return values
    if space == "parent":
        return {**values, "location": [float(v) for v in matrix(placement)[:3, 3]]}
    world = world_matrices(placements)[_index(placements, placement)]
    rotation, scale = decompose_linear(world[:3, :3])
    return {**values, "location": [float(v) for v in world[:3, 3]],
            "rotation": euler_degrees(rotation), "scale": scale}


def _commit(placements, placement, values):
    """Validate a complete candidate (transform + hierarchy) before writing."""
    index = _index(placements, placement)
    candidates = deepcopy(placements)
    update(candidates[index], values)
    world_matrices(candidates)
    return update(placement, values)


def set_transform(placements, placement, values, *, space="local"):
    """Set channels expressed in local, parent or world space atomically."""
    if space not in SPACES:
        raise ValueError("Space must be local, parent or world")
    if not isinstance(values, dict) or set(values) - set(DEFAULT):
        raise ValueError("Unknown transform field")
    if space == "local":
        return _commit(placements, placement, values)
    current = transform(placement)
    candidate = deepcopy(placement)
    update(candidate, values)  # Validates every requested channel as numbers.
    requested = transform(candidate)
    result = {k: requested[k] for k in ("rotation", "scale", "pivot") if k in values}
    local = {**current, **result}
    parent = parent_matrix(placements, placement)
    if space == "world" and ("rotation" in values or "scale" in values):
        # Unspecified world channels come from the current world decomposition.
        world_rotation, world_scale = decompose_linear(parent[:3, :3] @ _linear(current))
        if "rotation" in values:
            world_rotation = pbr._euler_rot(*np.radians(requested["rotation"])).astype(np.float64)
        if "scale" in values:
            world_scale = requested["scale"]
        rotation, scale = decompose_linear(
            np.linalg.inv(parent[:3, :3]) @ world_rotation @ np.diag(world_scale)
        )
        result["rotation"], result["scale"] = euler_degrees(rotation), scale
        local = {**local, **result}
    if "location" in values:
        # The request is the origin's position in the chosen space; the stored
        # location differs from it by the pivot term of the local matrix.
        origin = np.asarray(requested["location"], dtype=np.float64)
        if space == "world":
            origin = (np.linalg.inv(parent) @ [*origin, 1.0])[:3]
        pivot = np.asarray(local["pivot"])
        result["location"] = [float(v) for v in origin - pivot + _linear(local) @ pivot]
    return _commit(placements, placement, result)


def _axis_directions(linear):
    """World directions of a space's axes, for any invertible linear part.

    Identical to :func:`decompose_linear`'s rotation whenever the linear part
    is free of shear (its columns are already orthogonal, so normalising them
    is the rotation, with the same reflection-into-scale convention). Unlike
    ``decompose_linear`` it also answers on a sheared chain, where the columns
    stay unit length but stop being mutually orthogonal — enough to point a
    location delta, which never decomposes a result.
    """
    linear = np.asarray(linear, dtype=np.float64)
    scale = np.linalg.norm(linear, axis=0)
    if not np.isfinite(scale).all() or (scale < 1e-12).any():
        raise ValueError("Transform is degenerate")
    frame = linear / scale
    if np.linalg.det(frame) < 0:
        frame = frame * [-1.0, 1.0, 1.0]
    return frame


def _space_linear(placements, placement, space):
    if space == "world":
        return np.eye(3)
    if space == "parent":
        return parent_matrix(placements, placement)[:3, :3]
    return world_matrices(placements)[_index(placements, placement)][:3, :3]


def _frame(placements, placement, space, *, orthonormal=True):
    """Basis of ``space`` in world terms.

    ``orthonormal`` (rotation and scale deltas, which decompose their result)
    insists on a rigid frame and rejects a sheared chain; a location delta
    only needs directions and passes ``False``.
    """
    linear = _space_linear(placements, placement, space)
    return decompose_linear(linear)[0] if orthonormal else _axis_directions(linear)


def _shear_message(candidate, space):
    """Rotation/scale rejection that suggests a space it verified, or none."""
    works = []
    for other in SPACES:
        if other == space:
            continue
        try:
            decompose_linear(candidate(other))
        except ValueError:
            continue
        works.append(other)
    remedy = f"use {' or '.join(works)} space or apply transforms first" if works \
        else "apply the parent chain's transforms first"
    return f"Transform would introduce shear; {remedy}"


def transform_delta(placements, placement, group, amount, *, axis=None, space="world",
                    plane=False, free_axis=None):
    """Move/rotate/scale an object by a delta in world, parent or local space.

    This is the single implementation behind the Designer gizmo and the
    public scene.transform_delta tool. ``free_axis`` is expressed in the
    chosen space. Rotation and scale act about the object's pivot.
    """
    if group not in ("location", "rotation", "scale"):
        raise ValueError("Choose location, rotation or scale")
    if space not in SPACES:
        raise ValueError("Space must be local, parent or world")
    if isinstance(axis, str):
        axis = _AXES.get(axis.upper())
        if axis is None:
            raise ValueError("Axis must be X, Y, Z or free")
    elif axis is not None and (isinstance(axis, bool) or axis not in (0, 1, 2)):
        raise ValueError("Axis must be X, Y, Z or free")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        raise ValueError("Enter a finite amount")
    if type(plane) is not bool:
        raise ValueError("Plane must be boolean")
    if free_axis is not None:
        free_axis = np.asarray(free_axis, dtype=np.float64)
        if free_axis.shape != (3,) or not np.isfinite(free_axis).all() or np.linalg.norm(free_axis) == 0:
            raise ValueError("Free direction must contain three finite values and be nonzero")
        free_axis = free_axis / np.linalg.norm(free_axis)
    if plane and (axis is None or group == "rotation"):
        raise ValueError("Plane constraints require a move or scale axis")
    if group in ("location", "rotation") and axis is None and free_axis is None:
        raise ValueError("Move and rotate need an axis or a free direction")
    if group == "scale" and amount == 0:
        raise ValueError("Scale must be nonzero")
    current = transform(placement)
    parent_linear = parent_matrix(placements, placement)[:3, :3]
    if axis is not None and not plane:
        direction = np.eye(3)[:, axis]
    elif plane:
        direction = np.eye(3)[:, next(i for i in range(3) if i != axis)] if free_axis is None else free_axis.copy()
        direction[axis] = 0.0
        if np.linalg.norm(direction) == 0:
            raise ValueError("Free direction lies along the constrained axis")
        direction /= np.linalg.norm(direction)
    else:
        direction = free_axis
    values = {}
    if group == "location":
        # A move only needs a direction, so any invertible chain works — even
        # a sheared one, where no rigid frame exists. ``amount`` stays a world
        # distance: the frame is unit-column, so normalising is a no-op unless
        # the columns are skewed.
        step = _frame(placements, placement, space, orthonormal=False) @ direction
        delta = np.linalg.solve(parent_linear, step / np.linalg.norm(step) * amount)
        values["location"] = [float(v) for v in np.asarray(current["location"]) + delta]
    else:
        def candidate(in_space):
            """Local linear part this delta would produce, taken in ``in_space``."""
            frame = _frame(placements, placement, in_space)
            if group == "rotation":
                from .component_transform import rotation as axis_rotation
                change = axis_rotation(frame @ direction, amount)
            else:
                factors = np.ones(3)
                if axis is None:
                    factors[:] = amount
                elif plane:
                    factors[[i for i in range(3) if i != axis]] = amount
                else:
                    factors[axis] = amount
                change = frame @ np.diag(factors) @ frame.T
            return np.linalg.solve(parent_linear, change @ parent_linear @ _linear(current))
        try:
            rotation, scale = decompose_linear(candidate(space))
        except ValueError as exc:
            if "shear" not in str(exc):
                raise
            # Only name a space that was checked and works for this very delta.
            raise ValueError(_shear_message(candidate, space)) from None
        values["rotation"], values["scale"] = euler_degrees(rotation), scale
    checked = _commit(placements, placement, values)
    world = world_matrices(placements)[_index(placements, placement)]
    return {"transform": checked, "world_matrix": world.tolist()}


def is_visible(placement, excluded=()):
    """Retain authored visibility in the persisted placement properties."""
    return (
        bool(getattr(placement, "visible", True))
        and not bool((getattr(placement, "props", None) or {}).get("hidden", False))
        and getattr(placement, "entity_id", None) not in excluded
    )


def compose(placements, *, materials=False, polygon_normals=None, uv_status=None,
            excluded=None, face_colors=None):
    """Flatten only for rendering; authored geometry/attributes stay independent.

    ``excluded`` holds entity ids hidden by scene collections; their
    transforms still drive visible children. ``face_colors`` (a list) receives
    one linear RGB row per triangle for explicit material slots and -1 rows
    for inherited/neutral faces, for the solid viewport.
    """
    verts, faces, face_objects, uvs, face_materials, mats = [], [], [], [], [], []
    vertex_normals = []
    tangent_frames = []
    has_tangents = False
    has_normals = False
    count = 0
    excluded = set() if excluded is None else set(excluded)
    matrices = world_matrices(placements)
    for i, p in enumerate(placements):
        if p.kind != "Mesh3D" or not is_visible(p, excluded):
            continue
        mesh = mesh_edit.evaluate(p)
        if face_colors is not None:
            from .mesh_materials import solid_colors
            colors = solid_colors(p, mesh)
            face_colors.extend(
                np.full((len(mesh.faces), 3), -1.0).tolist() if colors is None else colors.tolist()
            )
        if uv_status is not None:
            from .mesh_uv_diagnostics import face_uv_status
            uv_status.extend(face_uv_status(mesh))
        m = matrices[i]
        verts.append(mesh.verts @ m[:3, :3].T + m[:3, 3])
        has_normals |= mesh.vert_normals is not None
        vertex_normals.append(
            pbr._transform_normals(mesh.vert_normals, m[:3, :3])
            if mesh.vert_normals is not None else np.zeros_like(mesh.verts)
        )
        face_indices = mesh.faces[:, ::-1] if np.linalg.det(m[:3, :3]) < 0 else mesh.faces
        if polygon_normals is not None:
            if mesh.topology is not None:
                from . import topology

                points = {v["id"]: v["position"] for v in mesh.topology["vertices"]}
                inverse = np.linalg.inv(m[:3, :3])
                for face in mesh.topology["faces"]:
                    normal = topology.normal([points[c["vertex"]] for c in face["corners"]]) @ inverse
                    normal /= np.linalg.norm(normal)
                    polygon_normals.extend([normal] * (len(face["corners"]) - 2))
            else:
                triangles = verts[-1][face_indices]
                normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
                polygon_normals.extend(normals)
        faces.append(face_indices + count)
        uvs.append(mesh.vert_uvs if mesh.vert_uvs is not None else np.zeros((len(mesh.verts), 2)))
        from .mesh_materials import render_materials
        surfaces, indices = render_materials(p, mesh)
        if materials and any(surface.normal_map is not None for surface in surfaces):
            from .mesh_tangents import corner_tangents, transform
            frames = transform(corner_tangents(mesh), m[:3, :3])
            if np.linalg.det(m[:3, :3]) < 0:
                frames = frames[:, ::-1]
            has_tangents = True
        else:
            frames = np.zeros((len(mesh.faces), 3, 4), np.float32)
        tangent_frames.append(frames)
        face_materials.extend((indices + len(mats)).tolist())
        mats.extend(surfaces)
        face_objects.extend([i] * len(mesh.faces))
        count += len(mesh.verts)
    if not verts or count == 0:
        return None, np.empty(0, dtype=np.int32)
    # Neutral solid viewport material; this does not edit authored materials.
    mesh = pbr.Mesh(
        np.concatenate(verts).astype(np.float32),
        np.concatenate(faces),
        face_mats=np.asarray(face_materials, dtype=np.int32) if materials else None,
        vert_uvs=np.concatenate(uvs).astype(np.float32),
        vert_normals=np.concatenate(vertex_normals).astype(np.float32) if has_normals else None,
        corner_tangents=np.concatenate(tangent_frames) if has_tangents else None,
    )
    return pbr.MeshObject(
        mesh,
        mats
        if materials
        else [pbr.Material(base_color=(0.45, 0.45, 0.45), metallic=0.0, roughness=0.8)],
    ), np.asarray(face_objects, dtype=np.int32)


def frame(placements, aspect=1.0, *, excluded=None):
    obj, _ = compose(placements, excluded=excluded)
    if obj is None:
        return [0.0, 0.0, 0.0], 10.0
    lo, hi = obj.mesh.verts.min(axis=0), obj.mesh.verts.max(axis=0)
    radius = max(float(np.linalg.norm(hi - lo)) / 2, 0.1)
    half_fov = np.arctan(np.tan(np.radians(38) / 2) * min(aspect, 1.0))
    return ((lo + hi) / 2).tolist(), float(radius / np.sin(half_fov) * 1.1)


def render(
    placements,
    width,
    height,
    *,
    target=(0.0, 0.0, 0.0),
    distance=10.0,
    yaw=0.65,
    pitch=0.4,
    projection="perspective",
    ortho_scale=7.0,
    shading="solid",
    grid=True,
    component_output=None,
    lighting=None,
    pass_output=None,
    excluded=None,
    reference=None,
):
    """Render the composed scene.

    ``excluded`` hides collection members (see collections.excluded_entities).
    ``reference`` is a scene_views reference entry (with decoded ``_pixels``)
    blended behind the grid of an orthographic axis view; it is drawn only
    when ``grid`` is true, so exports, render jobs and snapshots never
    include it.
    """
    if shading not in ("solid", "material", "checker"):
        raise ValueError("Shading must be solid, material or checker")
    uv_status = [] if shading == "checker" else None
    polygon_normals = [] if shading == "solid" else None
    face_colors = [] if shading == "solid" else None
    obj, face_objects = compose(placements, materials=shading == "material", polygon_normals=polygon_normals,
                                uv_status=uv_status, excluded=excluded, face_colors=face_colors)
    ids = np.full((height, width), -1, dtype=np.int32)
    empty_geometry = obj is None or len(obj.mesh.faces) == 0
    if empty_geometry:
        # Empty geometry still needs camera rays for the world grid.
        obj = pbr.MeshObject(
            pbr.Mesh(
                np.array([[0.0, -1e6, 0.0], [1.0, -1e6, 0.0], [0.0, -1e6, 1.0]], dtype=np.float32),
                np.array([[0, 1, 2]]),
            ),
            [pbr.Material()],
        )
        face_objects = np.array([-1], dtype=np.int32)
    from . import scene_lighting
    hits = {}
    rgba = pbr.render_mesh(
        width,
        height,
        obj,
        scene_lighting.environment(lighting if shading == "material" else None),
        cam_dist=distance,
        cam_yaw=yaw,
        cam_pitch=pitch,
        cam_target=target,
        transparent_bg=True,
        hit_output=hits,
        pass_output=pass_output,
        ortho_scale=ortho_scale if projection == "orthographic" else None,
    )
    faces = hits["face_index"]
    if empty_geometry:
        # The camera-ray sentinel is not authored geometry. An orthographic
        # camera can see it even a million meters away; suppress every hit.
        faces.fill(-1)
        hits["depth"].fill(np.inf)
        rgba = bytes(width * height * 4)
        if pass_output is not None:
            for k, v in pass_output.items():
                v.fill(np.inf if k == "depth" else 0)
    mask = faces >= 0
    ids[mask] = face_objects[faces[mask]]
    if component_output is not None:
        offsets = np.zeros(len(face_objects), dtype=np.int32)
        for identity in np.unique(face_objects):
            indices = np.flatnonzero(face_objects == identity)
            offsets[indices] = indices[0]
        local = np.full_like(faces, -1)
        local[mask] = faces[mask] - offsets[faces[mask]]
        component_output['face_index'] = local
        look = -np.array([np.cos(pitch) * np.sin(yaw), np.sin(pitch), np.cos(pitch) * np.cos(yaw)])
        # Camera-axis depth works for perspective and orthographic rays. Keep
        # this geometric buffer independent of shading and selection colors.
        component_output['depth'] = hits['depth'] * (hits['ray_direction'] @ look)
        component_output['occlusion_mesh'] = None if empty_geometry else obj.mesh
        component_output['occlusion_bvh'] = None if empty_geometry else pbr._cached_bvh_for(obj, obj.mesh.verts)
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).copy()
    background = pixels[:, :, 3] == 0
    if grid:
        pixels[background] = (48, 49, 52, 255)
    # Solid modeling shading is neutral, independent of material-preview studios.
    if mask.any() and shading == "solid" and polygon_normals:
        # Render triangles belonging to one authored polygon share its flat
        # normal. This avoids diagonal seams on nonplanar subdivided quads.
        normals = pbr._shading_normals(
            obj, faces[mask], hits["barycentric_u"][mask], hits["barycentric_v"][mask],
            np.asarray(polygon_normals)[faces[mask]],
        )
        light = np.array([0.2, 0.8, 1.0])
        light /= np.linalg.norm(light)
        gray = np.clip(
            145 * (0.65 + 0.35 * np.maximum(normals @ light, 0)), 0, 255
        ).astype(np.uint8)
        pixels[mask, :3] = gray[:, None]
        # Explicit material slot colours tint their faces; inherited slots
        # keep the neutral expression above byte for byte.
        colors = np.asarray(face_colors, dtype=np.float64)[faces[mask]] if face_colors else None
        if colors is not None and (colors >= 0).all(axis=1).any():
            explicit = (colors >= 0).all(axis=1)
            lit = (0.65 + 0.35 * np.maximum(normals @ light, 0))[explicit, None]
            tinted = np.clip(255 * pbr._linear_to_srgb(colors[explicit]) * lit, 0, 255).astype(np.uint8)
            rows = np.flatnonzero(mask.reshape(-1))[explicit]
            flat = pixels.reshape(-1, 4)
            flat[rows, :3] = tinted
    if mask.any() and shading == "checker":
        triangles = obj.mesh.vert_uvs[obj.mesh.faces[faces[mask]]]
        u, v = hits["barycentric_u"][mask], hits["barycentric_v"][mask]
        uv = triangles[:, 0] * (1 - u - v)[:, None] + triangles[:, 1] * u[:, None] + triangles[:, 2] * v[:, None]
        # Repeat an unlit 8-by-8 UV checker; reduce before multiplication to
        # keep very large authored coordinates from overflowing integer casts.
        cells = np.floor(np.mod(uv, 1.0) * 8).astype(np.int32)
        gray = np.where((cells[:, 0] + cells[:, 1]) % 2, 68, 208).astype(np.uint8)
        colors = np.repeat(gray[:, None], 3, axis=1)
        status = np.asarray(uv_status)[faces[mask]]
        colors[status == "missing"] = (170, 65, 190)
        colors[status == "collapsed"] = (230, 90, 45)
        pixels[mask, :3] = colors
    if not grid:
        return pixels.tobytes(), ids
    ro, rd = hits["ray_origin"], hits["ray_direction"]
    if projection == "orthographic":
        direction = rd[height // 2, width // 2]
        normal_axis = int(np.argmax(np.abs(direction)))
        if abs(direction[normal_axis]) > 1 - 1e-6:
            # Axis views need their own drawing plane. The horizontal floor
            # is edge-on in Front/Side and cannot supply a visible grid.
            # Project onto the target-depth plane so panning along the view
            # direction never hides the grid behind the camera.
            points = ro + rd * distance
            axes = [a for a in range(3) if a != normal_axis]
            coordinates = points[:, :, axes]
            footprint = ortho_scale / height
            visible = faces < 0
            if reference is not None:
                _draw_reference(pixels, points, visible, yaw, pitch, reference)
            line = np.min(np.abs(coordinates - np.round(coordinates)), axis=2)
            strength = np.where(visible, np.clip(1 - line / footprint, 0, 1), 0)
            strength *= max(0, 1 - footprint * 3)
            pixels[:, :, :3] = (
                pixels[:, :, :3] * (1 - strength[:, :, None])
                + np.array([85, 86, 89]) * strength[:, :, None]
            ).astype(np.uint8)
            colors = ((150, 65, 65), (75, 145, 80), (65, 100, 170))
            for index, axis in enumerate(axes):
                # The axis itself is the zero coordinate of the other
                # in-plane dimension, with its own consistent world color.
                line_mask = visible & (np.abs(coordinates[:, :, 1 - index]) < footprint)
                pixels[line_mask, :3] = colors[axis]
            return pixels.tobytes(), ids
    with np.errstate(divide="ignore", invalid="ignore"):
        plane_t = -ro[:, :, 1] / rd[:, :, 1]
        points = ro + rd * plane_t[:, :, None]
    visible = (plane_t > 0) & (faces < 0) & np.isfinite(plane_t)
    # World-space footprint of roughly one pixel, growing with distance.
    footprint = np.maximum(plane_t * np.tan(np.radians(38) / 2) * 2 / height, 0.001)
    if projection == "orthographic":
        footprint = np.full_like(plane_t, ortho_scale / height)
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


def _draw_reference(pixels, points, visible, yaw, pitch, reference):
    """Blend a world-anchored reference image onto background pixels only."""
    from . import material_image
    image = reference.get("_pixels")
    if image is None:
        image = material_image.pixels(reference["image"])
    look = -np.array([math.cos(pitch) * math.sin(yaw), math.sin(pitch), math.cos(pitch) * math.cos(yaw)])
    up_world = np.array([0.0, 0.0, -1.0]) if abs(look[1]) > 0.9999 else np.array([0.0, 1.0, 0.0])
    right = np.cross(look, up_world)
    right /= max(np.linalg.norm(right), 1e-8)
    up = np.cross(right, look)
    u, v = points @ right, points @ up
    (ox, oy), (w, h) = reference["offset"], reference["size"]
    inside = visible & (u >= ox - w / 2) & (u < ox + w / 2) & (v >= oy - h / 2) & (v < oy + h / 2)
    if not inside.any():
        return
    rows, cols = image.shape[:2]
    sx = np.clip(((u[inside] - (ox - w / 2)) / w * cols).astype(np.int64), 0, cols - 1)
    sy = np.clip(((1 - (v[inside] - (oy - h / 2)) / h) * rows).astype(np.int64), 0, rows - 1)
    sample = image[sy, sx].astype(np.float64)
    alpha = (sample[:, 3:4] / 255.0) * float(reference["opacity"])
    pixels[inside, :3] = (pixels[inside, :3] * (1 - alpha) + sample[:, :3] * alpha).astype(np.uint8)


def parent_data(placement):
    """Parent inverse also retains an affine offset after keep-world unparenting."""
    raw = (getattr(placement, "props", None) or {}).get("parent3d", {})
    if not isinstance(raw, dict) or set(raw) - {"id", "inverse"}:
        raise ValueError("Invalid parent3d fields")
    identity = raw.get("id")
    if identity is not None and (not isinstance(identity, str) or not identity):
        raise ValueError("Parent identity must be a nonempty string or null")
    inverse = np.asarray(raw.get("inverse", np.eye(4)), dtype=np.float64)
    if inverse.shape != (4, 4) or not np.isfinite(inverse).all():
        raise ValueError("Parent inverse must be a finite 4x4 affine matrix")
    if not np.allclose(inverse[3], [0, 0, 0, 1], atol=1e-12, rtol=0):
        raise ValueError("Parent inverse must be affine")
    if abs(np.linalg.det(inverse[:3, :3])) < 1e-12:
        raise ValueError("Parent inverse must be invertible")
    return identity, inverse


def world_matrices(placements):
    """Evaluate an acyclic entity hierarchy; names never determine relationships."""
    by_id = {}
    for i, p in enumerate(placements):
        identity = getattr(p, "entity_id", None)
        if identity:
            if identity in by_id:
                raise ValueError("Duplicate scene identity")
            by_id[identity] = i
    output, visiting = {}, set()

    def visit(i):
        if i in output:
            return output[i]
        if i in visiting:
            raise ValueError("3D parenting would create a cycle")
        visiting.add(i)
        p = placements[i]
        parent_id, inverse = parent_data(p)
        parent_world = np.eye(4)
        if parent_id is not None:
            if parent_id not in by_id:
                raise ValueError(f"Missing parent: {parent_id}")
            parent_index = by_id[parent_id]
            if placements[parent_index].kind not in ("Mesh3D", "SceneGroup"):
                raise ValueError("3D parent must be a mesh or scene group")
            parent_world = visit(parent_index)
        output[i] = parent_world @ inverse @ matrix(p)
        visiting.remove(i)
        return output[i]

    return [visit(i) for i in range(len(placements))]


def set_parent(placements, child, parent=None, *, keep_world=True):
    if child.kind not in ("Mesh3D", "SceneGroup") or (
        parent is not None and parent.kind not in ("Mesh3D", "SceneGroup")
    ):
        raise ValueError("3D parenting requires meshes or scene groups")
    ci = next((i for i, p in enumerate(placements) if p is child), None)
    pi = next((i for i, p in enumerate(placements) if p is parent), None)
    if ci is None or (parent is not None and pi is None):
        raise ValueError("Parent and child must belong to this scene")
    if child is parent:
        raise ValueError("Cannot parent an object to itself")
    matrices = world_matrices(placements)
    inverse = np.eye(4)
    if keep_world:
        pw = np.eye(4) if parent is None else matrices[pi]
        inverse = np.linalg.solve(pw, matrices[ci]) @ np.linalg.inv(matrix(child))
    data = {"id": None if parent is None else parent.entity_id, "inverse": inverse.tolist()}
    candidates = deepcopy(placements)
    candidates[ci].props["parent3d"] = data
    world_matrices(candidates)  # Validate the whole proposed graph before writing.
    child.props["parent3d"] = data
    return deepcopy(data)


def apply_transform(placements, placement, *, location=True, rotation=True, scale=True):
    """Bake local channels into owned geometry without moving children or UVs.

    Applied channels reset (location 0, rotation 0, scale 1); the pivot resets
    only when all three are applied. The baked matrix is inv(M_new) @ M_old,
    so world geometry, child world matrices and UVs are unchanged.
    """
    from dataclasses import replace

    if placement.kind != "Mesh3D":
        raise ValueError("Apply transforms requires mesh geometry")
    if not any((location, rotation, scale)):
        raise ValueError("Choose at least one channel to apply")
    world_matrices(placements)
    remaining = transform(placement)
    if location:
        remaining["location"] = [0.0, 0.0, 0.0]
    if rotation:
        remaining["rotation"] = [0.0, 0.0, 0.0]
    if scale:
        remaining["scale"] = [1.0, 1.0, 1.0]
    if location and rotation and scale:
        remaining["pivot"] = [0.0, 0.0, 0.0]
    candidate = deepcopy(placement)
    candidate.props["transform3d"] = remaining
    new_local = matrix(candidate)
    local = np.linalg.inv(new_local) @ matrix(placement)
    mesh = mesh_edit.evaluate(placement, include_modifiers=False)
    verts = mesh.verts @ local[:3, :3].T + local[:3, 3]
    normals = None
    if mesh.vert_normals is not None:
        normals = mesh.vert_normals @ np.linalg.inv(local[:3, :3])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    pivots = None if mesh.part_pivots is None else mesh.part_pivots @ local[:3, :3].T + local[:3, 3]
    faces = mesh.faces[:, ::-1].copy() if np.linalg.det(local[:3, :3]) < 0 else mesh.faces.copy()
    edited = replace(
        mesh,
        verts=verts.astype(np.float32),
        faces=faces,
        vert_normals=None if normals is None else normals.astype(np.float32),
        part_pivots=None if pivots is None else pivots.astype(np.float32),
    )
    if mesh.topology is not None:
        from . import topology
        doc = deepcopy(mesh.topology)
        for vertex in doc['vertices']:
            vertex['position'] = (local[:3,:3] @ np.array(vertex['position']) + local[:3,3]).tolist()
        for face in doc['faces']:
            if np.linalg.det(local[:3,:3]) < 0:
                face['corners'].reverse()
            for c in face['corners']:
                if c.get('normal') is not None:
                    n = np.array(c['normal']) @ np.linalg.inv(local[:3,:3])
                    c['normal'] = (n / np.linalg.norm(n)).tolist()
        if pivots is not None:
            doc['part_pivots'] = pivots.tolist()
        edited = topology.compile(doc)[0]
    mesh_document.validate(edited)
    from . import mesh_modifiers

    mesh_modifiers.evaluate_stack(edited, mesh_modifiers.settings(placement))
    children = []
    for child in placements:
        identity, inverse = parent_data(child)
        if identity == placement.entity_id:
            children.append((child, {"id": identity, "inverse": (local @ inverse).tolist()}))
    mesh_document.bind(placement, edited, label=placement.name)
    placement.props.pop("taper3d", None)
    placement.props["transform3d"] = remaining
    for child, data in children:
        child.props["parent3d"] = data


def detach_children(placements, removed):
    """Keep surviving children in place when their parent is deleted."""
    removed_ids = {getattr(p, "entity_id", None) for p in removed} - {None}
    world = world_matrices(placements)
    updates = []
    for i, p in enumerate(placements):
        parent_id, _ = parent_data(p)
        if getattr(p, "entity_id", None) not in removed_ids and parent_id in removed_ids:
            updates.append(
                (p, {"id": None, "inverse": (world[i] @ np.linalg.inv(matrix(p))).tolist()})
            )
    for p, data in updates:
        p.props["parent3d"] = data


def material(placement):
    """Use the same authored PBR fields in scene preview and native export."""
    from dataclasses import replace

    m = replace(
        pbr.PRESETS.get(
            getattr(placement, "pbr_preset", ""), pbr.Material(base_color=(0.55, 0.55, 0.55))
        )
    )
    for key, field in {
        "metallic": "pbr_metallic",
        "roughness": "pbr_roughness",
        "specular": "pbr_specular",
        "clear_coat": "pbr_clearcoat",
        "clear_coat_roughness": "pbr_clearcoat_roughness",
    }.items():
        setattr(m, key, getattr(placement, field, getattr(m, key)))
    fill = getattr(placement, "color_fill", None)
    if fill and getattr(placement, "pbr_use_color_fill", True):
        m.base_color = tuple(v / 255.0 for v in fill[:3])
    emissive = getattr(placement, "pbr_emissive", None)
    if emissive:
        m.emissive = tuple(v / 255.0 for v in emissive[:3])
    for key, field in {
        "albedo_map": "pbr_albedo_map",
        "normal_map": "pbr_normal_map",
        "metallic_rough_map": "pbr_metallic_rough_map",
        "ao_map": "pbr_ao_map",
        "emissive_map": "pbr_emissive_map",
    }.items():
        setattr(m, key, getattr(placement, field, "") or None)
    return m
