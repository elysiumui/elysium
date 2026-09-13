"""Every shipped .esk opens, legacy named mesh keys included.

Documents saved before geometry was embedded carry only the *name* of
their mesh ("Butterfly"), which used to live in the process-wide
MESH_LIBRARY. A fresh process has no such registration, and refusing to
open the project would strand every skin shipped in that format.
"""
import json
from pathlib import Path

import pytest
from elysium.aether._headless import HeadlessDesigner, Placement
from elysium.render import mesh_document, primitives

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def example_projects():
    return sorted(p for p in EXAMPLES.rglob("*.esk") if p.is_dir())


def test_the_repository_ships_example_projects():
    assert example_projects(), f"no .esk projects under {EXAMPLES}"


@pytest.mark.parametrize("project", example_projects(), ids=lambda p: p.name)
def test_every_shipped_example_project_opens(project):
    d = HeadlessDesigner.from_skin(project)
    assert d.skin_path == project.resolve()
    for p in d.placements:
        if p.kind == "Mesh3D":
            assert isinstance(p.mesh_kind, str) and p.mesh_kind
    d.mesh_store.clear()


def test_hello_opens_with_its_unregistered_name_reported_not_raised():
    """`examples/hello` references "Butterfly" and embeds no geometry."""
    d = HeadlessDesigner.from_skin(EXAMPLES / "hello" / "hello.esk")
    try:
        assert [p.mesh_kind for p in d.placements if p.kind == "Mesh3D"] == ["Butterfly"]
        assert d.missing_mesh_names == ["Butterfly"]
        assert "Butterfly" in d.menu_status and "mesh.register_from_file" in d.menu_status
    finally:
        d.mesh_store.clear()


def legacy_layout(tmp_path, mesh_kind, props=None):
    """A document with no ``mesh_document`` key, as saved before embedding."""
    project = tmp_path / "legacy.esk"
    project.mkdir()
    placement = Placement(kind="Mesh3D", name="Wing", mesh_kind=mesh_kind,
                          props=dict(props or {})).to_json()
    (project / "designer_layout.json").write_text(json.dumps({
        "window": {"name": "MainWindow"}, "placements": [placement]}))
    return project


def test_legacy_named_key_resolves_through_the_process_store_when_registered(tmp_path):
    project = legacy_layout(tmp_path, "Moth")
    mesh_document._PROCESS_STORE.put("Moth", primitives.build("Cube", {"size": 2})[0])
    try:
        d = HeadlessDesigner.from_skin(project)
        assert d.missing_mesh_names == []
        assert len(mesh_document.resolve("Moth", store=d.mesh_store).verts) == 8
        d.mesh_store.clear()
    finally:
        mesh_document.forget("Moth")


def test_legacy_document_naming_an_owned_revision_is_still_rejected(tmp_path):
    """Only an embedding document may name a ``mesh:`` revision."""
    project = legacy_layout(tmp_path, "mesh:wing:deadbeef")
    with pytest.raises(ValueError, match="missing mesh asset"):
        HeadlessDesigner.from_skin(project)


def test_embedded_document_missing_its_own_asset_still_fails(tmp_path):
    """The tamper check is untouched: a document that claims to carry its
    geometry must actually carry it."""
    d = HeadlessDesigner.from_skin(tmp_path / "owned.esk")
    p = Placement(kind="Mesh3D", name="Cube")
    primitives.bind(p, "Cube", store=d.mesh_store)
    d.placements = [p]
    d.save_layout()
    layout = d.skin_path / "designer_layout.json"
    data = json.loads(layout.read_text())
    data["mesh_document"]["assets"].pop(p.mesh_kind)
    data["mesh_document"]["hashes"]["assets"].pop(p.mesh_kind)
    layout.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="missing referenced mesh asset"):
        HeadlessDesigner.from_skin(d.skin_path)
    d.mesh_store.clear()


# ---------------------------------------------------------------------------
# A document that opens must also be writable.
#
# Reporting the unresolved name instead of raising only moved the failure:
# `capture()` adopts every referenced key, and it sits on both the
# `_snapshot()` checkpoint path and the `save_layout()` path, so every write
# command and every save died on the same name — including commands on
# placements that have nothing to do with the broken mesh, and including the
# `mesh.register_from_file` rebind the status message recommends.
# ---------------------------------------------------------------------------

CUBE_OBJ = """
v -1 -1 -1
v  1 -1 -1
v  1  1 -1
v -1  1 -1
v -1 -1  1
v  1 -1  1
v  1  1  1
v -1  1  1
f 1 2 3
f 1 3 4
f 5 6 7
f 5 7 8
f 1 2 6
f 1 6 5
f 2 3 7
f 2 7 6
f 3 4 8
f 3 8 7
f 4 1 5
f 4 5 8
"""


