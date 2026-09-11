"""Editable polygon/corner topology compiled to the existing triangle renderer.

Vertex, edge, polygon and corner IDs survive edits. Rendering triangulation is
an evaluated product, never the authoring identity. Operations return validated
copies so callers can publish one undoable mesh revision atomically.
"""

from copy import deepcopy
from itertools import pairwise
from math import isfinite

import numpy as np

MAX_FLOAT32 = float(np.finfo(np.float32).max)


def _id(doc, prefix):
    value = f"{prefix}{doc['next_id']}"
    doc["next_id"] += 1
    return value


def _corner(doc, vertex, uv=None, normal=None):
    return {"id": _id(doc, "c"), "vertex": vertex, "uv": deepcopy(uv), "normal": deepcopy(normal)}


def _edges(doc, loose=()):
    old = {tuple(sorted(e["vertices"])): e for e in doc["edges"]}
    needed = {}
    for face in doc["faces"]:
        ids = [c["vertex"] for c in face["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            pair = tuple(sorted((a, b)))
            needed[pair] = (
                old.get(pair)
                or needed.get(pair)
                or {"id": _id(doc, "e"), "vertices": list(pair), "seam": False, "sharp": False}
            )
    for edge in loose:
        needed.setdefault(tuple(sorted(edge["vertices"])), edge)
    doc["edges"] = list(needed.values())


def from_mesh(mesh, polygons=None):
    """Migrate triangles without welding separate vertices or losing attributes."""
    doc = {
        "schema_version": 1,
        "next_id": 1,
        "vertices": [],
        "edges": [],
        "faces": [],
        "part_names": deepcopy(mesh.part_names),
        "part_pivots": None if mesh.part_pivots is None else mesh.part_pivots.tolist(),
    }
    for i, position in enumerate(mesh.verts):
        doc["vertices"].append(
            {
                "id": _id(doc, "v"),
                "position": position.tolist(),
                "part": None if mesh.vert_part_ids is None else int(mesh.vert_part_ids[i]),
            }
        )
    for i, polygon in enumerate(mesh.faces if polygons is None else polygons):
        corners = [
            _corner(
                doc,
                doc["vertices"][int(v)]["id"],
                None if mesh.vert_uvs is None else mesh.vert_uvs[v].tolist(),
                None if mesh.vert_normals is None else mesh.vert_normals[v].tolist(),
            )
            for v in polygon
        ]
        doc["faces"].append(
            {
                "id": _id(doc, "f"),
                "corners": corners,
                "material": 0 if mesh.face_mats is None else int(mesh.face_mats[i]),
            }
        )
    _edges(doc)
    validate(doc)
    return doc


def normal(points):
    p = np.asarray(points, dtype=float)
    n = np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)
    length = np.linalg.norm(n)
    if length <= max(float(np.ptp(p, axis=0).max()) ** 2 * 1e-10, 1e-24):
        raise ValueError("Polygon has zero area")
    return n / length


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def triangles(points):
    """Ear-clip a simple polygon; preserve winding and reject intersecting edges."""
    points = np.asarray(points, dtype=float)
    n = normal(points)
    extent = max(float(np.ptp(points, axis=0).max()), 1e-12)
    if np.max(np.abs((points - points[0]) @ n)) > extent * 1e-6:
        if len(points) != 4:
            raise ValueError("Nonplanar n-gons must be split before deformation")
        # A deformed quad is a triangulated surface, not a planar polygon.
        # Its 2D projection may cross even when its 3D edges do not.
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            if (
                np.linalg.norm(np.cross(points[b] - points[a], points[c] - points[a]))
                <= extent**2 * 1e-12
            ):
                raise ValueError("Deformed quad contains a degenerate triangle")
        return [(0, 1, 2), (0, 2, 3)]
    p = np.delete(points, int(np.argmax(np.abs(n))), axis=1)
    span = max(float(np.ptp(p, axis=0).max()), 1e-12)
    p = (p - p[0]) / span
    count, eps = len(p), 1e-10
    for i in range(count):
        a, b = p[i], p[(i + 1) % count]
        if np.linalg.norm(a - b) < eps:
            raise ValueError("Polygon has a zero-length edge")
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            c, d = p[j], p[(j + 1) % count]
            o1, o2 = _cross(b - a, c - a), _cross(b - a, d - a)
            o3, o4 = _cross(d - c, a - c), _cross(d - c, b - c)
            if (
                o1 * o2 <= 0
                and o3 * o4 <= 0
                and np.all(
                    np.maximum(np.minimum(a, b), np.minimum(c, d))
                    <= np.minimum(np.maximum(a, b), np.maximum(c, d)) + eps
                )
            ):
                raise ValueError("Polygon edges intersect")
    area = sum(_cross(p[i], p[(i + 1) % count]) for i in range(count))
    sign = 1 if area > 0 else -1
    remaining, result = list(range(count)), []
    while len(remaining) > 3:
        for k, b in enumerate(remaining):
            a, c = remaining[k - 1], remaining[(k + 1) % len(remaining)]
            if sign * _cross(p[b] - p[a], p[c] - p[b]) <= eps:
                continue
            contains = any(
                all(
                    sign * _cross(p[v] - p[u], p[q] - p[u]) >= -eps
                    for u, v in ((a, b), (b, c), (c, a))
                )
                for q in remaining
                if q not in (a, b, c)
            )
            if not contains:
                result.append((a, b, c))
                remaining.pop(k)
                break
        else:
            raise ValueError("Polygon cannot be triangulated without degenerate faces")
    result.append(tuple(remaining))
    return result


def validate(doc):
    """Validate the complete retained source before compilation or publication."""
    fields = {
        "schema_version",
        "next_id",
        "vertices",
        "edges",
        "faces",
        "part_names",
        "part_pivots",
        "shading",
    }
    if (
        not isinstance(doc, dict)
        or set(doc) - fields
        or type(doc.get("schema_version")) is not int
        or doc["schema_version"] not in (1, 2, 3, 4, 5)
    ):
        raise ValueError("Unsupported editable topology version or fields")
    if "shading" in doc:
        from .mesh_normals import validate_settings
        if doc["schema_version"] < 4:
            raise ValueError("Normal policy requires topology version 4")
        validate_settings(doc["shading"])
    if type(doc.get("next_id")) is not int or doc["next_id"] < 1:
        raise ValueError("Invalid topology identity counter")
    for kind in ("vertices", "edges", "faces"):
        if not isinstance(doc.get(kind), list):
            raise ValueError(f"Topology {kind} must be an array")  # noqa: TRY004 — document validation boundary
    seen = set()

    def record(item, allowed, required):
        if not isinstance(item, dict) or set(item) - allowed or not required <= item.keys():
            raise ValueError("Invalid topology component fields")

    def identity(item, prefix):
        ident = item.get("id")
        if (
            not isinstance(ident, str)
            or len(ident) < 2
            or ident[0] != prefix
            or not ident[1:].isascii()
            or not ident[1:].isdigit()
            or ident[1] == "0"
            or int(ident[1:]) in seen
            or int(ident[1:]) >= doc["next_id"]
        ):
            raise ValueError("Invalid or duplicate topology identity")
        seen.add(int(ident[1:]))

    def vector(value, size, label):
        if (
            not isinstance(value, list)
            or len(value) != size
            or any(
                type(v) not in (int, float) or abs(v) > MAX_FLOAT32 or not isfinite(v)
                for v in value
            )
        ):
            raise ValueError(f"Invalid {label}: requires {size} finite numeric values")

    names = doc.get("part_names")
    if names is not None and (
        not isinstance(names, list)
        or any(not isinstance(n, str) for n in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("Part names must be an array of unique strings")
    pivots = doc.get("part_pivots")
    if pivots is not None:
        if not isinstance(pivots, list) or len(pivots) != len(names or []):
            raise ValueError("One pivot is required per named part")
        for pivot in pivots:
            vector(pivot, 3, "part pivot")
    verts = {}
    for vertex in doc["vertices"]:
        record(vertex, {"id", "position", "part"}, {"id", "position"})
        identity(vertex, "v")
        vector(vertex["position"], 3, "vertex position")
        part = vertex.get("part")
        if part is not None and (type(part) is not int or not 0 <= part < len(names or [])):
            raise ValueError("Vertex part index outside named parts")
        verts[vertex["id"]] = vertex["position"]
    needed = set()
    for face in doc["faces"]:
        allowed = {"id", "corners", "material"}
        if doc["schema_version"] >= 5:
            allowed.add("smooth")
        record(face, allowed, {"id", "corners", "material"})
        if "smooth" in face and type(face["smooth"]) is not bool:
            raise ValueError("Polygon smooth flag must be boolean")
        identity(face, "f")
        if type(face["material"]) is not int or not 0 <= face["material"] < 2**31:
            raise ValueError("Invalid polygon material slot")
        if not isinstance(face["corners"], list):
            raise ValueError("Polygon corners must be an array")  # noqa: TRY004 — document validation boundary
        ids = []
        for corner in face["corners"]:
            corner_fields = {"id", "vertex", "uv", "normal"}
            if doc["schema_version"] >= 3:
                corner_fields.add("pin")
            record(corner, corner_fields, {"id", "vertex"})
            if "pin" in corner and (
                type(corner["pin"]) is not bool
                or (corner["pin"] and corner.get("uv") is None)
            ):
                raise ValueError("Pinned UV corners require boolean pin state and UV coordinates")
            identity(corner, "c")
            if not isinstance(corner["vertex"], str) or corner["vertex"] not in verts:
                raise ValueError("Corner references a missing vertex")
            ids.append(corner["vertex"])
            for field, size in (("uv", 2), ("normal", 3)):
                value = corner.get(field)
                if value is not None:
                    vector(value, size, f"corner {field}")
        if len(ids) < 3 or len(ids) != len(set(ids)):
            raise ValueError("Polygon requires at least three distinct vertices")
        triangles([verts[i] for i in ids])
        needed.update(tuple(sorted((a, b))) for a, b in zip(ids, ids[1:] + ids[:1]))
    actual = set()
    for edge in doc["edges"]:
        record(edge, {"id", "vertices", "seam", "sharp"}, {"id", "vertices", "seam", "sharp"})
        identity(edge, "e")
        if (
            not isinstance(edge["vertices"], list)
            or len(edge["vertices"]) != 2
            or any(not isinstance(v, str) for v in edge["vertices"])
        ):
            raise ValueError("Edge requires two vertex identities")
        if type(edge["seam"]) is not bool or type(edge["sharp"]) is not bool:
            raise ValueError("Edge seam and sharp attributes must be booleans")
        pair = tuple(sorted(edge["vertices"]))
        if (
            pair in actual
            or pair[0] == pair[1]
            or any(v not in verts for v in pair)
            or (doc["schema_version"] == 1 and pair not in needed)
        ):
            raise ValueError("Invalid or duplicate polygon edge")
        actual.add(pair)
    if not needed <= actual:
        raise ValueError("Polygon edges are incomplete")


def compile(doc):
    """Return triangle mesh plus render-vertex and triangle-to-polygon identity maps."""
    from . import pbr

    validate(doc)
    vertices = {v["id"]: v for v in doc["vertices"]}
    positions, faces, materials, uvs, normals, parts, ids, face_ids = [], [], [], [], [], [], [], []
    lookup = {}
    has_uv = any(c.get("uv") is not None for f in doc["faces"] for c in f["corners"])
    has_normals = any(c.get("normal") is not None for f in doc["faces"] for c in f["corners"])
    generated_normals = None
    if "shading" in doc:
        from .mesh_normals import corner_normals
        generated_normals = corner_normals(doc)
        has_normals = True
    has_parts = any(v.get("part") is not None for v in doc["vertices"])
    for face in doc["faces"]:
        corners = face["corners"]
        start = min(range(len(corners)), key=lambda i: int(corners[i]["id"][1:]))
        corners = corners[start:] + corners[:start]
        points = [vertices[c["vertex"]]["position"] for c in corners]
        fallback = normal(points).tolist()
        compiled = []
        for c in corners:
            uv, n = c.get("uv") or [0.0, 0.0], c.get("normal") or fallback
            if generated_normals is not None:
                n = generated_normals[c["id"]]
            key = (c["vertex"], tuple(uv) if has_uv else None, tuple(n) if has_normals else None)
            if key not in lookup:
                lookup[key] = len(positions)
                v = vertices[c["vertex"]]
                positions.append(v["position"])
                ids.append(c["vertex"])
                uvs.append(uv)
                normals.append(n)
                parts.append(v.get("part") or 0)
            compiled.append(lookup[key])
        for triangle in triangles(points):
            faces.append([compiled[i] for i in triangle])
            materials.append(face["material"])
            face_ids.append(face["id"])
    if doc["schema_version"] >= 2:
        # Loose vertices/edges are authored geometry even without a surface.
        used = set(ids)
        for v in doc["vertices"]:
            if v["id"] not in used:
                positions.append(v["position"])
                ids.append(v["id"])
                uvs.append([0.0, 0.0])
                normals.append([0.0, 1.0, 0.0])
                parts.append(v.get("part") or 0)
    # Geometry order follows durable vertices, independent of face winding.
    rank = {v["id"]: i for i, v in enumerate(doc["vertices"])}
    order = sorted(range(len(ids)), key=lambda i: rank[ids[i]])
    inverse = {old: new for new, old in enumerate(order)}
    positions, uvs, normals, parts, ids = (
        [values[i] for i in order] for values in (positions, uvs, normals, parts, ids)
    )
    faces = [[inverse[i] for i in face] for face in faces]
    mesh = pbr.Mesh(
        np.asarray(positions, dtype=np.float32).reshape(-1, 3),
        np.asarray(faces, dtype=np.int32).reshape(-1, 3),
        face_mats=np.asarray(materials, dtype=np.int32),
        vert_uvs=np.asarray(uvs, dtype=np.float32).reshape(-1, 2) if has_uv else None,
        vert_normals=np.asarray(normals, dtype=np.float32).reshape(-1, 3) if has_normals else None,
        vert_part_ids=np.asarray(parts, dtype=np.int32) if has_parts else None,
        part_names=deepcopy(doc.get("part_names")),
        part_pivots=None
        if doc.get("part_pivots") is None
        else np.asarray(doc["part_pivots"], dtype=np.float32),
        topology=deepcopy(doc),
    )
    return mesh, ids, face_ids


def document(mesh):
    return deepcopy(mesh.topology) if mesh.topology is not None else from_mesh(mesh)


def face_attributes(face):
    """Attributes inherited by generated child faces; absent flags stay absent."""
    return {k: deepcopy(face[k]) for k in ("material", "smooth") if k in face}


def _selected(doc, face_ids):
    if not face_ids or len(set(face_ids)) != len(face_ids):
        raise ValueError("Select one or more distinct polygon faces")
    found = [f for f in doc["faces"] if f["id"] in face_ids]
    if len(found) != len(face_ids):
        raise ValueError("Selected polygon no longer exists")
    return found


def extrude(mesh, face_ids, distance, *, individual=False):
    if type(distance) not in (float, int) or not np.isfinite(distance) or abs(distance) <= 1e-12:
        raise ValueError("Extrusion distance must be finite and nonzero")
    doc = document(mesh)
    selected = _selected(doc, face_ids)
    groups = [[face] for face in selected] if individual else [selected]
    for group in groups:
        _extrude_region(doc, group, distance)
    return compile(doc)[0]


def _extrude_region(doc, selected, distance):
    """Mutate an unpublished document; each group keeps its own cap vertices."""
    loose = loose_edges(doc)
    verts = {v["id"]: v for v in doc["vertices"]}
    normals = [normal([verts[c["vertex"]]["position"] for c in f["corners"]]) for f in selected]
    direction = np.sum(normals, axis=0)
    if np.linalg.norm(direction) < 1e-8:
        raise ValueError("Selected faces have no common extrusion direction")
    offset = direction / np.linalg.norm(direction) * distance
    usage = {}
    for face in selected:
        cs = face["corners"]
        for a, b in zip(cs, cs[1:] + cs[:1]):
            pair = tuple(sorted((a["vertex"], b["vertex"])))
            usage.setdefault(pair, []).append((a, b, face_attributes(face)))
    if any(len(v) > 2 for v in usage.values()):
        raise ValueError("Cannot extrude a non-manifold face region")
    if any(len(v) == 2 and v[0][0]["vertex"] == v[1][0]["vertex"] for v in usage.values()):
        raise ValueError("Selected faces have inconsistent shared-edge winding")
    boundary = [v[0] for v in usage.values() if len(v) == 1]
    if not boundary:
        raise ValueError("Select an open face region with a boundary")
    moved = {}
    chosen = {c["vertex"] for f in selected for c in f["corners"]}
    for old in (identity for identity in verts if identity in chosen):
        v = deepcopy(verts[old])
        v["id"] = _id(doc, "v")
        v["position"] = (np.array(v["position"]) + offset).tolist()
        moved[old] = v["id"]
        doc["vertices"].append(v)
    sides = []
    for a, b, attributes in boundary:
        va, vb = a["vertex"], b["vertex"]
        corners = [
            _corner(doc, v, c.get("uv"))
            for v, c in zip((va, vb, moved[vb], moved[va]), (a, b, b, a))
        ]
        sides.append({"id": _id(doc, "f"), "corners": corners, **attributes})
    for face in selected:
        for c in face["corners"]:
            c["vertex"] = moved[c["vertex"]]
    doc["faces"].extend(sides)
    used = {c["vertex"] for f in doc["faces"] for c in f["corners"]}
    used.update(v for e in loose for v in e["vertices"])
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] in used or v["id"] not in moved]
    inherited_edges = {
        tuple(sorted((moved[e["vertices"][0]], moved[e["vertices"][1]]))): e
        for e in doc["edges"]
        if all(v in moved for v in e["vertices"])
    }
    _edges(doc, loose)
    for edge in doc["edges"]:
        source = inherited_edges.get(tuple(edge["vertices"]))
        if source is not None:
            edge["seam"], edge["sharp"] = source["seam"], source["sharp"]


def inset(mesh, face_ids, thickness):
    """Inset individual planar convex faces by an even local-space distance.

    Inner polygons retain face/corner identities and interpolate their original
    corner UVs. Adjacent selected faces are inset individually. Unsupported
    concavity, nonplanarity and collapsing offsets fail before publication.
    """
    if type(thickness) not in (int, float) or not np.isfinite(thickness) or thickness <= 0:
        raise ValueError("Inset thickness must be finite and positive")
    doc = document(mesh)
    loose = loose_edges(doc)
    selected = _selected(doc, face_ids)
    vertices = {v["id"]: v for v in doc["vertices"]}
    borders = []
    for face in selected:
        original = deepcopy(face["corners"])
        points = np.array([vertices[c["vertex"]]["position"] for c in original])
        n = normal(points)
        extent = max(float(np.ptp(points, axis=0).max()), 1e-12)
        if np.max(np.abs((points - points[0]) @ n)) > extent * 1e-6:
            raise ValueError("Inset currently requires planar faces")
        axis = points[1] - points[0]
        axis /= np.linalg.norm(axis)
        basis = np.array([axis, np.cross(n, axis)])
        plane = (points - points[0]) @ basis.T
        edges = np.roll(plane, -1, axis=0) - plane
        unit = edges / np.linalg.norm(edges, axis=1)[:, None]
        inward = np.column_stack((-unit[:, 1], unit[:, 0]))
        if any(_cross(unit[i - 1], unit[i]) <= 1e-10 for i in range(len(points))):
            raise ValueError("Inset currently requires convex faces without collinear corners")
        inner = np.array(
            [
                plane[i] + np.linalg.solve(np.array([inward[i - 1], inward[i]]), [thickness] * 2)
                for i in range(len(points))
            ]
        )
        # Every new point must satisfy every shifted edge half-plane. This
        # catches offsets beyond the inradius, including an apparently valid
        # polygon whose corners have crossed to the opposite side.
        distances = np.einsum("ijk,jk->ij", inner[:, None, :] - plane[None, :, :], inward)
        if np.any(distances < thickness - extent * 1e-9) or any(
            np.dot(inner[(i + 1) % len(inner)] - inner[i], unit[i]) <= extent * 1e-9
            for i in range(len(inner))
        ):
            raise ValueError("Inset thickness collapses the face; use a smaller value")
        source_triangles = triangles(points)
        source_uvs = [c.get("uv") for c in original]

        def uv_at(point, source_uvs=source_uvs, source_triangles=source_triangles, plane=plane):
            if all(uv is None for uv in source_uvs):
                return None
            for indices in source_triangles:
                a, b, c = plane[list(indices)]
                weights = np.linalg.solve(np.column_stack((b - a, c - a)), point - a)
                bary = np.array([1 - weights.sum(), *weights])
                if min(bary) >= -1e-8:
                    uvs = np.array([source_uvs[i] or [0, 0] for i in indices])
                    return (bary @ uvs).tolist()
            raise ValueError("Cannot interpolate inset corner attributes")

        for i, corner in enumerate(face["corners"]):
            vertex = deepcopy(vertices[corner["vertex"]])
            vertex["id"] = _id(doc, "v")
            vertex["position"] = (points[0] + inner[i] @ basis).tolist()
            doc["vertices"].append(vertex)
            corner.update(vertex=vertex["id"], uv=uv_at(inner[i]), normal=None)
        for i, a in enumerate(original):
            j = (i + 1) % len(original)
            corners = [a, original[j], face["corners"][j], face["corners"][i]]
            borders.append(
                {
                    "id": _id(doc, "f"),
                    **face_attributes(face),
                    "corners": [_corner(doc, c["vertex"], c.get("uv")) for c in corners],
                }
            )
    doc["faces"].extend(borders)
    _edges(doc, loose)
    return compile(doc)[0]


def edge_usage(doc):
    uses = {}
    for face in doc["faces"]:
        ids = [c["vertex"] for c in face["corners"]]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            uses.setdefault(tuple(sorted((a, b))), []).append((a, b))
    return uses


def loose_edges(doc):
    used = edge_usage(doc)
    return [e for e in doc["edges"] if tuple(sorted(e["vertices"])) not in used]


def delete_components(mesh, mode, identities):
    """Delete vertices, edges or faces; preserve surviving loose geometry.

    Face deletion removes only newly unused edges/vertices of the deleted faces.
    Edge deletion retains other edges as wires; vertex deletion removes all
    incident edges/faces. The object remains even when its geometry is empty.
    """
    doc = document(mesh)
    if mode not in ("vertices", "edges", "faces") or not identities:
        raise ValueError("Select components to delete")
    chosen = set(identities)
    if chosen - {v["id"] for v in doc[mode]}:
        raise ValueError("Selected components no longer exist")
    doc["schema_version"] = max(2, doc["schema_version"])
    removed_edges = set()
    candidates = set()
    if mode == "vertices":
        candidates = chosen
        removed_edges = {e["id"] for e in doc["edges"] if chosen.intersection(e["vertices"])}
        removed_faces = {
            f["id"] for f in doc["faces"] if any(c["vertex"] in chosen for c in f["corners"])
        }
    elif mode == "edges":
        removed_edges = chosen
        pairs = {tuple(sorted(e["vertices"])) for e in doc["edges"] if e["id"] in chosen}
        candidates = {v for pair in pairs for v in pair}
        removed_faces = set()
        for f in doc["faces"]:
            ids = [c["vertex"] for c in f["corners"]]
            if any(tuple(sorted((a, b))) in pairs for a, b in zip(ids, ids[1:] + ids[:1])):
                removed_faces.add(f["id"])
    else:
        removed_faces = chosen
        candidates = {c["vertex"] for f in doc["faces"] if f["id"] in chosen for c in f["corners"]}
        removed_pairs = edge_usage({"faces": [f for f in doc["faces"] if f["id"] in chosen]})
        remaining_pairs = edge_usage({"faces": [f for f in doc["faces"] if f["id"] not in chosen]})
        removed_edges = {
            e["id"]
            for e in doc["edges"]
            if tuple(sorted(e["vertices"])) in removed_pairs
            and tuple(sorted(e["vertices"])) not in remaining_pairs
        }
    doc["faces"] = [f for f in doc["faces"] if f["id"] not in removed_faces]
    doc["edges"] = [e for e in doc["edges"] if e["id"] not in removed_edges]
    used = {v for e in doc["edges"] for v in e["vertices"]}
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] not in candidates or v["id"] in used]
    return compile(doc)[0]


