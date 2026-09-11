"""Parameterized native primitives shared by Designer and public Aether tools."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from . import mesh_document, pbr, topology


def _polygon_source(mesh, polygons, aliases=None, corner_uvs=None):
    """Use explicit primitive connectivity, preserving render-corner seams.

    Aliases come from the primitive's parametric rings, never proximity welding.
    Coincident vertices in an arbitrary imported mesh remain independent.
    """
    aliases = aliases or {}
    source = sorted({aliases.get(i, i) for face in polygons for i in face})
    indices = {original: i for i, original in enumerate(source)}
    remapped = [[indices[aliases.get(i, i)] for i in face] for face in polygons]
    seed = pbr.Mesh(mesh.verts[source].copy(), np.empty((0, 3), dtype=np.int32))
    doc = topology.from_mesh(seed, remapped)
    for face_index, (face, original) in enumerate(zip(doc["faces"], polygons)):
        for corner_index, (corner, i) in enumerate(zip(face["corners"], original)):
            if corner_uvs is not None:
                corner["uv"] = corner_uvs[face_index][corner_index]
            elif mesh.vert_uvs is not None:
                corner["uv"] = mesh.vert_uvs[i].tolist()
            if mesh.vert_normals is not None:
                corner["normal"] = mesh.vert_normals[i].tolist()
    return topology.compile(doc)[0]


# name: (default, minimum, maximum, integer, visible label)
PARAMETERS = {
    "Cube": {"size": (2.0, 1e-6, 1e6, False, "Size")},
    "Sphere": {
        "radius": (1.0, 1e-6, 1e6, False, "Radius"),
        "rings": (16, 3, 512, True, "Rings"),
        "segments": (32, 3, 512, True, "Segments"),
    },
    "Cylinder": {
        "radius": (1.0, 1e-6, 1e6, False, "Radius"),
        "height": (2.0, 1e-6, 1e6, False, "Height"),
        "segments": (32, 3, 512, True, "Segments"),
    },
    "Cone": {
        "radius": (1.0, 1e-6, 1e6, False, "Radius"),
        "height": (2.0, 1e-6, 1e6, False, "Height"),
        "segments": (32, 3, 512, True, "Segments"),
    },
    "Plane": {
        "width": (2.0, 1e-6, 1e6, False, "Width"),
        "depth": (2.0, 1e-6, 1e6, False, "Depth"),
        "segments": (1, 1, 256, True, "Segments"),
    },
    "Torus": {
        "major_radius": (1.0, 1e-6, 1e6, False, "Major radius"),
        "minor_radius": (0.25, 1e-6, 1e6, False, "Minor radius"),
        "major_segments": (48, 3, 512, True, "Major segments"),
        "minor_segments": (12, 3, 512, True, "Minor segments"),
    },
}


def _validated_values(kind: str, parameters: dict | None) -> dict:
    if kind not in PARAMETERS:
        raise ValueError(f"unknown native primitive: {kind}")
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise TypeError("primitive parameters must be an object")
    spec = PARAMETERS[kind]
    unknown = set(parameters) - set(spec)
    if unknown:
        raise ValueError(f"unknown {kind} parameters: {', '.join(sorted(unknown))}")
    values = {}
    for key, (default, lower, upper, integer, _) in spec.items():
        value = parameters.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{key} must be numeric")
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{key} must be between {lower:g} and {upper:g}")
        if integer and int(value) != value:
            raise ValueError(f"{key} must be an integer")
        values[key] = int(value) if integer else float(value)
    if kind == "Torus" and values["minor_radius"] >= values["major_radius"]:
        raise ValueError("minor radius must be smaller than major radius")
    return values


def build(kind: str, parameters: dict | None = None) -> tuple[pbr.Mesh, dict]:
    """Build centered, Y-up geometry without mutating any document or preset."""
    values = _validated_values(kind, parameters)
    v = values
    if kind == "Cube":
        mesh = pbr.cube_mesh(v["size"])
    elif kind == "Sphere":
        mesh = pbr.sphere_mesh(rings=v["rings"], sectors=v["segments"], radius=v["radius"])
        uv = [
            (s / v["segments"], r / v["rings"])
            for r in range(v["rings"] + 1)
            for s in range(v["segments"] + 1)
        ]
        mesh = replace(
            mesh, vert_uvs=np.asarray(uv, dtype=np.float32), vert_normals=mesh.verts / v["radius"]
        )
    elif kind == "Cylinder":
        mesh = pbr.cylinder_mesh(v["radius"], v["height"], v["segments"])
    elif kind == "Cone":
        mesh = pbr.cone_mesh(v["radius"], v["height"], v["segments"])
        mesh = replace(mesh, verts=mesh.verts - np.array([0, v["height"] / 2, 0], dtype=np.float32))
    elif kind == "Plane":
        mesh = pbr.plane_mesh(v["width"], v["depth"], v["segments"])
    else:
        mesh = pbr.torus_mesh(
            v["major_radius"], v["minor_radius"], v["major_segments"], v["minor_segments"]
        )
        uv = [
            (i / v["major_segments"], j / v["minor_segments"])
            for i in range(v["major_segments"] + 1)
            for j in range(v["minor_segments"] + 1)
        ]
        mesh = replace(mesh, vert_uvs=np.asarray(uv, dtype=np.float32))
    # Legacy render factories contain degenerate sphere-pole triangles and
    # inward winding on some closed shapes. Authored geometry must not.
    tri = mesh.verts[mesh.faces].astype(np.float64)
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    scale = max(float(np.ptp(mesh.verts, axis=0).max()), 1e-12)
    valid = area > scale * scale * 1e-12
    mesh = replace(
        mesh,
        faces=mesh.faces[valid],
        face_mats=None if mesh.face_mats is None else mesh.face_mats[valid],
    )
    tri = mesh.verts[mesh.faces].astype(np.float64)
    if (
        kind != "Plane"
        and np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() < 0
    ):
        mesh = replace(mesh, faces=mesh.faces[:, [0, 2, 1]].copy())
    if kind == "Cube":
        polygons = [
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (2, 3, 7, 6),
            (1, 2, 6, 5),
            (0, 4, 7, 3),
        ]
        mesh = _polygon_source(mesh, polygons)
    elif kind == "Sphere":
        rings, n = v["rings"], v["segments"]
        aliases = {}
        for r in range(rings + 1):
            for s in range(n + 1):
                raw = r * (n + 1) + s
                aliases[raw] = r * (n + 1) if r in (0, rings) else r * (n + 1) + s % n
        polygons = []
        for r in range(rings):
            for s in range(n):
                a = r * (n + 1) + s
                b, c, d = a + 1, a + n + 1, a + n + 2
                polygons.append(
                    [b, d, c] if r == 0 else [a, b, c] if r == rings - 1 else [a, b, d, c]
                )
        # Latitude/longitude in Blender's Z-up convention, converted to Y-up.
        # Each polar triangle owns its midpoint longitude. Unwrap each face
        # across the back meridian, retaining distinct seam corners.
        sphere_uvs = []
        for face_index, polygon in enumerate(polygons):
            sector = face_index % n
            coords = []
            for raw in polygon:
                ring, meridian = divmod(raw, n + 1)
                longitude = (sector + .5) / n if ring in (0, rings) else meridian / n
                u = (.5 - longitude) % 1.0
                coords.append([u, 1.0 - ring / rings])
            high = max(uv[0] for uv in coords)
            sphere_uvs.append([[u + (1.0 if high - u > .5 else 0.0), v] for u, v in coords])
        mesh = _polygon_source(mesh, polygons, aliases, sphere_uvs)
    elif kind == "Torus":
        major, minor = v["major_segments"], v["minor_segments"]
        aliases = {
            i * (minor + 1) + j: (i % major) * (minor + 1) + j % minor
            for i in range(major + 1)
            for j in range(minor + 1)
        }
        polygons = []
        for i in range(major):
            for j in range(minor):
                a = i * (minor + 1) + j
                polygons.append([a, a + 1, a + minor + 2, a + minor + 1])
        mesh = _polygon_source(mesh, polygons, aliases)
    elif kind == "Cylinder":
        n = v["segments"]
        polygons = [[2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2] for i in range(n)]
        aliases = {2 * n: 0, 2 * n + 1: 1}
        for cap in (0, 1):
            center = (2 + cap) * (n + 1)
            rim = [center + 1 + i for i in range(n)]
            polygons.append(rim if cap == 0 else rim[::-1])
            aliases.update({raw: 2 * i + cap for i, raw in enumerate(rim)})
        mesh = _polygon_source(mesh, polygons, aliases)
    elif kind == "Cone":
        n = v["segments"]
        polygons = [[0, 2 + (i + 1) % n, 2 + i] for i in range(n)]
        polygons.append(list(range(2, n + 2)))
        mesh = _polygon_source(mesh, polygons)
    elif kind == "Plane":
        n = v["segments"]
        polygons = []
        for j in range(n):
            for i in range(n):
                a = j * (n + 1) + i
                polygons.append([a, a + n + 1, a + n + 2, a + 1])
        mesh = _polygon_source(mesh, polygons)
    mesh_document.validate(mesh)
    return mesh, values


def bind(placement, kind: str, parameters: dict | None = None) -> str:
    mesh, values = build(kind, parameters)
    key = mesh_document.bind(placement, mesh, label=kind)
    placement.props = dict(placement.props or {})
    placement.props["primitive"] = {"kind": kind, "parameters": values, "mesh_key": key}
    return key


def settings(placement) -> dict | None:
    """Only offer regeneration while geometry still matches its primitive."""
    value = (getattr(placement, "props", None) or {}).get("primitive")
    if not isinstance(value, dict) or value.get("mesh_key") != placement.mesh_kind:
        return None
    try:
        kind, parameters = value["kind"], value["parameters"]
        if set(parameters) != set(PARAMETERS[kind]):
            return None
        _validated_values(kind, parameters)
    except (KeyError, TypeError, ValueError):
        return None
    return value


def update(placement, parameters: dict) -> str:
    current = settings(placement)
    if current is None:
        raise ValueError("primitive parameters are unavailable after geometry editing")
    values = _validated_values(current["kind"], {**current["parameters"], **parameters})
    if values == current["parameters"]:
        return placement.mesh_kind
    return bind(placement, current["kind"], values)