@pytest.fixture
def hello_project(tmp_path):
    """A writable copy of the shipped legacy project (names "Butterfly")."""
    import shutil
    project = tmp_path / "hello.esk"
    shutil.copytree(EXAMPLES / "hello" / "hello.esk", project)
    return project


def open_session(project):
    from elysium.aether import Session
    from elysium.aether._headless import MODELS
    d = HeadlessDesigner.from_skin(project)
    return d, Session(designer=d, designer_models=MODELS)


def dispatch(designer, session, tool, **args):
    import uuid

    from elysium.aether.tools import REGISTRY
    from elysium.aether.types import ToolCall
    return designer.dispatch_persistent_tool(
        ToolCall(uuid.uuid4().hex, tool, args), session, REGISTRY)


def test_an_unresolved_legacy_name_does_not_freeze_the_document(hello_project):
    """Every write path works, and the name survives the round-trip."""
    d, session = open_session(hello_project)
    try:
        assert d.missing_mesh_names == ["Butterfly"]
        # Both read-only payload paths (save_layout, scene.document_hash).
        d.layout_payload()
        d.save_layout()

        # A command on an unrelated, healthy placement.
        unrelated = next(p for p in d.placements if p.kind != "Mesh3D")
        moved = dispatch(d, session, "placement.move",
                         id=session.id_for(unrelated), x=42.0, y=17.0)
        assert moved.ok, moved.error
        # And one on the placement whose mesh cannot be resolved.
        broken = next(p for p in d.placements if p.kind == "Mesh3D")
        posed = dispatch(d, session, "scene.transform_set",
                         id=session.id_for(broken), transform={"location": [1, 0, 0]})
        assert posed.ok, posed.error
        assert d.undo() and d.redo()
    finally:
        d.mesh_store.clear()

    # The saved document still names the mesh and still reports it on reopen;
    # it embeds no geometry for a name this process never resolved.
    saved = json.loads((hello_project / "designer_layout.json").read_text())
    assert [p["mesh"]["kind"] for p in saved["placements"]
            if p["kind"] == "Mesh3D"] == ["Butterfly"]
    assert "Butterfly" not in saved["mesh_document"]["assets"]
    reopened = HeadlessDesigner.from_skin(hello_project)
    try:
        assert reopened.missing_mesh_names == ["Butterfly"]
        assert [p.mesh_kind for p in reopened.placements
                if p.kind == "Mesh3D"] == ["Butterfly"]
    finally:
        reopened.mesh_store.clear()


def test_the_advertised_rebind_commits_and_then_embeds_the_geometry(
        hello_project, tmp_path):
    """`mesh.register_from_file` is a WRITE tool: it has to get past the
    checkpoint that the unresolved name used to fail."""
    model = tmp_path / "butterfly.obj"
    model.write_text(CUBE_OBJ)
    d, session = open_session(hello_project)
    try:
        assert "mesh.register_from_file" in d.menu_status
        result = dispatch(d, session, "mesh.register_from_file",
                          path=str(model), name="Butterfly")
        assert result.ok, result.error
        assert d.missing_mesh_names == []
        assert len(mesh_document.resolve("Butterfly", store=d.mesh_store).verts) == 8
        d.save_layout()
    finally:
        d.mesh_store.clear()
    saved = json.loads((hello_project / "designer_layout.json").read_text())
    assert "Butterfly" in saved["mesh_document"]["assets"]


def test_a_name_the_process_knows_is_still_embedded_even_when_tolerated(tmp_path):
    """`unresolved` relaxes nothing for a key that actually resolves."""
    project = legacy_layout(tmp_path, "Moth")
    mesh_document._PROCESS_STORE.put("Moth", primitives.build("Cube", {"size": 2})[0])
    try:
        d = HeadlessDesigner.from_skin(project)
        d.missing_mesh_names = ["Moth"]  # a stale report must not lose geometry
        assert "Moth" in d.layout_payload()["mesh_document"]["assets"]
        d.mesh_store.clear()
    finally:
        mesh_document.forget("Moth")


def test_capture_never_omits_an_owned_revision(tmp_path):
    """Only a document that owns a ``mesh:`` revision may name one."""
    d = HeadlessDesigner.from_skin(tmp_path / "owned.esk")
    p = Placement(kind="Mesh3D", name="Ghost", mesh_kind="mesh:ghost:deadbeef")
    d.placements = [p]
    with pytest.raises(ValueError, match="missing mesh asset"):
        mesh_document.capture(d.placements, store=d.mesh_store,
                              unresolved=["mesh:ghost:deadbeef"])
    d.mesh_store.clear()


