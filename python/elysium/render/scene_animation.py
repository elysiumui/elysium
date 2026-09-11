"""Persistent object transform keys, evaluated before the parent hierarchy.

Legacy complete-transform keys remain valid. Optional channel membership and
per-channel interpolation let the UI edit one axis without keying other axes.
"""
import math
from copy import deepcopy
from . import scene, animation_curve

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
        if not isinstance(key, dict) or not {"frame", "transform"} <= set(key) or set(key) - {"frame", "transform", "channels", "interpolation", "handles"}:
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
        if not isinstance(modes, dict) or any(c not in channels or mode not in ("LINEAR", "CONSTANT", "BEZIER") for c, mode in modes.items()):
            raise ValueError("Interpolation must be Linear, Constant or Bezier for a keyed channel")
        animation_curve.validate(key.get("handles", {}), channels)
        probe = deepcopy(placement)
        probe.props["transform3d"] = key["transform"]
        scene.transform(probe)
        for channel,pair in key.get('handles',{}).items():
            group,axis=channel.split('.');value=key['transform'][group]['xyz'.index(axis)]
            if any(not math.isfinite(value+offset[1]) for offset in pair.values()):
                raise ValueError('Curve handle values must remain finite')
        frames.append(frame)
    if frames != sorted(set(frames)):
        raise ValueError("3D keys must have unique ascending frames")
    for channel in ('scale.x','scale.y','scale.z'):
        chosen=[k for k in keys if channel in key_channels(k)]
        for left,right in zip(chosen,chosen[1:]):
            if interpolation(left,channel)!='BEZIER':continue
            i='xyz'.index(channel[-1])
            low,high=animation_curve.value_range(left['transform']['scale'][i],right['transform']['scale'][i],
                animation_curve.handles(chosen,left['frame'],channel)['right'],
                animation_curve.handles(chosen,right['frame'],channel)['left'],right['frame']-left['frame'])
            if low<1e-8 and high>-1e-8:raise ValueError('Scale curve must stay nonzero between keys; adjust its handles')
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
            if "handles" in source:source["handles"]={c:h for c,h in source["handles"].items() if c in remaining}
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
            for c in chosen:
                if c in original.get("handles", {}):destination.setdefault("handles", {})[c]=deepcopy(original["handles"][c])
        if mode is not None:
            destination.setdefault("interpolation", {}).update({c:mode for c in chosen})
    _commit(placement, keys)
    return tracks(placement)


def edit_keys(placement, selection, *, offset=0, duplicate=False, delete=False, mode=None):
    """Edit explicit (frame, channel) pairs as one transaction.

    A move vacates all selected sources before checking destinations, so adjacent
    selected keys can move together. Copies retain sources and reject collisions.
    Non-selected channels, values and interpolation are retained exactly.
    """
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise ValueError('Frame offset must be an integer')
    if not isinstance(duplicate, bool) or not isinstance(delete, bool):
        raise ValueError('Duplicate and delete must be on or off')
    if delete and (duplicate or offset or mode is not None):
        raise ValueError('Delete cannot be combined with other key edits')
    if duplicate and offset == 0:
        raise ValueError('Choose a nonzero frame offset for duplicate keys')
    if mode is not None and mode not in ('LINEAR', 'CONSTANT', 'BEZIER'):
        raise ValueError('Interpolation must be Linear, Constant or Bezier')
    if not isinstance(selection, (list, tuple)) or not selection:
        raise ValueError('Select at least one key')
    selected = set()
    for item in selection:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError('Each key selection must contain a frame and channel')
        frame, channel = item
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame <= 360000 or channel not in CHANNELS:
            raise ValueError('Select a valid key frame and transform channel')
        if (frame, channel) in selected:
            raise ValueError('Key selection must be unique')
        selected.add((frame, channel))
    keys = tracks(placement)
    by_frame = {key['frame']: key for key in keys}
    for frame, channel in selected:
        if frame not in by_frame or channel not in key_channels(by_frame[frame]):
            raise ValueError(f'Selected key no longer exists: frame {frame}, {channel}')
        if not delete and not 0 <= frame + offset <= 360000:
            raise ValueError('Every destination frame must be between 0 and 360000')
    originals = deepcopy(by_frame)
    if delete or (offset and not duplicate):
        for frame in {f for f, _ in selected}:
            key = by_frame[frame]
            remaining = [c for c in key_channels(key) if (frame, c) not in selected]
            if remaining:
                key['channels'] = remaining
                key['interpolation'] = {c: m for c, m in key.get('interpolation', {}).items() if c in remaining}
                if 'handles' in key:key['handles']={c:h for c,h in key['handles'].items() if c in remaining}
            else:
                del by_frame[frame]
    if not delete:
        for frame, channel in sorted(selected):
            target = frame + offset
            destination = by_frame.get(target)
            if offset and destination is not None and channel in key_channels(destination):
                raise ValueError(f'Destination already has a key: frame {target}, {channel}')
            original = originals[frame]
            if destination is None:
                destination = {'frame': target, 'transform': deepcopy(original['transform']), 'channels': []}
                by_frame[target] = destination
            if offset:
                group, axis = channel.split('.')
                destination['transform'][group]['xyz'.index(axis)] = original['transform'][group]['xyz'.index(axis)]
                destination['channels'] = [c for c in CHANNELS if c in set(key_channels(destination)) | {channel}]
                # Explicit default interpolation is unnecessary; retain authored metadata.
                if channel in original.get('interpolation', {}):
                    destination.setdefault('interpolation', {})[channel] = original['interpolation'][channel]
                if channel in original.get('handles', {}):
                    destination.setdefault('handles', {})[channel]=deepcopy(original['handles'][channel])
            if mode is not None:
                destination.setdefault('interpolation', {})[channel] = mode
    _commit(placement, list(by_frame.values()))
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
            group,axis=channel.split('.')
            values[group]['xyz'.index(axis)]=channel_value(channel_keys,channel,frame)
        scene.update(p, values)
    return output


