"""Fixed-reference or midpoint joining across neighboring corner-UV island edges."""

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


def stitch(
    placement,
    corner_ids=None,
    *,
    static_corner_id=None,
    clear_seams=True,
    midpoints=False,
    respect_seams=True,
):
    """Join shared source edges between exactly two selected UV islands.

    Selected corner seeds expand to exactly two complete islands. All their
    shared source edges join; clear_seams controls their seam flags. By default
    mesh seams split Stitch islands. Without midpoints, one island stays fixed
    and the other moves rigidly. Midpoints averages shared endpoints and moves
    both islands' remaining corners halfway, which can deform joined UV faces.
    Incompatible edge lengths/shapes and moving pins reject atomically.
    """
    if not isinstance(clear_seams, bool):
        raise ValueError("Clear seams must be true or false")  # noqa: TRY004 - shared UI validation contract
    if not isinstance(midpoints, bool):
        raise ValueError("Midpoints must be true or false")  # noqa: TRY004 - shared UI validation contract
    if not isinstance(respect_seams, bool):
        raise ValueError("Respect seams must be true or false")  # noqa: TRY004 - shared UI validation contract
    doc = mesh_uv.source(placement)
    islands = mesh_uv_islands.selected(doc, corner_ids, respect_seams=respect_seams)
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
    if midpoints:
        angle = np.arctan2(rotation[0, 1], rotation[0, 0]) / 2
        cosine, sine = np.cos(angle), np.sin(angle)
        half = np.array([[cosine, sine], [-sine, cosine]])
        center = (center_source + center_target) / 2
        # Blender snaps stitched endpoints to their arithmetic midpoint. Other
        # corners rotate halfway and translate; a rotated join can change UV shape.
        joined = (source + target) / 2
        new_anchors = {vertex: tuple(value.tolist()) for vertex, value in zip(anchors, joined)}
        fixed_corners = [c for f in fixed for c in f["corners"]]
        fixed_values = (
            np.array([c["uv"] for c in fixed_corners]) - center_target
        ) @ half.T + center
        for c, value in zip(fixed_corners, fixed_values):
            pair = anchors.get(c["vertex"])
            if pair and tuple(c["uv"]) == pair[1]:
                value = np.asarray(new_anchors[c["vertex"]])
            if c.get("pin", False) and not np.array_equal(c["uv"], value):
                raise ValueError(
                    "Midpoint stitch would move a pinned corner in the reference island"
                )
            c["uv"] = value.tolist()
        anchors = {v: (pair[0], new_anchors[v]) for v, pair in anchors.items()}
        rotation, center_target = half, center
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
        "fixed_face_ids": [] if midpoints else [f["id"] for f in fixed],
        "moved_face_ids": [f["id"] for f in (fixed + moving if midpoints else moving)],
        "corner_ids": [c["id"] for island in islands for f in island for c in f["corners"]],
    }
