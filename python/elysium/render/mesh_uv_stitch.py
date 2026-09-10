"""Rigid joining of two neighboring corner-UV islands across shared source edges."""

from collections import defaultdict

import numpy as np

from . import mesh_uv, mesh_uv_islands, topology


def _edges(island):
    result = defaultdict(list)
    for face in island:
        cs = face["corners"]
        for a, b in zip(cs, cs[1:] + cs[:1]):
            result[tuple(sorted((a["vertex"], b["vertex"])))].append((a, b))
    return result


def _validate_join(fixed, moving):
    def triangles(island):
        result = []
        for face in island:
            uv = np.array([c["uv"] for c in face["corners"]])
            result.extend(
                uv[list(t)] for t in topology.triangles(np.column_stack((uv, np.zeros(len(uv)))))
            )
        return np.array(result)

    first, second = triangles(fixed), triangles(moving)
    if len(first) + len(second) > 10000:
        raise ValueError("Stitch currently supports at most 10,000 triangles across two islands")
    low, high = first.min(axis=1), first.max(axis=1)
    extent = max(float(np.ptp(np.concatenate((first, second)).reshape(-1, 2), axis=0).max()), 1e-12)
    epsilon = extent * 1e-10
    for triangle in second:
        candidates = np.flatnonzero(
            np.all(high > triangle.min(axis=0) + epsilon, axis=1)
            & np.all(low < triangle.max(axis=0) - epsilon, axis=1)
        )
        for index in candidates:
            other = first[index]
            edges = np.concatenate(
                (np.roll(triangle, -1, axis=0) - triangle, np.roll(other, -1, axis=0) - other)
            )
            separated = False
            for edge in edges:
                axis = np.array([-edge[1], edge[0]])
                a, b = triangle @ axis, other @ axis
                overlap = min(a.max(), b.max()) - max(a.min(), b.min())
                if overlap <= epsilon * np.linalg.norm(axis):
                    separated = True
                    break
            if not separated:
                raise ValueError(
                    "Stitch would overlap the islands; adjust their UV orientation or shape first"
                )


def stitch(placement, corner_ids=None, *, static_corner_id=None, clear_seams=True):
    """Keep one island fixed; rigidly join its shared edges with one other island.

    Selected corner seeds expand to exactly two complete islands. All their
    shared source edges join; clear_seams controls their seam flags. No scaling/stretching
    is allowed. Pins that would move reject the complete operation.
    """
    if not isinstance(clear_seams, bool):
        raise ValueError("Clear seams must be true or false")
    doc = mesh_uv.source(placement)
    islands = mesh_uv_islands.selected(doc, corner_ids)
    if len(islands) != 2:
        raise ValueError("Select UV corners in exactly two neighboring islands to stitch")
    islands.sort(key=lambda island: min(int(f["id"][1:]) for f in island))
    if static_corner_id is not None:
        if not isinstance(static_corner_id, str):
            raise ValueError("The fixed island needs a current UV corner identity")
        owners = [
            i
            for i, island in enumerate(islands)
            if any(c["id"] == static_corner_id for f in island for c in f["corners"])
        ]
        if not owners:
            raise ValueError("The fixed UV corner must belong to one of the selected islands")
        if owners[0] == 1:
            islands.reverse()
    fixed, moving = islands
    fixed_edges, moving_edges = _edges(fixed), _edges(moving)
    shared = set(fixed_edges) & set(moving_edges)
    if not shared:
        raise ValueError("Selected UV islands do not share a source mesh edge")
    anchors = {}
    for edge in sorted(shared):
        if len(fixed_edges[edge]) != 1 or len(moving_edges[edge]) != 1:
            raise ValueError("Stitch requires manifold boundary edges between the islands")
        first = {c["vertex"]: c for c in fixed_edges[edge][0]}
        second = {c["vertex"]: c for c in moving_edges[edge][0]}
        for vertex in edge:
            pair = (tuple(second[vertex]["uv"]), tuple(first[vertex]["uv"]))
            if vertex in anchors and anchors[vertex] != pair:
                raise ValueError("Shared stitch vertices have ambiguous UVs within an island")
            anchors[vertex] = pair
    source = np.array([pair[0] for pair in anchors.values()])
    target = np.array([pair[1] for pair in anchors.values()])
    center_source, center_target = source.mean(axis=0), target.mean(axis=0)
    a, b = source - center_source, target - center_target
    extent = max(float(np.ptp(source, axis=0).max()), float(np.ptp(target, axis=0).max()))
    if extent <= 1e-12:
        raise ValueError("Stitch requires a shared edge with nonzero UV length")
    u, _, vt = np.linalg.svd(a.T @ b)
    correction = np.eye(2)
    correction[1, 1] = 1 if np.linalg.det(u @ vt) > 0 else -1
    rotation = u @ correction @ vt
    residual = float(np.max(np.linalg.norm(a @ rotation - b, axis=1)))
    if residual > max(extent * 1e-8, 1e-10):
        raise ValueError(
            "Stitch would stretch the islands; match their scale and shared edge shape first"
        )
    moving_corners = [c for f in moving for c in f["corners"]]
    uv = np.array([c["uv"] for c in moving_corners])
    result = (uv - center_source) @ rotation + center_target
    for c, value in zip(moving_corners, result):
        if c.get("pin", False):
            pair = anchors.get(c["vertex"])
            if (pair and pair[0] != pair[1]) or not np.allclose(c["uv"], value, atol=1e-10, rtol=0):
                raise ValueError(
                    "Stitch would move a pinned corner; keep its island fixed or unpin it"
                )
    for c, value in zip(moving_corners, result):
        if c.get("pin", False):
            continue
        pair = anchors.get(c["vertex"])
        # Shared endpoint assignments are exact so subsequent island detection
        # joins the charts instead of retaining a floating-point UV crack.
        c["uv"] = list(pair[1]) if pair and tuple(c["uv"]) == pair[0] else value.tolist()
    _validate_join(fixed, moving)
    for edge in doc["edges"]:
        if clear_seams and tuple(sorted(edge["vertices"])) in shared:
            edge["seam"] = False
    return {
        **mesh_uv._publish(placement, doc),
        "joined_edges": len(shared),
        "fixed_face_ids": [f["id"] for f in fixed],
        "moved_face_ids": [f["id"] for f in moving],
        "corner_ids": [c["id"] for island in islands for f in island for c in f["corners"]],
    }
