"""Persistent object transform keys, evaluated before the parent hierarchy.

Legacy complete-transform keys remain valid. Optional channel membership and
per-channel interpolation let the UI edit one axis without keying other axes.
"""
import math
from copy import deepcopy
from . import scene

FPS = 60
CHANNELS = tuple(f"{group}.{axis}" for group in scene.DEFAULT for axis in "xyz")
DEFAULT_SETTINGS = {"start": 0, "end": 144, "fps": 60, "loop": True, "flight_seconds": 3.0}


def settings(value=None):
    if value is not None and not isinstance(value, dict):
        raise ValueError("Animation settings must be an object")
    data = {**DEFAULT_SETTINGS, **(value or {})}
    if set(data) != set(DEFAULT_SETTINGS):
        raise ValueError("Unknown animation settings")
    for name in ("start", "end", "fps"):
        if isinstance(data[name], bool) or not isinstance(data[name], int):
            raise ValueError(f"Animation {name} must be an integer")
    if not 0 <= data["start"] <= data["end"] <= 360000:
        raise ValueError("Animation range must satisfy 0 ≤ start ≤ end ≤ 360000")
    if not 1 <= data["fps"] <= 240:
        raise ValueError("Frame rate must be between 1 and 240 fps")
    if not isinstance(data["loop"], bool):
        raise ValueError("Loop must be on or off")
    duration = data["flight_seconds"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not .1 <= duration <= 3600:
        raise ValueError("Desktop flight duration must be between 0.1 and 3600 seconds")
    return data


def key_channels(key):
    return tuple(key.get("channels", CHANNELS))


def interpolation(key, channel):
    return key.get("interpolation", {}).get(channel, "LINEAR")


def tracks(placement):
    keys = placement.props.get("keys3d", [])
    if not isinstance(keys, list):
        raise TypeError("3D keys must be a list")
    frames = []
    for key in keys:
        if not isinstance(key, dict) or not {"frame", "transform"} <= set(key) or set(key) - {"frame", "transform", "channels", "interpolation"}:
            raise ValueError("Invalid 3D key fields")
        if not isinstance(key["transform"], dict) or set(key["transform"]) != set(scene.DEFAULT):
            raise ValueError("3D keys require a complete transform")
        frame = key["frame"]
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame <= 360000:
            raise ValueError("Key frame must be an integer between 0 and 360000")
        channels = key.get("channels", list(CHANNELS))
        if not isinstance(channels, list) or not channels or any(c not in CHANNELS for c in channels) or len(channels) != len(set(channels)):
            raise ValueError("Key channels must be unique transform axes")
        modes = key.get("interpolation", {})
        if not isinstance(modes, dict) or any(c not in channels or mode not in ("LINEAR", "CONSTANT") for c, mode in modes.items()):
            raise ValueError("Interpolation must be Linear or Constant for a keyed channel")
        probe = deepcopy(placement)
        probe.props["transform3d"] = key["transform"]
        scene.transform(probe)
        frames.append(frame)
    if frames != sorted(set(frames)):
        raise ValueError("3D keys must have unique ascending frames")
    return deepcopy(keys)


def _channel_list(channels):
    channels = list(CHANNELS if channels is None else channels)
    if not channels or any(c not in CHANNELS for c in channels) or len(set(channels)) != len(channels):
        raise ValueError("Choose one or more unique transform channels")
    return channels


def _commit(placement, keys):
    candidate = deepcopy(placement)
    candidate.props["keys3d"] = sorted(keys, key=lambda key: key["frame"])
    placement.props["keys3d"] = tracks(candidate)


def set_key(placement, frame, transform=None, *, channels=None, mode=None):
    chosen = _channel_list(channels)
    keys = tracks(placement)
    values = scene.transform(placement)
    if transform is not None:
        probe = deepcopy(placement)
        scene.update(probe, transform)
        values = scene.transform(probe)
    key = next((key for key in keys if key["frame"] == frame), None)
    if key is None:
        key = {"frame": frame, "transform": values, "channels": chosen}
        keys.append(key)
    else:
        for channel in chosen:
            group, axis = channel.split(".")
            index = "xyz".index(axis)
            key["transform"][group][index] = values[group][index]
        key["channels"] = [c for c in CHANNELS if c in set(key_channels(key)) | set(chosen)]
    if mode is not None:
        key.setdefault("interpolation", {}).update({c: mode for c in chosen})
    if key.get("channels") == list(CHANNELS):
        key.pop("channels", None)
    _commit(placement, keys)
    return deepcopy(key)


def edit_key(placement, source_frame, *, channels=None, target_frame=None, duplicate=False, delete=False, mode=None):
    """Atomically move/copy/delete/change interpolation for selected key axes.

Collision with another key on the same channel is rejected. Other channels at
both frames are retained. An empty source key is removed after a move/delete.
"""
    for value in (source_frame, target_frame):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 360000):
            raise ValueError("Key frame must be an integer between 0 and 360000")
    if duplicate and target_frame in (None, source_frame):
        raise ValueError("Choose another frame for the duplicate key")
    chosen = _channel_list(channels)
    keys = tracks(placement)
    source = next((key for key in keys if key["frame"] == source_frame), None)
    if source is None or not set(chosen) <= set(key_channels(source)):
        raise ValueError("The selected channels have no key at this frame")
    original = deepcopy(source)
    if delete or (target_frame is not None and target_frame != source_frame and not duplicate):
        remaining = [c for c in key_channels(source) if c not in chosen]
        if remaining:
            source["channels"] = remaining
            source["interpolation"] = {c:m for c,m in source.get("interpolation", {}).items() if c in remaining}
        else:
            keys.remove(source)
    if not delete:
        target_frame = source_frame if target_frame is None else target_frame
        destination = next((key for key in keys if key["frame"] == target_frame), None)
        if target_frame != source_frame:
            if destination is not None and set(chosen) & set(key_channels(destination)):
                raise ValueError("Destination already has a key on the selected channel")
            if destination is None:
                destination = {"frame": target_frame, "transform": deepcopy(original["transform"]), "channels": []}
                keys.append(destination)
            for c in chosen:
                group, axis = c.split(".")
                i = "xyz".index(axis)
                destination["transform"][group][i] = original["transform"][group][i]
            destination["channels"] = [c for c in CHANNELS if c in set(key_channels(destination)) | set(chosen)]
            destination.setdefault("interpolation", {}).update({c:interpolation(original,c) for c in chosen})
        if mode is not None:
            destination.setdefault("interpolation", {}).update({c:mode for c in chosen})
    _commit(placement, keys)
    return tracks(placement)


