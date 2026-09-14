"""Mesh store lifecycle regressions.

Running render jobs must not lose geometry to a later commit's sweep, the
Designer's direct ``pbr.MESH_LIBRARY`` reads must keep working through the
deprecated shim for owned revisions and registered names alike, names from
``mesh.register_from_file`` must outlive every store swap, everything a
store holds must be canonical so saved hashes reload, named keys must keep
the old library's case-insensitive match (a ``"butterfly"`` placement finds
a ``"Butterfly"`` registration), a shim must live exactly as long as
some live store holds its key, and neither an import's filename stem nor a
registration may hijack a read-only preset (``cube.obj`` must not become
``"Cube"`` for anyone).
"""
import gc
import json
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from _native_session import native_session  # noqa: F401
from elysium.aether._headless import AppWindow, HeadlessDesigner, Placement
from elysium.render import mesh_document, pbr, primitives, scene, scene_render_job

CUBE_OBJ = (
    "v -1 -1 -1\nv 1 -1 -1\nv 1 1 -1\nv -1 1 -1\nv -1 -1 1\nv 1 -1 1\nv 1 1 1\nv -1 1 1\n"
    "f 1 4 3 2\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
)
# One triangle: unmistakable next to any preset (Cube has 12 faces, Sphere 616).
TRI_OBJ = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def _presets():
    """Genuine factories only: shims are transient mirrors of store keys."""
    return {k: v for k, v in pbr.MESH_LIBRARY.items()
            if not isinstance(v, mesh_document._ReadThrough)}


def _designer_library_lookup(mesh_kind):
    """The GUI Designer's render-worker lookup, verbatim: exact, then a
    case-insensitive scan, else the KeyError that blanks the placement."""
    _lib = pbr.MESH_LIBRARY
    factory = _lib.get(mesh_kind)
    if factory is None:
        for k, v in _lib.items():
            if k.lower() == mesh_kind.lower():
                factory = v
                break
    if factory is None:
        raise KeyError(f"mesh_kind {mesh_kind!r} not in MESH_LIBRARY")
    return factory()


def _wait_for_job(designer, timeout=10.0):
    tick = threading.Event()
    for _ in range(int(timeout / 0.01)):
        if scene_render_job.status(designer)["status"] != "running":
            break
        tick.wait(0.01)
    return scene_render_job.status(designer)


# --- 1. background render jobs are self-contained -----------------------------

def test_running_render_job_survives_the_sweep_of_a_later_committed_edit(native_session, monkeypatch, tmp_path):
    d, session, call = native_session
    cube = call("mesh.primitive_create", kind="Cube")["placement_id"]
    key1 = d.placements[0].mesh_kind
    entered, gate = threading.Event(), threading.Event()
    real_render = scene.render

    def gated(*args, **kwargs):
        entered.set()
        assert gate.wait(10)
        return real_render(*args, **kwargs)

    monkeypatch.setattr(scene, "render", gated)
    try:
        call("scene.render_start", destination=str(tmp_path / "out"), size=16, first=0, last=1)
        assert entered.wait(10)
        # Regenerating the primitive while the job sits inside its first frame
        # commits, saves and sweeps key1 out of the live document store.
        call("mesh.primitive_update", id=cube, parameters={"size": 3})
        key2 = d.placements[0].mesh_kind
        assert key2 != key1 and key1 not in d.mesh_store and key2 in d.mesh_store
    finally:
        gate.set()
    status = _wait_for_job(d)
    assert status["status"] == "complete", status
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert len(manifest["frames"]) == 2
    # The job rendered the revision it started with, not the later edit.
    assert set(manifest["source"]["mesh_document"]["assets"]) == {key1}


def test_direct_render_pins_its_own_store_against_live_eviction(tmp_path, monkeypatch):
    live = mesh_document.MeshStore()
    p = Placement(kind="Mesh3D", name="Cube")
    key = primitives.bind(p, "Cube", store=live)
    real_render = scene.render

    def evicting(*args, **kwargs):
        # An edit committed on the live document between two frames.
        live.retain([])
        return real_render(*args, **kwargs)

    monkeypatch.setattr(scene, "render", evicting)
    with mesh_document.using(live):
        result = scene_render_job.render([p], AppWindow(), tmp_path / "out", size=16, start=0, end=1)
    assert result["frames"] == 2 and key not in live
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert set(manifest["source"]["mesh_document"]["assets"]) == {key}


