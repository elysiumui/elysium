"""Named view presets, camera bookmarks and orthographic reference images.

Presets are the six axis views (orthographic) plus ``perspective``; their
yaw/pitch pairs live in :data:`scene.VIEW_PRESETS` and follow
``pbr.render_mesh``'s orbit camera. Bookmarks persist complete cameras on
``AppWindow.scene_bookmarks``; reference images persist owned PNGs per axis
view on ``AppWindow.scene_references`` and are blended behind the grid only
in that exact axis view.
"""

import math
from copy import deepcopy

from . import material_image, scene

MAX_BOOKMARKS = 64
AXIS_VIEWS = tuple(scene.VIEW_PRESETS)
REFERENCE_DEFAULT = {"opacity": 0.5, "offset": [0.0, 0.0]}


# --- presets --------------------------------------------------------------

def view_preset(current, name):
    """Camera for a named preset, keeping target/distance/ortho_scale."""
    camera = scene.camera(current)
    if name == "perspective":
        camera.update(yaw=scene.CAMERA_DEFAULT["yaw"], pitch=scene.CAMERA_DEFAULT["pitch"],
                      projection="perspective")
    elif name in scene.VIEW_PRESETS:
        yaw, pitch = scene.VIEW_PRESETS[name]
        camera.update(yaw=yaw, pitch=pitch, projection="orthographic")
    else:
        raise ValueError("View must be front, back, left, right, top, bottom or perspective")
    return scene.camera(camera)


def view_name(camera):
    """The axis preset an orthographic camera matches exactly, else None."""
    camera = scene.camera(camera)
    if camera["projection"] != "orthographic":
        return None
    for name, (yaw, pitch) in scene.VIEW_PRESETS.items():
        if (math.isclose(math.cos(camera["yaw"]), math.cos(yaw), abs_tol=1e-9)
                and math.isclose(math.sin(camera["yaw"]), math.sin(yaw), abs_tol=1e-9)
                and math.isclose(camera["pitch"], pitch, abs_tol=1e-9)):
            return name
    return None


# --- bookmarks ------------------------------------------------------------

def _name(value, what):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
        raise ValueError(f"{what} name requires 1–100 nonblank characters")
    return value.strip()


def bookmarks(values=None):
    if values is None or values == {}:
        return {"schema_version": 1, "next_id": 1, "items": []}
    if not isinstance(values, dict) or set(values) != {"schema_version", "next_id", "items"}:
        raise ValueError("Invalid camera bookmark fields")
    if type(values["schema_version"]) is not int or values["schema_version"] != 1:
        raise ValueError("Unsupported camera bookmark version")
    if type(values["next_id"]) is not int or values["next_id"] < 1:
        raise ValueError("Invalid bookmark identity counter")
    if not isinstance(values["items"], list) or len(values["items"]) > MAX_BOOKMARKS:
        raise ValueError(f"A scene supports at most {MAX_BOOKMARKS} camera bookmarks")
    result = deepcopy(values)
    seen, names = set(), set()
    for item in result["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "name", "camera"}:
            raise ValueError("Invalid camera bookmark entry")
        identity = item["id"]
        digits = identity[1:] if isinstance(identity, str) and identity.startswith("b") else ""
        if (not digits.isascii() or not digits.isdigit() or digits.startswith("0")
                or not 0 < int(digits) < values["next_id"] or identity in seen):
            raise ValueError("Invalid or duplicate bookmark identity")
        seen.add(identity)
        item["name"] = _name(item["name"], "Bookmark")
        if item["name"].casefold() in names:
            raise ValueError("Bookmark names must be unique")
        names.add(item["name"].casefold())
        item["camera"] = scene.camera(item["camera"])
    return result


def read_bookmarks(window):
    return bookmarks(getattr(window, "scene_bookmarks", None))


def _bookmark(state, ref):
    match = next((b for b in state["items"] if b["id"] == ref or b["name"].casefold() == str(ref).casefold()), None)
    if match is None:
        raise ValueError("Camera bookmark no longer exists")
    return match


def bookmark_set(window, name, camera=None):
    """Store the current (or given) camera; an existing name is replaced."""
    name = _name(name, "Bookmark")
    checked = scene.camera(getattr(window, "scene_camera", None) if camera is None else camera)
    state = read_bookmarks(window)
    existing = next((b for b in state["items"] if b["name"].casefold() == name.casefold()), None)
    if existing is not None:
        existing.update(name=name, camera=checked)
        identity = existing["id"]
    else:
        identity = f"b{state['next_id']}"
        state["next_id"] += 1
        state["items"].append({"id": identity, "name": name, "camera": checked})
    window.scene_bookmarks = bookmarks(state)
    return {"bookmark_id": identity, "bookmarks": read_bookmarks(window)}


def bookmark_go(window, ref):
    bookmark = _bookmark(read_bookmarks(window), ref)
    window.scene_camera = scene.camera(bookmark["camera"])
    window.scene_view = True
    return {"bookmark_id": bookmark["id"], "camera": deepcopy(window.scene_camera)}


def bookmark_remove(window, ref):
    state = read_bookmarks(window)
    bookmark = _bookmark(state, ref)
    state["items"] = [b for b in state["items"] if b["id"] != bookmark["id"]]
    window.scene_bookmarks = bookmarks(state)
    return read_bookmarks(window)


# --- reference images -----------------------------------------------------

def _reference(values):
    if not isinstance(values, dict) or set(values) != {"image", "opacity", "offset", "size"}:
        raise ValueError("Invalid reference image fields")
    pixels = material_image.pixels(values["image"])
    opacity = values["opacity"]
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
        raise ValueError("Reference opacity must be from 0 to 1")
    for key, positive in (("offset", False), ("size", True)):
        v = values[key]
        if (not isinstance(v, (list, tuple)) or len(v) != 2
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v)
                or (positive and any(x <= 0 for x in v))):
            raise ValueError(f"Reference {key} requires two finite meters" + (" greater than zero" if positive else ""))
    return {"image": deepcopy(values["image"]), "opacity": float(opacity),
            "offset": [float(v) for v in values["offset"]], "size": [float(v) for v in values["size"]],
            "_pixels": pixels}


