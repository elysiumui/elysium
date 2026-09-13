"""Reads run inside the Designer's document context, exactly as writes do.

A key only the document's own MeshStore holds — a named registration, a
legacy asset restored from the file — is invisible to anything that
dispatches against the process-wide fallback store. That covers the
bridge's tool journal (READ / NONE tools), its ``GET /snapshot`` preview
and the daemon's own dispatch.
"""
import asyncio
from types import SimpleNamespace

import pytest
from elysium.aether import Session
from elysium.aether._headless import MODELS, HeadlessDesigner, Placement
from elysium.aether.daemon import Daemon
from elysium.aether.execution import Operations, designer_context
from elysium.aether.types import ToolCall
from elysium.render import designer_preview, mesh_document, pbr

NAMED = "Butterfly"


@pytest.fixture
def named_document(tmp_path):
    """A document whose store — and only its store — holds ``Butterfly``."""
    d = HeadlessDesigner.from_skin(tmp_path / "named.esk")
    d.mesh_store.put(NAMED, pbr.MESH_LIBRARY["Cube"]())
    p = Placement(kind="Mesh3D", name=NAMED, mesh_kind=NAMED, w=64, h=64)
    d.placements = [p]
    session = Session(designer=d, designer_models=MODELS)
    assert NAMED not in mesh_document._PROCESS_STORE
    yield d, session, session.id_for(p)
    d.mesh_store.clear()


def cube_verts():
    return len(pbr.MESH_LIBRARY["Cube"]().verts)


def test_read_tool_resolves_a_key_only_the_document_store_holds(named_document):
    d, session, pid = named_document
    ops = Operations(d, lambda: session)
    _, future = ops.submit({"name": "mesh.topology_get", "args": {"id": pid}})
    receipt = future.result(timeout=30)
    assert receipt["status"] == "committed", receipt.get("error")
    assert len(receipt["value"]["topology"]["vertices"]) == cube_verts()


def test_invoke_read_runs_inside_the_document_context(named_document):
    d, session, _ = named_document
    ops = Operations(d, lambda: session)
    assert ops.invoke_read(lambda: mesh_document.default_store()) is d.mesh_store
    assert ops.invoke_read(lambda: len(mesh_document.resolve(NAMED).verts)) == cube_verts()


def test_snapshot_preview_paints_the_documents_mesh_not_the_sphere_fallback(
        named_document, monkeypatch):
    """GET /snapshot goes through invoke_read; a fallback would silently
    substitute the Sphere preset for the document's own geometry."""
    d, session, _ = named_document
    ops = Operations(d, lambda: session)
    designer_preview._MESH_CACHE.clear()
    rendered = []

    def spy(w, h, obj, env, **kwargs):
        rendered.append(len(obj.mesh.verts))
        return b"\0" * (w * h * 4)

    monkeypatch.setattr(pbr, "render_mesh", spy)
    ops.invoke_read(lambda: designer_preview.paint_designer_png(d))
    assert rendered == [cube_verts()]
    assert rendered != [len(pbr.MESH_LIBRARY["Sphere"]().verts)]


def test_daemon_dispatches_reads_inside_the_document_context(named_document):
    _d, session, pid = named_document
    daemon = Daemon(session, provider="stub")
    call = ToolCall("read-1", "mesh.topology_get", {"id": pid})
    result = asyncio.run(daemon._dispatch(call))
    assert result.ok, result.error
    assert len(result.value["topology"]["vertices"]) == cube_verts()


def test_designer_context_nests_without_disturbing_the_outer_binding(named_document):
    """run_transaction enters the context and a handler's own read may
    enter it again; the inner exit must restore, not clear, the binding."""
    d, _session, _ = named_document
    other = HeadlessDesigner.from_skin(d.skin_path.parent / "other.esk")
    try:
        with mesh_document.using(other):
            assert mesh_document.default_store() is other.mesh_store
            with designer_context(d):
                with designer_context(d):
                    assert mesh_document.default_store() is d.mesh_store
                assert mesh_document.default_store() is d.mesh_store
            assert mesh_document.default_store() is other.mesh_store
    finally:
        other.mesh_store.clear()