# --- 2. deprecated pbr.MESH_LIBRARY read-through shim --------------------------

def test_owned_key_is_readable_through_the_library_shim_until_evicted(monkeypatch):
    presets = _presets()
    store = mesh_document.MeshStore()
    p = SimpleNamespace(kind="Mesh3D", props={}, name="Cube", entity_id="e1")
    with mesh_document.using(store):
        key = primitives.bind(p, "Cube")
        # Every access pattern the Designer still uses directly.
        assert key in pbr.MESH_LIBRARY
        assert pbr.MESH_LIBRARY[key]() is store.get(key)
        assert pbr.MESH_LIBRARY.get(key)() is store.get(key)
        scan = next(v for k, v in pbr.MESH_LIBRARY.items() if k.lower() == key.lower())
        assert scan() is store.get(key)
        document = mesh_document.capture([p])
        # A fresh process has no shim; restore republishes it for owned keys.
        mesh_document.forget(key)
        assert key not in pbr.MESH_LIBRARY and key not in store
        mesh_document.restore(document, [p])
        assert key in store and pbr.MESH_LIBRARY[key]() is store.get(key)
        # Eviction removes the shim along with the revision.
        assert mesh_document.sweep([]) == [key]
        assert key not in pbr.MESH_LIBRARY and key not in store
        with pytest.raises(ValueError, match="missing mesh asset"):
            mesh_document.resolve(key)
        # A stale shim can never recurse back into resolve.
        primitives.bind(p, "Cube")
        stale = pbr.MESH_LIBRARY[p.mesh_kind]
        store.clear()
        assert p.mesh_kind not in pbr.MESH_LIBRARY
        monkeypatch.setitem(pbr.MESH_LIBRARY, p.mesh_kind, stale)
        with pytest.raises(ValueError, match="missing mesh asset"):
            mesh_document.resolve(p.mesh_kind)
        with pytest.raises(ValueError, match="missing mesh asset"):
            stale()
    # The GUI Designer has no document context: the process store publishes too.
    q = SimpleNamespace(kind="Mesh3D", props={}, name="Cube", entity_id="e2")
    key = primitives.bind(q, "Cube")
    assert pbr.MESH_LIBRARY[key]() is mesh_document.default_store().get(key)
    mesh_document.forget(key)
    assert key not in pbr.MESH_LIBRARY
    assert _presets() == presets


def test_rollback_evicts_the_failed_transactions_revision_and_its_shim(native_session):
    d, session, call = native_session
    call("mesh.primitive_create", kind="Cube")
    key1 = d.placements[0].mesh_kind
    before = d._snapshot()
    with mesh_document.using(d):
        primitives.update(d.placements[0], {"size": 3})  # a revision the snapshot does not carry
    key2 = d.placements[0].mesh_kind
    assert key2 in d.mesh_store and key2 in pbr.MESH_LIBRARY
    d._restore(before)
    assert d.placements[0].mesh_kind == key1
    assert key1 in d.mesh_store and pbr.MESH_LIBRARY[key1]() is d.mesh_store.get(key1)
    assert key2 not in d.mesh_store and key2 not in pbr.MESH_LIBRARY


# --- 3. named keys outlive store swaps; stored meshes are canonical ------------