def references(values=None):
    if values is None or values == {}:
        return {"schema_version": 1, "views": {}}
    if not isinstance(values, dict) or set(values) != {"schema_version", "views"}:
        raise ValueError("Invalid reference image fields")
    if type(values["schema_version"]) is not int or values["schema_version"] != 1:
        raise ValueError("Unsupported reference image version")
    if not isinstance(values["views"], dict) or set(values["views"]) - set(AXIS_VIEWS):
        raise ValueError("Reference views must be front, back, left, right, top or bottom")
    result = {"schema_version": 1, "views": {}}
    for view, entry in values["views"].items():
        checked = _reference(entry)
        checked.pop("_pixels")
        result["views"][view] = checked
    return result


def read_references(window):
    return references(getattr(window, "scene_references", None))


def _derived_size(image):
    """An unsized import's framing: 2 m tall at the image's own aspect."""
    height, width = material_image.pixels(image).shape[:2]
    return [2.0 * width / height, 2.0]


def _user_size(previous):
    """``previous``'s size when the user chose it, else ``None``.

    A stored entry records no provenance — ``_reference`` fixes the key set
    and the schema is version 1 — so it is recovered by comparing: a size
    that is exactly what its own image would have derived is the automatic
    one and must not outlive that image, while any other size is framing the
    user asked for and carries forward like opacity and offset.
    """
    size, image = previous.get("size"), previous.get("image")
    if size is None or image is None:
        return None
    try:
        derived = _derived_size(image)
    except ValueError:
        return None                      # undecodable: refit rather than guess
    return None if all(math.isclose(a, b) for a, b in zip(size, derived)) else size


def reference_set(window, view, path, *, opacity=None, offset=None, size=None):
    """Import a PNG/JPEG as the owned reference for one axis view."""
    if view not in AXIS_VIEWS:
        raise ValueError("Reference views must be front, back, left, right, top or bottom")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Reference image path must be text")
    image = material_image.import_image(path)
    state = read_references(window)
    previous = state["views"].get(view, {})
    if size is None:
        # Opacity and offset always carry forward; size only when the user
        # set it, so re-importing keeps a framing the user chose but refits
        # an automatic one — carrying that onto an image of a different
        # shape would draw the new image at the old image's aspect.
        size = _user_size(previous)
        if size is None:
            size = _derived_size(image)
    entry = {
        "image": image,
        "opacity": previous.get("opacity", REFERENCE_DEFAULT["opacity"]) if opacity is None else opacity,
        "offset": previous.get("offset", REFERENCE_DEFAULT["offset"]) if offset is None else offset,
        "size": size,
    }
    state["views"][view] = entry
    window.scene_references = references(state)
    return {"view": view, "references": read_references(window)}


def reference_clear(window, view):
    state = read_references(window)
    if view not in state["views"]:
        raise ValueError("No reference image is set for this view")
    del state["views"][view]
    window.scene_references = references(state)
    return read_references(window)


def reference_for_camera(window):
    """The reference entry (with decoded ``_pixels``) for the current axis view."""
    name = view_name(getattr(window, "scene_camera", None))
    if name is None:
        return None
    entry = read_references(window)["views"].get(name)
    return None if entry is None else _reference(entry)
