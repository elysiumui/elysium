"""Retained whole-mesh normal policy and source sharp-edge authoring."""

import math
from copy import deepcopy

import numpy as np

from . import mesh_document, mesh_edit, topology


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != {"mode", "angle", "respect_sharp"}:
        raise ValueError("Normal policy requires mode, angle and respect_sharp")
    if value["mode"] not in ("flat", "smooth"):
        raise ValueError("Normal mode must be flat or smooth")
    if (
        type(value["angle"]) not in (int, float)
        or not math.isfinite(value["angle"])
        or not 0 <= value["angle"] <= 180
    ):
        raise ValueError("Smooth angle must be between 0 and 180 degrees")
    if type(value["respect_sharp"]) is not bool:
        raise ValueError("Respect sharp must be boolean")


def corner_normals(doc, weighted=None):
    """Angle-weighted normals in connected smooth fans; no position welding."""
    policy = doc["shading"]
    points = {v["id"]: np.asarray(v["position"], dtype=float) for v in doc["vertices"]}
    faces = doc["faces"]
    normals, weights, parent, edge_faces = [], {}, {}, {}
    for fi, face in enumerate(faces):
        corners = face["corners"]
        normals.append(topology.normal([points[c["vertex"]] for c in corners]))
        for i, c in enumerate(corners):
            cid, vertex = c["id"], c["vertex"]
            parent[cid] = cid
            prev, nxt = corners[i - 1], corners[(i + 1) % len(corners)]
            a, b = points[prev["vertex"]] - points[vertex], points[nxt["vertex"]] - points[vertex]
            cosine = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
            weights[cid] = math.acos(float(np.clip(cosine, -1, 1)))
            pair = tuple(sorted((vertex, nxt["vertex"])))
            edge_faces.setdefault(pair, []).append((fi, vertex, nxt["vertex"], cid, nxt["id"]))
    if policy["mode"] == "flat":
        return {c["id"]: normals[i].tolist() for i, f in enumerate(faces) for c in f["corners"]}

    def find(cid):
        while parent[cid] != cid:
            parent[cid] = parent[parent[cid]]
            cid = parent[cid]
        return cid

    sharp = {tuple(sorted(e["vertices"])) for e in doc["edges"] if e["sharp"]}
    threshold = math.cos(math.radians(policy["angle"]))
    for pair, adjacent in edge_faces.items():
        # Boundaries, nonmanifold joins and inconsistent winding split fans.
        if len(adjacent) != 2 or (policy["respect_sharp"] and pair in sharp):
            continue
        a, b = adjacent
        if a[1:3] != b[1:3][::-1] or np.dot(normals[a[0]], normals[b[0]]) < threshold - 1e-12:
            continue
        for ca, cb in ((a[3], b[4]), (a[4], b[3])):
            parent[find(ca)] = find(cb)
    if weighted is not None:
        return _weighted_corners(faces, points, normals, weights, find, weighted)
    sums = {}
    for fi, face in enumerate(faces):
        for c in face["corners"]:
            root = find(c["id"])
            sums[root] = sums.get(root, np.zeros(3)) + normals[fi] * weights[c["id"]]
    result = {}
    for fi, face in enumerate(faces):
        for c in face["corners"]:
            n = sums[find(c["id"])]
            length = np.linalg.norm(n)
            result[c["id"]] = (n / length if length > 1e-12 else normals[fi]).tolist()
    return result