def test_registered_name_survives_rollback_undo_and_reload(native_session, tmp_path):
    d, session, call = native_session
    obj = tmp_path / "cube.obj"
    obj.write_text(CUBE_OBJ)
    call("mesh.register_from_file", path=str(obj), name="butterfly")

    def resolvable():
        with mesh_document.using(d):
            # Both the store lookup and the Designer's direct library read.
            return (len(mesh_document.resolve("butterfly").verts) == 8
                    and pbr.MESH_LIBRARY["butterfly"]() is d.mesh_store.get("butterfly"))

    assert resolvable() and "butterfly" in d.mesh_store
    # A failing command rolls the document back to its checkpoint...
    call.expect_failure("scene.transform_set", id="nope", transform={"location": [1, 2, 3]})
    assert resolvable()
    # ...an undo restores an earlier snapshot...
    before = d._snapshot()
    assert "butterfly" not in before["mesh_document"]["assets"]  # process state, not document state
    call("mesh.primitive_create", kind="Cube")
    d._restore(before)
    assert resolvable() and d.placements == []
    # ...and a reload from disk swaps the store again.
    d.load_layout()
    assert resolvable()
    # Once a placement references the name it is embedded, so a fresh process sees it.
    d.placements.append(Placement(kind="Mesh3D", name="Butterfly", mesh_kind="butterfly"))
    d.save_layout()
    fresh = HeadlessDesigner.from_skin(d.skin_path)
    assert len(mesh_document.resolve("butterfly", store=fresh.mesh_store).verts) == 8
    # The shim carries no geometry: it resolves through the current document
    # context (the process store when there is none, which is the GUI).
    assert isinstance(pbr.MESH_LIBRARY["butterfly"], mesh_document._ReadThrough)
    with mesh_document.using(fresh):
        assert pbr.MESH_LIBRARY["butterfly"]() is fresh.mesh_store.get("butterfly")


def test_non_canonical_meshes_are_stored_canonically_so_saved_hashes_reload(tmp_path, monkeypatch):
    # Designer deformers register float64 meshes under derived names; 0.1 is
    # not float32-representable, so a raw hash could never survive a reload.
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64) * 0.1
    faces = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int64)
    deformed = pbr.Mesh(verts=verts, faces=faces)
    monkeypatch.setitem(pbr.MESH_LIBRARY, "BendDeformed", lambda m=deformed: m)
    d = HeadlessDesigner.from_skin(tmp_path / "bent.esk")
    d.placements = [Placement(kind="Mesh3D", name="Bent", mesh_kind="BendDeformed")]
    d.save_layout()
    stored = d.mesh_store.get("BendDeformed")
    assert stored.verts.dtype == np.float32 and stored.faces.dtype == np.int32
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())["mesh_document"]
    assert saved["assets"]["BendDeformed"] == mesh_document.to_json(stored)
    reopened = HeadlessDesigner.from_skin(d.skin_path)
    np.testing.assert_array_equal(reopened.mesh_store.get("BendDeformed").verts, stored.verts)
    assert reopened.mesh_store.asset_hash("BendDeformed") == saved["hashes"]["assets"]["BendDeformed"]
    # The direct put path (mesh.register_from_file with a float64 importer) normalises too.
    store = mesh_document.MeshStore()
    store.put("named", deformed)
    assert store.get("named").verts.dtype == np.float32
    canonical = mesh_document.from_json(mesh_document.to_json(deformed))
    assert store.asset_hash("named") == mesh_document.semantic_hash(mesh_document.to_json(canonical))
    assert store.asset_hash("named") != mesh_document.semantic_hash(mesh_document.to_json(deformed))


# --- 4. named keys keep the old library's case-insensitive match ---------------

