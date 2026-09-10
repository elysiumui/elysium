"""UV continuity islands, deterministic packing and texture-density normalization."""

import numpy as np

from . import mesh_uv, topology


def groups(doc):
    """Faces connect only across a mesh edge with identical endpoint UVs.

    A marked source seam alone does not split existing UV coordinates.
    Unprojected faces are excluded until all of their corners have UVs.
    """
    faces = [f for f in doc["faces"] if all(c.get("uv") is not None for c in f["corners"])]
    parents = list(range(len(faces)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    edges = {}
    for i, face in enumerate(faces):
        corners = face["corners"]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            key = tuple(sorted(((a["vertex"], tuple(a["uv"])), (b["vertex"], tuple(b["uv"])))))
            if key in edges:
                first, second = root(i), root(edges[key])
                parents[max(first, second)] = min(first, second)
            else:
                edges[key] = i
    islands = {}
    for i, face in enumerate(faces):
        islands.setdefault(root(i), []).append(face)
    return list(islands.values())


def selected(doc, corner_ids=None):
    islands = groups(doc)
    corners = [c for island in islands for f in island for c in f["corners"]]
    chosen = mesh_uv._selected(corners, corner_ids, "projected UV corner")
    ids = {c["id"] for c in chosen}
    result = [
        island for island in islands if any(c["id"] in ids for f in island for c in f["corners"])
    ]
    if not result:
        raise ValueError("Project and select UV corners before editing islands")
    return result


def read(placement):
    doc = mesh_uv.source(placement)
    result = []
    for island in groups(doc):
        corners = [c for f in island for c in f["corners"]]
        uv = np.array([c["uv"] for c in corners])
        result.append(
            {
                "id": min(f["id"] for f in island),
                "face_ids": [f["id"] for f in island],
                "corner_ids": [c["id"] for c in corners],
                "min": uv.min(axis=0).tolist(),
                "max": uv.max(axis=0).tolist(),
            }
        )
    return result


def pack(placement, corner_ids=None, *, margin=0.02):
    """Pack whole selected islands into the unit tile without rotation.

    A deterministic height-sorted shelf arrangement maximizes a common scale
    by binary search. Margin is the padding around each island, in UV units: adjacent
    boxes have twice that gap, while the tile border has one margin. Existing relative island scale and winding persist.
    """
    margin = mesh_uv._number(margin)
    if not 0 <= margin < 0.5:
        raise ValueError("UV packing margin must be at least 0 and less than 0.5")
    doc = mesh_uv.source(placement)
    islands = selected(doc, corner_ids)
    boxes = []
    for island in islands:
        corners = [c for f in island for c in f["corners"]]
        uv = np.array([c["uv"] for c in corners])
        low, high = uv.min(axis=0), uv.max(axis=0)
        size = high - low
        if (size < 1e-12).any():
            raise ValueError("Packing requires islands with nonzero width and height")
        boxes.append((corners, uv, low, size, min(f["id"] for f in island)))
    boxes.sort(key=lambda b: (-b[3][1], -b[3][0], b[4]))

    def arrange(scale):
        x = y = margin
        row_height = 0.0
        offsets = []
        for _, _, _, size, _ in boxes:
            width, height = size * scale
            if x + width > 1 - margin + 1e-12:
                x, y = margin, y + row_height + 2 * margin
                row_height = 0.0
            if width > 1 - 2 * margin + 1e-12 or y + height > 1 - margin + 1e-12:
                return None
            offsets.append((x, y))
            x += width + 2 * margin
            row_height = max(row_height, height)
        return offsets

    lower, upper = 0.0, (1 - 2 * margin) / max(float(max(b[3])) for b in boxes)
    if arrange(upper) is not None:
        lower = upper
    else:
        for _ in range(64):
            middle = (lower + upper) / 2
            if arrange(middle) is None:
                upper = middle
            else:
                lower = middle
    offsets = arrange(lower)
    if offsets is None or lower <= 1e-12:
        raise ValueError("Packing margin leaves no room for these islands")
    for (corners, uv, low, _, _), offset in zip(boxes, offsets):
        result = (uv - low) * lower + offset
        for corner, value in zip(corners, result):
            corner["uv"] = value.tolist()
    return {
        **mesh_uv._publish(placement, doc),
        "islands": len(islands),
        "scale": lower,
        "margin": margin,
    }


def normalize(placement, corner_ids=None):
    """Equalize UV area per local surface area, preserving total selected UV area."""
    doc = mesh_uv.source(placement)
    islands = selected(doc, corner_ids)
    points = {v["id"]: np.array(v["position"]) for v in doc["vertices"]}
    areas = []
    for island in islands:
        mesh_area = uv_area = 0.0
        for face in island:
            corners = face["corners"]
            xyz = np.array([points[c["vertex"]] for c in corners])
            uv = np.array([c["uv"] for c in corners])
            for tri in topology.triangles(xyz):
                p, a, b = xyz[list(tri)]
                mesh_area += float(np.linalg.norm(np.cross(a - p, b - p))) / 2
                p, a, b = uv[list(tri)]
                a, b = a - p, b - p
                uv_area += abs(float(a[0] * b[1] - a[1] * b[0])) / 2
        if mesh_area <= 1e-12 or uv_area <= 1e-12:
            raise ValueError("Scale normalization requires nonzero surface and UV areas")
        areas.append((mesh_area, uv_area))
    density = sum(a[1] for a in areas) / sum(a[0] for a in areas)
    factors = []
    for island, (mesh_area, uv_area) in zip(islands, areas):
        factor = float(np.sqrt(density * mesh_area / uv_area))
        corners = [c for f in island for c in f["corners"]]
        uv = np.array([c["uv"] for c in corners])
        center = uv.mean(axis=0)
        for corner, value in zip(corners, (uv - center) * factor + center):
            corner["uv"] = value.tolist()
        factors.append(factor)
    return {
        **mesh_uv._publish(placement, doc),
        "islands": len(islands),
        "scale_factors": factors,
        "uv_area_per_surface_area": density,
    }