def loop_cut(mesh, identities, *, cuts=1):
    """Insert evenly spaced cuts through the quad strip reached from a seed edge."""
    if type(cuts) is not int or not 1 <= cuts <= 64:
        raise ValueError("Loop cut count must be an integer from 1 to 64")
    doc = document(mesh)
    edges = {e["id"]: e for e in doc["edges"]}
    if len(identities) != 1 or identities[0] not in edges:
        raise ValueError("Select one existing edge to start a centered loop cut")
    adjacent = {}
    face_pairs = {}
    for face in doc["faces"]:
        pairs = list(edge_usage({"faces": [face]}))
        face_pairs[face["id"]] = pairs
        for pair in pairs:
            adjacent.setdefault(pair, []).append(face)
    pending = [tuple(sorted(edges[identities[0]]["vertices"]))]
    cut, touched = set(), {}
    while pending:
        pair = pending.pop()
        if pair in cut:
            continue
        neighbors = adjacent.get(pair, [])
        if not 1 <= len(neighbors) <= 2:
            raise ValueError("Loop cut requires manifold quad edges, not loose wires")
        cut.add(pair)
        for face in neighbors:
            pairs = face_pairs[face["id"]]
            if len(pairs) != 4:
                raise ValueError("Loop cut requires a connected strip of quad faces")
            opposite = pairs[(pairs.index(pair) + 2) % 4]
            pending.append(opposite)
            touched[face["id"]] = face
    vertices = {v["id"]: v for v in doc["vertices"]}
    edge_points = {}
    split_edges = []
    for edge in doc["edges"]:
        pair = tuple(sorted(edge["vertices"]))
        if pair not in cut:
            split_edges.append(edge)
            continue
        a, b = [vertices[v] for v in edge["vertices"]]
        if a["part"] != b["part"]:
            raise ValueError("Loop cut cannot interpolate across named parts")
        chain = [a["id"]]
        for k in range(1, cuts + 1):
            fraction = k / (cuts + 1)
            point = (1 - fraction) * np.array(a["position"]) + fraction * np.array(b["position"])
            vertex = {"id": _id(doc, "v"), "position": point.tolist(), "part": a["part"]}
            doc["vertices"].append(vertex)
            chain.append(vertex["id"])
        chain.append(b["id"])
        edge_points[pair] = chain
        for i, (start, end) in enumerate(pairwise(chain)):
            half = deepcopy(edge)
            half["id"] = edge["id"] if i == 0 else _id(doc, "e")
            half["vertices"] = sorted((start, end))
            split_edges.append(half)
    faces, centers = [], []

    def interpolated_corner(a, b, chain, k):
        if k == 0:
            return a
        if k == cuts + 1:
            return b
        fraction = k / (cuts + 1)
        uv = None
        if a["uv"] is not None and b["uv"] is not None:
            uv = ((1 - fraction) * np.array(a["uv"]) + fraction * np.array(b["uv"])).tolist()
        n = None
        if a["normal"] is not None and b["normal"] is not None:
            average = (1 - fraction) * np.array(a["normal"]) + fraction * np.array(b["normal"])
            length = np.linalg.norm(average)
            if length > 1e-12:
                n = (average / length).tolist()
        return _corner(doc, chain[k], uv, n)

    def oriented_chain(a, b):
        chain = edge_points[tuple(sorted((a["vertex"], b["vertex"])))]
        return chain if chain[0] == a["vertex"] else chain[::-1]

    for face in doc["faces"]:
        if face["id"] not in touched:
            faces.append(face)
            continue
        pairs = face_pairs[face["id"]]
        crossed = [i for i, pair in enumerate(pairs) if pair in cut]
        if len(crossed) != 2 or (crossed[1] - crossed[0]) % 4 != 2:
            raise ValueError("Loop cut cannot cross itself within a face")
        i = crossed[0]
        c = face["corners"][i:] + face["corners"][:i]
        first, second = oriented_chain(c[0], c[1]), oriented_chain(c[3], c[2])
        for k in range(cuts + 1):
            corners = [
                interpolated_corner(c[0], c[1], first, k),
                interpolated_corner(c[0], c[1], first, k + 1),
                interpolated_corner(c[3], c[2], second, k + 1),
                interpolated_corner(c[3], c[2], second, k),
            ]
            faces.append(
                {
                    "id": face["id"] if k == 0 else _id(doc, "f"),
                    **face_attributes(face),
                    "corners": corners,
                }
            )
            if k:
                centers.append(tuple(sorted((first[k], second[k]))))
    loose = loose_edges(doc)
    doc["faces"] = faces
    doc["edges"] = split_edges
    _edges(doc, loose)
    doc["schema_version"] = max(2, doc["schema_version"])
    selected = [e["id"] for e in doc["edges"] if tuple(sorted(e["vertices"])) in centers]
    return compile(doc)[0], selected


