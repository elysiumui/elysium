"""Retained mesh/face normal policies and source sharp-edge authoring."""

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
    smooth = [f.get("smooth", policy["mode"] == "smooth") for f in faces]

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
        if not (smooth[a[0]] and smooth[b[0]]):
            continue
        if a[1:3] != b[1:3][::-1] or np.dot(normals[a[0]], normals[b[0]]) < threshold - 1e-12:
            continue
        for ca, cb in ((a[3], b[4]), (a[4], b[3])):
            parent[find(ca)] = find(cb)
    if weighted is not None:
        return _weighted_corners(faces, points, normals, weights, find, weighted, smooth)
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


def _weighted_corners(faces, points, normals, angles, find, settings, smooth):
    """Descending value bands and exponential bias, matching Blender's modifier."""
    groups, result = {}, {}
    for fi, face in enumerate(faces):
        if not smooth[fi]:
            result.update({c["id"]: normals[fi].tolist() for c in face["corners"]})
            continue
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
    if not any(f.get("smooth", policy["mode"] == "smooth") for f in doc["faces"]):
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
        "face_smooth_overrides": {f["id"]: f["smooth"] for f in doc["faces"] if "smooth" in f},
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
    for face in doc["faces"]:
        face.pop("smooth", None)
    return _publish(placement, doc)


def set_faces_smooth(placement, face_ids, smooth=True):
    """Override selected computed face shading; authored custom normals stay explicit."""
    if type(smooth) is not bool:
        raise ValueError("Face smooth value must be boolean")
    doc = _source(placement)
    if "shading" not in doc:
        raise ValueError("Choose whole-mesh Smooth or Flat before editing face shading")
    if (not isinstance(face_ids, list) or not face_ids
            or any(not isinstance(i, str) for i in face_ids)
            or len(set(face_ids)) != len(face_ids)):
        raise ValueError("Select distinct source face identities")
    selected = topology._selected(doc, face_ids)
    doc["schema_version"] = max(5, doc["schema_version"])
    for face in selected:
        face["smooth"] = smooth
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


def transfer(placements, target, source, *, space="world"):
    """Copy evaluated source corner normals onto identically ordered target topology."""
    if source is target or getattr(source, "entity_id", None) == getattr(target, "entity_id", None):
        raise ValueError("Choose distinct source and target meshes")
    if space not in ("world", "local"):
        raise ValueError("Normal transfer space must be world or local")
    if source.kind != "Mesh3D" or target.kind != "Mesh3D":
        raise ValueError("Normal transfer requires two meshes")
    indices = []
    for placement in (source, target):
        matches = [i for i, p in enumerate(placements) if p is placement]
        if len(matches) != 1:
            raise ValueError("Normal transfer requires distinct objects in the current scene")
        indices.append(matches[0])
    src = topology.document(mesh_edit.evaluate(source))
    dst = _source(target)

    def signature(doc):
        lookup = {v["id"]: i for i, v in enumerate(doc["vertices"])}
        return (
            len(lookup),
            [tuple(lookup[c["vertex"]] for c in f["corners"]) for f in doc["faces"]],
        )

    if not src["faces"] or signature(src) != signature(dst):
        raise ValueError("Normal transfer requires matching vertex, polygon and corner ordering")
    matrix = np.eye(3)
    if space == "world":
        from . import scene

        matrices = scene.world_matrices(placements)
        try:
            matrix = np.linalg.inv(matrices[indices[0]][:3, :3]) @ matrices[indices[1]][:3, :3]
        except np.linalg.LinAlgError as exc:
            raise ValueError("Normal transfer requires invertible object transforms") from exc
    compiled, vertex_ids, face_ids = topology.compile(src)
    observed = {}
    points = {v["id"]: v["position"] for v in src["vertices"]}
    fallback = {
        f["id"]: topology.normal([points[c["vertex"]] for c in f["corners"]]) for f in src["faces"]
    }
    for triangle, face_id in zip(compiled.faces, face_ids):
        for index in triangle:
            observed[(face_id, vertex_ids[index])] = (
                fallback[face_id] if compiled.vert_normals is None else compiled.vert_normals[index]
            )
    for sf, tf in zip(src["faces"], dst["faces"]):
        for sc, tc in zip(sf["corners"], tf["corners"]):
            normal = np.asarray(observed[(sf["id"], sc["vertex"])]) @ matrix
            length = np.linalg.norm(normal)
            if not np.isfinite(normal).all() or length <= 1e-12:
                raise ValueError("Normal transfer encountered an undefined normal")
            tc["normal"] = (normal / length).tolist()
    _mark_discontinuities(dst)
    dst.pop("shading", None)
    return _publish(target, dst)


def _mark_discontinuities(dst):
    # Custom-normal discontinuities require split fans in Blender's representation.
    # Preserve existing sharp flags and seams; only add new manifold discontinuities.
    adjacency = {}
    for face in dst["faces"]:
        cs = face["corners"]
        for i, c in enumerate(cs):
            nxt = cs[(i + 1) % len(cs)]
            pair = tuple(sorted((c["vertex"], nxt["vertex"])))
            adjacency.setdefault(pair, []).append((c, nxt))
    for edge in dst["edges"]:
        uses = adjacency.get(tuple(sorted(edge["vertices"])), [])
        if len(uses) == 2 and uses[0][0]["vertex"] == uses[1][1]["vertex"]:
            a, b = uses
            if any(
                np.dot(c["normal"], d["normal"]) < 1 - 1e-4 for c, d in ((a[0], b[1]), (a[1], b[0]))
            ):
                edge["sharp"] = True


def set_direction(placement, face_ids, normal):
    """Set selected source face-corner normals to one normalized local direction."""
    doc = _source(placement)
    if (
        not isinstance(face_ids, list)
        or not face_ids
        or any(not isinstance(i, str) for i in face_ids)
        or len(set(face_ids)) != len(face_ids)
    ):
        raise ValueError("Select distinct source face identities")
    if set(face_ids) - {f["id"] for f in doc["faces"]}:
        raise ValueError("Selected face no longer exists")
    if (
        not isinstance(normal, (list, tuple))
        or len(normal) != 3
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in normal)
    ):
        raise ValueError("Normal direction requires three finite numbers")
    # Scale first so finite extreme components cannot overflow the normalization.
    n = np.asarray(normal, dtype=float)
    scale = float(np.max(np.abs(n)))
    if scale == 0:
        raise ValueError("Normal direction must be nonzero")
    n /= scale
    n /= np.linalg.norm(n)
    mesh, ids, face_map = topology.compile(doc)
    existing = {}
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    fallback = {
        f["id"]: topology.normal([points[c["vertex"]] for c in f["corners"]]) for f in doc["faces"]
    }
    for triangle, fid in zip(mesh.faces, face_map):
        for i in triangle:
            existing[fid, ids[i]] = (
                fallback[fid] if mesh.vert_normals is None else mesh.vert_normals[i]
            )
    for face in doc["faces"]:
        for c in face["corners"]:
            c["normal"] = (
                n if face["id"] in face_ids else np.asarray(existing[face["id"], c["vertex"]])
            ).tolist()
    _mark_discontinuities(doc)
    doc.pop("shading", None)
    return _publish(placement, doc)
