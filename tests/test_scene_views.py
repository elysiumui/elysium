"""NP-06 (e)(f): view presets, camera bookmarks and orthographic reference images."""
import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from _native_session import native_session  # noqa: F401
from elysium.aether._headless import AppWindow, HeadlessDesigner, Placement
from elysium.render import primitives, scene, scene_views

X, Y, Z = (150, 65, 65), (75, 145, 80), (65, 100, 170)


def cube():
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube", entity_id="entity:" + "a" * 32, visible=True)
    primitives.bind(p, "Cube")
    return p


def quadrant_png(path):
    image = Image.new("RGBA", (2, 2))
    image.putpixel((0, 0), (255, 0, 0, 255))  # top-left red
    image.putpixel((1, 0), (0, 255, 0, 255))  # top-right green
    image.putpixel((0, 1), (0, 0, 255, 255))  # bottom-left blue
    image.putpixel((1, 1), (255, 255, 255, 0))  # bottom-right transparent
    image.save(path)
    return str(path)


def pixel_at(world_x, world_y, size=120, ortho_scale=6.0):
    """Pixel (row, col) of an in-plane world coordinate for a centred axis view."""
    half = ortho_scale / 2
    col = int(round((world_x / half + 1) / 2 * (size - 1)))
    row = int(round((1 - world_y / half) / 2 * (size - 1)))
    return row, col


@pytest.mark.parametrize(
    "name,yaw,pitch,colors",
    [
        ("front", 0.0, 0.0, (X, Y)), ("back", np.pi, 0.0, (X, Y)),
        ("right", np.pi / 2, 0.0, (Y, Z)), ("left", -np.pi / 2, 0.0, (Y, Z)),
        ("top", 0.0, np.pi / 2, (X, Z)), ("bottom", 0.0, -np.pi / 2, (X, Z)),
    ],
)
def test_axis_presets_are_orthographic_and_show_the_expected_in_plane_axes(name, yaw, pitch, colors):
    current = scene.camera({"target": [1, 2, 3], "distance": 4, "ortho_scale": 6, "yaw": 0.3, "pitch": 0.2})
    camera = scene_views.view_preset(current, name)
    assert camera["projection"] == "orthographic"
    assert camera["yaw"] == pytest.approx(yaw) and camera["pitch"] == pytest.approx(pitch)
    assert camera["target"] == [1, 2, 3] and camera["distance"] == 4 and camera["ortho_scale"] == 6
    assert scene_views.view_name(camera) == name
    rgba, ids = scene.render([], 120, 120, **{**camera, "target": [0, 0, 0]})
    pixels = np.frombuffer(rgba, np.uint8).reshape(120, 120, 4)
    assert (ids == -1).all()
    for color in colors:
        assert np.count_nonzero(np.all(pixels[:, :, :3] == color, axis=2)) >= 100
    columns = np.flatnonzero(np.any(pixels[10, :, :3] != (48, 49, 52), axis=1))
    groups = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    assert len(groups) == 7


def test_perspective_preset_restores_defaults_and_names_round_trip():
    ortho = scene_views.view_preset(scene.camera({"distance": 3}), "top")
    restored = scene_views.view_preset(ortho, "perspective")
    assert restored["projection"] == "perspective" and restored["distance"] == 3
    assert restored["yaw"] == scene.CAMERA_DEFAULT["yaw"] and restored["pitch"] == scene.CAMERA_DEFAULT["pitch"]
    assert scene_views.view_name(restored) is None
    assert scene_views.view_name({**ortho, "yaw": 0.3}) is None
    assert scene_views.view_name({**ortho, "projection": "perspective"}) is None
    assert scene_views.view_name(scene_views.view_preset(ortho, "back")) == "back"
    with pytest.raises(ValueError):
        scene_views.view_preset(ortho, "isometric")


def test_bookmarks_set_replace_go_remove_and_limits():
    w = SimpleNamespace(scene_camera=scene.camera({"yaw": 1.0}), scene_view=False)
    first = scene_views.bookmark_set(w, "Hero")
    assert first["bookmark_id"] == "b1"
    w.scene_camera = scene.camera({"yaw": 2.0})
    replaced = scene_views.bookmark_set(w, " hero ")
    assert replaced["bookmark_id"] == "b1" and len(replaced["bookmarks"]["items"]) == 1
    assert replaced["bookmarks"]["items"][0]["camera"]["yaw"] == 2.0
    scene_views.bookmark_set(w, "Side", camera={"yaw": 0.5, "projection": "orthographic"})
    w.scene_camera = scene.camera()
    gone = scene_views.bookmark_go(w, "side")
    assert gone["bookmark_id"] == "b2" and w.scene_camera["yaw"] == 0.5 and w.scene_view is True
    scene_views.bookmark_go(w, "b1")
    assert w.scene_camera["yaw"] == 2.0
    scene_views.bookmark_remove(w, "Hero")
    assert [b["id"] for b in scene_views.read_bookmarks(w)["items"]] == ["b2"]
    with pytest.raises(ValueError):
        scene_views.bookmark_go(w, "Hero")
    before = deepcopy(w.scene_bookmarks)
    with pytest.raises(ValueError):
        scene_views.bookmark_set(w, "Bad", camera={"yaw": float("nan")})
    with pytest.raises(ValueError):
        scene_views.bookmark_set(w, "")
    assert w.scene_bookmarks == before
    for i in range(63):
        scene_views.bookmark_set(w, f"view {i}")
    with pytest.raises(ValueError, match="at most 64"):
        scene_views.bookmark_set(w, "one too many")
    assert len(scene_views.read_bookmarks(w)["items"]) == 64
    assert AppWindow.from_json({"scene_bookmarks": w.scene_bookmarks}).scene_bookmarks == w.scene_bookmarks
    with pytest.raises(ValueError):
        AppWindow.from_json({"scene_bookmarks": {**w.scene_bookmarks, "next_id": 1}})