def slide_edges(mesh, identities, factor):
    """Slide one connected quad edge chain/loop toward either neighboring rail.

    A geometric seed and dominant local axis define the positive rail, making
    the sign independent of source record order. UV coordinates stay unchanged.
    """
    if type(factor) not in (int, float) or not isfinite(factor) or not -1 < factor < 1:
        raise ValueError("Slide factor must be finite and strictly between -1 and 1")
    doc = document(mesh)
    chosen = set(identities)
    edges = {e["id"]: e for e in doc["edges"]}
    if not chosen or chosen - edges.keys():
        raise ValueError("Select existing edges to slide")
    incident, selected_incident = {}, {}
    for edge in doc["edges"]:
        for vertex in edge["vertices"]:
            incident.setdefault(vertex, set()).add(edge["id"])
            if edge["id"] in chosen:
                selected_incident.setdefault(vertex, set()).add(edge["id"])
    if any(len(e) > 2 or len(incident[v] - e) != 2 for v, e in selected_incident.items()):
        raise ValueError("Slide requires one unbranched quad loop or boundary-to-boundary chain")
    pairs = {tuple(sorted(e["vertices"])): e["id"] for e in doc["edges"] if e["id"] in chosen}
    sides = {identity: [] for identity in chosen}
    for face in doc["faces"]:
        vertices = [c["vertex"] for c in face["corners"]]
        for i, (a, b) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
            identity = pairs.get(tuple(sorted((a, b))))
            if identity is None:
                continue
            if len(vertices) != 4:
                raise ValueError("Slide requires quad faces on both sides")
            sides[identity].append({a: vertices[i - 1], b: vertices[(i + 2) % 4]})
    if any(len(rails) != 2 for rails in sides.values()):
        raise ValueError("Slide requires two manifold neighboring faces per edge")
    positions = {v["id"]: np.array(v["position"]) for v in doc["vertices"]}
    seed = min(
        chosen,
        key=lambda identity: sorted(tuple(positions[v]) for v in edges[identity]["vertices"]),
    )
    rail_centers = [np.mean([positions[v] for v in rail.values()], axis=0) for rail in sides[seed]]
    axis = int(np.argmax(np.abs(rail_centers[0] - rail_centers[1])))
    positive = 0 if rail_centers[0][axis] > rail_centers[1][axis] else 1
    targets = dict(sides[seed][positive if factor >= 0 else 1 - positive])
    pending, visited = [seed], {seed}
    while pending:
        identity = pending.pop()
        for vertex in edges[identity]["vertices"]:
            for neighbor in selected_incident[vertex] - visited:
                choices = [
                    rail
                    for rail in sides[neighbor]
                    if all(v not in targets or targets[v] == target for v, target in rail.items())
                ]
                if len(choices) != 1:
                    raise ValueError("Slide rails are ambiguous or inconsistently connected")
                targets.update(choices[0])
                visited.add(neighbor)
                pending.append(neighbor)
    if visited != chosen or set(targets.values()) & set(selected_incident):
        raise ValueError("Slide one connected edge chain or loop at a time")
    result = np.array(
        [
            positions[v["id"]] + abs(factor) * (positions[targets[v["id"]]] - positions[v["id"]])
            if v["id"] in targets
            else positions[v["id"]]
            for v in doc["vertices"]
        ]
    )
    weights = np.array([v["id"] in targets for v in doc["vertices"]], dtype=float)
    return _publish_positions(doc, result, weights)


