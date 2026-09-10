"""Retained mesh modifiers; source assets stay editable and unchanged on evaluation."""

from copy import deepcopy

import numpy as np

from . import mesh_document, topology

DEFAULTS = {
    "Mirror": {"axis": "x", "offset": 0.0, "merge": False, "threshold": 1e-6},
    "Array": {"count": 2, "offset": [3.0, 0.0, 0.0]},
    "Solidify": {"thickness": 0.1, "offset": -1.0, "rim": True},
    "Subdivision": {"levels": 1, "method": "catmull-clark", "boundary": "all"},
}


def parameters(kind, values):
    if (
        not isinstance(kind, str)
        or kind not in DEFAULTS
        or not isinstance(values, dict)
        or set(values) - set(DEFAULTS[kind])
    ):
        raise ValueError("Unknown modifier kind or parameters")
    result = {**deepcopy(DEFAULTS[kind]), **deepcopy(values)}
    if kind == "Mirror":
        if result["axis"] not in ("x", "y", "z") or type(result["merge"]) is not bool:
            raise ValueError("Mirror requires an axis x/y/z and boolean merge")
        for name in ("offset", "threshold"):
            value = result[name]
            if type(value) not in (int, float) or not np.isfinite(value):
                raise ValueError("Mirror distances must be finite numbers")
        if result["threshold"] < 0:
            raise ValueError("Mirror merge threshold cannot be negative")
    elif kind == "Array":
        if type(result["count"]) is not int or not 1 <= result["count"] <= 64:
            raise ValueError("Array count must be a whole number from 1 to 64")
        result["offset"] = topology._coordinates(result["offset"]).tolist()
    elif kind == "Solidify":
        for name in ("thickness", "offset"):
            if type(result[name]) not in (int, float) or not np.isfinite(result[name]):
                raise ValueError("Solidify thickness and offset must be finite numbers")
        if abs(result["thickness"]) <= 1e-12 or not -1 <= result["offset"] <= 1:
            raise ValueError("Solidify needs nonzero thickness and offset from -1 to 1")
        if type(result["rim"]) is not bool:
            raise ValueError("Solidify rim must be boolean")
    else:
        if type(result["levels"]) is not int or not 1 <= result["levels"] <= 4:
            raise ValueError("Subdivision levels must be a whole number from 1 to 4")
        if result["method"] not in ("catmull-clark", "simple"):
            raise ValueError("Subdivision method must be catmull-clark or simple")
        if result["boundary"] not in ("all", "keep_corners"):
            raise ValueError("Subdivision boundary must be all or keep_corners")
    return result