def test_reference_image_blends_behind_the_grid_in_its_axis_view_only(tmp_path):
    w = SimpleNamespace(scene_camera=scene_views.view_preset(scene.camera({"ortho_scale": 6}), "front"),
                        scene_references=scene_views.references())
    p = cube()
    result = scene_views.reference_set(w, "front", quadrant_png(tmp_path / "ref.png"))
    entry = result["references"]["views"]["front"]
    assert entry["size"] == [2.0, 2.0] and entry["offset"] == [0.0, 0.0] and entry["opacity"] == 0.5
    # A 4 m square at full opacity reaches past the 2 m cube.
    result = scene_views.reference_set(w, "front", quadrant_png(tmp_path / "ref.png"), opacity=1.0, size=[4, 4])
    assert result["references"]["views"]["front"]["size"] == [4.0, 4.0]
    reference = scene_views.reference_for_camera(w)
    assert reference is not None and reference["_pixels"].shape == (2, 2, 4)
    view = {**w.scene_camera}
    plain, plain_ids = scene.render([p], 120, 120, **view)
    shown, ids = scene.render([p], 120, 120, **view, reference=reference)
    plain = np.frombuffer(plain, np.uint8).reshape(120, 120, 4)
    shown = np.frombuffer(shown, np.uint8).reshape(120, 120, 4)
    np.testing.assert_array_equal(ids, plain_ids)
    np.testing.assert_array_equal(shown[ids >= 0], plain[ids >= 0])
    # The cube covers [-1, 1]; sample the image just outside it, off the grid lines.
    assert tuple(shown[pixel_at(-1.5, 0.5)][:3]) == (255, 0, 0)
    assert tuple(shown[pixel_at(1.5, 0.5)][:3]) == (0, 255, 0)
    outside = pixel_at(2.5, 2.5)
    np.testing.assert_array_equal(shown[outside], plain[outside])
    # Half opacity blends with the background; transparent texels leave it untouched.
    scene_views.reference_set(w, "front", quadrant_png(tmp_path / "ref.png"), opacity=0.5, size=[6, 6])
    reference = scene_views.reference_for_camera(w)
    shown, _ = scene.render([], 120, 120, **view, reference=reference)
    shown = np.frombuffer(shown, np.uint8).reshape(120, 120, 4)
    assert tuple(shown[pixel_at(-1.5, 1.5)][:3]) == (151, 24, 26)
    assert tuple(shown[pixel_at(1.5, 1.5)][:3]) == (24, 152, 26)
    assert tuple(shown[pixel_at(-1.5, -1.5)][:3]) == (24, 24, 153)
    assert tuple(shown[pixel_at(1.5, -1.5)][:3]) == (48, 49, 52)
    # Grid lines are drawn over the image.
    assert tuple(shown[pixel_at(0, 1.5)][:3]) == Y
    # Other cameras and grid-less renders ignore the reference.
    ignored, _ = scene.render([], 120, 120, **view, grid=False, reference=reference)
    assert not np.frombuffer(ignored, np.uint8).any()
    perspective = {**view, "projection": "perspective"}
    with_ref, _ = scene.render([], 120, 120, **perspective, reference=reference)
    without, _ = scene.render([], 120, 120, **perspective)
    assert with_ref == without
    w.scene_camera = scene_views.view_preset(w.scene_camera, "top")
    assert scene_views.reference_for_camera(w) is None
    w.scene_camera = scene.camera(perspective)
    assert scene_views.reference_for_camera(w) is None
    scene_views.reference_clear(w, "front")
    assert scene_views.read_references(w)["views"] == {}
    with pytest.raises(ValueError):
        scene_views.reference_clear(w, "front")