def dissolve_edges(mesh, identities):
    """Join planar face regions across selected interior edges, keeping boundaries.

    Boundary vertices are retained, and existing loose geometry is untouched.
    Holes, mixed materials, inconsistent winding and nonplanar regions reject.
    """
    doc = document(mesh)
    chosen = set(identities)
    edges = {e["id"]: tuple(sorted(e["vertices"])) for e in doc["edges"]}
    if not chosen or chosen - edges.keys():
        raise ValueError("Select existing interior edges to dissolve")
    by_pair = {}
    for face in doc["faces"]:
        for pair in edge_usage({"faces": [face]}):
            by_pair.setdefault(pair, []).append(face["id"])
    adjacency = {}
    for identity in chosen:
        neighbors = by_pair.get(edges[identity], [])
        if len(neighbors) != 2:
            raise ValueError("Dissolve requires interior edges shared by exactly two faces")
        a, b = neighbors
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    remaining = set(adjacency)
    groups = []
    for face in doc["faces"]:
        if face["id"] not in remaining:
            continue
        pending, group = [face["id"]], set()
        while pending:
            identity = pending.pop()
            if identity in group:
                continue
            group.add(identity)
            pending.extend(adjacency[identity] - group)
        remaining -= group
        groups.append([f for f in doc["faces"] if f["id"] in group])
    positions = {v["id"]: v["position"] for v in doc["vertices"]}
    candidates, removed, joined = set(), set(), []
    for group in groups:
        if len({f["material"] for f in group}) != 1:
            raise ValueError("Dissolve faces with one material at a time")
        default_smooth = doc.get("shading", {}).get("mode") == "smooth"
        if len({f.get("smooth", default_smooth) for f in group}) != 1:
            raise ValueError("Dissolve faces with one shading mode at a time")
        uses = edge_usage({"faces": group})
        if any(len(u) > 2 or (len(u) == 2 and u[0] != u[1][::-1]) for u in uses.values()):
            raise ValueError("Dissolve region has inconsistent or nonmanifold winding")
        boundary = {}
        for face in group:
            corners = face["corners"]
            for first, second in zip(corners, corners[1:] + corners[:1]):
                a, b = first["vertex"], second["vertex"]
                candidates.add(a)
                if len(uses[tuple(sorted((a, b)))]) == 1:
                    if a in boundary:
                        raise ValueError("Dissolve requires a simple boundary without branches")
                    boundary[a] = (b, first)
        if len(boundary) < 3:
            raise ValueError("Dissolve requires an open planar face region")
        current = start = next(iter(boundary))
        cycle, visited = [], set()
        while current not in visited:
            if current not in boundary:
                raise ValueError("Dissolve region boundary is not closed")
            visited.add(current)
            current, corner = boundary[current]
            cycle.append(corner)
        if current != start or len(visited) != len(boundary):
            raise ValueError("Dissolve holes or multiple boundary loops separately")
        points = np.array([positions[c["vertex"]] for c in cycle])
        n = normal(points)
        all_points = np.array([positions[c["vertex"]] for f in group for c in f["corners"]])
        if (
            np.max(np.abs((all_points - points[0]) @ n))
            > max(float(np.ptp(all_points, axis=0).max()), 1e-12) * 1e-6
        ):
            raise ValueError("Dissolve requires coplanar faces")
        triangles(points)
        for corner in cycle:
            corner["normal"] = None
        joined.append({"id": group[0]["id"], **face_attributes(group[0]), "corners": cycle})
        removed.update(f["id"] for f in group)
    loose = loose_edges(doc)
    doc["faces"] = [f for f in doc["faces"] if f["id"] not in removed] + joined
    _edges(doc, loose)
    used = {v for e in doc["edges"] for v in e["vertices"]}
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] not in candidates or v["id"] in used]
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], [f["id"] for f in joined]


def fill_loop(mesh, mode, identities):
    """Cap one simple closed boundary/wire loop, preserving its edge identities."""
    doc = document(mesh)
    if mode not in ("vertices", "edges") or not identities:
        raise ValueError("Select one closed loop of boundary edges or vertices")
    chosen = set(identities)
    if chosen - {v["id"] for v in doc[mode]}:
        raise ValueError("Selected components no longer exist")
    edges = [
        e
        for e in doc["edges"]
        if (e["id"] in chosen if mode == "edges" else set(e["vertices"]) <= chosen)
    ]
    graph = {}
    for edge in edges:
        a, b = edge["vertices"]
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    if (
        len(graph) < 3
        or any(len(n) != 2 for n in graph.values())
        or (mode == "vertices" and set(graph) != chosen)
    ):
        raise ValueError("Fill requires one closed loop without branches")
    start = next(iter(graph))
    cycle, previous, current = [start], start, graph[start][0]
    while current != start:
        if current in cycle:
            raise ValueError("Fill requires one closed loop")
        cycle.append(current)
        following = next(n for n in graph[current] if n != previous)
        previous, current = current, following
    if len(cycle) != len(graph):
        raise ValueError("Fill one boundary loop at a time")
    uses = edge_usage(doc)
    orientations = []
    for a, b in zip(cycle, cycle[1:] + cycle[:1]):
        shared = uses.get(tuple(sorted((a, b))), [])
        if len(shared) > 1:
            raise ValueError("Cannot fill an edge already shared by two faces")
        if shared:
            orientations.append(shared[0] == (a, b))
    if orientations and any(o != orientations[0] for o in orientations):
        raise ValueError("Boundary winding is inconsistent")
    if orientations and orientations[0]:
        cycle.reverse()
    vertices = {v["id"]: v["position"] for v in doc["vertices"]}
    points = np.array([vertices[v] for v in cycle])
    n = normal(points)
    if (
        np.max(np.abs((points - points[0]) @ n))
        > max(float(np.ptp(points, axis=0).max()), 1e-12) * 1e-6
    ):
        raise ValueError("Fill requires a planar boundary loop")
    triangles(points)  # Reject crossed or degenerate loops before publishing.
    uv = np.delete(points, int(np.argmax(np.abs(n))), axis=1)
    uv = (uv - uv.min(axis=0)) / np.maximum(np.ptp(uv, axis=0), 1e-12)
    corners = [_corner(doc, v, coord.tolist()) for v, coord in zip(cycle, uv)]
    face = {"id": _id(doc, "f"), "corners": corners, "material": 0}
    doc["faces"].append(face)
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], face["id"]


