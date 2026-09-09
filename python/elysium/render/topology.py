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
    if not isinstance(doc, dict) or doc.get("schema_version") not in (1, 2):
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
            usage.setdefault(pair, []).append((a, b, face["material"]))
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
    for a, b, material in boundary:
        va, vb = a["vertex"], b["vertex"]
        corners = [
            _corner(doc, v, c.get("uv"))
            for v, c in zip((va, vb, moved[vb], moved[va]), (a, b, b, a))
        ]
        sides.append({"id": _id(doc, "f"), "corners": corners, "material": material})
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
                    "material": face["material"],
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
    doc["schema_version"] = 2
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
    doc["schema_version"] = 2
    return compile(doc)[0], face["id"]


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
    doc["schema_version"] = 2
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
    doc["schema_version"] = 2
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
    doc["schema_version"] = 2
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
        pair: face["material"] for face in doc["faces"] for pair in edge_usage({"faces": [face]})
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
                "material": materials.get(pair, 0),
            }
        )
        cap = deepcopy(by_pair[pair])
        cap["id"] = _id(doc, "e")
        cap["vertices"] = sorted((duplicates[a], duplicates[b]))
        doc["edges"].append(cap)
        cap_ids.append(cap["id"])
    _edges(doc, preserved)
    doc["schema_version"] = 2
    return compile(doc)[0], cap_ids


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


def edit_selected(
    placement, operation, *, distance=1.0, offset=(0.0, 0.0, 0.0), position=(0.0, 0.0, 0.0)
):
    from . import mesh_document

    if placement.kind != "Mesh3D":
        raise ValueError("Component editing requires a mesh")
    selected = placement.props.get("components3d", {})
    mesh = mesh_document.resolve(placement.mesh_kind)
    if operation == "add_vertex":
        result, vertex_id = add_vertex(mesh, position)
        selected = {"mode": "vertices", "ids": [vertex_id]}
    elif operation in ("connect", "extrude_vertices"):
        if selected.get("mode") != "vertices":
            raise ValueError("Choose vertex selection mode first")
        if operation == "connect":
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
    elif operation == "move":
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
        result = move_vertices(mesh, ids, offset)
    else:
        raise ValueError("Unknown topology operation")
    key = mesh_document.bind(placement, result, label=placement.name)
    placement.props["components3d"] = deepcopy(selected)
    return {
        "mesh_key": key,
        "vertices": len(result.topology["vertices"]),
        "edges": len(result.topology["edges"]),
        "faces": len(result.topology["faces"]),
        "selection": deepcopy(selected),
    }
