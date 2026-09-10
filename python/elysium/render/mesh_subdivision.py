"""Discrete Catmull-Clark and Simple subdivision of retained polygon surfaces."""

from copy import deepcopy

import numpy as np

from . import topology


def _average(corners, field):
    values = [c.get(field) for c in corners]
    if any(v is None for v in values):
        return None
    result = np.mean(values, axis=0)
    if field == "normal":
        length = np.linalg.norm(result)
        if length <= 1e-12:
            return None
        result /= length
    return result.tolist()


def step(mesh, method, boundary):
    source = topology.document(mesh)
    vertices, edges, faces = (source[k] for k in ("vertices", "edges", "faces"))
    corners = sum(len(f["corners"]) for f in faces)
    if len(vertices) + 3 * len(edges) + len(faces) + 5 * corners > 1_000_000:
        raise ValueError("Subdivision exceeds the evaluated component limit")
    usage = topology.edge_usage(source)
    if not faces or any(len(u) > 2 or (len(u) == 2 and u[0] != u[1][::-1]) for u in usage.values()):
        raise ValueError("Subdivision requires a consistently oriented manifold surface")
    points = {v["id"]: np.asarray(v["position"], dtype=float) for v in vertices}
    parts = {v["id"]: v.get("part") for v in vertices}
    edge_faces = {pair: [] for pair in usage}
    vertex_faces = {identity: [] for identity in points}
    vertex_edges = {identity: [] for identity in points}
    face_points = {}
    for face in faces:
        ids = [c["vertex"] for c in face["corners"]]
        if len({parts[v] for v in ids}) != 1:
            raise ValueError("Subdivision faces must belong to one named part")
        face_points[face["id"]] = np.mean([points[v] for v in ids], axis=0)
        for a, b in zip(ids, ids[1:] + ids[:1]):
            edge_faces[tuple(sorted((a, b)))].append(face["id"])
            vertex_faces[a].append(face["id"])
    for edge in edges:
        pair = tuple(sorted(edge["vertices"]))
        if pair not in usage:
            raise ValueError("Subdivision does not support loose edges")
        for identity in pair:
            vertex_edges[identity].append(pair)
    moved = {}
    for identity, point in points.items():
        incident = vertex_faces[identity]
        pairs = vertex_edges[identity]
        if not incident:
            raise ValueError("Subdivision does not support isolated vertices")
        connected, pending = {incident[0]}, [incident[0]]
        links = {f: set() for f in incident}
        for pair in pairs:
            for f in edge_faces[pair]:
                links[f].update(edge_faces[pair])
        while pending:
            for neighbor in links[pending.pop()] - connected:
                connected.add(neighbor)
                pending.append(neighbor)
        if len(connected) != len(incident):
            raise ValueError("Subdivision requires one connected surface fan per vertex")
        boundary_neighbors = [
            next(v for v in pair if v != identity) for pair in pairs if len(usage[pair]) == 1
        ]
        if len(boundary_neighbors) not in (0, 2):
            raise ValueError("Subdivision requires manifold boundary loops")
        if method == "simple" or (boundary == "keep_corners" and len(incident) == 1):
            moved[identity] = point
        elif boundary_neighbors:
            moved[identity] = point * 0.75 + sum(points[v] for v in boundary_neighbors) * 0.125
        else:
            n = len(pairs)
            f = np.mean([face_points[identity] for identity in incident], axis=0)
            r = np.mean([(points[a] + points[b]) / 2 for a, b in pairs], axis=0)
            moved[identity] = (f + 2 * r + (n - 3) * point) / n
    doc = deepcopy(source)
    for vertex in doc["vertices"]:
        vertex["position"] = moved[vertex["id"]].tolist()
    edge_ids, face_ids = {}, {}
    for edge in edges:
        pair = tuple(sorted(edge["vertices"]))
        p = (points[pair[0]] + points[pair[1]]) / 2
        if method == "catmull-clark" and len(edge_faces[pair]) == 2:
            p = (p * 2 + sum(face_points[f] for f in edge_faces[pair])) / 4
        identity = topology._id(doc, "v")
        edge_ids[pair] = identity
        doc["vertices"].append({"id": identity, "position": p.tolist(), "part": parts[pair[0]]})
    for face in faces:
        identity = topology._id(doc, "v")
        face_ids[face["id"]] = identity
        doc["vertices"].append(
            {
                "id": identity,
                "position": face_points[face["id"]].tolist(),
                "part": parts[face["corners"][0]["vertex"]],
            }
        )
    doc["edges"] = []
    for edge in edges:
        middle = edge_ids[tuple(sorted(edge["vertices"]))]
        for index, vertex in enumerate(edge["vertices"]):
            added = deepcopy(edge)
            added["id"] = edge["id"] if index == 0 else topology._id(doc, "e")
            added["vertices"] = sorted((vertex, middle))
            doc["edges"].append(added)
    doc["faces"] = []
    for face in faces:
        original = face["corners"]
        center = face_ids[face["id"]]
        for i, corner in enumerate(original):
            before, after = original[i - 1], original[(i + 1) % len(original)]
            next_edge = edge_ids[tuple(sorted((corner["vertex"], after["vertex"])))]
            previous_edge = edge_ids[tuple(sorted((before["vertex"], corner["vertex"])))]
            new_corners = [deepcopy(corner)]
            for identity, interpolation in (
                (next_edge, [corner, after]),
                (center, original),
                (previous_edge, [before, corner]),
            ):
                new_corners.append(
                    topology._corner(
                        doc,
                        identity,
                        _average(interpolation, "uv"),
                        _average(interpolation, "normal"),
                    )
                )
            doc["faces"].append(
                {
                    "id": face["id"] if i == 0 else topology._id(doc, "f"),
                    "material": face["material"],
                    "corners": new_corners,
                }
            )
    topology._edges(doc)
    doc["schema_version"] = max(2, doc["schema_version"])
    return topology.compile(doc)[0]


def evaluate(mesh, values):
    source = topology.document(mesh)
    vertices, edges, faces = (len(source[k]) for k in ("vertices", "edges", "faces"))
    corners = sum(len(face["corners"]) for face in source["faces"])
    for _ in range(values["levels"]):
        vertices, edges, faces, corners = (
            vertices + edges + faces,
            2 * edges + corners,
            corners,
            4 * corners,
        )
        if vertices + edges + corners > 1_000_000:
            raise ValueError("Subdivision exceeds the evaluated component limit")
    for _ in range(values["levels"]):
        mesh = step(mesh, values["method"], values["boundary"])
    return mesh