def bisect(mesh, plane_point, plane_normal, *, keep="both", fill=False):
    """Split an entire mesh at a local plane, optionally removing one side."""
    point, direction = _coordinates(plane_point), _coordinates(plane_normal)
    length = float(np.linalg.norm(direction))
    if length <= 1e-12 or not np.isfinite(length):
        raise ValueError("Bisect normal must be nonzero and finite")
    if keep not in ("both", "negative", "positive") or type(fill) is not bool:
        raise ValueError("Choose both, negative or positive side and a boolean fill")
    if fill and keep == "both":
        raise ValueError("Choose one side to retain before filling the cut")
    direction /= length
    doc = document(mesh)
    vertices = {v["id"]: v for v in doc["vertices"]}
    points = {v: np.asarray(record["position"], dtype=float) for v, record in vertices.items()}
    distances = {v: float((p - point) @ direction) for v, p in points.items()}
    tolerance = max(max((abs(d) for d in distances.values()), default=1), 1) * 1e-8
    signs = {v: 0 if abs(d) <= tolerance else (1 if d > 0 else -1) for v, d in distances.items()}
    original_uses = edge_usage(doc)
    if fill and any(
        len(original_uses.get(tuple(sorted(e["vertices"])), [])) != 2 for e in doc["edges"]
    ):
        raise ValueError("Fill bisect requires a closed surface")
    loose_ids = {e["id"] for e in doc["edges"] if tuple(sorted(e["vertices"])) not in original_uses}
    crossings = {}
    for edge in list(doc["edges"]):
        a, b = edge["vertices"]
        if signs[a] * signs[b] != -1:
            continue
        if vertices[a]["part"] != vertices[b]["part"]:
            raise ValueError("Bisect cannot interpolate across named parts")
        ratio = distances[a] / (distances[a] - distances[b])
        vertex = {
            "id": _id(doc, "v"),
            "position": (points[a] + ratio * (points[b] - points[a])).tolist(),
            "part": vertices[a]["part"],
        }
        doc["vertices"].append(vertex)
        crossings[tuple(sorted((a, b)))] = vertex["id"]
        signs[vertex["id"]] = 0
        split = deepcopy(edge)
        split["id"] = _id(doc, "e")
        if edge["id"] in loose_ids:
            loose_ids.add(split["id"])
        edge["vertices"] = sorted((a, vertex["id"]))
        split["vertices"] = sorted((vertex["id"], b))
        doc["edges"].append(split)
    new_faces = []
    used_corners = set()
    sides = (-1, 1) if keep == "both" else ((-1,) if keep == "negative" else (1,))
    for face in doc["faces"]:
        old = face["corners"]
        face_signs = {signs[c["vertex"]] for c in old}
        split_face = -1 in face_signs and 1 in face_signs
        if split_face:
            n_crossings = sum(
                signs[a["vertex"]] * signs[b["vertex"]] == -1
                for a, b in zip(old, old[1:] + old[:1])
            )
            if n_crossings > 2:
                raise ValueError(
                    "Bisect of a disconnected concave face requires splitting it first"
                )
        emitted = 0
        for side in sides:
            if not split_face and keep == "both" and emitted:
                continue
            corners = []
            for current, following in zip(old, old[1:] + old[:1]):
                a, b = current["vertex"], following["vertex"]
                if signs[a] * side >= 0:
                    corners.append(deepcopy(current))
                if signs[a] * signs[b] == -1:
                    identity = crossings[tuple(sorted((a, b)))]
                    ratio = distances[a] / (distances[a] - distances[b])
                    uv = (
                        None
                        if current["uv"] is None or following["uv"] is None
                        else (
                            (1 - ratio) * np.asarray(current["uv"])
                            + ratio * np.asarray(following["uv"])
                        ).tolist()
                    )
                    n = None
                    if current["normal"] is not None and following["normal"] is not None:
                        weighted = (1 - ratio) * np.asarray(current["normal"]) + ratio * np.asarray(
                            following["normal"]
                        )
                        if np.linalg.norm(weighted) > 1e-12:
                            n = (weighted / np.linalg.norm(weighted)).tolist()
                    corners.append(_corner(doc, identity, uv, n))
            if len(corners) < 3:
                continue
            for corner in corners:
                if corner["id"] in used_corners:
                    corner["id"] = _id(doc, "c")
                used_corners.add(corner["id"])
            result = {
                "id": face["id"] if emitted == 0 else _id(doc, "f"),
                "corners": corners,
                **face_attributes(face),
            }
            new_faces.append(result)
            emitted += 1
    doc["faces"] = new_faces
    # Retain source wire segments and surviving isolated points, including an
    # entirely empty result when a clear side removes the whole object.
    allowed = {
        v
        for v, sign in signs.items()
        if keep == "both" or sign == 0 or sign == (-1 if keep == "negative" else 1)
    }
    wire = [e for e in doc["edges"] if e["id"] in loose_ids and set(e["vertices"]) <= allowed]
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] in allowed]
    _edges(doc, wire)
    doc["schema_version"] = max(2, doc["schema_version"])
    result = compile(doc)[0]
    cut_ids = [e["id"] for e in doc["edges"] if all(signs[v] == 0 for v in e["vertices"])]
    if fill and cut_ids:
        boundary = edge_usage(doc)
        cut_ids = [
            e["id"]
            for e in doc["edges"]
            if e["id"] in cut_ids and len(boundary.get(tuple(sorted(e["vertices"])), [])) == 1
        ]
        if cut_ids:
            result, face_id = fill_loop(result, "edges", cut_ids)
            return result, "faces", [face_id]
    return result, "edges", cut_ids


def bevel_edges(mesh, identities, distance, *, segments=1):
    """Bevel one convex-solid edge with a circular profile and 1–64 segments."""
    if type(segments) is not int or not 1 <= segments <= 64:
        raise ValueError("Bevel segments must be a whole number from 1 to 64")
    if type(distance) not in (int, float) or not np.isfinite(distance) or distance <= 0:
        raise ValueError("Bevel distance must be positive and finite")
    doc = document(mesh)
    selected = set(identities)
    edges = [e for e in doc["edges"] if e["id"] in selected]
    if len(selected) != 1 or len(edges) != 1:
        raise ValueError("Select exactly one edge to bevel")
    usage = edge_usage(doc)
    if any(len(u) != 2 or u[0] != u[1][::-1] for u in usage.values()) or len(usage) != len(
        doc["edges"]
    ):
        raise ValueError("Edge bevel requires a closed consistently wound solid")
    if len({v["part"] for v in doc["vertices"]}) != 1:
        raise ValueError("Bevel within one named part")
    points = {v["id"]: np.asarray(v["position"], dtype=float) for v in doc["vertices"]}
    cloud = np.array(list(points.values()))
    tolerance = max(float(np.ptp(cloud, axis=0).max()), 1e-12) * 1e-7
    pair = tuple(sorted(edges[0]["vertices"]))
    neighbors = []
    for face in doc["faces"]:
        n = normal([points[c["vertex"]] for c in face["corners"]])
        origin = points[face["corners"][0]["vertex"]]
        if np.any((cloud - origin) @ n > tolerance) or any(
            abs(float((points[c["vertex"]] - origin) @ n)) > tolerance for c in face["corners"]
        ):
            raise ValueError("Edge bevel currently requires a convex solid with planar faces")
        directions = edge_usage({"faces": [face]}).get(pair)
        if directions:
            a, b = directions[0]
            tangent = points[b] - points[a]
            tangent /= np.linalg.norm(tangent)
            inward = np.cross(n, tangent)
            neighbors.append((face, n, inward))
    if len(neighbors) != 2:
        raise ValueError("Select an edge shared by exactly two faces")
    n0, n1 = neighbors[0][1], neighbors[1][1]
    if abs(float(n0 @ n1)) >= 1 - 1e-8:
        raise ValueError("Cannot bevel a coplanar or folded edge")
    plane_normal = n0 + n1
    midpoint = sum(points[v] for v in pair) / 2
    plane_point = midpoint + distance * neighbors[0][2]
    # Reject offsets that reach unrelated corners instead of silently clamping
    # or cutting a larger region than the selected edge.
    if any(
        float((p - plane_point) @ plane_normal) >= -tolerance
        for v, p in points.items()
        if v not in pair
    ):
        raise ValueError("Bevel distance reaches neighboring vertices")
    cutting_planes = [(plane_point, plane_normal)]
    if segments > 1:
        inward0, inward1 = neighbors[0][2], neighbors[1][2]
        center = midpoint + distance * (inward0 + inward1) / (1 + float(inward0 @ inward1))
        radius = float(np.linalg.norm(plane_point - center))
        angle = float(np.arccos(np.clip(n0 @ n1, -1, 1)))
        vectors = [
            (np.sin((1 - t) * angle) * n0 + np.sin(t * angle) * n1) / np.sin(angle)
            for t in np.linspace(0, 1, segments + 1)
        ]
        cutting_planes = [
            (center + radius * vectors[i], vectors[i] + vectors[i + 1]) for i in range(segments)
        ]
    result, cap_ids = mesh, []
    for cut_point, cut_normal in cutting_planes:
        result, mode, faces = bisect(
            result, cut_point.tolist(), cut_normal.tolist(), keep="negative", fill=True
        )
        if mode != "faces" or len(faces) != 1:
            raise ValueError("Bevel did not produce one closed surface per segment")
        cap_ids.extend(faces)
    result_doc = document(result)
    for face in result_doc["faces"]:
        if face["id"] in cap_ids:
            face.update(face_attributes(neighbors[0][0]))
    if len(set(cap_ids).intersection(f["id"] for f in result_doc["faces"])) != segments:
        raise ValueError("Bevel segments intersected each other")
    return compile(result_doc)[0], cap_ids


