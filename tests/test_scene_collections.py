"""NP-06 (d): persistent scene collections with exclusive membership and visibility."""
import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from _native_session import native_session  # noqa: F401
from elysium import scene_identity
from elysium.aether._headless import AppWindow, HeadlessDesigner, Placement
from elysium.render import collections, primitives, scene


def cube(name="Cube"):
    p = SimpleNamespace(kind="Mesh3D", props={}, name=name, entity_id=scene_identity.new_id(), visible=True)
    primitives.bind(p, "Cube")
    return p


def window():
    return SimpleNamespace(scene_collections=collections.settings())


def test_lifecycle_uses_stable_ids_and_validated_tables():
    w = window()
    a, b = cube("A"), cube("B")
    first = collections.create(w, " Hull ")
    second = collections.create(w, "Wings", parent=first["collection_id"])
    assert first["collection_id"] == "col1" and second["collection_id"] == "col2"
    assert [c["name"] for c in collections.read(w)["items"]] == ["Hull", "Wings"]
    collections.assign(w, [a, b], [a.entity_id], "col1")
    collections.assign(w, [a, b], [b.entity_id], "col2")
    assert collections.collection_of(w, a.entity_id) == "col1"
    assert collections.collection_of(w, b.entity_id) == "col2"
    collections.update(w, "col2", name="Engines", visible=False)
    item = next(c for c in collections.read(w)["items"] if c["id"] == "col2")
    assert item["name"] == "Engines" and item["visible"] is False and item["parent"] == "col1"
    collections.remove(w, "col1")
    remaining = collections.read(w)["items"]
    assert [c["id"] for c in remaining] == ["col2"] and remaining[0]["parent"] is None
    assert collections.collection_of(w, a.entity_id) is None
    assert collections.create(w, "Third")["collection_id"] == "col3"  # ids never reused


@pytest.mark.parametrize(
    "operation",
    [
        lambda w, a: collections.create(w, "hull"),
        lambda w, a: collections.create(w, ""),
        lambda w, a: collections.create(w, "New", parent="col9"),
        lambda w, a: collections.update(w, "col1", parent="col2"),
        lambda w, a: collections.update(w, "col1", parent="col1"),
        lambda w, a: collections.update(w, "col2", name="Hull"),
        lambda w, a: collections.update(w, "col1", visible="yes"),
        lambda w, a: collections.assign(w, [a], ["entity:" + "0" * 32], "col1"),
        lambda w, a: collections.assign(w, [a], [a.entity_id], "col9"),
        lambda w, a: collections.assign(w, [a], [a.entity_id, a.entity_id], "col1"),
        lambda w, a: collections.remove(w, "col9"),
    ],
)
def test_invalid_mutations_reject_atomically(operation):
    w = window()
    a = cube()
    collections.create(w, "Hull")
    collections.create(w, "Wings", parent="col1")
    before = deepcopy(w.scene_collections)
    with pytest.raises(ValueError):
        operation(w, a)
    assert w.scene_collections == before


def test_assign_moves_between_collections_and_unassigns():
    w = window()
    a, b = cube("A"), cube("B")
    collections.create(w, "Left")
    collections.create(w, "Right")
    collections.assign(w, [a, b], [a.entity_id, b.entity_id], "col1")
    collections.assign(w, [a, b], [a.entity_id], "col2")
    items = {c["id"]: c["members"] for c in collections.read(w)["items"]}
    assert items == {"col1": [b.entity_id], "col2": [a.entity_id]}
    collections.assign(w, [a, b], [a.entity_id, b.entity_id], None)
    assert all(not c["members"] for c in collections.read(w)["items"])


def test_exclusion_hides_members_and_nested_members_but_keeps_transforms():
    w = window()
    parent, child, other = cube("Parent"), cube("Child"), cube("Other")
    objects = [parent, child, other]
    scene.update(parent, {"location": [5, 0, 0]})
    scene.set_parent(objects, child, parent, keep_world=False)
    scene.update(other, {"location": [0, 0, 5]})
    collections.create(w, "Rig")
    collections.create(w, "Inner", parent="col1")
    collections.assign(w, objects, [parent.entity_id], "col1")
    collections.assign(w, objects, [other.entity_id], "col2")
    assert collections.excluded_entities(w, objects) == set()
    collections.update(w, "col1", visible=False)
    excluded = collections.excluded_entities(w, objects)
    assert excluded == {parent.entity_id, other.entity_id}
    composed, owners = scene.compose(objects, excluded=excluded)
    assert set(owners) == {1}
    assert composed.mesh.verts[:, 0].mean() == pytest.approx(5)  # child still follows its hidden parent
    _, ids = scene.render(objects, 64, 64, excluded=excluded, grid=False)
    assert set(np.unique(ids)) <= {-1, 1}
    collections.update(w, "col1", visible=True, exclude=True)
    assert collections.excluded_entities(w, objects) == excluded
    collections.update(w, "col1", exclude=False)
    assert collections.excluded_entities(w, objects) == set()
    assert scene.is_visible(parent) and not scene.is_visible(parent, {parent.entity_id})


