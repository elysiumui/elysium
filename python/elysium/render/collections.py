"""Persistent scene collections: named, nestable object groups with visibility.

Collections live on ``AppWindow.scene_collections`` and reference objects by
scene entity identity, never by name or list index. Membership is exclusive
(an object belongs to at most one collection). A collection that is hidden
(``visible`` false) or excluded (``exclude`` true), or that has such an
ancestor, removes its members from every composed render while their
transforms keep driving visible children. Every mutation validates a complete
candidate table before writing the window.
"""

from copy import deepcopy

from .. import scene_identity

MAX_COLLECTIONS = 256
UNSET = object()


def _empty():
    return {"schema_version": 1, "next_id": 1, "items": []}


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
        raise ValueError("Collection name requires 1–100 nonblank characters")
    return value.strip()


def settings(values=None):
    if values is None or values == {}:
        return _empty()
    if not isinstance(values, dict) or set(values) != {"schema_version", "next_id", "items"}:
        raise ValueError("Invalid scene collection fields")
    if type(values["schema_version"]) is not int or values["schema_version"] != 1:
        raise ValueError("Unsupported scene collection version")
    if type(values["next_id"]) is not int or values["next_id"] < 1:
        raise ValueError("Invalid collection identity counter")
    if not isinstance(values["items"], list) or len(values["items"]) > MAX_COLLECTIONS:
        raise ValueError(f"A scene supports at most {MAX_COLLECTIONS} collections")
    result = deepcopy(values)
    seen, names, members = set(), set(), set()
    for item in result["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "name", "parent", "members", "visible", "exclude"}:
            raise ValueError("Invalid collection entry")
        identity = item["id"]
        digits = identity[3:] if isinstance(identity, str) and identity.startswith("col") else ""
        if (not digits.isascii() or not digits.isdigit() or digits.startswith("0")
                or not 0 < int(digits) < values["next_id"] or identity in seen):
            raise ValueError("Invalid or duplicate collection identity")
        seen.add(identity)
        item["name"] = _name(item["name"])
        if item["name"].casefold() in names:
            raise ValueError("Collection names must be unique")
        names.add(item["name"].casefold())
        for flag in ("visible", "exclude"):
            if type(item[flag]) is not bool:
                raise ValueError(f"Collection {flag} must be boolean")
        if not isinstance(item["members"], list) or len(set(item["members"])) != len(item["members"]):
            raise ValueError("Collection members must be distinct scene identities")
        for member in item["members"]:
            if not isinstance(member, str):
                raise ValueError("Collection members must be scene identities")
            scene_identity.parse(member)
            if member in members:
                raise ValueError("An object belongs to at most one collection")
            members.add(member)
    parents = {item["id"]: item["parent"] for item in result["items"]}
    for identity, parent in parents.items():
        if parent is not None and (not isinstance(parent, str) or parent not in parents or parent == identity):
            raise ValueError("Collection parent must be another existing collection")
        seen_chain = {identity}
        while parent is not None:
            if parent in seen_chain:
                raise ValueError("Collection nesting would create a cycle")
            seen_chain.add(parent)
            parent = parents[parent]
    return result


def read(window):
    return settings(getattr(window, "scene_collections", None))


def _write(window, candidate):
    window.scene_collections = settings(candidate)
    return read(window)


def _item(state, identity):
    match = next((item for item in state["items"] if item["id"] == identity), None)
    if match is None:
        raise ValueError("Collection no longer exists")
    return match


def create(window, name, parent=None):
    state = read(window)
    if parent is not None:
        _item(state, parent)
    identity = f"col{state['next_id']}"
    state["next_id"] += 1
    state["items"].append({"id": identity, "name": _name(name), "parent": parent, "members": [],
                           "visible": True, "exclude": False})
    return {"collection_id": identity, "collections": _write(window, state)}


def remove(window, identity):
    """Children re-parent to the removed collection's parent; members unassign."""
    state = read(window)
    removed = _item(state, identity)
    state["items"] = [item for item in state["items"] if item["id"] != identity]
    for item in state["items"]:
        if item["parent"] == identity:
            item["parent"] = removed["parent"]
    return _write(window, state)


def _entity_ids(placements):
    return {getattr(p, "entity_id", None) for p in placements} - {None}


def assign(window, placements, entity_ids, identity):
    """Move objects into a collection (identity None unassigns them)."""
    if not isinstance(entity_ids, (list, tuple)) or not entity_ids or len(set(entity_ids)) != len(entity_ids):
        raise ValueError("Select distinct objects to assign")
    known = _entity_ids(placements)
    unknown = [e for e in entity_ids if e not in known]
    if unknown:
        raise ValueError(f"Unknown scene object: {unknown[0]}")
    state = read(window)
    target = None if identity is None else _item(state, identity)
    for item in state["items"]:
        item["members"] = [m for m in item["members"] if m not in entity_ids]
    if target is not None:
        target["members"].extend(entity_ids)
    return _write(window, state)


def update(window, identity, *, name=None, parent=UNSET, visible=None, exclude=None):
    state = read(window)
    item = _item(state, identity)
    if name is not None:
        item["name"] = _name(name)
    if parent is not UNSET:
        if parent is not None:
            _item(state, parent)
        item["parent"] = parent
    if visible is not None:
        item["visible"] = visible
    if exclude is not None:
        item["exclude"] = exclude
    return _write(window, state)


def collection_of(window, entity_id):
    for item in read(window)["items"]:
        if entity_id in item["members"]:
            return item["id"]
    return None


def excluded_entities(window, placements):
    """Members of hidden/excluded collections or of their descendants."""
    state = read(window)
    parents = {item["id"]: item["parent"] for item in state["items"]}
    hidden = {item["id"] for item in state["items"] if not item["visible"] or item["exclude"]}

    def blocked(identity):
        while identity is not None:
            if identity in hidden:
                return True
            identity = parents[identity]
        return False

    known = _entity_ids(placements)
    return {m for item in state["items"] if blocked(item["id"]) for m in item["members"] if m in known}


def prune(window, placements):
    """Drop member identities that no longer exist; returns the dropped ids."""
    state = read(window)
    known = _entity_ids(placements)
    dropped = []
    for item in state["items"]:
        keep = [m for m in item["members"] if m in known]
        dropped.extend(m for m in item["members"] if m not in known)
        item["members"] = keep
    if dropped:
        _write(window, state)
    return dropped