def bevel_vertices(mesh, identities, distance):
    """Truncate closed convex three-edge corners by distance along each edge."""
    if type(distance) not in (int, float) or not np.isfinite(distance) or distance <= 0:
        raise ValueError("Bevel distance must be positive and finite")
    doc = document(mesh)
    selected = set(identities)
    vertices = {v["id"]: v for v in doc["vertices"]}
    if not selected or selected - vertices.keys():
        raise ValueError("Select existing vertices to bevel")
    positions = {v: np.asarray(record["position"], dtype=float) for v, record in vertices.items()}
    graph = {v: [] for v in vertices}
    usage = edge_usage(doc)
    for edge in doc["edges"]:
        a, b = edge["vertices"]
        graph[a].append(b)
        graph[b].append(a)
        if selected.intersection((a, b)):
            uses = usage.get(tuple(sorted((a, b))), [])
            if len(uses) != 2 or uses[0] != uses[1][::-1]:
                raise ValueError("Vertex bevel requires a closed consistently wound surface")
            length = float(np.linalg.norm(positions[b] - positions[a]))
            if distance * (int(a in selected) + int(b in selected)) >= length * (1 - 1e-9):
                raise ValueError("Bevel distance collapses an existing edge")
    incident = {v: [] for v in selected}
    for face in doc["faces"]:
        for corner in face["corners"]:
            if corner["vertex"] in selected:
                incident[corner["vertex"]].append(face)
    for v in selected:
        if len(graph[v]) != 3 or len(incident[v]) != 3:
            raise ValueError("Vertex bevel currently requires three-edge manifold corners")
        if any(vertices[n]["part"] != vertices[v]["part"] for n in graph[v]):
            raise ValueError("Bevel within one named part")
        for face in incident[v]:
            n = normal([positions[c["vertex"]] for c in face["corners"]])
            extent = max(float(np.linalg.norm(positions[u] - positions[v])) for u in graph[v])
            if any(float((positions[u] - positions[v]) @ n) > extent * 1e-7 for u in graph[v]):
                raise ValueError("Vertex bevel requires locally convex corners")
    cuts = {}
    for v in vertices:
        if v not in selected:
            continue
        for neighbor in graph[v]:
            length = float(np.linalg.norm(positions[neighbor] - positions[v]))
            ratio = distance / length
            added = {
                "id": _id(doc, "v"),
                "position": (positions[v] + ratio * (positions[neighbor] - positions[v])).tolist(),
                "part": vertices[v]["part"],
            }
            doc["vertices"].append(added)
            cuts[(v, neighbor)] = (added["id"], ratio)
    cap_edges = {v: [] for v in selected}
    for face in doc["faces"]:
        old = face["corners"]
        corners = []
        for i, corner in enumerate(old):
            v = corner["vertex"]
            if v not in selected:
                corners.append(corner)
                continue
            previous, following = old[i - 1], old[(i + 1) % len(old)]
            new = []
            for j, neighbor in enumerate((previous, following)):
                identity, ratio = cuts[(v, neighbor["vertex"])]
                uv = (
                    None
                    if corner["uv"] is None or neighbor["uv"] is None
                    else (
                        (1 - ratio) * np.asarray(corner["uv"]) + ratio * np.asarray(neighbor["uv"])
                    ).tolist()
                )
                item = _corner(doc, identity, uv, corner["normal"])
                if j == 0:
                    item["id"] = corner["id"]
                new.append(item)
            corners.extend(new)
            cap_edges[v].append((new[1]["vertex"], new[0]["vertex"]))
        face["corners"] = corners
    # Shortened original edges keep their IDs and flags.
    for edge in doc["edges"]:
        a, b = edge["vertices"]
        edge["vertices"] = sorted(
            (cuts[(a, b)][0] if a in selected else a, cuts[(b, a)][0] if b in selected else b)
        )
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] not in selected]
    points = {v["id"]: np.asarray(v["position"]) for v in doc["vertices"]}
    faces = []
    for v in vertices:
        if v not in selected:
            continue
        links = dict(cap_edges[v])
        start = cap_edges[v][0][0]
        cycle = [start, links[start], links[links[start]]]
        if len(set(cycle)) != 3 or links[cycle[-1]] != start:
            raise ValueError("Vertex bevel corner fan is inconsistent")
        coords = np.array([points[c] for c in cycle])
        n = normal(coords)
        uv = np.delete(coords, int(np.argmax(np.abs(n))), axis=1)
        uv = (uv - uv.min(axis=0)) / np.maximum(np.ptp(uv, axis=0), 1e-12)
        face = {
            "id": _id(doc, "f"),
            "corners": [_corner(doc, c, coord.tolist()) for c, coord in zip(cycle, uv)],
            **face_attributes(incident[v][0]),
        }
        doc["faces"].append(face)
        faces.append(face["id"])
    _edges(doc, loose_edges(doc))
    return compile(doc)[0], faces


def bridge_edges(mesh, identities):
    """Join two equal boundary/wire loops or chains with untwisted quads.

    Neighboring faces constrain winding; nearest total endpoint distance chooses
    alignment. This initial bridge has no subdivisions, twist or merge mode.
    """
    doc = document(mesh)
    chosen = set(identities)
    edges = [e for e in doc["edges"] if e["id"] in chosen]
    if not chosen or chosen != {e["id"] for e in edges}:
        raise ValueError("Select two existing boundary edge loops or chains")
    uses = edge_usage(doc)
    vertices = {v["id"]: v for v in doc["vertices"]}
    graph = {}
    for edge in edges:
        a, b = edge["vertices"]
        if len(uses.get(tuple(sorted((a, b))), [])) > 1:
            raise ValueError("Bridge requires boundary or wire edges")
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    if any(len(n) > 2 for n in graph.values()):
        raise ValueError("Bridge loops cannot branch")
    if len({vertices[v]["part"] for v in graph}) != 1:
        raise ValueError("Bridge within one named part")
    key = lambda v: tuple(vertices[v]["position"])
    remaining = set(graph)
    paths = []
    while remaining:
        seed = min(remaining, key=key)
        group, pending = {seed}, [seed]
        while pending:
            for v in graph[pending.pop()]:
                if v not in group:
                    group.add(v)
                    pending.append(v)
        ends = [v for v in group if len(graph[v]) == 1]
        if len(ends) not in (0, 2):
            raise ValueError("Bridge requires simple chains or closed loops")
        closed = not ends
        start = min(ends or group, key=key)
        path, previous, current = [start], None, start
        while True:
            options = [v for v in graph[current] if v != previous and v != start]
            if not options:
                break
            following = min(options, key=key)
            if following in path:
                raise ValueError("Bridge requires simple edge loops")
            path.append(following)
            previous, current = current, following
        if len(path) != len(group):
            raise ValueError("Bridge requires simple edge loops")
        paths.append((path, closed))
        remaining -= group
    if len(paths) != 2 or paths[0][1] != paths[1][1] or len(paths[0][0]) != len(paths[1][0]):
        raise ValueError(
            "Bridge requires exactly two separate loops or chains with equal vertex counts"
        )
    a, closed = paths[0]
    b = paths[1][0]
    n = len(a)
    count = n if closed else n - 1
    existing = {tuple(sorted(e["vertices"])) for e in doc["edges"]}
    candidates = []
    for aa in (a, list(reversed(a))):
        for bb0 in (b, list(reversed(b))):
            for shift in range(n if closed else 1):
                bb = bb0[shift:] + bb0[:shift]
                if any(tuple(sorted(pair)) in existing for pair in zip(aa, bb)):
                    continue
                faces = [[aa[i], aa[(i + 1) % n], bb[(i + 1) % n], bb[i]] for i in range(count)]
                valid = True
                for face in faces:
                    for u, v in zip(face, face[1:] + face[:1]):
                        neighbors = uses.get(tuple(sorted((u, v))), [])
                        if neighbors and neighbors[0] != (v, u):
                            valid = False
                    try:
                        triangles([vertices[v]["position"] for v in face])
                    except ValueError:
                        valid = False
                if valid:
                    distance = sum(
                        float(
                            np.linalg.norm(
                                np.asarray(vertices[u]["position"]) - vertices[v]["position"]
                            )
                        )
                        for u, v in zip(aa, bb)
                    )
                    signature = tuple(key(v) for face in faces for v in face)
                    # Without neighboring faces, choose positive dominant-axis
                    # winding rather than inheriting arbitrary edge storage order.
                    wire_only = not any(uses.get(tuple(sorted(e["vertices"]))) for e in edges)
                    direction = normal([vertices[v]["position"] for v in faces[0]])
                    winding_rank = int(wire_only and direction[np.argmax(np.abs(direction))] < 0)
                    candidates.append((distance, winding_rank, signature, faces))
    if not candidates:
        raise ValueError("No nondegenerate bridge with consistent boundary winding")
    faces = min(candidates, key=lambda c: (c[0], c[1], c[2]))[3]
    preserved = loose_edges(doc)
    materials = {
        pair: face_attributes(face) for face in doc["faces"] for pair in edge_usage({"faces": [face]})
    }
    added = []
    for cycle in faces:
        # New surface gets an explicit unit-square UV per quad. Existing UVs
        # are untouched; interpolated UV bridging is a separate pending mode.
        face = {
            "id": _id(doc, "f"),
            "corners": [
                _corner(doc, v, uv) for v, uv in zip(cycle, ([0, 0], [1, 0], [1, 1], [0, 1]))
            ],
            **materials.get(tuple(sorted(cycle[:2])), {"material": 0}),
        }
        doc["faces"].append(face)
        added.append(face["id"])
    _edges(doc, preserved)
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], added


def _coordinates(values):
    if (
        not isinstance(values, (list, tuple, np.ndarray))
        or len(values) != 3
        or any(type(v) not in (int, float) or not np.isfinite(v) for v in values)
    ):
        raise ValueError("Requires three finite coordinates in local meters")
    return np.asarray(values, dtype=float)


def add_vertex(mesh, position):
    """Add an isolated editable vertex without welding to nearby geometry."""
    point = _coordinates(position)
    doc = document(mesh)
    vertex = {"id": _id(doc, "v"), "position": point.tolist(), "part": None}
    doc["vertices"].append(vertex)
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], vertex["id"]


def connect_vertices(mesh, identities):
    """Connect two existing vertices; never split faces or duplicate an edge."""
    doc = document(mesh)
    chosen = set(identities)
    vertices = {v["id"]: v for v in doc["vertices"]}
    if len(chosen) != 2 or chosen - vertices.keys():
        raise ValueError("Select exactly two existing vertices to connect")
    pair = sorted(chosen)
    if any(set(e["vertices"]) == chosen for e in doc["edges"]):
        raise ValueError("Selected vertices are already connected")
    if np.array_equal(vertices[pair[0]]["position"], vertices[pair[1]]["position"]):
        raise ValueError("Cannot connect coincident vertices")
    edge = {"id": _id(doc, "e"), "vertices": pair, "seam": False, "sharp": False}
    doc["edges"].append(edge)
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], edge["id"]


def extrude_vertices(mesh, identities, offset):
    """Duplicate each selected point with a connecting edge; keep all old geometry."""
    delta = _coordinates(offset)
    if not np.any(delta):
        raise ValueError("Vertex extrusion requires a nonzero offset")
    doc = document(mesh)
    chosen = set(identities)
    if not chosen or chosen - {v["id"] for v in doc["vertices"]}:
        raise ValueError("Select existing vertices to extrude")
    new_ids = []
    for vertex in list(doc["vertices"]):
        if vertex["id"] not in chosen:
            continue
        added = deepcopy(vertex)
        added["id"] = _id(doc, "v")
        added["position"] = (np.asarray(vertex["position"]) + delta).tolist()
        doc["vertices"].append(added)
        new_ids.append(added["id"])
        doc["edges"].append(
            {
                "id": _id(doc, "e"),
                "vertices": sorted((vertex["id"], added["id"])),
                "seam": False,
                "sharp": False,
            }
        )
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], new_ids