def _weighted_corners(faces, points, normals, angles, find, settings):
    """Descending value bands and exponential bias, matching Blender's modifier."""
    groups = {}
    for fi, face in enumerate(faces):
        corners = face["corners"]
        coords = np.asarray([points[c["vertex"]] for c in corners])
        area = np.linalg.norm(np.cross(coords, np.roll(coords, -1, axis=0)).sum(axis=0)) / 2
        for c in corners:
            value = area if settings["mode"] == "face_area" else angles[c["id"]]
            if settings["mode"] == "face_angle":
                value *= area
            group = find(c["id"]) if settings["keep_sharp"] else c["vertex"]
            groups.setdefault(group, []).append((value, fi, c["id"]))
    bias = settings["weight"] / 50
    if settings["weight"] == 100:
        bias = 32767.0
    elif settings["weight"] == 1:
        bias = 1 / 32767.0
    elif (bias - 1) * 25 > 1:
        bias = (bias - 1) * 25
    result = {}
    for items in groups.values():
        items.sort(key=lambda item: -item[0])
        band, previous, contributions = 0, 0.0, []
        for value, fi, cid in items:
            if previous == 0:
                previous = value
            if abs(previous - value) > settings["threshold"]:
                band += 1
                previous = value
            # Log scaling avoids overflow for extreme bias and high-valence vertices.
            if value > 0:
                contributions.append((math.log(value) - band * math.log(bias), fi))
        maximum = max((v for v, _ in contributions), default=0.0)
        n = sum((math.exp(v - maximum) * normals[fi] for v, fi in contributions), np.zeros(3))
        length = np.linalg.norm(n)
        for _, fi, cid in items:
            result[cid] = (n / length if length > 1e-12 else normals[fi]).tolist()
    return result


def weighted_mesh(mesh, settings):
    """Bake evaluated custom corners only; retained source policy stays untouched."""
    doc = topology.document(mesh)
    policy = doc.get("shading")
    if policy is None:
        # Authored meshes have no explicit face-smoothing flags. Preserve a wholly
        # flat authored mesh; otherwise use source edge connectivity and sharp flags.
        points = {v["id"]: v["position"] for v in doc["vertices"]}
        flat = all(
            c["normal"] is None
            or np.allclose(
                c["normal"],
                topology.normal([points[k["vertex"]] for k in f["corners"]]),
                atol=1e-6,
                rtol=0,
            )
            for f in doc["faces"]
            for c in f["corners"]
        )
        policy = {"mode": "flat" if flat else "smooth", "angle": 180.0, "respect_sharp": True}
    if policy["mode"] == "flat":
        return mesh
    doc["shading"] = policy
    normals = corner_normals(doc, weighted=settings)
    doc.pop("shading", None)
    for face in doc["faces"]:
        for corner in face["corners"]:
            corner["normal"] = normals[corner["id"]]
    return topology.compile(doc)[0]


def _source(placement):
    if placement.kind != "Mesh3D":
        raise ValueError("Normal authoring requires a mesh")
    return topology.document(mesh_document.resolve(placement.mesh_kind))


def read(placement):
    doc = _source(placement)
    mesh, ids, face_ids = topology.compile(doc)
    return {
        "policy": deepcopy(
            doc.get("shading", {"mode": "authored", "angle": 180.0, "respect_sharp": True})
        ),
        "sharp_edge_ids": [e["id"] for e in doc["edges"] if e["sharp"]],
        "render_vertex_ids": ids,
        "triangles": mesh.faces.tolist(),
        "triangle_face_ids": face_ids,
        "normals": None if mesh.vert_normals is None else mesh.vert_normals.tolist(),
    }


def _publish(placement, doc):
    result = topology.compile(doc)[0]
    mesh_edit.evaluate_mesh(result, placement)
    mesh_document.bind(placement, result, label=getattr(placement, "name", "Mesh"))
    return read(placement)


def set_policy(placement, mode, *, angle=180.0, respect_sharp=True):
    policy = {"mode": mode, "angle": angle, "respect_sharp": respect_sharp}
    validate_settings({**policy, "mode": "smooth" if mode == "authored" else mode})
    doc = _source(placement)
    if mode == "authored":
        doc.pop("shading", None)
    else:
        doc["schema_version"] = max(4, doc["schema_version"])
        doc["shading"] = policy
    return _publish(placement, doc)


def set_sharp(placement, edge_ids, sharp=True):
    if type(sharp) is not bool:
        raise ValueError("Sharp edge value must be boolean")
    doc = _source(placement)
    if (
        not isinstance(edge_ids, list)
        or not edge_ids
        or any(not isinstance(i, str) for i in edge_ids)
        or len(set(edge_ids)) != len(edge_ids)
    ):
        raise ValueError("Select distinct source edge identities")
    selected = [e for e in doc["edges"] if e["id"] in edge_ids]
    if len(selected) != len(edge_ids):
        raise ValueError("Selected edge no longer exists")
    for edge in selected:
        edge["sharp"] = sharp
    return _publish(placement, doc)