def test_named_keys_resolve_case_insensitively_within_the_document():
    # Before the store existed, mesh.register_from_file wrote pbr.MESH_LIBRARY[name]
    # and resolve() casefold-scanned that table, so a placement saved with a
    # lowercased mesh_kind still found its CamelCase registration.
    presets = _presets()
    cube, sphere = pbr.MESH_LIBRARY["Cube"](), pbr.MESH_LIBRARY["Sphere"]()
    store = mesh_document.MeshStore()
    store.put("Butterfly", cube)
    for variant in ("butterfly", "BUTTERFLY", "bUtTeRfLy"):
        assert mesh_document.resolve(variant, store=store) is store.get("Butterfly")
    with mesh_document.using(store):
        assert mesh_document.resolve("butterfly") is store.get("Butterfly")
    # An exact key always wins over a case variant.
    store.put("butterfly", sphere)
    assert mesh_document.resolve("butterfly", store=store) is store.get("butterfly")
    assert mesh_document.resolve("Butterfly", store=store) is store.get("Butterfly")
    # Owned keys are exact identities in both directions: neither an
    # upper-cased owned key nor a re-cased label finds the revision.
    p = SimpleNamespace(kind="Mesh3D", props={})
    key = mesh_document.bind(p, cube, label="Wing", store=store)
    for variant in (key.upper(), key.replace("Wing", "wing")):
        with pytest.raises(ValueError, match="missing mesh asset"):
            mesh_document.resolve(variant, store=store)
    # Named keys are never matched across other documents' stores...
    other = mesh_document.MeshStore()
    other.put("Moth", cube)
    with pytest.raises(ValueError, match="missing mesh asset"):
        mesh_document.resolve("moth", store=store)
    # ...but the process store takes part in every document's lookup in both
    # spellings. It is not another document: it is the fallback a Designer
    # that has not adopted a per-document store registers into, so a read
    # dispatched inside a document's context must still find the CamelCase
    # registration for a placement saved with a lowercased mesh_kind.
    mesh_document.default_store().put("Moth", cube)
    try:
        process = mesh_document.default_store()
        assert mesh_document.resolve("Moth", store=store) is process.get("Moth")
        assert mesh_document.resolve("moth", store=store) is process.get("Moth")
        assert mesh_document.resolve("moth") is process.get("Moth")
    finally:
        mesh_document.forget("Moth")
    with pytest.raises(ValueError, match="missing mesh asset"):
        mesh_document.resolve("moth", store=store)
    # Presets still match case-insensitively behind the stores, untouched.
    assert len(mesh_document.resolve("cube", store=store).faces) == len(cube.faces)
    assert _presets() == presets


def test_case_mismatched_reference_is_captured_under_the_referenced_key():
    store = mesh_document.MeshStore()
    store.put("Butterfly", pbr.MESH_LIBRARY["Cube"]())
    p = SimpleNamespace(kind="Mesh3D", props={}, name="B", entity_id="e1", mesh_kind="butterfly")
    document = mesh_document.capture([p], store=store)
    # Adopted under the key the placement references, sharing the canonical object.
    assert set(document["assets"]) == {"butterfly"}
    assert store.get("butterfly") is store.get("Butterfly")
    assert document["hashes"]["assets"]["butterfly"] == store.asset_hash("Butterfly")
    # A fresh process (no "Butterfly" registration) reloads by the exact saved key.
    fresh = mesh_document.MeshStore()
    mesh_document.restore(document, [p], store=fresh)
    assert fresh.keys() == ["butterfly"]
    reloaded = mesh_document.resolve("butterfly", store=fresh)
    assert mesh_document.to_json(reloaded) == document["assets"]["butterfly"]


def test_registered_camelcase_name_binds_a_lowercased_saved_placement(native_session, tmp_path):
    d, session, call = native_session
    obj = tmp_path / "Butterfly.obj"
    obj.write_text(CUBE_OBJ)
    call("mesh.register_from_file", path=str(obj), name="Butterfly")
    # Saved skins carry mesh_kind lowercased against the CamelCase registration
    # (see tools/mesh._build_mesh_for_placement and designer_preview).
    d.placements.append(Placement(kind="Mesh3D", name="Butterfly", mesh_kind="butterfly"))
    d.save_layout()  # used to raise "missing mesh asset: butterfly"
    assert d.mesh_store.get("butterfly") is d.mesh_store.get("Butterfly")
    # Every persistent tool call checkpoints the document through capture.
    pid = d.placements[0].entity_id
    result = call("scene.transform_set", id=pid, transform={"location": [1, 2, 3]})
    assert result["transform"]["location"] == [1.0, 2.0, 3.0]
    # The hit-test / preview path materialises the registered geometry.
    from elysium.aether.tools.mesh import _build_mesh_for_placement
    with mesh_document.using(d):
        mesh, _obj = _build_mesh_for_placement(d.placements[0])
        assert len(mesh.verts) == 8
    # The asset is embedded under the referenced key, so a fresh process that
    # never registered "Butterfly" reloads it by exact key.
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())["mesh_document"]
    assert "butterfly" in saved["assets"]
    fresh = HeadlessDesigner.from_skin(d.skin_path)
    assert len(mesh_document.resolve("butterfly", store=fresh.mesh_store).verts) == 8
    # The registration and the adopted lowercase key are both visible to the
    # Designer's direct reads (exact get and its case-insensitive scan).
    with mesh_document.using(d):
        assert _designer_library_lookup("Butterfly") is d.mesh_store.get("Butterfly")
        assert _designer_library_lookup("butterfly") is d.mesh_store.get("butterfly")