def extrude_edges(mesh, identities, offset):
    """Sweep boundary/wire chains into quads, with shared new vertices and stable caps."""
    delta = _coordinates(offset)
    if not np.any(delta):
        raise ValueError("Edge extrusion requires a nonzero offset")
    doc = document(mesh)
    chosen = set(identities)
    edges = [e for e in doc["edges"] if e["id"] in chosen]
    if not chosen or chosen - {e["id"] for e in edges}:
        raise ValueError("Select existing edges to extrude")
    uses = edge_usage(doc)
    graph = {}
    by_pair = {}
    for edge in edges:
        a, b = edge["vertices"]
        pair = tuple(sorted((a, b)))
        if len(uses.get(pair, [])) > 1:
            raise ValueError("Extrude boundary or wire edges, not edges shared by two faces")
        by_pair[pair] = edge
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    if any(len(n) > 2 for n in graph.values()):
        raise ValueError("Extrude edge chains or loops without branches")
    remaining = set(by_pair)
    oriented = []
    while remaining:
        active = {v for pair in remaining for v in pair}
        start = next((v for v in graph if v in active and len(graph[v]) == 1), None)
        start = start or next(v for v in graph if v in active)
        current, chain = start, []
        while True:
            following = next(
                (v for v in graph[current] if tuple(sorted((current, v))) in remaining), None
            )
            if following is None:
                break
            remaining.remove(tuple(sorted((current, following))))
            chain.append((current, following))
            current = following
        directions = [
            uses[tuple(sorted((a, b)))][0] == (a, b)
            for a, b in chain
            if uses.get(tuple(sorted((a, b))))
        ]
        if directions and any(d != directions[0] for d in directions):
            raise ValueError("Selected boundary winding is inconsistent")
        # Blender edge-only extrusion puts the base edge in reverse order
        # when a wire has no neighboring face to establish its winding.
        if not directions or directions[0]:
            chain = [(b, a) for a, b in chain]
        oriented.extend(chain)
    source_vertices = {v["id"]: v for v in doc["vertices"]}
    duplicates = {}
    for vertex in list(doc["vertices"]):
        if vertex["id"] in graph:
            added = deepcopy(vertex)
            added["id"] = _id(doc, "v")
            added["position"] = (np.asarray(vertex["position"]) + delta).tolist()
            duplicates[vertex["id"]] = added["id"]
            doc["vertices"].append(added)
    materials = {
        pair: face_attributes(face) for face in doc["faces"] for pair in edge_usage({"faces": [face]})
    }
    preserved = loose_edges(doc)
    cap_ids = []
    height = float(np.linalg.norm(delta))
    for a, b in oriented:
        pair = tuple(sorted((a, b)))
        width = float(
            np.linalg.norm(
                np.asarray(source_vertices[b]["position"]) - source_vertices[a]["position"]
            )
        )
        cycle = [a, b, duplicates[b], duplicates[a]]
        uv = [[0, 0], [width, 0], [width, height], [0, height]]
        doc["faces"].append(
            {
                "id": _id(doc, "f"),
                "corners": [_corner(doc, v, coord) for v, coord in zip(cycle, uv)],
                **materials.get(pair, {"material": 0}),
            }
        )
        cap = deepcopy(by_pair[pair])
        cap["id"] = _id(doc, "e")
        cap["vertices"] = sorted((duplicates[a], duplicates[b]))
        doc["edges"].append(cap)
        cap_ids.append(cap["id"])
    _edges(doc, preserved)
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], cap_ids


def merge_center(mesh, vertex_ids):
    """Weld selected vertices at their mean, preserving surviving source identities.

    Adjacent collapsed corners/edges disappear. Pinched polygons require an
    explicit split first; they are never silently repaired or triangulated away.
    """
    doc = document(mesh)
    chosen = set(vertex_ids)
    vertices = [v for v in doc["vertices"] if v["id"] in chosen]
    if len(chosen) < 2 or len(vertices) != len(chosen):
        raise ValueError("Select at least two existing vertices to merge")
    if len({v["part"] for v in vertices}) != 1:
        raise ValueError("Merge vertices within the same named part")
    survivor = vertices[0]
    target = survivor["id"]
    survivor["position"] = np.mean([v["position"] for v in vertices], axis=0).tolist()
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] not in chosen or v is survivor]
    faces = []
    for face in doc["faces"]:
        affected = any(c["vertex"] in chosen for c in face["corners"])
        corners = []
        for corner in face["corners"]:
            if corner["vertex"] in chosen:
                corner["vertex"] = target
            if affected:
                corner["normal"] = None
            if not corners or corners[-1]["vertex"] != corner["vertex"]:
                corners.append(corner)
        if len(corners) > 1 and corners[-1]["vertex"] == corners[0]["vertex"]:
            corners.pop()
        if len(corners) < 3:
            continue
        if len({c["vertex"] for c in corners}) != len(corners):
            raise ValueError("Merge would pinch a polygon; split it first")
        face["corners"] = corners
        faces.append(face)
    doc["faces"] = faces
    edges = {}
    for edge in doc["edges"]:
        pair = tuple(sorted(target if v in chosen else v for v in edge["vertices"]))
        if pair[0] == pair[1]:
            continue
        if pair in edges:
            edges[pair]["seam"] |= edge["seam"]
            edges[pair]["sharp"] |= edge["sharp"]
        else:
            edge["vertices"] = list(pair)
            edges[pair] = edge
    doc["edges"] = list(edges.values())
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], target


def merge_distance(mesh, vertex_ids, threshold=0.0001, *, centroid=True):
    """Weld selected local-space neighborhoods without mutating the source.

    Neighborhoods are visited in source-vertex order, excluding points already
    assigned to an earlier neighborhood. Distances are inclusive. This is not
    transitive chain welding. See docs/merge-distance.md for the full contract.
    """
    if type(threshold) not in (int, float) or not isfinite(threshold) or not 0 <= threshold <= MAX_FLOAT32:
        raise ValueError("Merge threshold must be finite, nonnegative local meters")
    if type(centroid) is not bool:
        raise ValueError("Centroid must be a boolean")
    doc = document(mesh)
    chosen = set(vertex_ids)
    vertices = [v for v in doc["vertices"] if v["id"] in chosen]
    if not vertices or len(vertices) != len(chosen):
        raise ValueError("Select existing vertices to merge by distance")
    if len({v["part"] for v in vertices}) != 1:
        raise ValueError("Merge vertices within the same named part")
    from scipy.spatial import cKDTree

    positions = np.asarray([v["position"] for v in vertices], dtype=float)
    tree = cKDTree(positions)
    assigned = set()
    targets = {}
    changed = set()
    for i, vertex in enumerate(vertices):
        if i in assigned:
            continue
        neighbors = sorted(j for j in tree.query_ball_point(positions[i], threshold) if j not in assigned)
        assigned.update(neighbors)
        if len(neighbors) < 2:
            continue
        mean = positions[neighbors].mean(axis=0)
        survivor = min(neighbors, key=lambda j: (float(np.sum((positions[j] - mean) ** 2)), j)) if len(neighbors) > 2 else neighbors[0]
        target = vertices[survivor]["id"]
        for j in neighbors:
            targets[vertices[j]["id"]] = target
        if centroid:
            vertices[survivor]["position"] = mean.tolist()
        changed.update(vertices[j]["id"] for j in neighbors)
    selection = list(dict.fromkeys(targets.get(v["id"], v["id"]) for v in vertices))
    if not targets:
        return mesh, selection
    doc["vertices"] = [v for v in doc["vertices"] if targets.get(v["id"], v["id"]) == v["id"]]
    faces, seen_faces = [], set()
    for face in doc["faces"]:
        affected = any(c["vertex"] in changed for c in face["corners"])
        corners = []
        for corner in face["corners"]:
            corner["vertex"] = targets.get(corner["vertex"], corner["vertex"])
            if affected:
                corner["normal"] = None
            if not corners or corners[-1]["vertex"] != corner["vertex"]:
                corners.append(corner)
        if len(corners) > 1 and corners[0]["vertex"] == corners[-1]["vertex"]:
            corners.pop()
        if len(corners) < 3:
            continue
        ids = [c["vertex"] for c in corners]
        if len(set(ids)) != len(ids):
            raise ValueError("Merge would pinch a polygon; split it first")
        # Opposite winding also denotes the same welded face. Keep the first
        # source face and its corner attributes rather than averaging UV seams.
        first = ids.index(min(ids))
        cycle = ids[first:] + ids[:first]
        key = min(tuple(cycle), (cycle[0], *reversed(cycle[1:])))
        if key in seen_faces:
            continue
        seen_faces.add(key)
        face["corners"] = corners
        faces.append(face)
    doc["faces"] = faces
    edges = {}
    for edge in doc["edges"]:
        pair = tuple(sorted(targets.get(v, v) for v in edge["vertices"]))
        if pair[0] == pair[1]:
            continue
        if pair in edges:
            edges[pair]["seam"] |= edge["seam"]
            edges[pair]["sharp"] |= edge["sharp"]
        else:
            edge["vertices"] = list(pair)
            edges[pair] = edge
    doc["edges"] = list(edges.values())
    doc["schema_version"] = max(2, doc["schema_version"])
    return compile(doc)[0], selection


def _influence(doc, vertex_ids, radius):
    if type(radius) not in (int, float) or not 0 <= radius <= MAX_FLOAT32 or not isfinite(radius):
        raise ValueError("Proportional radius must be finite and nonnegative")
    if not vertex_ids or set(vertex_ids) - {v["id"] for v in doc["vertices"]}:
        raise ValueError("Select existing vertices")
    positions = np.array([v["position"] for v in doc["vertices"]], dtype=float)
    mask = np.array([v["id"] in vertex_ids for v in doc["vertices"]])
    if radius > 0:
        from scipy.spatial import cKDTree

        distances, _ = cKDTree(positions[mask]).query(positions, distance_upper_bound=radius)
        weights = np.clip(1 - distances / radius, 0, 1)
        weights = weights**2 * (3 - 2 * weights)
        weights[mask] = 1
    else:
        weights = mask.astype(float)
    return positions, mask, weights


def _publish_positions(doc, positions, weights):
    moved = set()
    for vertex, position, weight in zip(doc["vertices"], positions, weights):
        if weight > 0:
            vertex["position"] = position.tolist()
            moved.add(vertex["id"])
    # Recalculate affected normals, preserving corner UVs and material slots.
    for face in doc["faces"]:
        if any(c["vertex"] in moved for c in face["corners"]):
            for c in face["corners"]:
                c["normal"] = None
    return compile(doc)[0]


def move_vertices(mesh, vertex_ids, offset, *, radius=0.0):
    """Move points with optional smooth Euclidean falloff from selected vertices."""
    delta = _coordinates(offset)
    doc = document(mesh)
    positions, _, weights = _influence(doc, vertex_ids, radius)
    return _publish_positions(doc, positions + weights[:, None] * delta, weights)


