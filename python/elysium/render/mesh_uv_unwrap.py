"""Seam-cut least-squares conformal UV charts with persistent corner pins."""

from collections import defaultdict

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsqr
from scipy.spatial import ConvexHull

from . import mesh_uv, mesh_uv_islands, topology


def _charts(doc, face_ids):
    faces = mesh_uv._selected(doc["faces"], face_ids, "face")
    if not faces:
        raise ValueError("Unwrap needs selected surface faces")
    corners = {c["id"]: c for f in faces for c in f["corners"]}
    if len(corners) > 50000:
        raise ValueError("Unwrap currently supports at most 50,000 selected face corners")
    parents = {key: key for key in corners}
    face_parents = {f["id"]: f["id"] for f in faces}

    def find(table, key):
        while table[key] != key:
            table[key] = table[table[key]]
            key = table[key]
        return key

    def union(table, a, b):
        a, b = find(table, a), find(table, b)
        table[max(a, b)] = min(a, b)

    seams = {tuple(sorted(e["vertices"])) for e in doc["edges"] if e["seam"]}
    edges = defaultdict(list)
    for face in faces:
        cs = face["corners"]
        for a, b in zip(cs, cs[1:] + cs[:1]):
            edges[tuple(sorted((a["vertex"], b["vertex"])))].append((face["id"], a, b))
    for pair, uses in edges.items():
        if len(uses) > 2:
            raise ValueError("Unwrap requires edge-manifold surfaces")
        if len(uses) == 2:
            (first, a, b), (second, c, d) = uses
            if a["vertex"] != d["vertex"] or b["vertex"] != c["vertex"]:
                raise ValueError("Unwrap requires consistently oriented neighboring faces")
            if pair not in seams:
                union(parents, a["id"], d["id"])
                union(parents, b["id"], c["id"])
                union(face_parents, first, second)
    grouped = defaultdict(list)
    for face in faces:
        grouped[find(face_parents, face["id"])].append(face)
    return list(grouped.values()), {key: find(parents, key) for key in corners}


def _solve(faces, roots, points):
    corners = [c for f in faces for c in f["corners"]]
    identities = list(dict.fromkeys(roots[c["id"]] for c in corners))
    index = {key: i for i, key in enumerate(identities)}
    node_for = {c["id"]: index[roots[c["id"]]] for c in corners}
    positions = np.empty((len(identities), 3))
    for c in corners:
        positions[node_for[c["id"]]] = points[c["vertex"]]
    uses = defaultdict(list)
    for f in faces:
        cs = f["corners"]
        for a, b in zip(cs, cs[1:] + cs[:1]):
            a, b = node_for[a["id"]], node_for[b["id"]]
            uses[tuple(sorted((a, b)))].append((a, b))
    boundary = [use[0] for use in uses.values() if len(use) == 1]
    if not boundary or len(identities) - len(uses) + len(faces) != 1:
        raise ValueError(
            "Mark seams to open each unwrap chart into a disk (one boundary, no holes)"
        )
    if len(boundary) > 2048:
        raise ValueError("Unwrap chart boundary currently supports at most 2,048 edges")
    following = {a: b for a, b in boundary}
    if len(following) != len(boundary) or len({b for a, b in boundary}) != len(boundary):
        raise ValueError("Unwrap chart boundary must be one simple loop")
    start = min(following)
    cycle = [start]
    node = following[start]
    while node != start and node not in cycle:
        cycle.append(node)
        node = following.get(node, start)
    if node != start or len(cycle) != len(boundary):
        raise ValueError("Unwrap chart boundary must be one connected loop")
    fixed = {}
    pin_count = 0
    for c in corners:
        if not c.get("pin", False):
            continue
        pin_count += 1
        node = node_for[c["id"]]
        uv = np.array(c["uv"])
        if node in fixed and not np.allclose(fixed[node], uv, atol=1e-9, rtol=0):
            raise ValueError("Conflicting pins meet across an uncut edge; mark a seam first")
        fixed[node] = uv
    if len(fixed) < 2:
        if fixed:
            first = next(iter(fixed))
        else:
            seed = cycle[0]
            first = max(cycle, key=lambda i: float(np.linalg.norm(positions[i] - positions[seed])))
            fixed[first] = np.array([0.0, 0.0])
        second = max(cycle, key=lambda i: float(np.linalg.norm(positions[i] - positions[first])))
        distance = float(np.linalg.norm(positions[second] - positions[first]))
        if distance <= 1e-12:
            raise ValueError("Unwrap anchors need distinct mesh positions")
        fixed[second] = fixed[first] + [distance, 0.0]
    fixed_uv = np.array(list(fixed.values()))
    if np.linalg.norm(np.ptp(fixed_uv, axis=0)) <= 1e-12:
        raise ValueError("Unwrap pins need at least two distinct UV locations")
    rows = []
    cols = []
    values = []
    triangles = []
    for f in faces:
        cs = f["corners"]
        start = min(range(len(cs)), key=lambda i: int(cs[i]["id"][1:]))
        cs = cs[start:] + cs[:start]
        xyz = np.array([points[c["vertex"]] for c in cs])
        for tri in topology.triangles(xyz):
            nodes = [node_for[cs[i]["id"]] for i in tri]
            p, a, b = xyz[list(tri)]
            x = a - p
            y = b - p
            length = float(np.linalg.norm(x))
            height = float(np.linalg.norm(np.cross(x, y))) / length
            horizontal = float(y @ x) / length
            area = length * height / 2
            if area <= 1e-24:
                raise ValueError("Unwrap has a degenerate source triangle")
            local = np.array([[0.0, 0.0], [length, 0.0], [horizontal, height]])
            gx = np.array(
                [local[1, 1] - local[2, 1], local[2, 1] - local[0, 1], local[0, 1] - local[1, 1]]
            ) / (2 * np.sqrt(area))
            gy = np.array(
                [local[2, 0] - local[1, 0], local[0, 0] - local[2, 0], local[1, 0] - local[0, 0]]
            ) / (2 * np.sqrt(area))
            row = len(triangles) * 2
            triangles.append(nodes)
            for i, node in enumerate(nodes):
                rows.extend([row, row, row + 1, row + 1])
                cols.extend([node * 2, node * 2 + 1, node * 2, node * 2 + 1])
                values.extend([gx[i], -gy[i], gy[i], gx[i]])
    matrix = coo_matrix(
        (values, (rows, cols)), shape=(2 * len(triangles), 2 * len(identities))
    ).tocsr()
    fixed_columns = np.array([2 * node + axis for node in fixed for axis in (0, 1)], dtype=int)
    fixed_values = np.array([fixed[node][axis] for node in fixed for axis in (0, 1)])
    fixed_set = set(fixed_columns)
    free = np.array([i for i in range(matrix.shape[1]) if i not in fixed_set], dtype=int)
    solution = np.empty(matrix.shape[1])
    solution[fixed_columns] = fixed_values
    if len(free):
        rhs = -(matrix[:, fixed_columns] @ fixed_values)
        result = lsqr(
            matrix[:, free],
            rhs,
            atol=1e-11,
            btol=1e-11,
            conlim=1e10,
            iter_lim=min(10000, max(1000, len(free) * 4)),
        )
        # Code 0 is an exact zero solution, possible when pins already fix all
        # other corners and the remaining corner belongs at the UV origin.
        if result[1] not in (0, 1, 2, 4, 5) or not np.isfinite(result[0]).all():
            raise ValueError("Conformal unwrap did not converge; simplify the chart or add seams")
        solution[free] = result[0]
    uv = solution.reshape(-1, 2)
    extent = max(float(np.ptp(uv, axis=0).max()), 1e-12)
    for tri in triangles:
        p, a, b = uv[tri]
        if topology._cross(a - p, b - p) <= extent * extent * 1e-12:
            raise ValueError(
                "Conformal unwrap folded or collapsed a triangle; adjust pins or seams"
            )
    # A positive triangle orientation plus a simple chart boundary rules out
    # a global overlap for these disk charts. Reuse the polygon validator.
    topology.triangles([[*uv[node], 0.0] for node in cycle])
    return corners, node_for, uv, pin_count


