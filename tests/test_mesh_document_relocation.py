"""NP-03 acceptance: document-owned geometry survives moves, fresh processes and tampering."""
import gc
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path, PurePosixPath

import numpy as np
import pytest
from PIL import Image

from _native_session import native_session  # noqa: F401
from elysium.aether._headless import LAYOUT_VERSION, HeadlessDesigner, Placement
from elysium.render import mesh_document, pbr, primitives, scene

WORKTREE_PYTHON = str(Path(__file__).resolve().parent.parent / "python")
SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "designer-layout-1.json"

REPORT = '''
import json, sys
from pathlib import Path
from elysium.aether._headless import HeadlessDesigner
from elysium.render import mesh_document, scene
d = HeadlessDesigner.from_skin(Path(sys.argv[1]))
payload = d.layout_payload()
key = next(p.mesh_kind for p in d.placements if p.kind == "Mesh3D")
print(json.dumps({
    "document_hash": mesh_document.document_hash(payload),
    "mesh": mesh_document.to_json(mesh_document.resolve(key, store=d.mesh_store)),
    "world": [m.tolist() for m in scene.world_matrices(d.placements)],
}))
'''


def write_png(path, color=(255, 0, 0, 255)):
    Image.new("RGBA", (2, 2), color).save(path)
    return str(path)


def top_face(d, placement_id):
    from elysium.render import topology
    p = next(p for p in d.placements if p.entity_id == placement_id)
    doc = topology.document(mesh_document.resolve(p.mesh_kind, store=d.mesh_store))
    points = {v["id"]: v["position"] for v in doc["vertices"]}
    return next(f["id"] for f in doc["faces"] if all(points[c["vertex"]][1] > 0 for c in f["corners"]))


