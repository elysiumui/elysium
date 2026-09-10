"""Corner-domain UV authoring shared by Designer and public mesh tools."""

from copy import deepcopy

import numpy as np

from . import mesh_document, mesh_edit, topology


def _number(value):
    if type(value) not in (int, float) or not np.isfinite(value):
        raise ValueError("UV values must be finite numbers")
    return float(value)


def _pair(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("UV coordinates require two numbers")
    return np.array([_number(v) for v in value])


def _publish(placement, doc):
    result = topology.compile(doc)[0]
    mesh_edit.evaluate_mesh(result, placement)
    key = mesh_document.bind(placement, result, label=getattr(placement, "name", "Mesh"))
    return {"mesh_key": key, "corners": sum(len(f["corners"]) for f in doc["faces"])}


def source(placement):
    if placement.kind != "Mesh3D":
        raise ValueError("UV editing requires a mesh")
    return topology.document(mesh_document.resolve(placement.mesh_kind))


def _selected(records, ids, label):
    if ids is None:
        return list(records)
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(v, str) for v in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError(f"Select distinct {label} identities")
    selected = [r for r in records if r["id"] in ids]
    if len(selected) != len(ids):
        raise ValueError(f"Selected {label} no longer exists")
    return selected


def project(placement, mode, *, face_ids=None, yaw=0.0, pitch=0.0):
    """Project selected source faces, preserving topology and independent corner UVs."""
    yaw, pitch = _number(yaw), _number(pitch)
    if not isinstance(mode, str):
        raise ValueError("UV projection mode must be a string")  # noqa: TRY004 — public UV validation contract
    mode = mode.lower()
    if mode not in (
        "planar",
        "camera",
        "planar_xy",
        "planar_xz",
        "planar_yz",
        "cylindrical",
        "spherical",
    ):
        raise ValueError("Unknown UV projection mode")
    doc = source(placement)
    faces = _selected(doc["faces"], face_ids, "face")
    if not faces:
        raise ValueError("UV projection needs surface faces")
    points = {v["id"]: np.asarray(v["position"], dtype=float) for v in doc["vertices"]}
    identities = list(dict.fromkeys(c["vertex"] for f in faces for c in f["corners"]))
    values = np.array([points[v] for v in identities])
    if mode in ("planar", "camera", "planar_xy", "planar_xz", "planar_yz"):
        if mode == "planar_xy":
            u, v = np.array([1, 0, 0]), np.array([0, 1, 0])
        elif mode == "planar_xz":
            u, v = np.array([1, 0, 0]), np.array([0, 0, -1])
        elif mode == "planar_yz":
            u, v = np.array([0, 0, -1]), np.array([0, 1, 0])
        else:
            look = -np.array(
                [np.cos(pitch) * np.sin(yaw), np.sin(pitch), np.cos(pitch) * np.cos(yaw)]
            )
            up = np.array([0, 0, -1]) if abs(look[1]) > 0.9999 else np.array([0, 1, 0])
            u = np.cross(look, up)
            u /= np.linalg.norm(u)
            v = np.cross(u, look)
        uv = np.column_stack((values @ u, values @ v))
        uv = (uv - uv.min(axis=0)) / np.maximum(np.ptp(uv, axis=0), 1e-6)
    else:
        u = (np.arctan2(values[:, 2], values[:, 0]) + np.pi) / (2 * np.pi)
        if mode == "cylindrical":
            v = (values[:, 1] - values[:, 1].min()) / max(float(np.ptp(values[:, 1])), 1e-6)
        else:
            radius = np.linalg.norm(values, axis=1)
            if (radius < 1e-12).any():
                raise ValueError("Spherical projection needs vertices away from the origin")
            v = np.arccos(np.clip(values[:, 1] / radius, -1, 1)) / np.pi
        uv = np.column_stack((u, v))
    lookup = dict(zip(identities, uv))
    for face in faces:
        face_uv = np.array([lookup[c["vertex"]] for c in face["corners"]])
        if mode in ("cylindrical", "spherical"):
            poles = np.array(
                [np.linalg.norm(points[c["vertex"]][[0, 2]]) < 1e-12 for c in face["corners"]]
            )
            regular = face_uv[~poles, 0]
            if len(regular) and np.ptp(regular) > 0.5:
                face_uv[(face_uv[:, 0] < 0.5) & ~poles, 0] += 1
            if poles.any() and (~poles).any():
                face_uv[poles, 0] = face_uv[~poles, 0].mean()
        for corner, pair in zip(face["corners"], face_uv):
            corner["uv"] = pair.tolist()
    return {**_publish(placement, doc), "mode": mode, "yaw": yaw, "pitch": pitch}


def transform(placement, corner_ids=None, *, offset=(0.0, 0.0), scale=(1.0, 1.0), angle=0.0):
    # Blender UV Editor uses clockwise positive numeric rotation.
    offset, scale, angle = _pair(offset), _pair(scale), -np.radians(_number(angle))
    doc = source(placement)
    corners = _selected([c for f in doc["faces"] for c in f["corners"]], corner_ids, "UV corner")
    if not corners or any(c.get("uv") is None for c in corners):
        raise ValueError("Project or assign UVs before transforming selected corners")
    uv = np.array([c["uv"] for c in corners])
    center = uv.mean(axis=0)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    result = ((uv - center) * scale) @ rotation.T + center + offset
    for corner, pair in zip(corners, result):
        corner["uv"] = pair.tolist()
    return _publish(placement, doc)


def seams(placement, edge_ids, enabled=True):
    if type(enabled) is not bool:
        raise ValueError("Seam state must be boolean")
    doc = source(placement)
    edges = _selected(doc["edges"], edge_ids, "edge")
    if not edges:
        raise ValueError("Select source edges to mark seams")
    for edge in edges:
        edge["seam"] = enabled
    return _publish(placement, doc)


def read(placement):
    doc = source(placement)
    return {
        "faces": [
            {
                "id": f["id"],
                "corners": [
                    {
                        "id": c["id"],
                        "vertex": c["vertex"],
                        "uv": deepcopy(c.get("uv")),
                        "pin": c.get("pin", False),
                    }
                    for c in f["corners"]
                ],
            }
            for f in doc["faces"]
        ],
        "seams": [e["id"] for e in doc["edges"] if e["seam"]],
    }


def pin(placement, corner_ids, enabled=True):
    """Persist UV pin state on selected retained corners; manual transforms remain allowed."""
    if type(enabled) is not bool:
        raise ValueError("UV pin state must be boolean")
    doc = source(placement)
    corners = _selected([c for f in doc["faces"] for c in f["corners"]], corner_ids, "UV corner")
    if not corners or any(c.get("uv") is None for c in corners):
        raise ValueError("Project and select UV corners before pinning")
    doc["schema_version"] = 3
    for corner in corners:
        corner["pin"] = enabled
    return _publish(placement, doc)