def test_designer_without_the_hook_still_dispatches(named_document):
    """Older Designers and test doubles define no transaction_context."""
    _d, session, _pid = named_document
    ops = Operations(SimpleNamespace(placements=[]), lambda: session)
    assert ops.invoke_read(lambda: mesh_document.default_store()) is mesh_document._PROCESS_STORE
    assert ops.invoke_read(lambda: "ok") == "ok"


# ---------------------------------------------------------------------------
# Binding reads to the document store must not lose the documented
# case-insensitive fallback. A Designer that has not adopted a per-document
# store registers into the process store, and a saved skin may carry the
# placement's mesh_kind lowercased ("butterfly") while the registration is
# CamelCase ("Butterfly"). Scanning the document store alone made such a read
# fail — and made GET /snapshot silently paint the Sphere preset instead.
# ---------------------------------------------------------------------------

LOWERCASED = NAMED.lower()


@pytest.fixture
def process_registered_document(tmp_path):
    """The name lives in the process store only; the placement lowercases it."""
    d = HeadlessDesigner.from_skin(tmp_path / "process.esk")
    mesh_document._PROCESS_STORE.put(NAMED, pbr.MESH_LIBRARY["Cube"]())
    p = Placement(kind="Mesh3D", name=NAMED, mesh_kind=LOWERCASED, w=64, h=64)
    d.placements = [p]
    session = Session(designer=d, designer_models=MODELS)
    assert LOWERCASED not in d.mesh_store and NAMED not in d.mesh_store
    try:
        yield d, session, session.id_for(p)
    finally:
        d.mesh_store.clear()
        mesh_document.forget(NAMED)


def test_a_case_variant_of_a_process_registered_name_still_resolves(
        process_registered_document):
    d, _session, _pid = process_registered_document
    with designer_context(d):
        assert len(mesh_document.resolve(LOWERCASED).verts) == cube_verts()


def test_read_tool_finds_a_process_registered_name_in_another_case(
        process_registered_document):
    d, session, pid = process_registered_document
    ops = Operations(d, lambda: session)
    _, future = ops.submit({"name": "mesh.topology_get", "args": {"id": pid}})
    receipt = future.result(timeout=30)
    assert receipt["status"] == "committed", receipt.get("error")
    assert len(receipt["value"]["topology"]["vertices"]) == cube_verts()


def test_snapshot_preview_does_not_substitute_the_sphere_for_a_case_variant(
        process_registered_document, monkeypatch):
    """The failure mode is silent: designer_preview falls through to the
    Sphere preset rather than reporting the unresolved name."""
    d, session, _pid = process_registered_document
    ops = Operations(d, lambda: session)
    designer_preview._MESH_CACHE.clear()
    rendered = []

    def spy(w, h, obj, env, **kwargs):
        rendered.append(len(obj.mesh.verts))
        return b"\0" * (w * h * 4)

    monkeypatch.setattr(pbr, "render_mesh", spy)
    ops.invoke_read(lambda: designer_preview.paint_designer_png(d))
    assert rendered == [cube_verts()]
    assert rendered != [len(pbr.MESH_LIBRARY["Sphere"]().verts)]


def test_a_case_variant_is_never_taken_from_another_documents_store(tmp_path):
    """The widened fallback is the process store, not every document."""
    owner = HeadlessDesigner.from_skin(tmp_path / "owner.esk")
    reader = HeadlessDesigner.from_skin(tmp_path / "reader.esk")
    try:
        owner.mesh_store.put(NAMED, pbr.MESH_LIBRARY["Cube"]())
        with designer_context(reader):
            with pytest.raises(ValueError, match="missing mesh asset"):
                mesh_document.resolve(LOWERCASED)
    finally:
        owner.mesh_store.clear()
        reader.mesh_store.clear()