def fresh_process_report(project):
    env = {**os.environ, "PYTHONPATH": WORKTREE_PYTHON}
    result = subprocess.run([sys.executable, "-c", REPORT, str(project)],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_authored_project_survives_move_and_fresh_process_with_identical_hashes(native_session, tmp_path):
    d, session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube", parameters={"size": 2})["placement_id"]
    call("mesh.components_select", id=cube, mode="faces", ids=[top_face(d, cube)])
    call("mesh.components_edit", id=cube, operation="extrude", distance=0.5)
    slot = call("material.slot_add", id=cube, name="Red", values={"base_color": [1, 0, 0]})["slot_id"]
    call("material.slot_image_set", id=cube, slot_id=slot, path=write_png(tmp_path / "albedo.png"))
    call("scene.transform_set", id=cube, transform={"location": [1, 2, 3], "rotation": [10, 20, 30]})
    group = call("scene.group_create", name="Rig")["placement_id"]
    call("scene.transform_set", id=group, transform={"rotation": [0, 45, 0], "scale": [2, 2, 2]})
    call("scene.parent_set", id=cube, parent_id=group)
    hashes = call("scene.document_hash")
    assert hashes["document_version"] == LAYOUT_VERSION
    key = next(p.mesh_kind for p in d.placements if p.kind == "Mesh3D")
    assert key.startswith("mesh:") and key in hashes["mesh_document"]["assets"]
    expected = {
        "document_hash": hashes["document_hash"],
        "mesh": mesh_document.to_json(mesh_document.resolve(key, store=d.mesh_store)),
        "world": [m.tolist() for m in scene.world_matrices(d.placements)],
    }
    moved = tmp_path / "elsewhere" / "relocated.esk"
    moved.parent.mkdir()
    shutil.move(str(d.skin_path), str(moved))
    assert fresh_process_report(moved) == expected


def test_tampered_asset_is_rejected_with_clear_error_and_document_untouched(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / "native.esk")
    p = Placement(kind="Mesh3D", name="Cube")
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.save_layout()
    layout = d.skin_path / "designer_layout.json"
    data = json.loads(layout.read_text())
    asset = data["mesh_document"]["assets"][p.mesh_kind]
    # A consistent edit (positions and compiled vertices both doubled) passes
    # structural validation; only the recorded hash can catch it.
    asset["verts"] = (np.asarray(asset["verts"]) * 2).tolist()
    for vertex in asset["topology"]["vertices"]:
        vertex["position"] = [v * 2 for v in vertex["position"]]
    layout.write_text(json.dumps(data))
    window, placements, store = d.window_doc, d.placements, d.mesh_store
    with pytest.raises(ValueError, match="does not match its recorded hash"):
        d.load_layout()
    assert d.window_doc is window and d.placements is placements and d.mesh_store is store
    np.testing.assert_allclose(np.abs(mesh_document.resolve(p.mesh_kind, store=store).verts), 1)


CUBE_OBJ = """v -1 -1 -1
v 1 -1 -1
v 1 1 -1
v -1 1 -1
v -1 -1 1
v 1 -1 1
v 1 1 1
v -1 1 1
f 1 4 3 2
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""


def legacy_file_project(root):
    d = HeadlessDesigner.from_skin(root / "legacy.esk")
    obj = d.skin_path / "cube.obj"
    obj.write_text(CUBE_OBJ)
    p = Placement(kind="Mesh3D", name="Imported")
    p.mesh_kind = f"file:{obj}"
    d.placements = [p]
    d.save_layout()
    return d.skin_path, obj


def test_legacy_file_mesh_kind_migrates_to_owned_asset_after_relocation(tmp_path):
    project, obj = legacy_file_project(tmp_path)
    saved = json.loads((project / "designer_layout.json").read_text())
    assert saved["placements"][0]["mesh"]["kind"] == f"file:{obj}"
    moved = tmp_path / "moved" / "legacy.esk"
    moved.parent.mkdir()
    shutil.move(str(project), str(moved))
    assert not obj.exists()
    d = HeadlessDesigner.from_skin(moved)
    p = d.placements[0]
    assert p.mesh_kind.startswith("mesh:")
    assert p.props["import_source"] == {"name": "cube.obj", "path": "cube.obj"}
    assert mesh_document.resolve(p.mesh_kind, store=d.mesh_store).verts.shape == (8, 3)
    d.save_layout()
    reopened = json.loads((moved / "designer_layout.json").read_text())
    assert reopened["placements"][0]["mesh"]["kind"] == p.mesh_kind
    assert p.mesh_kind in reopened["mesh_document"]["assets"]
    # The file itself is no longer required once the geometry is embedded.
    (moved / "cube.obj").unlink()
    assert HeadlessDesigner.from_skin(moved).placements[0].mesh_kind == p.mesh_kind


def test_missing_legacy_mesh_file_is_reported_and_document_untouched(tmp_path):
    project, obj = legacy_file_project(tmp_path)
    obj.unlink()
    d = HeadlessDesigner(project)
    with pytest.raises(ValueError, match="Missing mesh file cube.obj"):
        d.load_layout()
    assert d.placements == []


# Every kind of on-disk asset reference a placement can hold, as
# (attribute, how the saved JSON spells it, how to read one back).
ASSET_REFERENCES = [
    ("pbr_albedo_map", lambda j: j["pbr_maps"]["albedo"], lambda p: p.pbr_albedo_map),
    ("pbr_normal_map", lambda j: j["pbr_maps"]["normal"], lambda p: p.pbr_normal_map),
    ("texture_path", lambda j: j["texture"]["path"], lambda p: p.texture_path),
    ("image_path", lambda j: j["image_path"], lambda p: p.image_path),
    ("mesh_part_textures", lambda j: j["mesh"]["part_textures"]["Wing_Left"],
     lambda p: p.mesh_part_textures["Wing_Left"]),
    ("texture_layers", lambda j: j["texture_layers"][0]["path"],
     lambda p: p.texture_layers[0]["path"]),
]


def textured_placement(paths):
    """One placement carrying ``paths[field]`` in every asset reference."""
    return Placement(
        kind="Mesh3D", name="Cube",
        pbr_albedo_map=paths["pbr_albedo_map"],
        pbr_normal_map=paths["pbr_normal_map"],
        texture_path=paths["texture_path"],
        image_path=paths["image_path"],
        mesh_part_textures={"Wing_Left": paths["mesh_part_textures"]},
        texture_layers=[{"path": paths["texture_layers"], "opacity": 0.5}])


def test_every_in_project_asset_reference_is_saved_relative_and_resolved_after_move(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / "textured.esk")
    (d.skin_path / "textures").mkdir()
    inside = {field: write_png(d.skin_path / "textures" / f"{field}.png")
              for field, _saved, _read in ASSET_REFERENCES}
    p = textured_placement(inside)
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.save_layout()
    # Live objects are not rewritten.
    assert [read(p) for _f, _s, read in ASSET_REFERENCES] == list(inside.values())
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())["placements"][0]
    assert [spelling(saved) for field, spelling, _r in ASSET_REFERENCES] == [
        f"textures/{field}.png" for field, _s, _r in ASSET_REFERENCES]
    # Unrelated layer data survives the rewrite untouched.
    assert saved["texture_layers"][0]["opacity"] == 0.5
    moved = tmp_path / "moved" / "textured.esk"
    moved.parent.mkdir()
    shutil.move(str(d.skin_path), str(moved))
    reopened = HeadlessDesigner.from_skin(moved).placements[0]
    for field, _spelling, read in ASSET_REFERENCES:
        assert read(reopened) == str(moved / "textures" / f"{field}.png"), field
        assert Path(read(reopened)).is_file(), field


def test_assets_outside_the_project_keep_their_absolute_path(tmp_path):
    """Documented limitation: only in-project files travel with the project."""
    d = HeadlessDesigner.from_skin(tmp_path / "external.esk")
    (tmp_path / "shared").mkdir()
    outside = {field: write_png(tmp_path / "shared" / f"{field}.png")
               for field, _s, _r in ASSET_REFERENCES}
    p = textured_placement(outside)
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.save_layout()
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())["placements"][0]
    assert [spelling(saved) for _f, spelling, _r in ASSET_REFERENCES] == list(outside.values())
    moved = tmp_path / "moved" / "external.esk"
    moved.parent.mkdir()
    shutil.move(str(d.skin_path), str(moved))
    reopened = HeadlessDesigner.from_skin(moved).placements[0]
    assert [read(reopened) for _f, _s, read in ASSET_REFERENCES] == list(outside.values())


def test_two_documents_in_one_process_have_separate_stores(tmp_path):
    a = HeadlessDesigner.from_skin(tmp_path / "a.esk")
    b = HeadlessDesigner.from_skin(tmp_path / "b.esk")
    pa = Placement(kind="Mesh3D", name="A")
    with mesh_document.using(a):
        key_a = primitives.bind(pa, "Cube")
    a.placements = [pa]
    pb = Placement(kind="Mesh3D", name="B")
    key_b = primitives.bind(pb, "Sphere", store=b.mesh_store)
    b.placements = [pb]
    assert key_a in a.mesh_store and key_a not in b.mesh_store
    assert key_b in b.mesh_store and key_b not in a.mesh_store
    assert key_a not in mesh_document._PROCESS_STORE
    before = b._snapshot()
    with mesh_document.using(b):
        # Owned keys are globally unambiguous, so cross-document reads work.
        assert mesh_document.resolve(key_a) is a.mesh_store.get(key_a)
        assert mesh_document.sweep(b.placements) == []
        primitives.update(pb, {"radius": 2})
        assert mesh_document.sweep(b.placements) == [key_b]
    b._restore(before)
    assert key_b in b.mesh_store and b.placements[0].mesh_kind == key_b
    assert key_a in a.mesh_store and a.placements[0].mesh_kind == key_a


def test_committed_transaction_sweeps_superseded_revision_and_undo_restores_it(native_session):
    d, session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube")["placement_id"]
    key1 = d.placements[0].mesh_kind
    assert key1 in d.mesh_store
    before = d._snapshot()
    call("mesh.uv_project", id=cube, mode="planar_xy")
    key2 = d.placements[0].mesh_kind
    assert key2 != key1
    assert key2 in d.mesh_store and key1 not in d.mesh_store
    d._restore(before)
    assert d.placements[0].mesh_kind == key1
    assert key1 in d.mesh_store and key2 not in d.mesh_store
    assert len(mesh_document.resolve(key1, store=d.mesh_store).verts) == 8


def _genuine_factories():
    return {k: v for k, v in pbr.MESH_LIBRARY.items() if not isinstance(v, mesh_document._ReadThrough)}


def test_restore_never_shadows_preset_or_third_party_factories(monkeypatch):
    # A legacy document may carry assets under a preset name ("Cube") or a
    # name a Designer deformer registered itself. restore() publishes those
    # into the store only; the library entries stay untouched. Only a name
    # nobody owns gets the deprecated read-through shim, and it leaves with
    # the store that held it.
    authored = primitives.build("Cube", {"size": 3})[0]
    deformed = primitives.build("Cube", {"size": 5})[0]
    monkeypatch.setitem(pbr.MESH_LIBRARY, "BendDeformed", lambda m=deformed: m)
    before = _genuine_factories()
    document = {"schema_version": 1, "assets": {
        "Cube": mesh_document.to_json(authored),
        "BendDeformed": mesh_document.to_json(authored),
        "butterfly": mesh_document.to_json(authored),
    }}
    store = mesh_document.MeshStore()
    mesh_document.restore(document, store=store)
    assert list(_genuine_factories()) == list(before)
    assert all(pbr.MESH_LIBRARY[k] is before[k] for k in before)
    assert isinstance(pbr.MESH_LIBRARY["butterfly"], mesh_document._ReadThrough)
    np.testing.assert_allclose(np.abs(mesh_document.resolve("Cube", store=store).verts), 1.5)
    np.testing.assert_allclose(np.abs(mesh_document.resolve("BendDeformed", store=store).verts), 1.5)
    np.testing.assert_allclose(np.abs(pbr.MESH_LIBRARY["Cube"]().verts), 0.5)
    np.testing.assert_allclose(np.abs(pbr.MESH_LIBRARY["BendDeformed"]().verts), 2.5)
    # Named legacy keys never leak into other documents.
    other = mesh_document.MeshStore()
    np.testing.assert_allclose(np.abs(mesh_document.resolve("Cube", store=other).verts), 0.5)
    with pytest.raises(ValueError, match="missing mesh asset"):
        mesh_document.resolve("butterfly", store=other)
    del store
    gc.collect()
    assert "butterfly" not in pbr.MESH_LIBRARY


def test_document_version_rules_and_schema(tmp_path):
    from jsonschema import Draft202012Validator
    d = HeadlessDesigner.from_skin(tmp_path / "versioned.esk")
    p = Placement(kind="Mesh3D", name="Cube")
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.save_layout()
    layout = d.skin_path / "designer_layout.json"
    saved = json.loads(layout.read_text())
    assert saved["document_version"] == LAYOUT_VERSION == 1
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(saved)
    newer = deepcopy(saved)
    newer["document_version"] = 99
    layout.write_text(json.dumps(newer))
    with pytest.raises(ValueError, match="requires a newer Elysium"):
        HeadlessDesigner.from_skin(d.skin_path)
    for bad in ("1", -1, True):
        broken = deepcopy(saved)
        broken["document_version"] = bad
        layout.write_text(json.dumps(broken))
        with pytest.raises(ValueError):
            HeadlessDesigner.from_skin(d.skin_path)
    legacy = deepcopy(saved)
    del legacy["document_version"]
    layout.write_text(json.dumps(legacy))
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert reopened.placements[0].mesh_kind == p.mesh_kind
    reopened.save_layout()
    assert json.loads(layout.read_text())["document_version"] == 1
    assert "document_version" not in reopened._layout_extra


def test_mesh_import_tools_embed_geometry_as_owned_assets(native_session, tmp_path):
    d, session, call = native_session
    obj = tmp_path / "cube.obj"
    obj.write_text(CUBE_OBJ)
    first = call("mesh.import", path=str(obj))
    second = call("mesh.import_3d", path=str(obj))
    assert first["mesh_key"].startswith("mesh:cube:")
    assert second["mesh_key"].startswith("mesh:cube:") and second["mesh_name"] == "cube"
    # Presets are untouched; the owned keys appear only as read-through
    # Designer shims that forward to the store (they carry no geometry of
    # their own). mesh_name is the filename stem, not a named key: "cube"
    # stays the preset for every spelling.
    assert list(_genuine_factories()) == ["Sphere", "Cube", "Cylinder", "Torus", "Plane", "Cone"]
    assert second["mesh_name"] == "cube" and "cube" not in d.mesh_store
    assert "cube" not in pbr.MESH_LIBRARY
    with mesh_document.using(d):
        assert len(mesh_document.resolve("cube").faces) == len(pbr.MESH_LIBRARY["Cube"]().faces)
        for key in (first["mesh_key"], second["mesh_key"]):
            assert pbr.MESH_LIBRARY[key]() is d.mesh_store.get(key)
    obj.unlink()
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())
    assert set(saved["mesh_document"]["assets"]) == {first["mesh_key"], second["mesh_key"]}
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    assert [p.props["import_source"]["name"] for p in reopened.placements] == ["cube.obj", "cube.obj"]


# --- legacy `file:` assets move with the project ------------------------------

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def cloned_butterfly(tmp_path):
    """``examples/butterfly`` as a second user receives it.

    The asset is present, beside the project in ``_3ds/``, but the
    absolute path the document records was written on the author's
    machine and exists nowhere here — which is the whole situation a
    clone is in.
    """
    root = tmp_path / "clone"
    root.mkdir()
    shutil.copytree(EXAMPLES / "butterfly" / "butterfly.esk", root / "butterfly.esk")
    shutil.copytree(EXAMPLES / "butterfly" / "_3ds", root / "_3ds")
    layout = root / "butterfly.esk" / "designer_layout.json"
    data = json.loads(layout.read_text())
    recorded = Path(data["placements"][0]["mesh"]["kind"][5:])
    # The fixture writes a POSIX authoring path; PurePosixPath reads it as
    # absolute on every platform, where WindowsPath would not.
    assert PurePosixPath(recorded.as_posix()).is_absolute()
    assert recorded.parent.name == "_3ds"
    authored = Path("/authoring-machine/projects/butterfly") / recorded.parent.name / recorded.name
    assert not authored.exists()
    data["placements"][0]["mesh"]["kind"] = f"file:{authored}"
    layout.write_text(json.dumps(data))
    return root / "butterfly.esk"


def test_absolute_legacy_path_is_found_again_in_its_project_relative_location(tmp_path):
    project = cloned_butterfly(tmp_path)
    d = HeadlessDesigner.from_skin(project)
    try:
        p = next(p for p in d.placements if p.kind == "Mesh3D")
        assert p.mesh_kind.startswith("mesh:butterfly:")
        assert p.props["import_source"]["name"] == "butterfly.3ds"
        assert len(mesh_document.resolve(p.mesh_kind, store=d.mesh_store).verts) > 0
    finally:
        d.mesh_store.clear()


def test_absolute_legacy_path_tries_longer_tails_before_the_bare_filename(tmp_path):
    """The most specific tail wins: a same-named file loose in the project
    must not shadow the one in the recorded subdirectory."""
    project = tmp_path / "tails.esk"
    project.mkdir()
    (tmp_path / "meshes").mkdir()
    (tmp_path / "meshes" / "cube.obj").write_text(CUBE_OBJ)
    # A decoy of the same name loose in the project, with a different
    # vertex count so the wrong pick is unmistakable.
    (tmp_path / "cube.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 2 4\n")
    placement = Placement(kind="Mesh3D", name="Imported")
    placement.mesh_kind = "file:/elsewhere/authored/meshes/cube.obj"
    (project / "designer_layout.json").write_text(json.dumps(
        {"window": {"name": "MainWindow"}, "placements": [placement.to_json()]}))
    d = HeadlessDesigner.from_skin(project)
    try:
        assert d.placements[0].props["import_source"]["path"] == str(tmp_path / "meshes" / "cube.obj")
        verts = mesh_document.resolve(d.placements[0].mesh_kind, store=d.mesh_store).verts
        assert len(verts) == 8  # the cube in meshes/, not the 4-vertex decoy
    finally:
        d.mesh_store.clear()


def test_absolute_legacy_path_with_no_project_copy_still_reports_the_missing_file(tmp_path):
    project = tmp_path / "gone.esk"
    project.mkdir()
    placement = Placement(kind="Mesh3D", name="Imported")
    placement.mesh_kind = "file:/elsewhere/authored/_3ds/wing.3ds"
    (project / "designer_layout.json").write_text(json.dumps(
        {"window": {"name": "MainWindow"}, "placements": [placement.to_json()]}))
    d = HeadlessDesigner(project)
    with pytest.raises(ValueError, match="Missing mesh file wing.3ds"):
        d.load_layout()
    assert d.placements == []
