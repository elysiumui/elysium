"""Native mesh deformations shared by numeric GUI fields and public tools."""

from copy import deepcopy

import numpy as np

from . import mesh_document

TAPER_DEFAULT = {"axis": "z", "start": [1.0, 1.0, 1.0], "end": [1.0, 1.0, 1.0]}


def taper_settings(placement):
    raw = placement.props.get("taper3d", {})
    if not isinstance(raw, dict) or set(raw) - set(TAPER_DEFAULT):
        raise ValueError("Unknown taper fields")
    result = {**deepcopy(TAPER_DEFAULT), **deepcopy(raw)}
    if result["axis"] not in ("x", "y", "z"):
        raise ValueError("Taper axis must be x, y or z")
    for field in ("start", "end"):
        v = result[field]
        if (
            not isinstance(v, (list, tuple))
            or len(v) != 3
            or any(
                isinstance(x, bool)
                or not isinstance(x, (float, int))
                or not np.isfinite(x)
                or x <= 0
                or x > 1e4
                for x in v
            )
        ):
            raise ValueError("Taper factors require three positive finite numbers")
    return result


def taper_set(placement, values):
    if placement.kind != "Mesh3D":
        raise ValueError("Taper requires a mesh object")
    candidate = deepcopy(placement)
    candidate.props["taper3d"] = {**taper_settings(placement), **values}
    checked = taper_settings(candidate)
    placement.props["taper3d"] = checked
    return deepcopy(checked)


def evaluate(placement):
    source = mesh_document.resolve(placement.mesh_kind)
    if "taper3d" not in placement.props:
        return source
    settings = taper_settings(placement)
    axis = "xyz".index(settings["axis"])
    verts = source.verts.copy()
    along = verts[:, axis]
    span = float(np.ptp(along))
    if span <= 1e-8:
        raise ValueError("Taper needs nonzero extent along its axis")
    t = ((along - along.min()) / span)[:, None]
    factors = np.array(settings["start"]) * (1 - t) + np.array(settings["end"]) * t
    factors[:, axis] = 1.0
    verts *= factors
    return mesh_document.with_vertices(source, verts)
