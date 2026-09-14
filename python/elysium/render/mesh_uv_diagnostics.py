"""Read-only local-space UV shape distortion and source-face validity."""

import numpy as np

from . import mesh_uv, topology


def inspect(placement):
    """Report triangle stretch ratios; 1 means similarity, not texture density.

    Ratios use singular values of the map from an orthonormal source triangle
    to UV space. Missing or collapsed UVs have no finite stretch value.
    Object transforms and modifier output are deliberately not measured here.
    """
    doc = mesh_uv.source(placement)
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    result = []
    for face in doc["faces"]:
        corners = face["corners"]
        item = {"face_id": face["id"], "status": "valid", "max_stretch": None, "triangles": []}
        if any(c["uv"] is None for c in corners):
            item["status"] = "missing"
            result.append(item)
            continue
        xyz = np.array([points[c["vertex"]] for c in corners], dtype=float)
        uv = np.array([c["uv"] for c in corners], dtype=float)
        for triangle in topology.triangles(xyz):
            a, b, c = xyz[list(triangle)]
            e, f = b - a, c - a
            length = np.linalg.norm(e)
            height = np.linalg.norm(np.cross(e, f)) / length
            source = np.array([[length, np.dot(e, f) / length], [0, height]])
            u, v, w = uv[list(triangle)]
            jacobian = np.column_stack((v - u, w - u)) @ np.linalg.inv(source)
            singular = np.linalg.svd(jacobian, compute_uv=False)
            valid = singular[0] > 0 and singular[1] > singular[0] * 1e-12
            item["triangles"].append(
                {
                    "corner_ids": [corners[i]["id"] for i in triangle],
                    "stretch": float(singular[0] / singular[1]) if valid else None,
                    "area_ratio": float(abs(np.linalg.det(jacobian))),
                    "uv_winding": int(np.sign(np.linalg.det(jacobian))),
                }
            )
            if not valid:
                item["status"] = "collapsed"
        if item["status"] == "valid":
            item["max_stretch"] = max(t["stretch"] for t in item["triangles"])
        result.append(item)
    valid = [f["max_stretch"] for f in result if f["status"] == "valid"]
    return {
        "space": "local_source",
        "faces": result,
        "max_stretch": max(valid, default=None),
        "missing_faces": sum(f["status"] == "missing" for f in result),
        "collapsed_faces": sum(f["status"] == "collapsed" for f in result),
    }


def face_uv_status(mesh):
    """One status per evaluated render triangle; never invent UVs for a face."""
    if mesh.topology is None:
        return np.full(len(mesh.faces), "valid" if mesh.vert_uvs is not None else "missing")
    result = []
    points = {v["id"]: v["position"] for v in mesh.topology["vertices"]}
    for face in mesh.topology["faces"]:
        cs = face["corners"]
        status = "missing" if any(c["uv"] is None for c in cs) else "valid"
        xyz = np.array([points[c["vertex"]] for c in cs])
        for triangle in topology.triangles(xyz):
            value = status
            if status == "valid":
                uv = np.array([cs[i]["uv"] for i in triangle])
                a, b = uv[1] - uv[0], uv[2] - uv[0]
                area = abs(a[0] * b[1] - a[1] * b[0])
                if area <= max(np.linalg.norm(a) * np.linalg.norm(b) * 1e-12, 1e-30):
                    value = "collapsed"
            result.append(value)
    return np.array(result)