def seek(designer, frame):
    evaluated = pose(designer.placements, frame)
    for p, evaluated_p in zip(designer.placements, evaluated):
        if p.kind in ("Mesh3D", "SceneGroup"):
            scene.update(p, scene.transform(evaluated_p))
    designer.window_doc.scene_frame = frame
    return frame


def set_handles(placement,frame,channel,left,right):
    if isinstance(frame,bool) or not isinstance(frame,int) or not 0<=frame<=360000:
        raise ValueError('Key frame must be an integer between 0 and 360000')
    keys=tracks(placement)
    key=next((k for k in keys if k['frame']==frame and channel in key_channels(k)),None)
    if key is None:raise ValueError('Select an existing key for curve handles')
    key.setdefault('handles',{})[channel]={'left':deepcopy(left),'right':deepcopy(right)}
    key.setdefault('interpolation',{})[channel]='BEZIER'
    _commit(placement,keys)
    return tracks(placement)


def channel_value(keys,channel,frame):
    """Evaluate an already validated, nonempty single-channel track."""
    left=next((k for k in reversed(keys) if k['frame']<=frame),keys[0])
    right=next((k for k in keys if k['frame']>=frame),keys[-1])
    group,axis=channel.split('.');i='xyz'.index(axis)
    a,b=left['transform'][group][i],right['transform'][group][i]
    if left['frame']==right['frame'] or interpolation(left,channel)=='CONSTANT':return a
    if interpolation(left,channel)=='BEZIER':
        return animation_curve.evaluate(frame,left['frame'],right['frame'],a,b,
            animation_curve.handles(keys,left['frame'],channel)['right'],
            animation_curve.handles(keys,right['frame'],channel)['left'])
    t=(frame-left['frame'])/(right['frame']-left['frame'])
    return a+(b-a)*t


def edit_object_keys(placements,selection,*,offset=0,duplicate=False,delete=False,mode=None):
    """Edit explicit (entity ID, frame, channel) keys as one scene transaction."""
    if not isinstance(selection,(list,tuple)) or not selection:
        raise ValueError('Select at least one object key')
    grouped={};seen=set()
    for item in selection:
        if not isinstance(item,(list,tuple)) or len(item)!=3:
            raise ValueError('Object keys require an identity, frame and channel')
        identity,frame,channel=item
        if not isinstance(identity,str) or not identity or isinstance(frame,bool) or not isinstance(frame,int) or not isinstance(channel,str):
            raise ValueError('Object keys require a string identity, integer frame and channel')
        key=(identity,frame,channel)
        if key in seen:raise ValueError('Select each object key only once')
        seen.add(key);grouped.setdefault(identity,[]).append((frame,channel))
    changes=[];result={}
    for identity,keys in grouped.items():
        matches=[p for p in placements if getattr(p,'entity_id',None)==identity]
        if len(matches)!=1:raise ValueError('Selected object no longer exists or has an ambiguous identity: '+identity)
        p=matches[0]
        if p.kind not in ('Mesh3D','SceneGroup') or p.props.get('selection_locked'):
            raise ValueError('Selected object keys require unlocked meshes or groups')
        candidate=deepcopy(p)
        result[identity]=edit_keys(candidate,keys,offset=offset,duplicate=duplicate,delete=delete,mode=mode)
        changes.append((p,candidate))
    # A collision on the last object cannot leave earlier objects edited.
    for p,candidate in changes:p.props['keys3d']=deepcopy(candidate.props['keys3d'])
    return result
