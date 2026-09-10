"""Versioned, lossless mesh assets for authored Designer documents.

MESH_LIBRARY is a renderer cache, not persistent storage. These functions
serialize the actual geometry and attributes referenced by a document and
restore them before placements are painted. No pickle or executable factories
are stored. Loading validates the entire asset set before publishing any key.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace

import numpy as np

from . import pbr

SCHEMA_VERSION = 2
ARRAY_FIELDS = {
    "verts": (np.float32, 3), "faces": (np.int32, 3),
    "face_mats": (np.int32, None), "vert_normals": (np.float32, 3),
    "vert_uvs": (np.float32, 2), "vert_part_ids": (np.int32, None),
    "part_pivots": (np.float32, 3),
}


def validate(mesh: pbr.Mesh) -> None:
    """Reject malformed/non-finite data before it reaches rendering/native code."""
    for key, (_, width) in ARRAY_FIELDS.items():
        value = getattr(mesh, key)
        if value is None:
            if key in ("verts", "faces"):
                raise ValueError(f"mesh.{key} is required")
            continue
        value = np.asarray(value)
        if value.ndim != (2 if width else 1) or (width and value.shape[1] != width):
            raise ValueError(f"invalid mesh.{key} shape")
        if ARRAY_FIELDS[key][0] == np.int32 and value.dtype.kind not in "iu":
            raise ValueError(f"mesh.{key} must contain integer indices")
        if not np.isfinite(value).all():
            raise ValueError(f"non-finite mesh.{key}")
    n = len(mesh.verts)
    if len(mesh.faces) and (mesh.faces.min() < 0 or mesh.faces.max() >= n):
        raise ValueError("face index outside vertex array")
    for key in ("vert_normals", "vert_uvs", "vert_part_ids"):
        value = getattr(mesh, key)
        if value is not None and len(value) != n:
            raise ValueError(f"mesh.{key} must have one entry per vertex")
    if mesh.face_mats is not None and (
        len(mesh.face_mats) != len(mesh.faces) or (mesh.face_mats < 0).any()
    ):
        raise ValueError("invalid face material indices")
    if mesh.part_names is not None:
        if not all(isinstance(s, str) for s in mesh.part_names):
            raise ValueError("part names must be strings")
        if len(set(mesh.part_names)) != len(mesh.part_names):
            raise ValueError("part names must be unique")
    if mesh.part_pivots is not None and len(mesh.part_pivots) != len(mesh.part_names or []):
        raise ValueError("one pivot is required per part")
    if mesh.vert_part_ids is not None and len(mesh.vert_part_ids) and (
        mesh.vert_part_ids.min() < 0 or mesh.vert_part_ids.max() >= len(mesh.part_names or [])
    ):
        raise ValueError("part index outside part names")

    if mesh.topology is not None:
        from . import topology
        compiled, _, _ = topology.compile(mesh.topology)
        if mesh.part_names != compiled.part_names:
            raise ValueError("Editable topology and compiled mesh.part_names disagree")
        for key in ARRAY_FIELDS:
            a, b = getattr(mesh, key), getattr(compiled, key)
            if a is None and b is None:
                continue
            if a is None or b is None or a.shape != b.shape or not np.allclose(a, b, atol=1e-6, rtol=1e-6):
                raise ValueError(f"Editable topology and compiled mesh.{key} disagree")


def to_json(mesh: pbr.Mesh) -> dict:
    validate(mesh)
    data = {key: (None if getattr(mesh, key) is None else getattr(mesh, key).tolist())
            for key in ARRAY_FIELDS}
    data["part_names"] = None if mesh.part_names is None else list(mesh.part_names)
    if mesh.topology is not None:
        from copy import deepcopy
        data["topology"] = deepcopy(mesh.topology)
    return data


def from_json(data: dict) -> pbr.Mesh:
    if not isinstance(data, dict) or set(data) - (set(ARRAY_FIELDS) | {"part_names", "topology"}):
        raise ValueError("unknown or invalid mesh asset fields")
    kwargs = {}
    for key, (dtype, width) in ARRAY_FIELDS.items():
        value = data.get(key)
        if value is None:
            kwargs[key] = None
            continue
        raw = np.asarray(value)
        if dtype == np.int32 and (not np.isfinite(raw).all() or (raw != np.floor(raw)).any()):
            raise ValueError(f"mesh.{key} contains non-integer indices")
        if dtype == np.int32 and raw.size and (raw.min() < -(2**31) or raw.max() >= 2**31):
            raise ValueError(f"mesh.{key} index overflow")
        array = np.asarray(value, dtype=dtype)
        if array.size == 0:
            array = array.reshape((0, width) if width else (0,))
        kwargs[key] = array
    kwargs["part_names"] = data.get("part_names")
    from copy import deepcopy
    kwargs["topology"] = deepcopy(data.get("topology"))
    mesh = pbr.Mesh(**kwargs)
    validate(mesh)
    return mesh


def resolve(kind: str) -> pbr.Mesh:
    if kind.startswith("file:"):
        return pbr.import_mesh_from_file(kind[5:])
    factory = pbr.MESH_LIBRARY.get(kind)
    if factory is None:
        factory = next((v for k, v in pbr.MESH_LIBRARY.items() if k.casefold() == kind.casefold()), None)
    if factory is None:
        raise ValueError(f"missing mesh asset: {kind}")
    return factory()


def bind(placement, mesh: pbr.Mesh, *, label: str = "") -> str:
    """Give an edited placement its own immutable mesh revision/cache key."""
    validate(mesh)
    owned = from_json(to_json(mesh))
    key = "mesh:" + (label + ":" if label else "") + uuid.uuid4().hex
    pbr.MESH_LIBRARY[key] = lambda m=owned: m
    placement.mesh_kind = key
    return key


def capture(placements) -> dict:
    from . import mesh_edit, mesh_modifiers, scene, scene_animation
    scene.world_matrices(placements)
    for p in placements:
        scene_animation.tracks(p)
        mesh_edit.taper_settings(p)
        mesh_modifiers.settings(p)
    assets = {}
    for placement in placements:
        if placement.kind == "Mesh3D":
            # File imports stay explicit dependencies until native editing
            # converts them to owned mesh assets. The bundle exporter embeds
            # file references separately; do not alter a placement on reads.
            keys = [placement.mesh_kind]
            source = (getattr(placement, "props", None) or {}).get("skin_source_mesh")
            if source:
                keys.append(source)
            for key in keys:
                if not key.startswith("file:") and key not in assets:
                    assets[key] = to_json(resolve(key))
    return {"schema_version": SCHEMA_VERSION, "assets": assets}


def restore(document: dict | None, placements=None) -> None:
    if document is None:  # Legacy document without embedded geometry.
        return
    if not isinstance(document, dict) or document.get("schema_version") not in (1, SCHEMA_VERSION):
        raise ValueError("unsupported mesh document version")
    raw = document.get("assets")
    if not isinstance(raw, dict) or not all(isinstance(k, str) and k for k in raw):
        raise ValueError("invalid mesh asset map")
    from . import mesh_edit, mesh_modifiers, scene, scene_animation
    scene.world_matrices(placements or [])
    for p in placements or []:
        scene_animation.tracks(p)
        mesh_edit.taper_settings(p)
        mesh_modifiers.settings(p)
    assets = {key: from_json(value) for key, value in raw.items()}
    for placement in placements or []:
        if placement.kind != "Mesh3D":
            continue
        keys = [placement.mesh_kind]
        source = (getattr(placement, "props", None) or {}).get("skin_source_mesh")
        if source:
            keys.append(source)
        for key in keys:
            if not key.startswith("file:") and key not in assets:
                raise ValueError(f"document is missing referenced mesh asset: {key}")
    for key, mesh in assets.items():
        pbr.MESH_LIBRARY[key] = lambda m=mesh: m


def semantic_hash(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def with_vertices(mesh: pbr.Mesh, verts: np.ndarray) -> pbr.Mesh:
    """Preserve authored attributes and recompute derived normals after deformation."""
    verts = np.asarray(verts, dtype=np.float32)
    if verts.shape != mesh.verts.shape:
        raise ValueError("topology-preserving deformation changed vertex count")
    normals = None
    if mesh.vert_normals is not None:
        normals = np.zeros_like(verts)
        tri = verts[mesh.faces]
        face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        for corner in range(3):
            np.add.at(normals, mesh.faces[:, corner], face_normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    if mesh.topology is not None:
        from copy import deepcopy

        from . import topology
        doc = deepcopy(mesh.topology)
        _, ids, _ = topology.compile(doc)
        positions = {}
        for identity, position in zip(ids, verts):
            if identity in positions and not np.allclose(position, positions[identity]):
                raise ValueError("Deformation split an editable vertex across corners")
            positions[identity] = position
        for vertex in doc['vertices']:
            if vertex['id'] in positions:
                vertex['position'] = positions[vertex['id']].tolist()
        for face in doc['faces']:
            for corner in face['corners']:
                corner['normal'] = None
        return topology.compile(doc)[0]
    result = replace(mesh, verts=verts.copy(), vert_normals=normals)
    validate(result)
    return result
