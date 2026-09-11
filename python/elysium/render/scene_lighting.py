"""Persistent scene lights and deterministic direct-light integration.

Y-up meters; local -Y is the emission direction for sun/area lights.
Point power is total isotropic flux. Square area power is total forward
hemisphere flux. Sun strength is irradiance normal to its direction.
"""

from copy import deepcopy
import math

import numpy as np

DEFAULT_LIGHT = {
    "name": "Light", "type": "sun", "enabled": True,
    "position": [0.0, 3.0, 0.0], "rotation": [0.0, 0.0, 0.0],
    "color": [1.0, 1.0, 1.0], "power": 3.0, "size": 2.0,
}


def light(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULT_LIGHT):
        raise ValueError("Unknown light fields")
    result = {**deepcopy(DEFAULT_LIGHT), **deepcopy(values)}
    if result["type"] not in ("sun", "point", "area"):
        raise ValueError("Light type must be sun, point or area")
    if type(result["enabled"]) is not bool:
        raise ValueError("Light enabled must be boolean")
    if not isinstance(result["name"], str) or not 1 <= len(result["name"].strip()) <= 100:
        raise ValueError("Light name requires 1–100 characters")
    result["name"] = result["name"].strip()
    for key in ("position", "rotation", "color"):
        v = result[key]
        if not isinstance(v, (list, tuple)) or len(v) != 3:
            raise ValueError(f"Light {key} requires three numbers")
        if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e6 for x in v):
            raise ValueError(f"Light {key} requires finite numbers within ±1000000")
        if key == "color" and any(not 0 <= x <= 1 for x in v):
            raise ValueError("Light color requires linear RGB from 0 to 1")
        result[key] = list(v)
    for key in ("power", "size"):
        x = result[key]
        if type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1e6:
            raise ValueError(f"Light {key} must be finite from 0 to 1000000")
    if result["size"] <= 0:
        raise ValueError("Area size must be positive")
    return result


def settings(values=None):
    if values is None or values == {}:
        return {"schema_version": 1, "enabled": False, "next_id": 1,
                "ambient": [0.0, 0.0, 0.0], "lights": []}
    if not isinstance(values, dict) or set(values) != {"schema_version", "enabled", "next_id", "ambient", "lights"}:
        raise ValueError("Invalid scene lighting fields")
    if type(values["schema_version"]) is not int or values["schema_version"] != 1 or type(values["enabled"]) is not bool:
        raise ValueError("Invalid scene lighting version or enabled flag")
    if type(values["next_id"]) is not int or values["next_id"] < 1:
        raise ValueError("Invalid light identity counter")
    if not isinstance(values["lights"], list) or len(values["lights"]) > 32:
        raise ValueError("A scene supports at most 32 lights")
    result = deepcopy(values)
    result["ambient"] = light({"color": values["ambient"]})["color"]
    seen = set()
    for item in result["lights"]:
        if not isinstance(item, dict) or set(item) != {"id", *DEFAULT_LIGHT}:
            raise ValueError("Invalid light entry")
        identity = item["id"]
        if not isinstance(identity, str) or not identity.startswith("l") or not identity[1:].isascii() or not identity[1:].isdigit() or identity[1:].startswith("0") or not 0 < int(identity[1:]) < values["next_id"] or identity in seen:
            raise ValueError("Invalid or duplicate light identity")
        seen.add(identity)
        item.update(light({k: item[k] for k in DEFAULT_LIGHT}))
    return result


def read(window):
    return settings(getattr(window, "scene_lighting", None))


def add(window, values=None):
    checked = light({} if values is None else values)
    state = read(window)
    identity = f"l{state['next_id']}"
    state["next_id"] += 1
    state["enabled"] = True
    state["lights"].append({"id": identity, **checked})
    window.scene_lighting = settings(state)
    return {"light_id": identity, "lighting": read(window)}


def update(window, identity, values=None, *, remove=False):
    state = read(window)
    index = next((i for i, v in enumerate(state["lights"]) if v["id"] == identity), None)
    if index is None:
        raise ValueError("Light no longer exists")
    if remove:
        state["lights"].pop(index)
    else:
        if not isinstance(values, dict):
            raise ValueError("Light values must be an object")
        old = state["lights"][index]
        state["lights"][index] = {"id": identity, **light({**{k: old[k] for k in DEFAULT_LIGHT}, **values})}
    window.scene_lighting = settings(state)
    return read(window)


def configure(window, *, enabled=None, ambient=None):
    state = read(window)
    if enabled is not None:
        state["enabled"] = enabled
    if ambient is not None:
        state["ambient"] = ambient
    window.scene_lighting = settings(state)
    return read(window)


def environment(values=None, studio="Default Soft Studio"):
    from . import pbr
    state = settings(values)
    if not state["enabled"]:
        return pbr.to_environment(pbr.STUDIOS.get(studio, pbr.STUDIOS["Default Soft Studio"]))
    return pbr.Environment(zenith=tuple(state["ambient"]), horizon=tuple(state["ambient"]),
                           ground=tuple(state["ambient"]), sun_color=(0, 0, 0),
                           fill_color=(0, 0, 0), authored_lights=state["lights"])


def samples(item, points):
    """Yield direction, incident radiance weight and finite emitter distance.

    Square area integration uses a fixed 4×4 midpoint quadrature. This is
    deterministic preview integration, not a converged soft-shadow claim.
    """
    from . import pbr
    rotation = pbr._euler_rot(*np.radians(item["rotation"])).astype(float)
    color = np.asarray(item["color"]) * item["power"]
    if item["type"] == "sun":
        yield np.broadcast_to(rotation[:, 1], points.shape), np.broadcast_to(color, points.shape), np.full(len(points), np.inf)
        return
    if item["type"] == "point":
        emitters = [(np.asarray(item["position"]), color / (4 * math.pi))]
    else:
        emitters = [(np.asarray(item["position"]) + rotation @ np.array([x, 0, z]) * item["size"], color / (16 * math.pi))
                    for x in (-.375, -.125, .125, .375) for z in (-.375, -.125, .125, .375)]
    for position, weight in emitters:
        delta = position - points
        distance = np.linalg.norm(delta, axis=1)
        direction = delta / np.maximum(distance[:, None], 1e-8)
        incident = np.broadcast_to(weight, points.shape).copy() / np.maximum(distance[:, None] ** 2, 1e-12)
        if item["type"] == "area":
            incident *= np.maximum(direction @ rotation[:, 1], 0)[:, None]
        yield direction, incident, distance


def direct(env, points, normals, view, mat, overrides, obj, vertices, bvh):
    from . import pbr
    output = np.zeros_like(points)
    extent = np.max(np.ptp(vertices, axis=0)) if len(vertices) else 1
    epsilon = max(1e-6, float(extent) * 1e-6)
    for item in env.authored_lights or []:
        if not item["enabled"] or item["power"] == 0:
            continue
        for direction, incident, distance in samples(item, points):
            t, faces, _, _ = pbr._intersect_rays_mesh(points + normals * epsilon, direction, vertices, obj.mesh.faces, bvh)
            visible = (faces < 0) | (t >= distance - 2 * epsilon)
            output += pbr._shade_pixels(normals, view, direction, incident * visible[:, None], mat, overrides)
    return output