def test_persistence_through_window_json_and_layout_with_pruning(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / "collections.esk")
    a, b = Placement(kind="Mesh3D", name="A"), Placement(kind="Mesh3D", name="B")
    for p in (a, b):
        primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [a, b]
    collections.create(d.window_doc, "Hull")
    collections.assign(d.window_doc, d.placements, [a.entity_id, b.entity_id], "col1")
    collections.update(d.window_doc, "col1", exclude=True)
    encoded = AppWindow.from_json(d.window_doc.to_json())
    assert encoded.scene_collections == d.window_doc.scene_collections
    d.save_layout()
    layout = d.skin_path / "designer_layout.json"
    saved = json.loads(layout.read_text())
    assert saved["window"]["scene_collections"]["items"][0]["members"] == [a.entity_id, b.entity_id]
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert reopened.window_doc.scene_collections == d.window_doc.scene_collections
    # A member whose object disappeared is pruned on load.
    saved["placements"] = [saved["placements"][0]]
    layout.write_text(json.dumps(saved))
    pruned = HeadlessDesigner.from_skin(d.skin_path)
    assert pruned.window_doc.scene_collections["items"][0]["members"] == [a.entity_id]
    # An invalid persisted table is rejected without publishing anything.
    saved["window"]["scene_collections"]["items"][0]["parent"] = "col1"
    layout.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="parent must be another existing collection"):
        pruned.load_layout()
    assert pruned.window_doc.scene_collections["items"][0]["parent"] is None


def test_placement_tools_prune_and_inherit_collections(native_session):
    d, session, call = native_session
    first = call("mesh.primitive_create", kind="Cube")["placement_id"]
    second = call("mesh.primitive_create", kind="Sphere")["placement_id"]
    hull = call("scene.collection_create", name="Hull")["collection_id"]
    call("scene.collection_assign", ids=[first, second], collection_id=hull)
    copy = call("placement.duplicate", id=first)["placement_id"]
    members = call("scene.collections_get")["collections"]["items"][0]["members"]
    assert members == [first, second, copy]
    call("placement.remove", id=second)
    members = call("scene.collections_get")["collections"]["items"][0]["members"]
    assert members == [first, copy]
    call("scene.collection_set", collection_id=hull, visible=False)
    excluded = collections.excluded_entities(d.window_doc, d.placements)
    assert excluded == {first, copy}
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())
    assert saved["window"]["scene_collections"]["items"][0]["visible"] is False
    failed = call.expect_failure("scene.collection_set", collection_id=hull, parent_id=hull)
    assert "existing collection" in failed.error or "cycle" in failed.error
    call("scene.collection_set", collection_id=hull, parent_id=None, visible=True)
    call("scene.collection_assign", ids=[copy], collection_id=None)
    call("scene.collection_delete", collection_id=hull)
    assert call("scene.collections_get")["collections"]["items"] == []


def test_render_job_and_snapshot_omit_excluded_objects(tmp_path):
    from elysium.render import scene_render_job
    from elysium.render.designer_preview import paint_designer_png

    d = HeadlessDesigner.from_skin(tmp_path / "hidden.esk")
    p = Placement(kind="Mesh3D", name="Cube")
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.window_doc.scene_view = True
    d.window_doc.scene_camera = scene.camera({"yaw": 0, "pitch": 0, "distance": 6})
    d.window_doc.w, d.window_doc.h = 48, 48
    visible = np.array(Image.open(BytesIO(paint_designer_png(d))))
    assert visible[24, 24, 3] == 255
    collections.create(d.window_doc, "Hidden")
    collections.assign(d.window_doc, d.placements, [p.entity_id], "col1")
    collections.update(d.window_doc, "col1", exclude=True)
    hidden = np.array(Image.open(BytesIO(paint_designer_png(d))))
    assert not hidden[:, :, 3].any()
    scene_render_job.render(d.placements, d.window_doc, tmp_path / "job", size=24, channels=["beauty"])
    frame = np.array(Image.open(tmp_path / "job" / "frame-0000-beauty.png"))
    assert not frame[:, :, 3].any()