def _align(uv):
    """Rotate an unpinned chart to its minimum-area bounding rectangle."""
    hull = uv[ConvexHull(uv).vertices]
    edges = np.roll(hull, -1, axis=0) - hull
    angles = np.unique(np.round(np.arctan2(edges[:, 1], edges[:, 0]) % (np.pi / 2), 12))
    best, best_area = uv, float("inf")
    for angle in angles:
        cosine, sine = np.cos(angle), np.sin(angle)
        rotated = uv @ np.array([[cosine, -sine], [sine, cosine]])
        area = float(np.prod(np.ptp(rotated, axis=0)))
        if area < best_area - max(area, 1e-24) * 1e-10:
            best, best_area = rotated, area
    return best


def unwrap(placement, face_ids=None, *, fit_tile=True, margin=0.02):
    """Solve manifold disk charts cut at marked edges; preserve authored pins.

    Entirely unpinned selections align and fit the unit tile by default. If any
    chart has pins, their authored coordinates remain fixed and free charts
    are placed alongside. Turning fit_tile off retains the raw solved layout.
    """
    if type(fit_tile) is not bool:
        raise ValueError("UV tile fitting must be a boolean")
    margin = mesh_uv._number(margin)
    if not 0 <= margin < 0.5:
        raise ValueError("UV packing margin must be at least 0 and less than 0.5")
    doc = mesh_uv.source(placement)
    charts, roots = _charts(doc, face_ids)
    points = {v["id"]: np.array(v["position"], dtype=float) for v in doc["vertices"]}
    solved = [_solve(chart, roots, points) for chart in charts]
    pinned_bounds = [uv[:, 0].max() for _, _, uv, pins in solved if pins]
    cursor = max(pinned_bounds, default=0.0)
    total_pins = 0
    for corners, nodes, uv, pins in solved:
        total_pins += pins
        if not pins:
            if fit_tile:
                uv = _align(uv)
            low = uv.min(axis=0)
            span = np.ptp(uv, axis=0)
            if cursor:
                cursor += max(float(span.max()) * 0.05, 0.01)
            uv = uv - low + [cursor, 0.0]
            cursor += float(span[0])
        for c in corners:
            if not c.get("pin", False):
                c["uv"] = uv[nodes[c["id"]]].tolist()
    fitted = fit_tile and not total_pins
    if fitted:
        mesh_uv_islands.pack_charts(charts, margin)
    return {
        **mesh_uv._publish(placement, doc),
        "charts": len(charts),
        "pinned_corners": total_pins,
        "method": "conformal",
        "fitted_to_tile": fitted,
    }