# --- 5. named keys reach the Designer's direct library reads -------------------

def test_registered_and_imported_names_satisfy_the_gui_designers_direct_reads(tmp_path, monkeypatch):
    # The GUI Designer dispatches tools on a designer with no document
    # context and no mesh_store: names land in the process store and must
    # still satisfy its MESH_LIBRARY[mesh_kind]() render path, otherwise the
    # placement mesh.register_from_file promises to rebind stays blank.
    from elysium.aether import Session
    from elysium.aether._headless import MODELS
    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    presets = _presets()
    (tmp_path / "Butterfly.obj").write_text(CUBE_OBJ)
    (tmp_path / "moth.obj").write_text(CUBE_OBJ)
    designer = SimpleNamespace(placements=[], window_doc=SimpleNamespace(w=800.0, h=600.0), menu_status="")
    session = Session(designer=designer, designer_models=MODELS)
    keys = []
    try:
        result = REGISTRY.dispatch(ToolCall("t1", "mesh.register_from_file",
                                            {"path": str(tmp_path / "Butterfly.obj"), "name": "Butterfly"}), session)
        assert result.ok, result.error
        keys.append("Butterfly")
        # A saved skin carries the lowercased mesh_kind: the exact get misses
        # and the worker's case-insensitive scan finds the registration.
        assert pbr.MESH_LIBRARY.get("butterfly") is None
        assert len(_designer_library_lookup("butterfly").verts) == 8
        assert pbr.MESH_LIBRARY["Butterfly"]() is mesh_document.default_store().get("Butterfly")
        # mesh.import_3d embeds the geometry under an owned key only; the
        # placement it creates renders through the same direct read. The
        # filename stem (`mesh_name`) is informational, never a named key.
        result = REGISTRY.dispatch(ToolCall("t2", "mesh.import_3d", {"path": str(tmp_path / "moth.obj")}), session)
        assert result.ok, result.error
        keys.append(result.value["mesh_key"])
        assert result.value["mesh_name"] == "moth"
        assert "moth" not in mesh_document.default_store() and "moth" not in pbr.MESH_LIBRARY
        with pytest.raises(ValueError, match="missing mesh asset"):
            mesh_document.resolve("moth")
        (placement,) = designer.placements
        assert placement.mesh_kind == result.value["mesh_key"]
        assert len(mesh_document.resolve(placement.mesh_kind).verts) == 8
        assert _designer_library_lookup(placement.mesh_kind) is mesh_document.default_store().get(placement.mesh_kind)
        # Shims never replace a genuine factory.
        assert _presets() == presets
    finally:
        for key in keys:
            mesh_document.forget(key)
    assert not any(key in pbr.MESH_LIBRARY for key in keys)


def test_shim_lives_exactly_as_long_as_some_live_store_holds_the_key(monkeypatch):
    presets = _presets()
    cube = pbr.MESH_LIBRARY["Cube"]()
    a, b = mesh_document.MeshStore(), mesh_document.MeshStore()
    a.put("moth", cube)
    shim = pbr.MESH_LIBRARY["moth"]
    assert isinstance(shim, mesh_document._ReadThrough)
    b.put("moth", cube)
    assert pbr.MESH_LIBRARY["moth"] is shim  # idempotent
    # Dropping the key from one store keeps the shim while another holds it.
    a.pop("moth")
    assert pbr.MESH_LIBRARY["moth"] is shim
    # A store that dies without being cleared (a render job's private
    # snapshot, a superseded document store) releases its shims.
    del b
    gc.collect()
    assert "moth" not in pbr.MESH_LIBRARY
    # Owned keys: a live sweep during a render leaves the shim to the
    # snapshot store that still holds the revision, until that one dies.
    p = SimpleNamespace(kind="Mesh3D", props={})
    key = mesh_document.bind(p, cube, label="Wing", store=a)
    private = mesh_document.snapshot_store([p], source=a)
    assert a.retain([]) == [key] and key not in a and key in private
    assert pbr.MESH_LIBRARY[key]() is private.get(key)
    del private
    gc.collect()
    assert key not in pbr.MESH_LIBRARY
    # A genuine factory under the same name (a preset, or one the Designer
    # registered itself) is never shadowed on put nor removed on pop.
    monkeypatch.setitem(pbr.MESH_LIBRARY, "BendDeformed", lambda m=cube: m)
    genuine = pbr.MESH_LIBRARY["BendDeformed"]
    a.put("BendDeformed", cube)
    a.put("Cube", cube)
    assert pbr.MESH_LIBRARY["BendDeformed"] is genuine and pbr.MESH_LIBRARY["Cube"] is presets["Cube"]
    a.pop("BendDeformed")
    a.pop("Cube")
    assert pbr.MESH_LIBRARY["BendDeformed"] is genuine and pbr.MESH_LIBRARY["Cube"] is presets["Cube"]
    assert {k: v for k, v in _presets().items() if k != "BendDeformed"} == presets


