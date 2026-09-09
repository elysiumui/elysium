"""Editable polygon/corner topology compiled to the existing triangle renderer.

Vertex, edge, polygon and corner IDs survive edits. Rendering triangulation is
an evaluated product, never the authoring identity. Operations return validated
copies so callers can publish one undoable mesh revision atomically.
"""

from copy import deepcopy

import numpy as np


def _id(doc, prefix):
    value = f"{prefix}{doc['next_id']}"
    doc["next_id"] += 1
    return value


def _corner(doc, vertex, uv=None, normal=None):
    return {"id": _id(doc, "c"), "vertex": vertex, "uv": deepcopy(uv), "normal": deepcopy(normal)}


def _edges(doc):
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
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError("Unsupported editable topology version")
    if type(doc.get("next_id")) is not int or doc["next_id"] < 1:
        raise ValueError("Invalid topology identity counter")
    seen = set()

    def identity(item):
        ident = item.get("id")
        if (
            not isinstance(ident, str)
            or len(ident) < 2
            or not ident[1:].isdigit()
            or ident in seen
            or int(ident[1:]) >= doc["next_id"]
        ):
            raise ValueError("Invalid or duplicate topology identity")
        seen.add(ident)

    verts = {}
    for vertex in doc["vertices"]:
        identity(vertex)
        values = vertex["position"]
        if len(values) != 3 or any(
            type(v) not in (int, float) or not np.isfinite(v) for v in values
        ):
            raise ValueError("Vertex position must have three finite coordinates")
        verts[vertex["id"]] = values
    needed = set()
    for face in doc["faces"]:
        identity(face)
        if type(face["material"]) is not int or face["material"] < 0:
            raise ValueError("Invalid polygon material slot")
        ids = []
        for corner in face["corners"]:
            identity(corner)
            if corner["vertex"] not in verts:
                raise ValueError("Corner references a missing vertex")
            ids.append(corner["vertex"])
            for field, size in (("uv", 2), ("normal", 3)):
                value = corner.get(field)
                if value is not None and (len(value) != size or not np.isfinite(value).all()):
                    raise ValueError(f"Invalid corner {field}")
        if len(ids) < 3 or len(ids) != len(set(ids)):
            raise ValueError("Polygon requires at least three distinct vertices")
        triangles([verts[i] for i in ids])
        needed.update(tuple(sorted((a, b))) for a, b in zip(ids, ids[1:] + ids[:1]))
    actual = set()
    for edge in doc["edges"]:
        identity(edge)
        if len(edge["vertices"]) != 2:
            raise ValueError("Edge requires two vertices")
        pair = tuple(sorted(edge["vertices"]))
        if pair in actual or pair not in needed:
            raise ValueError("Invalid or duplicate polygon edge")
        actual.add(pair)
    if actual != needed:
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


def _selected(doc, face_ids):
    if not face_ids or len(set(face_ids)) != len(face_ids):
        raise ValueError("Select one or more distinct polygon faces")
    found = [f for f in doc["faces"] if f["id"] in face_ids]
    if len(found) != len(face_ids):
        raise ValueError("Selected polygon no longer exists")
    return found


def extrude(mesh, face_ids, distance):
    if type(distance) not in (float, int) or not np.isfinite(distance) or abs(distance) <= 1e-12:
        raise ValueError("Extrusion distance must be finite and nonzero")
    doc = document(mesh)
    selected = _selected(doc, face_ids)
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
            usage.setdefault(pair, []).append((a, b, face["material"]))
    if any(len(v) > 2 for v in usage.values()):
        raise ValueError("Cannot extrude a non-manifold face region")
    boundary = [v[0] for v in usage.values() if len(v) == 1]
    if not boundary:
        raise ValueError("Select an open face region with a boundary")
    moved = {}
    for old in {c["vertex"] for f in selected for c in f["corners"]}:
        v = deepcopy(verts[old])
        v["id"] = _id(doc, "v")
        v["position"] = (np.array(v["position"]) + offset).tolist()
        moved[old] = v["id"]
        doc["vertices"].append(v)
    sides = []
    for a, b, material in boundary:
        va, vb = a["vertex"], b["vertex"]
        corners = [_corner(doc, v) for v in (va, vb, moved[vb], moved[va])]
        sides.append({"id": _id(doc, "f"), "corners": corners, "material": material})
    for face in selected:
        for c in face["corners"]:
            c["vertex"] = moved[c["vertex"]]
    doc["faces"].extend(sides)
    used = {c["vertex"] for f in doc["faces"] for c in f["corners"]}
    doc["vertices"] = [v for v in doc["vertices"] if v["id"] in used or v["id"] not in moved]
    _edges(doc)
    return compile(doc)[0]


def inset(mesh, face_ids, thickness):
    """Inset individual planar convex faces by an even local-space distance.

    Inner polygons retain face/corner identities and interpolate their original
    corner UVs. Adjacent selected faces are inset individually. Unsupported
    concavity, nonplanarity and collapsing offsets fail before publication.
    """
    if type(thickness) not in (int, float) or not np.isfinite(thickness) or thickness <= 0:
        raise ValueError("Inset thickness must be finite and positive")
    doc = document(mesh)
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
                    "material": face["material"],
                    "corners": [_corner(doc, c["vertex"], c.get("uv")) for c in corners],
                }
            )
    doc["faces"].extend(borders)
    _edges(doc)
    return compile(doc)[0]


def move_vertices(mesh, vertex_ids, offset):
    if len(offset) != 3 or any(type(v) not in (int, float) or not np.isfinite(v) for v in offset):
        raise ValueError("Move requires three finite coordinates")
    doc = document(mesh)
    if not vertex_ids or set(vertex_ids) - {v["id"] for v in doc["vertices"]}:
        raise ValueError("Select existing vertices")
    for vertex in doc["vertices"]:
        if vertex["id"] in vertex_ids:
            vertex["position"] = (np.asarray(vertex["position"]) + offset).tolist()
    # Recalculate edited corner normals, preserving corner UVs and material slots.
    for face in doc["faces"]:
        if any(c["vertex"] in vertex_ids for c in face["corners"]):
            for c in face["corners"]:
                c["normal"] = None
    return compile(doc)[0]


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


def edit_selected(placement, operation, *, distance=1.0, offset=(0.0, 0.0, 0.0)):
    from . import mesh_document

    if placement.kind != "Mesh3D":
        raise ValueError("Component editing requires a mesh")
    selected = placement.props.get("components3d", {})
    mesh = mesh_document.resolve(placement.mesh_kind)
    if operation in ("extrude", "inset"):
        if selected.get("mode") != "faces":
            raise ValueError(f"{operation.title()} requires selected faces")
        result = (extrude if operation == "extrude" else inset)(
            mesh, selected.get("ids", []), distance
        )
    elif operation == "move":
        doc = document(mesh)
        chosen = selected.get("ids", [])
        mode = selected.get("mode")
        if mode == "vertices":
            ids = chosen
        elif mode == "edges":
            ids = {v for e in doc["edges"] if e["id"] in chosen for v in e["vertices"]}
        elif mode == "faces":
            ids = {c["vertex"] for f in doc["faces"] if f["id"] in chosen for c in f["corners"]}
        else:
            raise ValueError("Select components to move")
        result = move_vertices(mesh, ids, offset)
    else:
        raise ValueError("Unknown topology operation")
    key = mesh_document.bind(placement, result, label=placement.name)
    return {
        "mesh_key": key,
        "vertices": len(result.topology["vertices"]),
        "edges": len(result.topology["edges"]),
        "faces": len(result.topology["faces"]),
        "selection": deepcopy(selected),
    }