def transform_vertices(mesh, vertex_ids, operation, values, *, radius=0.0):
    """Rotate (XYZ local degrees) or scale about the selected vertex mean.

    Proportional rotation weights angles, not endpoint displacements. Scaling
    weights each factor's difference from one. Both use the original distances.
    """
    values = _coordinates(values)
    doc = document(mesh)
    positions, mask, weights = _influence(doc, vertex_ids, radius)
    center = positions[mask].mean(axis=0)
    transformed = positions - center
    if operation == "rotate":
        for axis, degrees in enumerate(values):
            a, b = (axis + 1) % 3, (axis + 2) % 3
            radians = np.radians(degrees * weights)
            cosine, sine = np.cos(radians), np.sin(radians)
            first = transformed[:, a].copy()
            second = transformed[:, b].copy()
            transformed[:, a] = cosine * first - sine * second
            transformed[:, b] = sine * first + cosine * second
    elif operation == "scale":
        transformed *= 1 + weights[:, None] * (values - 1)
    else:
        raise ValueError("Choose component rotate or scale")
    return _publish_positions(doc, transformed + center, weights)


def select(placement, mode, identities, *, additive=False):
    """Shared persisted component selection for GUI and Aether."""
    from . import mesh_document

    if placement.kind != "Mesh3D" or mode not in ("vertices", "edges", "faces"):
        raise ValueError("Component selection requires a mesh and vertex/edge/face mode")
    mesh = mesh_document.resolve(placement.mesh_kind)
    doc = document(mesh)
    valid = {entry["id"] for entry in doc[mode]}
    if set(identities) - valid:
        raise ValueError("Selected components do not exist on this mesh")
    previous = placement.props.get("components3d", {})
    values = set(previous.get("ids", [])) if additive and previous.get("mode") == mode else set()
    values.symmetric_difference_update(identities) if additive else values.update(identities)
    if mesh.topology is None:
        mesh_document.bind(placement, compile(doc)[0], label=placement.name)
    selection = {"mode": mode, "ids": sorted(values)}
    placement.props["components3d"] = selection
    return deepcopy(selection)


def expand_edge_selection(placement, pattern):
    """Expand seeds across quad opposites (ring) or regular four-edge vertices (loop)."""
    from . import mesh_document

    if pattern not in ("loop", "ring") or placement.kind != "Mesh3D":
        raise ValueError("Choose an edge loop or ring on a mesh")
    selection = placement.props.get("components3d", {})
    if selection.get("mode") != "edges" or not selection.get("ids"):
        raise ValueError("Select one or more seed edges first")
    doc = document(mesh_document.resolve(placement.mesh_kind))
    edges = {e["id"]: e for e in doc["edges"]}
    chosen = set(selection["ids"])
    if chosen - edges.keys():
        raise ValueError("Selected edges no longer exist")
    pair_ids = {tuple(sorted(e["vertices"])): e["id"] for e in doc["edges"]}
    edge_faces = {e: set() for e in edges}
    incident = {}
    adjacency = {e: set() for e in edges}
    for edge in edges.values():
        for vertex in edge["vertices"]:
            incident.setdefault(vertex, set()).add(edge["id"])
    for face in doc["faces"]:
        vertices = [c["vertex"] for c in face["corners"]]
        boundary = [
            pair_ids[tuple(sorted((a, b)))] for a, b in zip(vertices, vertices[1:] + vertices[:1])
        ]
        for edge in boundary:
            edge_faces[edge].add(face["id"])
        if pattern == "ring" and len(boundary) == 4:
            for i, edge in enumerate(boundary):
                adjacency[edge].add(boundary[(i + 2) % 4])
    if pattern == "loop":
        quad_faces = {f["id"] for f in doc["faces"] if len(f["corners"]) == 4}
        for around in incident.values():
            if len(around) != 4 or any(
                len(edge_faces[e]) != 2 or not edge_faces[e] <= quad_faces for e in around
            ):
                continue
            for edge in around:
                opposite = [
                    other
                    for other in around
                    if other != edge and not edge_faces[edge] & edge_faces[other]
                ]
                if len(opposite) == 1:
                    adjacency[edge].add(opposite[0])
    else:
        # Ambiguous nonmanifold fans terminate the traversal.
        for edge, neighbors in adjacency.items():
            if len(edge_faces[edge]) > 2:
                neighbors.clear()
            else:
                adjacency[edge] = {e for e in neighbors if len(edge_faces[e]) <= 2}
    pending = list(chosen)
    while pending:
        edge = pending.pop()
        new = adjacency[edge] - chosen
        chosen.update(new)
        pending.extend(new)
    return select(placement, "edges", sorted(chosen))


def edit_selected(
    placement,
    operation,
    *,
    distance=1.0,
    offset=(0.0, 0.0, 0.0),
    position=(0.0, 0.0, 0.0),
    radius=0.0,
    rotation=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
    cuts=1,
    factor=0.0,
    segments=1,
    plane_point=(0.0, 0.0, 0.0),
    plane_normal=(1.0, 0.0, 0.0),
    keep="both",
    fill=False,
    threshold=0.0001,
    centroid=True,
):
    from . import mesh_document

    if placement.kind != "Mesh3D":
        raise ValueError("Component editing requires a mesh")
    selected = placement.props.get("components3d", {})
    mesh = mesh_document.resolve(placement.mesh_kind)
    if operation == "add_vertex":
        result, vertex_id = add_vertex(mesh, position)
        selected = {"mode": "vertices", "ids": [vertex_id]}
    elif operation in ("connect", "extrude_vertices", "merge_center", "merge_distance"):
        if selected.get("mode") != "vertices":
            raise ValueError("Choose vertex selection mode first")
        if operation == "merge_distance":
            result, vertex_ids = merge_distance(mesh, selected.get("ids", []), threshold, centroid=centroid)
            selected = {"mode": "vertices", "ids": vertex_ids}
        elif operation == "merge_center":
            result, vertex_id = merge_center(mesh, selected.get("ids", []))
            selected = {"mode": "vertices", "ids": [vertex_id]}
        elif operation == "connect":
            result, edge_id = connect_vertices(mesh, selected.get("ids", []))
            selected = {"mode": "edges", "ids": [edge_id]}
        else:
            result, vertex_ids = extrude_vertices(mesh, selected.get("ids", []), offset)
            selected = {"mode": "vertices", "ids": vertex_ids}
    elif operation == "extrude_edges":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result, edge_ids = extrude_edges(mesh, selected.get("ids", []), offset)
        selected = {"mode": "edges", "ids": edge_ids}
    elif operation == "bisect":
        if selected.get("mode") != "faces" or set(selected.get("ids", [])) != {
            f["id"] for f in document(mesh)["faces"]
        }:
            raise ValueError("Select all mesh faces for Bisect")
        result, mode, ids = bisect(mesh, plane_point, plane_normal, keep=keep, fill=fill)
        selected = {"mode": mode, "ids": ids}
    elif operation == "bevel_edges":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result, face_ids = bevel_edges(mesh, selected.get("ids", []), distance, segments=segments)
        selected = {"mode": "faces", "ids": face_ids}
    elif operation == "bevel_vertices":
        if selected.get("mode") != "vertices":
            raise ValueError("Choose vertex selection mode first")
        result, face_ids = bevel_vertices(mesh, selected.get("ids", []), distance)
        selected = {"mode": "faces", "ids": face_ids}
    elif operation == "bridge_edges":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result, face_ids = bridge_edges(mesh, selected.get("ids", []))
        selected = {"mode": "faces", "ids": face_ids}
    elif operation == "dissolve_edges":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result, face_ids = dissolve_edges(mesh, selected.get("ids", []))
        selected = {"mode": "faces", "ids": face_ids}
    elif operation == "loop_cut":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result, edge_ids = loop_cut(mesh, selected.get("ids", []), cuts=cuts)
        selected = {"mode": "edges", "ids": edge_ids}
    elif operation == "slide_edges":
        if selected.get("mode") != "edges":
            raise ValueError("Choose edge selection mode first")
        result = slide_edges(mesh, selected.get("ids", []), factor)
    elif operation in ("extrude", "extrude_individual", "inset"):
        if selected.get("mode") != "faces":
            raise ValueError(f"{operation.title()} requires selected faces")
        if operation == "inset":
            result = inset(mesh, selected.get("ids", []), distance)
        else:
            result = extrude(
                mesh,
                selected.get("ids", []),
                distance,
                individual=operation == "extrude_individual",
            )
    elif operation == "delete":
        result = delete_components(mesh, selected.get("mode"), selected.get("ids", []))
        selected = {"mode": selected["mode"], "ids": []}
    elif operation == "fill":
        result, face_id = fill_loop(mesh, selected.get("mode"), selected.get("ids", []))
        selected = {"mode": "faces", "ids": [face_id]}
    elif operation in ("move", "rotate", "scale"):
        doc = document(mesh)
        chosen = selected.get("ids", [])
        mode = selected.get("mode")
        if mode not in ("vertices", "edges", "faces") or set(chosen) - {c["id"] for c in doc[mode]}:
            raise ValueError("Select existing components to move")
        if mode == "vertices":
            ids = chosen
        elif mode == "edges":
            ids = {v for e in doc["edges"] if e["id"] in chosen for v in e["vertices"]}
        elif mode == "faces":
            ids = {c["vertex"] for f in doc["faces"] if f["id"] in chosen for c in f["corners"]}
        else:
            raise ValueError("Select components to move")
        if operation == "move":
            result = move_vertices(mesh, ids, offset, radius=radius)
        else:
            result = transform_vertices(
                mesh, ids, operation, rotation if operation == "rotate" else scale, radius=radius
            )
    else:
        raise ValueError("Unknown topology operation")
    from . import mesh_edit

    mesh_edit.evaluate_mesh(result, placement)
    key = placement.mesh_kind if result is mesh else mesh_document.bind(placement, result, label=placement.name)
    placement.props["components3d"] = deepcopy(selected)
    return {
        "mesh_key": key,
        "vertices": len(result.topology["vertices"]),
        "edges": len(result.topology["edges"]),
        "faces": len(result.topology["faces"]),
        "selection": deepcopy(selected),
    }