def settings(placement):
    raw = placement.props.get("modifiers3d", {"schema_version": 1, "next_id": 1, "items": []})
    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "next_id", "items"}
        or type(raw["schema_version"]) is not int
        or raw["schema_version"] != 1
    ):
        raise ValueError("Invalid modifier stack schema")
    if (
        type(raw["next_id"]) is not int
        or raw["next_id"] < 1
        or not isinstance(raw["items"], list)
        or len(raw["items"]) > 64
    ):
        raise ValueError("Invalid modifier stack counter or items")
    result = deepcopy(raw)
    seen = set()
    for item in result["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "kind", "enabled", "parameters"}:
            raise ValueError("Invalid modifier record")
        identity = item["id"]
        suffix = identity[3:] if isinstance(identity, str) and identity.startswith("mod") else ""
        if (
            not suffix.isascii()
            or not suffix.isdigit()
            or suffix.startswith("0")
            or int(suffix) >= raw["next_id"]
            or identity in seen
        ):
            raise ValueError("Invalid or duplicate modifier identity")
        seen.add(identity)
        if type(item["enabled"]) is not bool:
            raise ValueError("Modifier enabled must be boolean")
        item["parameters"] = parameters(item["kind"], item["parameters"])
    return result


def _copies(mesh, kind, values):
    source = topology.document(mesh)
    doc = deepcopy(source)
    originals = {v["id"]: v for v in doc["vertices"]}
    axis = "xyz".index(values["axis"]) if kind == "Mirror" else None
    existing = {tuple(sorted(e["vertices"])): e for e in doc["edges"]}
    copies = range(1, 2 if kind == "Mirror" else values["count"])
    for index in copies:
        mapping = {}
        for vertex in source["vertices"]:
            p = np.array(vertex["position"], dtype=float)
            if kind == "Mirror":
                delta = p[axis] - values["offset"]
                if values["merge"] and abs(delta) <= values["threshold"]:
                    mapping[vertex["id"]] = vertex["id"]
                    originals[vertex["id"]]["position"][axis] = values["offset"]
                    continue
                p[axis] = 2 * values["offset"] - p[axis]
            else:
                p += index * np.asarray(values["offset"])
            added = deepcopy(vertex)
            added["id"] = topology._id(doc, "v")
            added["position"] = p.tolist()
            mapping[vertex["id"]] = added["id"]
            doc["vertices"].append(added)
        for edge in source["edges"]:
            pair = tuple(sorted(mapping[v] for v in edge["vertices"]))
            if pair not in existing:
                added = deepcopy(edge)
                added["id"] = topology._id(doc, "e")
                added["vertices"] = list(pair)
                doc["edges"].append(added)
                existing[pair] = added
        for face in source["faces"]:
            added = deepcopy(face)
            added["id"] = topology._id(doc, "f")
            if kind == "Mirror":
                added["corners"].reverse()
            for corner in added["corners"]:
                corner["id"] = topology._id(doc, "c")
                corner["vertex"] = mapping[corner["vertex"]]
                if kind == "Mirror" and corner["normal"] is not None:
                    corner["normal"][axis] *= -1
            doc["faces"].append(added)
    doc["schema_version"] = max(2, doc["schema_version"])
    return topology.compile(doc)[0]


def _solidify(mesh, values):
    """Simple shell along angle-weighted vertex normals, with optional boundary rims."""
    source = topology.document(mesh)
    usage = topology.edge_usage(source)
    if not source["faces"] or any(
        len(uses) > 2 or (len(uses) == 2 and uses[0] != uses[1][::-1]) for uses in usage.values()
    ):
        raise ValueError("Solidify requires a consistently oriented manifold surface")
    points = {v["id"]: np.asarray(v["position"], dtype=float) for v in source["vertices"]}
    normals = {identity: np.zeros(3) for identity in points}
    incident = {identity: [] for identity in points}
    boundary = {}
    for face in source["faces"]:
        corners = face["corners"]
        ids = [c["vertex"] for c in corners]
        n = topology.normal([points[v] for v in ids])
        for i, identity in enumerate(ids):
            before = points[ids[i - 1]] - points[identity]
            after = points[ids[(i + 1) % len(ids)]] - points[identity]
            before /= np.linalg.norm(before)
            after /= np.linalg.norm(after)
            angle = np.arccos(np.clip(before @ after, -1, 1))
            if np.cross(before, after) @ n > 0:
                angle = 2 * np.pi - angle
            normals[identity] += n * angle
            incident[identity].append({ids[i - 1], ids[(i + 1) % len(ids)]})
            a, b = identity, ids[(i + 1) % len(ids)]
            pair = tuple(sorted((a, b)))
            if len(usage[pair]) == 1:
                boundary[pair] = (face, corners[i], corners[(i + 1) % len(ids)])
    if any(tuple(sorted(e["vertices"])) not in usage for e in source["edges"]):
        raise ValueError("Solidify does not support loose edges")
    for identity, n in normals.items():
        length = np.linalg.norm(n)
        if length <= 1e-12:
            raise ValueError("Solidify needs a defined normal at every vertex")
        # Edge-manifoldness alone does not reject two sheets touching at a point.
        fans = incident[identity]
        connected = {0}
        pending = [0]
        while pending:
            current = pending.pop()
            for i, neighbors in enumerate(fans):
                if i not in connected and neighbors & fans[current]:
                    connected.add(i)
                    pending.append(i)
        if len(connected) != len(fans):
            raise ValueError("Solidify requires one connected surface fan per vertex")
        normals[identity] = n / length
    doc = deepcopy(source)
    thickness, offset = values["thickness"], values["offset"]
    mapping = {}
    for original, vertex in zip(source["vertices"], doc["vertices"][:]):
        identity = original["id"]
        vertex["position"] = (
            points[identity] + normals[identity] * thickness * (offset + 1) / 2
        ).tolist()
        added = deepcopy(original)
        added["id"] = topology._id(doc, "v")
        added["position"] = (
            points[identity] + normals[identity] * thickness * (offset - 1) / 2
        ).tolist()
        mapping[identity] = added["id"]
        doc["vertices"].append(added)
    for edge in source["edges"]:
        added = deepcopy(edge)
        added["id"] = topology._id(doc, "e")
        added["vertices"] = [mapping[v] for v in edge["vertices"]]
        doc["edges"].append(added)
    for face in source["faces"]:
        added = deepcopy(face)
        added["id"] = topology._id(doc, "f")
        added["corners"].reverse()
        for corner in added["corners"]:
            corner["id"] = topology._id(doc, "c")
            corner["vertex"] = mapping[corner["vertex"]]
            if corner["normal"] is not None:
                corner["normal"] = [-v for v in corner["normal"]]
        doc["faces"].append(added)
    if values["rim"]:
        for face, a, b in boundary.values():
            doc["faces"].append(
                {
                    "id": topology._id(doc, "f"),
                    "material": face["material"],
                    "corners": [
                        topology._corner(doc, identity, corner["uv"])
                        for identity, corner in (
                            (b["vertex"], b),
                            (a["vertex"], a),
                            (mapping[a["vertex"]], a),
                            (mapping[b["vertex"]], b),
                        )
                    ],
                }
            )
    if thickness < 0:
        for face in doc["faces"]:
            face["corners"].reverse()
            for corner in face["corners"]:
                if corner["normal"] is not None:
                    corner["normal"] = [-v for v in corner["normal"]]
    topology._edges(doc)
    doc["schema_version"] = max(2, doc["schema_version"])
    return topology.compile(doc)[0]


def evaluate_stack(mesh, stack):
    result = mesh
    for item in stack["items"]:
        if item["enabled"]:
            if item["kind"] == "Subdivision":
                from . import mesh_subdivision

                result = mesh_subdivision.evaluate(result, item["parameters"])
                continue
            doc = topology.document(result)
            copies = item["parameters"]["count"] if item["kind"] == "Array" else 2
            size = (
                len(doc["vertices"])
                + len(doc["edges"])
                + sum(len(f["corners"]) for f in doc["faces"])
            )
            rim_size = 0
            if item["kind"] == "Solidify" and item["parameters"]["rim"]:
                rim_size = 6 * sum(len(u) == 1 for u in topology.edge_usage(doc).values())
            if size * copies + rim_size > 1_000_000:
                raise ValueError("Modifier stack exceeds the evaluated component limit")
            result = (
                _solidify(result, item["parameters"])
                if item["kind"] == "Solidify"
                else _copies(result, item["kind"], item["parameters"])
            )
    return result


def _publish(placement, stack):
    if placement.kind != "Mesh3D":
        raise ValueError("Modifiers require a mesh object")
    candidate = deepcopy(placement)
    candidate.props["modifiers3d"] = deepcopy(stack)
    checked = settings(candidate)
    from . import mesh_edit

    evaluate_stack(mesh_edit.evaluate(candidate, include_modifiers=False), checked)
    placement.props["modifiers3d"] = checked
    return deepcopy(checked)


def add(placement, kind, values=None):
    stack = settings(placement)
    identity = f"mod{stack['next_id']}"
    stack["next_id"] += 1
    stack["items"].append(
        {
            "id": identity,
            "kind": kind,
            "enabled": True,
            "parameters": parameters(kind, {} if values is None else values),
        }
    )
    return _publish(placement, stack)


def update(placement, identity, *, values=None, enabled=None, index=None, remove=False):
    stack = settings(placement)
    item = next((m for m in stack["items"] if m["id"] == identity), None)
    if item is None:
        raise ValueError("Modifier no longer exists")
    if values is not None:
        if not isinstance(values, dict):
            raise ValueError("Modifier parameters must be an object")
        item["parameters"] = parameters(item["kind"], {**item["parameters"], **values})
    if enabled is not None:
        if type(enabled) is not bool:
            raise ValueError("Modifier enabled must be boolean")
        item["enabled"] = enabled
    if index is not None:
        if type(index) is not int or not 0 <= index < len(stack["items"]):
            raise ValueError("Modifier index is outside the stack")
        stack["items"].remove(item)
        stack["items"].insert(index, item)
    if remove:
        stack["items"].remove(item)
    return _publish(placement, stack)


def apply_all(placement):
    if placement.kind != "Mesh3D":
        raise ValueError("Modifiers require a mesh object")
    from . import mesh_edit

    mesh = mesh_edit.evaluate(placement)
    key = mesh_document.bind(placement, mesh, label=placement.name)
    placement.props.pop("modifiers3d", None)
    placement.props.pop("taper3d", None)
    placement.props["components3d"] = {"mode": "vertices", "ids": []}
    return {
        "mesh_key": key,
        "vertices": len(mesh.topology["vertices"]),
        "edges": len(mesh.topology["edges"]),
        "faces": len(mesh.topology["faces"]),
    }