# ---------------------------------------------------------------------------
# The notice is a report, not a running commentary.
#
# `after_commit` runs after EVERY committed command, so re-announcing an
# unchanged unresolved-name notice there overwrote `menu_status` — the one
# channel a tool has to say what it just did (GET /state, GET /logs,
# meta.live_menu_status, the CLI's `# status:` line) — for the whole life of
# a legacy document.
# ---------------------------------------------------------------------------


def test_a_commit_keeps_the_tools_own_status_while_a_name_is_unresolved(hello_project):
    d, session = open_session(hello_project)
    try:
        assert d.missing_mesh_names == ["Butterfly"]
        ball = next(p for p in d.placements if p.name == "Ball")
        d._get_paint_mask(ball)  # the live Brush tool's lazily built mask
        cleared = dispatch(d, session, "texture.clear_paint_mask",
                           id=session.id_for(ball))
        assert cleared.ok, cleared.error
        assert d.menu_status == "PaintMask cleared on Ball"
        # The machine-readable channel still carries the unresolved name.
        assert d.missing_mesh_names == ["Butterfly"]
        # And a second, unrelated commit does not resurrect the banner.
        moved = dispatch(d, session, "placement.move",
                         id=session.id_for(ball), x=12.0, y=9.0)
        assert moved.ok, moved.error
        assert "Unresolved mesh names" not in d.menu_status
    finally:
        d.mesh_store.clear()


def test_the_commit_that_binds_the_last_name_still_reports_the_transition(
        hello_project, tmp_path):
    """A real change to the set is still worth saying out loud."""
    model = tmp_path / "butterfly.obj"
    model.write_text(CUBE_OBJ)
    d, session = open_session(hello_project)
    try:
        result = dispatch(d, session, "mesh.register_from_file",
                          path=str(model), name="Butterfly")
        assert result.ok, result.error
        assert d.missing_mesh_names == []
        assert "bound again" in d.menu_status
    finally:
        d.mesh_store.clear()


def test_a_legacy_skin_source_mesh_name_is_reported_like_any_other(tmp_path):
    """`mesh_document.referenced_keys` — the set `capture` adopts — is
    `mesh_kind` PLUS `props["skin_source_mesh"]`. Tolerating only the first
    left the second to raise `missing mesh asset` out of every checkpoint
    and every save: the same freeze, through the other key."""
    project = legacy_layout(tmp_path, "Cube", props={"skin_source_mesh": "Butterfly"})
    d = HeadlessDesigner.from_skin(project)
    try:
        assert d.missing_mesh_names == ["Butterfly"]
        assert "Butterfly" in d.menu_status
        payload = d.layout_payload()
        assert "Butterfly" not in payload["mesh_document"]["assets"]
        assert "Cube" in payload["mesh_document"]["assets"]
        d._snapshot()
        d.save_layout()
        reopened = HeadlessDesigner.from_skin(project)
        try:
            assert reopened.missing_mesh_names == ["Butterfly"]
            assert reopened.placements[0].props["skin_source_mesh"] == "Butterfly"
        finally:
            reopened.mesh_store.clear()
    finally:
        d.mesh_store.clear()


def test_scene_view_snapshot_renders_a_legacy_document_with_an_unresolved_name(tmp_path):
    """GET /snapshot must not 500 on a document that deliberately opens.

    The 2D branch has always substituted a preset for an unresolvable mesh;
    the scene branch composes one shared buffer and used to let the
    ValueError escape, so `paint_designer_png` — the function behind the
    bridge's snapshot endpoint — raised for exactly the legacy documents
    this release made openable.
    """
    from elysium.render import designer_preview

    designer = HeadlessDesigner.from_skin("examples/hello/hello.esk")
    assert designer.missing_mesh_names, "fixture must carry an unresolved name"

    designer.window_doc.scene_view = False
    assert designer_preview.paint_designer_png(designer)

    designer.window_doc.scene_view = True
    assert designer_preview.paint_designer_png(designer)


def test_scene_preview_keeps_the_placements_it_can_resolve():
    from types import SimpleNamespace

    from elysium.render import designer_preview

    resolves = designer_preview._scene_mesh_resolves
    assert resolves(SimpleNamespace(kind="Mesh3D", mesh_kind="Cube"))
    assert not resolves(SimpleNamespace(kind="Mesh3D", mesh_kind="no-such-mesh"))
    assert resolves(SimpleNamespace(kind="Image"))