def pose(placements, frame):
    if isinstance(frame, bool) or not isinstance(frame, (int, float)) or not math.isfinite(frame) or frame < 0:
        raise ValueError("Frame must be nonnegative and finite")
    output = deepcopy(placements)
    for p in output:
        keys = tracks(p)
        if not keys:
            continue
        values = scene.transform(p)
        for channel in CHANNELS:
            channel_keys = [key for key in keys if channel in key_channels(key)]
            if not channel_keys:
                continue
            left = next((k for k in reversed(channel_keys) if k["frame"] <= frame), channel_keys[0])
            right = next((k for k in channel_keys if k["frame"] >= frame), channel_keys[-1])
            t = 0.0 if left["frame"] == right["frame"] or interpolation(left,channel) == "CONSTANT" else (frame-left["frame"])/(right["frame"]-left["frame"])
            group, axis = channel.split(".")
            i = "xyz".index(axis)
            a, b = left["transform"][group][i], right["transform"][group][i]
            values[group][i] = a + (b-a)*t
        scene.update(p, values)
    return output


def seek(designer, frame):
    evaluated = pose(designer.placements, frame)
    for p, evaluated_p in zip(designer.placements, evaluated):
        if p.kind in ("Mesh3D", "SceneGroup"):
            scene.update(p, scene.transform(evaluated_p))
    designer.window_doc.scene_frame = frame
    return frame