# --- 6. imports and registrations never hijack a read-only preset --------------

def _gui_session(tmp_path, monkeypatch):
    """A designer with no document context and no mesh_store: the GUI path."""
    from elysium.aether import Session
    from elysium.aether._headless import MODELS
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    designer = SimpleNamespace(placements=[], window_doc=SimpleNamespace(w=800.0, h=600.0), menu_status="")
    return designer, Session(designer=designer, designer_models=MODELS)


def test_import_3d_stem_never_becomes_a_preset_for_the_document(native_session, tmp_path):
    # Importing sphere.obj used to register "sphere" as a named key, and the
    # case-insensitive store tier then served that one triangle for every
    # "Sphere" placement: the checkpoint persisted it as the preset asset.
    d, session, call = native_session
    presets = _presets()
    sphere_faces = len(pbr.MESH_LIBRARY["Sphere"]().faces)
    obj = tmp_path / "sphere.obj"
    obj.write_text(TRI_OBJ)
    imported = call("mesh.import_3d", path=str(obj))
    assert imported["mesh_name"] == "sphere" and imported["tris"] == 1
    # The owned key carries the geometry; the stem is informational only.
    assert imported["mesh_key"] in d.mesh_store and "sphere" not in d.mesh_store
    assert "sphere" not in pbr.MESH_LIBRARY
    # A preset placement added after the import (Placement's default
    # mesh_kind is "Sphere") keeps the preset in memory and on disk.
    call("placement.add", kind="Mesh3D", x=0, y=0, w=100, h=100)
    assert d.placements[1].mesh_kind == "Sphere"
    with mesh_document.using(d):
        assert len(mesh_document.resolve("Sphere").faces) == sphere_faces
        assert len(mesh_document.resolve("sphere").faces) == sphere_faces
        assert len(mesh_document.resolve(imported["mesh_key"]).faces) == 1
        assert len(_designer_library_lookup("sphere").faces) == sphere_faces
    saved = json.loads((d.skin_path / "designer_layout.json").read_text())["mesh_document"]
    assert len(saved["assets"]["Sphere"]["faces"]) == sphere_faces
    assert len(saved["assets"][imported["mesh_key"]]["faces"]) == 1
    fresh = HeadlessDesigner.from_skin(d.skin_path)
    try:
        faces = {p.mesh_kind: len(mesh_document.resolve(p.mesh_kind, store=fresh.mesh_store).faces)
                 for p in fresh.placements}
        assert faces == {imported["mesh_key"]: 1, "Sphere": sphere_faces}
    finally:
        fresh.mesh_store.clear()
    assert _presets() == presets


