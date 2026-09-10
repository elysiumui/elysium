"""Retained Edge Split evaluation using source face fans, without position welding."""

import math
from copy import deepcopy

import numpy as np

from . import topology


def evaluate(mesh, settings):
    if not settings["use_angle"] and not settings["use_sharp"]:
        return mesh
    doc = topology.document(mesh)
    corners = sum(len(f["corners"]) for f in doc["faces"])
    if len(doc["vertices"]) + len(doc["edges"]) + 4 * corners > 1_000_000:
        raise ValueError("Edge Split exceeds the evaluated component limit")
    points = {v["id"]: np.asarray(v["position"]) for v in doc["vertices"]}
    vertex_records = {v["id"]: v for v in doc["vertices"]}
    source_edges = {tuple(sorted(e["vertices"])): deepcopy(e) for e in doc["edges"]}
    normals, adjacency, parent = [], {}, {}
    for fi, face in enumerate(doc["faces"]):
        cs = face["corners"]
        normals.append(topology.normal([points[c["vertex"]] for c in cs]))
        for i, c in enumerate(cs):
            nxt = cs[(i + 1) % len(cs)]
            parent[c["id"]] = c["id"]
            pair = tuple(sorted((c["vertex"], nxt["vertex"])))
            adjacency.setdefault(pair, []).append(
                (fi, {c["vertex"]: c["id"], nxt["vertex"]: nxt["id"]})
            )
    use_angle = settings["use_angle"] and settings["angle"] < 180
    # Blender gives comparisons a small angular slack at the specified boundary.
    threshold = math.cos(math.radians(settings["angle"]) + 0.000000175)
    split = set()
    for pair, uses in adjacency.items():
        if settings["use_sharp"] and source_edges[pair]["sharp"]:
            split.add(pair)
        if (
            use_angle
            and len(uses) > 1
            and (
                len(uses) > 2
                or math.radians(settings["angle"]) < np.finfo(np.float32).eps
                or np.dot(normals[uses[0][0]], normals[uses[1][0]]) < threshold
            )
        ):
            split.add(pair)
    if not split:
        return mesh

    def find(cid):
        while parent[cid] != cid:
            parent[cid] = parent[parent[cid]]
            cid = parent[cid]
        return cid

    for pair, uses in adjacency.items():
        if pair in split:
            continue
        for _, other in uses[1:]:
            for vertex in pair:
                parent[find(other[vertex])] = find(uses[0][1][vertex])
    affected = {v for pair in split for v in pair}
    assigned, origin = {}, {v: v for v in points}
    for face in doc["faces"]:
        for corner in face["corners"]:
            vertex = corner["vertex"]
            if vertex not in affected:
                continue
            fans = assigned.setdefault(vertex, {})
            root = find(corner["id"])
            if root not in fans:
                if not fans:
                    fans[root] = vertex
                else:
                    added = deepcopy(vertex_records[vertex])
                    added["id"] = topology._id(doc, "v")
                    doc["vertices"].append(added)
                    origin[added["id"]] = vertex
                    fans[root] = added["id"]
            corner["vertex"] = fans[root]
    loose = [e for pair, e in source_edges.items() if pair not in adjacency]
    topology._edges(doc, loose)
    for edge in doc["edges"]:
        old = source_edges[tuple(sorted(origin[v] for v in edge["vertices"]))]
        for key, value in old.items():
            if key not in ("id", "vertices"):
                edge[key] = deepcopy(value)
    doc["schema_version"] = max(2, doc["schema_version"])
    return topology.compile(doc)[0]
