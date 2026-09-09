"""Persistent 60-fps transform keys evaluated before the parent hierarchy."""

import math
from copy import deepcopy

from . import scene

FPS = 60


def tracks(placement):
    keys = placement.props.get("keys3d", [])
    if not isinstance(keys, list):
        raise TypeError("3D keys must be a list")
    frames = []
    for key in keys:
        if not isinstance(key, dict) or set(key) != {"frame", "transform"}:
            raise ValueError("Invalid 3D key fields")
        if not isinstance(key["transform"], dict) or set(key["transform"]) != set(scene.DEFAULT):
            raise ValueError("3D keys require a complete transform")
        frame = key["frame"]
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame <= 360000:
            raise ValueError("Key frame must be an integer between 0 and 360000")
        probe = deepcopy(placement)
        probe.props["transform3d"] = key["transform"]
        scene.transform(probe)
        frames.append(frame)
    if frames != sorted(set(frames)):
        raise ValueError("3D keys must have unique ascending frames")
    return deepcopy(keys)


def set_key(placement, frame, transform=None):
    keys = tracks(placement)
    key = {"frame": frame, "transform": scene.transform(placement)}
    if transform is not None:
        probe = deepcopy(placement)
        scene.update(probe, transform)
        key["transform"] = scene.transform(probe)
    candidate = deepcopy(placement)
    candidate.props["keys3d"] = sorted(
        [k for k in keys if k["frame"] != frame] + [key], key=lambda k: k["frame"]
    )
    placement.props["keys3d"] = tracks(candidate)
    return deepcopy(key)


def pose(placements, frame):
    if (
        isinstance(frame, bool)
        or not isinstance(frame, (int, float))
        or not math.isfinite(frame)
        or frame < 0
    ):
        raise ValueError("Frame must be nonnegative and finite")
    output = deepcopy(placements)
    for p in output:
        keys = tracks(p)
        if not keys:
            continue
        left = next((k for k in reversed(keys) if k["frame"] <= frame), keys[0])
        right = next((k for k in keys if k["frame"] >= frame), keys[-1])
        t = (
            0.0
            if left["frame"] == right["frame"]
            else (frame - left["frame"]) / (right["frame"] - left["frame"])
        )
        values = {
            field: [
                a + (b - a) * t for a, b in zip(left["transform"][field], right["transform"][field])
            ]
            for field in scene.DEFAULT
        }
        scene.update(p, values)
    return output


def seek(designer, frame):
    evaluated = pose(designer.placements, frame)
    for p, evaluated_p in zip(designer.placements, evaluated):
        if p.kind in ("Mesh3D", "SceneGroup"):
            scene.update(p, scene.transform(evaluated_p))
    designer.window_doc.scene_frame = frame
    return frame