def test_gui_path_import_3d_never_leaks_into_other_documents(tmp_path, monkeypatch):
    # The GUI Designer dispatches tools without a document context, so an
    # import's named key used to land in the process store, which every
    # document consulted: cube.obj became "Cube" for the whole process while
    # the Designer's own MESH_LIBRARY["Cube"]() still drew the preset.
    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall
    presets = _presets()
    cube_faces = len(pbr.MESH_LIBRARY["Cube"]().faces)
    (tmp_path / "cube.obj").write_text(TRI_OBJ)
    designer, session = _gui_session(tmp_path, monkeypatch)
    result = REGISTRY.dispatch(ToolCall("t1", "mesh.import_3d", {"path": str(tmp_path / "cube.obj")}), session)
    assert result.ok, result.error
    key = result.value["mesh_key"]
    try:
        assert result.value["mesh_name"] == "cube"
        assert key in mesh_document.default_store() and "cube" not in mesh_document.default_store()
        # Every spelling of the preset name is the preset, on both read paths.
        for kind in ("Cube", "cube", "CUBE"):
            assert len(mesh_document.resolve(kind).faces) == cube_faces
            assert len(_designer_library_lookup(kind).faces) == cube_faces
        assert len(pbr.MESH_LIBRARY["Cube"]().faces) == cube_faces
        assert len(_designer_library_lookup(key).faces) == 1
        # A separate document in the same process resolves and persists the preset.
        other = HeadlessDesigner.from_skin(tmp_path / "other.esk")
        try:
            other.placements.append(Placement(kind="Mesh3D", name="Cube", mesh_kind="Cube"))
            other.save_layout()
            saved = json.loads((other.skin_path / "designer_layout.json").read_text())["mesh_document"]
            assert len(saved["assets"]["Cube"]["faces"]) == cube_faces
            assert len(mesh_document.resolve("Cube", store=other.mesh_store).faces) == cube_faces
        finally:
            other.mesh_store.clear()
        assert _presets() == presets
    finally:
        mesh_document.forget(key)
        mesh_document.forget("cube")  # a regression must not cascade into other tests
    assert key not in pbr.MESH_LIBRARY


def test_presets_win_over_case_variants_held_by_a_store():
    # Exact keys always win; a preset (any spelling) beats a case variant a
    # store holds; a case variant with no preset behind it still matches.
    # This is the order the Designer's own MESH_LIBRARY scan follows, so
    # viewport and preview / export agree on every spelling.
    presets = _presets()
    cube_faces = len(pbr.MESH_LIBRARY["Cube"]().faces)
    tri = mesh_document.from_json({"verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]]})
    store = mesh_document.MeshStore()
    try:
        store.put("cube", tri)
        store.put("Butterfly", tri)
        with mesh_document.using(store):
            assert mesh_document.resolve("cube") is store.get("cube")
            for kind in ("Cube", "CUBE", "cUbE"):
                assert len(mesh_document.resolve(kind).faces) == cube_faces
                assert len(_designer_library_lookup(kind).faces) == cube_faces
            for kind in ("Butterfly", "butterfly", "BUTTERFLY"):
                assert mesh_document.resolve(kind) is store.get("Butterfly")
                assert _designer_library_lookup(kind) is store.get("Butterfly")
            # capture adopts the preset under "Cube", never the store's "cube".
            p = SimpleNamespace(kind="Mesh3D", props={}, name="C", entity_id="e1", mesh_kind="Cube")
            document = mesh_document.capture([p])
            assert len(document["assets"]["Cube"]["faces"]) == cube_faces
            assert store.get("Cube") is not store.get("cube")
            assert mesh_document.snapshot_store([p]).get("Cube") is store.get("Cube")
        assert _presets() == presets
    finally:
        store.clear()


def test_register_from_file_refuses_read_only_preset_names(native_session, tmp_path):
    # A registration that only differs from a preset by case would be served
    # by resolve() for its exact spelling but by the preset for every other
    # spelling (and by the Designer's scan): presets are simply off limits.
    d, session, call = native_session
    presets = _presets()
    cube_faces = len(pbr.MESH_LIBRARY["Cube"]().faces)
    obj = tmp_path / "cube.obj"
    obj.write_text(TRI_OBJ)
    for name in ("Cube", "cube", "CUBE"):
        failed = call.expect_failure("mesh.register_from_file", path=str(obj), name=name)
        assert "preset" in failed.error
        assert name not in d.mesh_store and name not in mesh_document.default_store()
    with mesh_document.using(d):
        assert len(mesh_document.resolve("cube").faces) == cube_faces
    assert _presets() == presets
    # Any other name still registers, case-insensitively resolvable.
    call("mesh.register_from_file", path=str(obj), name="Cubelet")
    with mesh_document.using(d):
        assert mesh_document.resolve("cubelet") is d.mesh_store.get("Cubelet")
