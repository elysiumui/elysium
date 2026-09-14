"""HeadlessDesigner history: undo/redo round-trips whole documents (mesh
assets included) and transactional rollback restores geometry."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from elysium import aether
from elysium.aether import execution
from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
from elysium.aether.tools import Registry, Tool
from elysium.render import mesh_document, primitives


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


def _designer(tmp_path):
    d = HeadlessDesigner.from_skin(tmp_path / "undo.esk")
    p = Placement(kind="Mesh3D", name="Cube", x=10, y=10, w=100, h=100)
    primitives.bind(p, "Cube", {"size": 2})
    d.placements = [p]
    d.save_layout()
    return d


def _geometry(d):
    return {p.mesh_kind: mesh_document.resolve(p.mesh_kind).verts.copy()
            for p in d.placements if p.kind == "Mesh3D"}


def test_operation_then_undo_then_redo_restores_document_equality(home):
    d = _designer(home)
    session = aether.Session(designer=d, designer_models=MODELS)
    ops = execution.Operations(d, lambda: session)
    before = d._snapshot()
    before_hash = mesh_document.semantic_hash(before["mesh_document"])
    pid = session.id_for(d.placements[0])
    _, fut = ops.submit({"name": "mesh.primitive_update", "args": {"id": pid, "parameters": {"size": 4}}})
    receipt = fut.result()
    assert receipt["status"] == "committed" and receipt["revision"] == 1
    _, fut = ops.submit({"name": "placement.move", "args": {"id": pid, "x": 50, "y": 60}})
    assert fut.result()["revision"] == 2
    after = d._snapshot()
    after_hash = mesh_document.semantic_hash(after["mesh_document"])
    assert after != before and after_hash != before_hash
    assert np.ptp(mesh_document.resolve(d.placements[0].mesh_kind).verts, axis=0).max() == pytest.approx(4)
    assert len(d._undo_stack) == 2 and d._redo_stack == []

    assert d.undo() and d.undo()
    assert d._snapshot() == before
    assert mesh_document.semantic_hash(d._snapshot()["mesh_document"]) == before_hash
    assert np.ptp(mesh_document.resolve(d.placements[0].mesh_kind).verts, axis=0).max() == pytest.approx(2)
    assert d._document_revision == 4 and len(d._redo_stack) == 2
    assert not d.undo()

    assert d.redo() and d.redo()
    assert d._snapshot() == after
    assert mesh_document.semantic_hash(d._snapshot()["mesh_document"]) == after_hash
    assert (d.placements[0].x, d.placements[0].y) == (50, 60)
    assert d._document_revision == 6 and d._redo_stack == []
    assert not d.redo()
    mesh_document.resolve(d.placements[0].mesh_kind)


def test_undo_limit_is_enforced(home):
    d = _designer(home)
    d._undo_limit = 3
    session = aether.Session(designer=d, designer_models=MODELS)
    ops = execution.Operations(d, lambda: session)
    pid = session.id_for(d.placements[0])
    for i in range(5):
        _, fut = ops.submit({"name": "placement.move", "args": {"id": pid, "x": i, "y": 0}})
        assert fut.result()["status"] == "committed"
    assert len(d._undo_stack) == 3
    assert [s["placements"][0]["x"] for s in d._undo_stack] == [1, 2, 3]
    assert d._document_revision == 5
    for _ in range(3):
        assert d.undo()
    assert d.placements[0].x == 1 and not d.undo()


def test_rollback_restores_mesh_assets_not_only_placement_fields(home, monkeypatch):
    d = _designer(home)
    session = aether.Session(designer=d, designer_models=MODELS)
    registry = Registry()
    monkeypatch.setattr(execution, "REGISTRY", registry)
    def rebind_then_fail(session, id):
        p = session.lookup(id)
        primitives.bind(p, "Sphere", {"radius": 3})
        p.x = 999
        return {"error": "rebinding exploded"}
    registry.add(Tool("mesh.rebind", "test", {"type": "object", "properties": {"id": {"type": "string"}},
                      "required": ["id"]}, rebind_then_fail))
    pid = session.id_for(d.placements[0])
    old_key = d.placements[0].mesh_kind
    old_geometry = _geometry(d)
    ops = execution.Operations(d, lambda: session)
    _, fut = ops.submit({"name": "mesh.rebind", "args": {"id": pid}})
    receipt = fut.result()
    assert receipt["status"] == "failed" and "rebinding exploded" in receipt["error"]
    assert receipt["revision"] == 0 and receipt.get("rollback_error") is None
    p = d.placements[0]
    assert p.mesh_kind == old_key and p.x == 10
    np.testing.assert_array_equal(mesh_document.resolve(old_key).verts, old_geometry[old_key])
    assert primitives.settings(p)["kind"] == "Cube"
    assert d._undo_stack == [] and d._document_revision == 0
