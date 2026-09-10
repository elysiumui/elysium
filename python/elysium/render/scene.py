"""Authored meter-space transforms and a shared, depth-tested scene preview.

Designer uses right-handed +Y up. Object Euler angles are XYZ degrees;
local matrices are T(location) T(pivot) Rz Ry Rx S T(-pivot).
Canvas layout coordinates and per-placement preview cameras are unrelated.
"""

from copy import deepcopy

import numpy as np

from . import mesh_document, mesh_edit, pbr

DEFAULT = {
    "location": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "pivot": [0.0, 0.0, 0.0],
}

CAMERA_DEFAULT = {
    "target": [0.0, 0.0, 0.0],
    "distance": 10.0,
    "yaw": 0.65,
    "pitch": 0.4,
    "projection": "perspective",
    "ortho_scale": 7.0,
}


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


def compose(placements, *, materials=False, polygon_normals=None):
    """Flatten only for rendering; authored geometry/attributes stay independent."""
    verts, faces, face_objects, uvs, face_materials, mats = [], [], [], [], [], []
    count = 0
    matrices = world_matrices(placements)
    for i, p in enumerate(placements):
        if p.kind != "Mesh3D" or not getattr(p, "visible", True):
            continue
        mesh = mesh_edit.evaluate(p)
        m = matrices[i]
        verts.append(mesh.verts @ m[:3, :3].T + m[:3, 3])
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
        face_materials.extend([len(mats)] * len(mesh.faces))
        mats.append(material(p))
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
    )
    return pbr.MeshObject(
        mesh,
        mats
        if materials
        else [pbr.Material(base_color=(0.45, 0.45, 0.45), metallic=0.0, roughness=0.8)],
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
):
    polygon_normals = [] if shading == "solid" else None
    obj, face_objects = compose(placements, materials=shading == "material", polygon_normals=polygon_normals)
    ids = np.full((height, width), -1, dtype=np.int32)
    if obj is None or len(obj.mesh.faces) == 0:
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
        ortho_scale=ortho_scale if projection == "orthographic" else None,
    )
    faces = hits["face_index"]
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
        component_output['occlusion_mesh'] = obj.mesh
        component_output['occlusion_bvh'] = pbr._cached_bvh_for(obj, obj.mesh.verts)
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).copy()
    background = pixels[:, :, 3] == 0
    if grid:
        pixels[background] = (48, 49, 52, 255)
    # Solid modeling shading is neutral, independent of material-preview studios.
    if mask.any() and shading == "solid" and polygon_normals:
        # Render triangles belonging to one authored polygon share its flat
        # normal. This avoids diagonal seams on nonplanar subdivided quads.
        normals = np.asarray(polygon_normals)
        light = np.array([0.2, 0.8, 1.0])
        light /= np.linalg.norm(light)
        gray = np.clip(
            145 * (0.65 + 0.35 * np.maximum(normals[faces[mask]] @ light, 0)), 0, 255
        ).astype(np.uint8)
        pixels[mask, :3] = gray[:, None]
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
            line = np.min(np.abs(coordinates - np.round(coordinates)), axis=2)
            visible = faces < 0
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


def apply_transform(placements, placement):
    """Bake local TRS/pivot into owned geometry without moving children or UVs."""
    from dataclasses import replace

    if placement.kind != "Mesh3D":
        raise ValueError("Apply transforms requires mesh geometry")
    world_matrices(placements)
    local = matrix(placement)
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
    placement.props["transform3d"] = deepcopy(DEFAULT)
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
