"""Persistent object-local material slots and source-face assignment."""

import math
from copy import deepcopy

import numpy as np

from . import material_graph, material_image, mesh_document, mesh_edit, pbr, topology

DEFAULTS = {
    "base_color": [0.55, 0.55, 0.55],
    "metallic": 0.0,
    "roughness": 0.5,
    "specular": 0.5,
    "clear_coat": 0.0,
    "clear_coat_roughness": 0.05,
    "emissive": [0.0, 0.0, 0.0],
}
MAX_SLOTS = 64


def parameters(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError("Unknown material surface parameters")
    result = {**deepcopy(DEFAULTS), **deepcopy(values)}
    for name, value in result.items():
        vector = name in ("base_color", "emissive")
        if vector and (not isinstance(value, (list, tuple)) or len(value) != 3):
            raise ValueError("Material colors require three numeric components")
        limit = 64 if name == "emissive" else 1
        if any(
            type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= limit
            for v in (value if vector else [value])
        ):
            raise ValueError(f"Material {name} requires finite values from 0 to {limit}")
        if vector:
            result[name] = list(value)
    return result


def _source(p):
    if p.kind != "Mesh3D":
        raise ValueError("Material slots require a mesh object")
    return topology.document(mesh_document.resolve(p.mesh_kind))


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError("Material name requires 1–100 nonblank characters")
    return value.strip()


def _validate(table):
    if (
        not isinstance(table, dict)
        or set(table) != {"schema_version", "next_id", "slots"}
        or type(table["schema_version"]) is not int
        or table["schema_version"] != 1
        or type(table["next_id"]) is not int
        or table["next_id"] < 2
        or not isinstance(table["slots"], list)
        or not 1 <= len(table["slots"]) <= MAX_SLOTS
    ):
        raise ValueError("Invalid material slot table")
    seen = set()
    for slot in table["slots"]:
        if (
            not isinstance(slot, dict)
            or set(slot) - {"id", "name", "parameters", "albedo_image", "color_graph"}
            or not {"id", "name", "parameters"} <= set(slot)
        ):
            raise ValueError("Invalid material slot fields")
        if "color_graph" in slot:
            material_graph.evaluate(slot["color_graph"])
        if "albedo_image" in slot:
            material_image.pixels(slot["albedo_image"])
        identity = slot["id"]
        if (
            not isinstance(identity, str)
            or len(identity) < 2
            or identity[0] != "m"
            or not identity[1:].isascii()
            or not identity[1:].isdigit()
            or identity[1] == "0"
            or not 0 < int(identity[1:]) < table["next_id"]
            or identity in seen
        ):
            raise ValueError("Invalid or duplicate material slot identity")
        seen.add(identity)
        _name(slot["name"])
        if slot["parameters"] is not None:
            parameters(slot["parameters"])


def table(p):
    doc = _source(p)
    result = deepcopy(p.props.get("materials3d"))
    if result is None:
        count = max((f["material"] for f in doc["faces"]), default=0) + 1
        if count > MAX_SLOTS:
            raise ValueError("Material authoring supports at most 64 source slots")
        result = {
            "schema_version": 1,
            "next_id": count + 1,
            "slots": [
                {
                    "id": f"m{i + 1}",
                    "name": "Object material" if i == 0 else f"Object material {i + 1}",
                    "parameters": None,
                }
                for i in range(count)
            ],
        }
    _validate(result)
    if any(f["material"] >= len(result["slots"]) for f in doc["faces"]):
        raise ValueError("Source face references a missing material slot")
    return result


def read(p):
    result = table(p)
    doc = _source(p)
    return {
        "table": result,
        "face_slots": {f["id"]: result["slots"][f["material"]]["id"] for f in doc["faces"]},
    }


def resolved_parameters(p, slot):
    if slot["parameters"] is not None:
        return parameters(slot["parameters"])
    from . import scene

    material = scene.material(p)
    return {
        key: list(getattr(material, key))
        if key in ("base_color", "emissive")
        else getattr(material, key)
        for key in DEFAULTS
    }


def render_materials(p, mesh):
    """Return surfaces and local triangle indices; legacy scenes keep object shading."""
    from . import scene

    if "materials3d" not in getattr(p, "props", {}):
        return [scene.material(p)], np.zeros(len(mesh.faces), dtype=np.int32)
    slots = table(p)["slots"]
    indices = (
        mesh.face_mats if mesh.face_mats is not None else np.zeros(len(mesh.faces), dtype=np.int32)
    )
    if len(indices) and (indices.min() < 0 or indices.max() >= len(slots)):
        raise ValueError("Evaluated face references a missing material slot")
    materials = [
        scene.material(p)
        if s["parameters"] is None
        else pbr.Material(**parameters(s["parameters"]))
        for s in slots
    ]
    for slot, surface in zip(slots, materials):
        if "color_graph" in slot:
            color = material_graph.evaluate(slot["color_graph"])
            if color is not None:
                surface.base_color = tuple(color)
        if "albedo_image" in slot:
            surface.albedo_map = material_image.pixels(slot["albedo_image"])
            surface.albedo_sampling = "closest_repeat"
    return materials, indices


def _publish(p, slots, doc=None):
    _validate(slots)
    doc = _source(p) if doc is None else doc
    if any(f["material"] >= len(slots["slots"]) for f in doc["faces"]):
        raise ValueError("Source face references a missing material slot")
    candidate = deepcopy(p)
    candidate.props["materials3d"] = slots
    mesh = topology.compile(doc)[0]
    evaluated = mesh_edit.evaluate_mesh(mesh, candidate)
    if (
        evaluated.face_mats is not None
        and len(evaluated.face_mats)
        and evaluated.face_mats.max() >= len(slots["slots"])
    ):
        raise ValueError("Evaluated face references a missing material slot")
    if doc != _source(p):
        mesh_document.bind(p, mesh, label=getattr(p, "name", "Mesh"))
    p.props["materials3d"] = deepcopy(slots)
    return read(p)


def add(p, name="Material", values=None):
    slots = table(p)
    if len(slots["slots"]) >= MAX_SLOTS:
        raise ValueError("Material authoring supports at most 64 slots")
    identity = f"m{slots['next_id']}"
    slots["next_id"] += 1
    slots["slots"].append(
        {
            "id": identity,
            "name": _name(name),
            "parameters": parameters({} if values is None else values),
        }
    )
    return {**_publish(p, slots), "slot_id": identity}


def _slot(slots, identity):
    matches = [(i, s) for i, s in enumerate(slots["slots"]) if s["id"] == identity]
    if not matches:
        raise ValueError("Material slot no longer exists")
    return matches[0]


def update(p, slot_id, *, name=None, values=None):
    slots = table(p)
    _, slot = _slot(slots, slot_id)
    if name is not None:
        slot["name"] = _name(name)
    if values is not None:
        if not isinstance(values, dict):
            raise ValueError("Material surface parameters require an object")
        slot["parameters"] = parameters({**resolved_parameters(p, slot), **values})
    return _publish(p, slots)


def assign(p, face_ids, slot_id):
    slots = table(p)
    index, _ = _slot(slots, slot_id)
    if (
        not isinstance(face_ids, list)
        or not face_ids
        or any(not isinstance(i, str) for i in face_ids)
        or len(set(face_ids)) != len(face_ids)
    ):
        raise ValueError("Select distinct current source faces")
    doc = _source(p)
    for face in topology._selected(doc, face_ids):
        face["material"] = index
    return _publish(p, slots, doc)


def remove(p, slot_id):
    slots = table(p)
    index, _ = _slot(slots, slot_id)
    doc = _source(p)
    if len(slots["slots"]) == 1:
        raise ValueError("Keep at least one material slot")
    if any(f["material"] == index for f in doc["faces"]):
        raise ValueError("Assign this slot’s faces to another material before removing it")
    slots["slots"].pop(index)
    for face in doc["faces"]:
        if face["material"] > index:
            face["material"] -= 1
    return _publish(p, slots, doc)


def render_object(p, *, legacy_flap=False):
    """Build the same evaluated surfaces for an individual Layout preview."""
    from dataclasses import replace

    mesh = mesh_edit.evaluate(p)
    if legacy_flap and getattr(p, "mesh_flap", 0):
        from .designer_preview import _flap_imported_parts

        mesh = _flap_imported_parts(mesh, p.mesh_flap)
    materials, indices = render_materials(p, mesh)
    return pbr.MeshObject(replace(mesh, face_mats=indices), materials)


def preview_key(p):
    """Include inherited surface changes as well as explicit slot edits."""
    import json

    from . import scene

    if "materials3d" not in getattr(p, "props", {}):
        return None
    return (
        json.dumps(signature(p), sort_keys=True),
        repr(scene.material(p)),
        repr(p.props.get("modifiers3d")),
        repr(p.props.get("taper3d")),
    )


def set_image(p, slot_id, path):
    """Own a decoded image in the project; empty path clears this slot's override."""
    slots = table(p)
    _, slot = _slot(slots, slot_id)
    if not isinstance(path, str):
        raise ValueError("Material image path must be text")  # noqa: TRY004
    if path.strip():
        slot["albedo_image"] = material_image.import_image(path)
    else:
        slot.pop("albedo_image", None)
    return _publish(p, slots)


def signature(p):
    """Avoid serializing embedded image bytes on every viewport frame."""
    value = deepcopy(getattr(p, "props", {}).get("materials3d"))
    if isinstance(value, dict) and isinstance(value.get("slots"), list):
        for slot in value["slots"]:
            if isinstance(slot, dict) and isinstance(slot.get("albedo_image"), dict):
                image = slot["albedo_image"]
                if isinstance(image.get("png_base64"), str):
                    image["png_base64"] = hash(image["png_base64"])
    return value


def graph_read(p, slot_id):
    slots = table(p)
    _, slot = _slot(slots, slot_id)
    graph = deepcopy(slot.get("color_graph", material_graph.empty()))
    return {"graph": graph, "base_color": material_graph.evaluate(graph)}


def graph_set(p, slot_id, graph):
    material_graph.evaluate(graph)
    slots = table(p)
    _, slot = _slot(slots, slot_id)
    slot["color_graph"] = deepcopy(graph)
    return _publish(p, slots)