def test_reference_validation_persistence_and_tampering(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / "refs.esk")
    p = Placement(kind="Mesh3D", name="Cube")
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    path = quadrant_png(tmp_path / "ref.png")
    for kwargs in ({"opacity": 2}, {"size": [0, 1]}, {"offset": [1]}, {"size": [float("nan"), 1]}):
        with pytest.raises(ValueError):
            scene_views.reference_set(d.window_doc, "front", path, **kwargs)
    with pytest.raises(ValueError):
        scene_views.reference_set(d.window_doc, "iso", path)
    with pytest.raises(ValueError):
        scene_views.reference_set(d.window_doc, "front", str(tmp_path / "missing.png"))
    assert d.window_doc.scene_references["views"] == {}
    scene_views.reference_set(d.window_doc, "top", path, opacity=0.25, offset=[1, -1], size=[3, 4])
    d.save_layout()
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert reopened.window_doc.scene_references == d.window_doc.scene_references
    layout = d.skin_path / "designer_layout.json"
    data = json.loads(layout.read_text())
    data["window"]["scene_references"]["views"]["top"]["image"]["sha256"] = "0" * 64
    layout.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest"):
        reopened.load_layout()
    assert reopened.window_doc.scene_references == d.window_doc.scene_references


def test_tool_level_presets_bookmarks_and_references_persist(native_session, tmp_path):
    d, session, call = native_session
    preset = call("scene.view_preset", name="right")
    assert preset["camera"]["projection"] == "orthographic" and d.window_doc.scene_view is True
    assert call("scene.camera_bookmarks_get")["view"] == "right"
    saved = call("scene.camera_bookmark_set", name="Side")
    assert saved["bookmark_id"] == "b1"
    call("scene.view_preset", name="perspective")
    assert call("scene.camera_bookmarks_get")["view"] is None
    call("scene.camera_bookmark_go", name="Side")
    assert d.window_doc.scene_camera["yaw"] == pytest.approx(np.pi / 2)
    call("scene.reference_image_set", view="front", path=quadrant_png(tmp_path / "ref.png"), opacity=0.75)
    refs = call("scene.reference_images_get")["references"]["views"]
    assert refs["front"]["opacity"] == 0.75 and refs["front"]["size"] == [2.0, 2.0]
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert reopened.window_doc.scene_bookmarks["items"][0]["name"] == "Side"
    assert reopened.window_doc.scene_references["views"]["front"]["opacity"] == 0.75
    call("scene.reference_image_clear", view="front")
    call("scene.camera_bookmark_remove", name="Side")
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert reopened.window_doc.scene_bookmarks["items"] == [] and reopened.window_doc.scene_references["views"] == {}
    failed = call.expect_failure("scene.reference_image_set", view="front", path=str(tmp_path / "nope.png"))
    assert "PNG or JPEG" in failed.error


def test_resetting_a_reference_image_keeps_the_user_set_size(tmp_path):
    camera = scene_views.view_preset(scene.camera({"ortho_scale": 6}), "front")
    w = SimpleNamespace(scene_camera=camera, scene_references=scene_views.references())
    path = quadrant_png(tmp_path / "ref.png")
    scene_views.reference_set(w, "front", path, opacity=0.8, offset=[1.0, -2.0], size=[5.0, 0.5])
    # Swapping the image keeps every framing choice, size included: opacity
    # and offset always did, size silently snapped back to the pixel aspect.
    entry = scene_views.reference_set(w, "front", path)["references"]["views"]["front"]
    assert entry["opacity"] == 0.8 and entry["offset"] == [1.0, -2.0]
    assert entry["size"] == [5.0, 0.5]
    # An explicit size still wins, and a first import still derives one.
    assert scene_views.reference_set(w, "front", path, size=[1.0, 1.0]
                                     )["references"]["views"]["front"]["size"] == [1.0, 1.0]
    assert scene_views.reference_set(w, "back", path
                                     )["references"]["views"]["back"]["size"] == [2.0, 2.0]


def solid_png(path, width, height):
    Image.new("RGBA", (width, height), (200, 60, 60, 255)).save(path)
    return str(path)


def test_swapping_a_reference_image_refits_a_size_the_user_never_set(tmp_path):
    camera = scene_views.view_preset(scene.camera({"ortho_scale": 6}), "front")
    w = SimpleNamespace(scene_camera=camera, scene_references=scene_views.references())
    wide = solid_png(tmp_path / "wide.png", 400, 200)     # aspect 2.0
    tall = solid_png(tmp_path / "tall.png", 200, 400)     # aspect 0.5
    first = scene_views.reference_set(w, "front", wide)["references"]["views"]["front"]
    assert first["size"] == [4.0, 2.0]                    # 2 m tall at the image aspect
    # A derived size belongs to the image it was derived from. Re-shooting or
    # re-cropping the reference refits it; carrying the old box forward would
    # draw the new image at 4x the wrong aspect.
    second = scene_views.reference_set(w, "front", tall)["references"]["views"]["front"]
    assert second["size"] == [1.0, 2.0]
    # Framing the user asked for still survives the swap, and still wins as
    # a fresh argument.
    scene_views.reference_set(w, "front", tall, offset=[1.0, -2.0], size=[5.0, 0.5])
    kept = scene_views.reference_set(w, "front", wide)["references"]["views"]["front"]
    assert kept["size"] == [5.0, 0.5] and kept["offset"] == [1.0, -2.0]
    assert scene_views.reference_set(w, "front", tall, size=[3.0, 3.0]
                                     )["references"]["views"]["front"]["size"] == [3.0, 3.0]
