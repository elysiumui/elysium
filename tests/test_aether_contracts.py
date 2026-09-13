"""NP-02: tool contracts — schemas validated at registration, one shared
confirmation policy, structured errors, checkpoint/rollback semantics."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from elysium.aether import execution
from elysium.aether.tools import REGISTRY, Registry, Tool
from elysium.aether.types import SideEffect, ToolCall, ToolError, TrustMode, normalize_tool_value

SCHEMA = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}


def _session(trust=TrustMode.COLLABORATIVE, designer=None):
    return SimpleNamespace(trust=trust, designer=designer,
                           snapshots=SimpleNamespace(capture=lambda *a, **k: SimpleNamespace(id="snap")),
                           audit=lambda _: None)


# --- schema contracts --------------------------------------------------------

def test_every_registered_tool_schema_is_valid():
    assert len(REGISTRY.all()) > 100
    for tool in REGISTRY.all():
        Draft202012Validator.check_schema(tool.input_schema)
        assert tool.requires_confirmation in ("never", "destructive", "always"), tool.name
        assert isinstance(tool.side_effect, SideEffect), tool.name


def test_register_tool_rejects_invalid_schema_at_registration():
    with pytest.raises(ValueError, match="broken"):
        Registry().add(Tool("broken", "test", {"type": "list"}, lambda: None))
    with pytest.raises(ValueError, match="requires_confirmation"):
        Registry().add(Tool("policy", "test", SCHEMA, lambda: None, requires_confirmation="sometimes"))
    with pytest.raises(ValueError, match="side_effect"):
        Registry().add(Tool("effect", "test", SCHEMA, lambda: None, side_effect="write"))


def test_schema_violation_names_tool_and_path():
    registry = Registry()
    registry.add(Tool("set", "test", SCHEMA, lambda value: {"value": value}))
    result = registry.dispatch(ToolCall("c", "set", {"value": "nope"}), _session())
    assert not result.ok
    assert "invalid arguments for set" in result.error and "value" in result.error


# --- confirmation policy -----------------------------------------------------

@pytest.mark.parametrize("policy,effect,trust", [
    ("always", SideEffect.READ, TrustMode.AUTONOMOUS),
    ("destructive", SideEffect.DESTRUCTIVE, TrustMode.AUTONOMOUS),
    ("never", SideEffect.WRITE, TrustMode.CAUTIOUS),
])
def test_dispatch_enforces_declared_policy_when_confirmed_is_given(policy, effect, trust):
    registry = Registry()
    ran = []
    registry.add(Tool("set", "test", SCHEMA, lambda value: ran.append(value) or {"value": value},
                      side_effect=effect, requires_confirmation=policy))
    session = _session(trust)
    denied = registry.dispatch(ToolCall("a", "set", {"value": 1}), session, confirmed=False)
    assert not denied.ok and denied.error.startswith("confirmation_required")
    assert ran == []
    allowed = registry.dispatch(ToolCall("b", "set", {"value": 2}), session, confirmed=True)
    assert allowed.ok and ran == [2]
    legacy = registry.dispatch(ToolCall("c", "set", {"value": 3}), session)
    assert legacy.ok and ran == [2, 3]


def test_unrestricted_tools_never_need_confirmation():
    tool = Tool("t", "test", SCHEMA, lambda value: value, side_effect=SideEffect.WRITE)
    assert not execution.confirmation_required(tool, TrustMode.COLLABORATIVE, False)
    assert not execution.confirmation_required(tool, TrustMode.AUTONOMOUS, False)
    assert execution.confirmation_required(tool, TrustMode.CAUTIOUS, False)
    read = Tool("r", "test", SCHEMA, lambda value: value, side_effect=SideEffect.READ)
    assert not execution.confirmation_required(read, TrustMode.CAUTIOUS, False)


def test_policy_helper_is_shared_by_operations_headless_and_daemon(tmp_path, monkeypatch):
    from elysium.aether import daemon as daemon_mod
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    seen = []
    real = execution.confirmation_required
    def spy(tool, trust, confirmed):
        seen.append(tool.name)
        return real(tool, trust, confirmed)
    monkeypatch.setattr(execution, "confirmation_required", spy)
    monkeypatch.setattr(daemon_mod, "confirmation_required", spy)
    d = HeadlessDesigner.from_skin(tmp_path / "policy.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    args = {"kind": "Card", "x": 1, "y": 1, "w": 10, "h": 10}
    # 1. Operations (inline: no dispatcher on the designer).
    ops = execution.Operations(d, lambda: session)
    _, fut = ops.submit({"name": "placement.add", "args": args})
    assert fut.result()["status"] == "committed"
    assert seen.count("placement.add") == 1
    # 2. HeadlessDesigner.dispatch_persistent_tool with an explicit confirmed flag.
    tool = REGISTRY.get("placement.add")
    res = d.dispatch_persistent_tool(ToolCall("h", "placement.add", args), session, REGISTRY, confirmed=False)
    assert res.ok
    assert seen.count("placement.add") >= 2
    # 3. Daemon._dispatch.
    before = len(seen)
    dm = aether.Daemon(session, provider="stub")
    asyncio.run(dm._dispatch(ToolCall("d", "placement.add", args)))
    assert len(seen) > before
    assert len(d.placements) == 3


# --- structured errors ---------------------------------------------------------

def test_tool_error_becomes_structured_failure():
    registry = Registry()
    def boom(value):
        raise ToolError("no_such_thing", f"nothing at {value}", details={"value": value})
    registry.add(Tool("set", "test", SCHEMA, boom))
    result = registry.dispatch(ToolCall("c", "set", {"value": 4}), _session())
    assert not result.ok
    assert result.error == "no_such_thing: nothing at 4"
    assert result.value == {"error": {"code": "no_such_thing", "message": "nothing at 4",
                                      "details": {"value": 4}}}
    assert str(ToolError("a", "b")) == "a: b"
    from elysium import aether
    assert aether.ToolError is ToolError


@pytest.mark.parametrize("value,path", [
    ({"textures": [{"name": "a"}, {"error": "x"}]}, "textures[1].error"),
    ({"job": {"status": "failed", "error": "y"}}, "job.error"),
    ({"probe": {"to_json_err": "ignored", "nested": {"error": {"code": "z"}}}}, "probe.nested.error"),
])
def test_nested_error_keys_become_warnings_not_failures(value, path):
    ok, error, warnings = normalize_tool_value(value)
    assert ok and error is None
    assert len(warnings) == 1 and warnings[0]["path"] == path
    registry = Registry()
    registry.add(Tool("set", "test", SCHEMA, lambda value, _v=value: dict(_v)))
    result = registry.dispatch(ToolCall("c", "set", {"value": 1}), _session())
    assert result.ok and result.error is None and result.warnings == warnings


def test_warning_walk_is_bounded():
    deep = {"error": "leaf"}
    for _ in range(12):
        deep = {"child": deep}
    ok, _, warnings = normalize_tool_value({"root": deep})
    assert ok and warnings == []
    many = {"items": [{"error": f"e{i}"} for i in range(80)]}
    ok, _, warnings = normalize_tool_value(many)
    assert ok and len(warnings) == 50


def test_top_level_ok_false_is_failure():
    assert normalize_tool_value({"ok": False})[:2] == (False, "tool reported ok=false")
    assert normalize_tool_value({"error": {"code": "c", "message": "m"}})[:2] == (False, "m")
    assert normalize_tool_value({"error": ""})[0] is True
    assert normalize_tool_value([1, 2])[0] is True
    registry = Registry()
    registry.add(Tool("set", "test", SCHEMA, lambda value: {"ok": False}))
    result = registry.dispatch(ToolCall("c", "set", {"value": 1}), _session())
    assert not result.ok and result.error == "tool reported ok=false"


# --- daemon writes are transactional -----------------------------------------

def test_checkpoint_failure_aborts_daemon_write(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "daemon.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    def fail(*a, **k):
        raise OSError("checkpoint disk full")
    session.snapshots.capture = fail
    daemon = aether.Daemon(session, provider="stub")
    q = daemon.subscribe()

    async def go():
        task = asyncio.create_task(daemon.turn(
            '/tool placement.add {"kind":"Card","x":40,"y":40,"w":200,"h":120}'))
        results = []
        for _ in range(20):
            ev = await asyncio.wait_for(q.get(), timeout=2.0)
            if ev.kind == "tool_result": results.append(ev.payload)
            if ev.kind == "done": break
        await task
        return results

    results = asyncio.run(go())
    assert len(results) == 1
    assert results[0]["ok"] is False and "Cannot checkpoint" in results[0]["error"]
    assert "disk full" in results[0]["error"]
    assert d.placements == []
    tool_msg = [m for m in session.messages if m.role == "tool"][-1]
    assert json.loads(tool_msg.content)["ok"] is False


def test_daemon_write_does_not_go_through_headless_persist_when_absent(tmp_path, monkeypatch):
    from elysium.aether import daemon as daemon_mod
    from elysium.aether._headless import MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    designer = SimpleNamespace(value=0, _undo_stack=[], _redo_stack=[], _document_revision=0)
    designer._snapshot = lambda: {"value": designer.value}
    designer._restore = lambda snap: setattr(designer, "value", snap["value"])
    assert not hasattr(designer, "dispatch_persistent_tool")
    session = aether.Session(designer=designer, designer_models=MODELS)
    captured = []
    session.snapshots.capture = lambda s, action: captured.append(action) or SimpleNamespace(id="ck")
    registry = Registry()
    monkeypatch.setattr(daemon_mod, "REGISTRY", registry)
    def set_value(session, value):
        session.designer.value = value
        return {"error": "nope"} if value < 0 else {"value": value}
    registry.add(Tool("set", "test", SCHEMA, set_value))
    daemon = aether.Daemon(session, provider="stub")
    ok = asyncio.run(daemon._dispatch(ToolCall("a", "set", {"value": 5})))
    assert ok.ok and ok.snapshot_id == "ck" and designer.value == 5
    assert designer._document_revision == 1 and designer._undo_stack == [{"value": 0}]
    bad = asyncio.run(daemon._dispatch(ToolCall("b", "set", {"value": -1})))
    assert not bad.ok and bad.error == "nope" and bad.snapshot_id == "ck"
    assert designer.value == 5 and designer._document_revision == 1
    assert captured == ["set", "set"]


def test_daemon_serializes_warnings(tmp_path, monkeypatch):
    from elysium.aether import daemon as daemon_mod
    from elysium.aether.types import ToolResult
    res = ToolResult(id="x", ok=True, value={"jobs": [{"error": "late"}]},
                     warnings=[{"path": "jobs[0].error", "message": "late"}])
    assert json.loads(daemon_mod._serialize_result(res))["warnings"] == res.warnings
    assert daemon_mod._serialize_event(res)["warnings"] == res.warnings
    plain = ToolResult(id="y", ok=True, value=1)
    assert "warnings" not in json.loads(daemon_mod._serialize_result(plain))
    assert "warnings" not in daemon_mod._serialize_event(plain)


# --- checkpoints: asset manifest + undoable restore ----------------------------

def _png(path):
    from PIL import Image
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(path)


def test_snapshot_restore_returns_asset_report_and_bumps_revision(tmp_path, monkeypatch):
    import tarfile
    from elysium.aether import session as session_mod
    from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    tex = tmp_path / "wing.png"; _png(tex)
    albedo = tmp_path / "albedo.png"; _png(albedo)
    layer = tmp_path / "layer.png"; _png(layer)
    d = HeadlessDesigner.from_skin(tmp_path / "assets.esk")
    d.placements.append(Placement(kind="Image", name="Pic", texture_path=str(tex),
                                  pbr_albedo_map=str(albedo),
                                  texture_layers=[{"path": str(layer)}],
                                  mesh_part_textures={"wing": str(tex)}))
    assert session_mod.external_asset_refs(d) == [str(tex), str(albedo), str(layer)]
    session = aether.Session(designer=d, designer_models=MODELS)
    snap = session.snapshots.capture(session, action="a")
    with tarfile.open(snap.path) as tar:
        manifest = json.loads(tar.extractfile("assets.json").read())
    assert {m["path"]: m["exists"] for m in manifest} == {str(tex): True, str(albedo): True, str(layer): True}
    assert all(len(m["sha256"]) == 64 for m in manifest)
    tex.unlink()
    from PIL import Image
    Image.new("RGBA", (4, 4), (99, 99, 99, 255)).save(albedo)
    d.placements.append(Placement(kind="Card", name="Extra"))
    revision = d._document_revision
    report = session.snapshots.restore(snap, session)
    assert report == {"restored": snap.id, "missing_assets": [str(tex)],
                      "changed_assets": [str(albedo)]}
    assert d._document_revision == revision + 1
    assert [p.name for p in d.placements] == ["Pic"]


def test_snapshot_restore_through_operations_is_undoable(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "restore.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    ops = execution.Operations(d, lambda: session)
    card = {"kind": "Card", "x": 1, "y": 1, "w": 10, "h": 10}
    assert ops.submit({"name": "placement.add", "args": card})[1].result()["status"] == "committed"
    snap = session.snapshots.capture(session, action="one-card")
    assert ops.submit({"name": "placement.add", "args": {**card, "x": 2}})[1].result()["status"] == "committed"
    assert len(d.placements) == 2
    pre_restore = d._snapshot()
    denied = ops.submit({"name": "snapshot.restore", "args": {"id": snap.id}})[1].result()
    assert denied["status"] == "failed" and "confirmation_required" in denied["error"]
    receipt = ops.submit({"name": "snapshot.restore", "args": {"id": snap.id}, "confirm": True})[1].result()
    assert receipt["status"] == "committed"
    assert receipt["value"] == {"restored": snap.id, "missing_assets": [], "changed_assets": []}
    assert len(d.placements) == 1
    assert receipt["revision"] == d._document_revision == 4     # 2 adds + restore bump + commit bump
    assert d._undo_stack[-1] == pre_restore
    assert d.undo()
    assert d._snapshot() == pre_restore and len(d.placements) == 2
    tool = REGISTRY.get("snapshot.restore")
    assert tool.undoable and tool.side_effect is SideEffect.DESTRUCTIVE
    assert REGISTRY.get("snapshot.branch").side_effect is SideEffect.NONE


# --- classification pass -------------------------------------------------------

def test_dev_tools_are_classified():
    expected = {
        "dev.eval": (SideEffect.DESTRUCTIVE, False, "always"),
        "dev.reload_module": (SideEffect.DESTRUCTIVE, False, "destructive"),
        "dev.reload_designer_module": (SideEffect.DESTRUCTIVE, False, "destructive"),
        "dev.designer_module_info": (SideEffect.READ, False, "never"),
        "dev.dump_placement_attrs": (SideEffect.READ, False, "never"),
        "dev.dump_tool": (SideEffect.READ, False, "never"),
        "dev.thread_dump": (SideEffect.READ, False, "never"),
        "dev.probe_designer": (SideEffect.READ, False, "never"),
        "agent.report_capability_gap": (SideEffect.NONE, False, "never"),
        "texture.read_info": (SideEffect.READ, False, "never"),
        "texture.flush_caches": (SideEffect.NONE, False, "never"),
        "texture.delete_from_library": (SideEffect.DESTRUCTIVE, False, "destructive"),
        "texture.extract_from_image": (SideEffect.NONE, False, "never"),
        "texture.crop_to_match": (SideEffect.NONE, False, "never"),
        "texture.assemble_atlas": (SideEffect.NONE, False, "never"),
        "texture.generate_pbr_maps": (SideEffect.NONE, False, "never"),
        "mesh.save_landmarks": (SideEffect.NONE, False, "never"),
        # Cache / out-of-project file writers: NONE, never READ.
        "mesh.render_part_mask": (SideEffect.NONE, False, "never"),
        "mesh.render_final": (SideEffect.NONE, False, "never"),
        "mesh.world_to_screen": (SideEffect.READ, False, "never"),
        # Library-PNG writers that also bind the result: the binding is
        # undoable, the file is not.
        "material.project_photo": (SideEffect.WRITE, False, "never"),
        "material.project_per_part": (SideEffect.WRITE, False, "never"),
        "texture.transfer_uv_band": (SideEffect.WRITE, False, "never"),
        "mesh.bake_paint_mask_to_uv_albedo": (SideEffect.WRITE, False, "never"),
        "mesh.generate_normal_map_from_albedo": (SideEffect.WRITE, False, "never"),
        "run.start": (SideEffect.NONE, False, "never"),
        "run.stop": (SideEffect.DESTRUCTIVE, False, "never"),
        "run.simulate_input": (SideEffect.NONE, False, "never"),
        "tester.set_baseline": (SideEffect.NONE, False, "never"),
        "tester.replay": (SideEffect.NONE, False, "never"),
        "animation.play": (SideEffect.NONE, False, "never"),
        "animation.set_playhead": (SideEffect.NONE, False, "never"),
        "placement.select": (SideEffect.NONE, False, "never"),
        "view.set_zoom": (SideEffect.NONE, False, "never"),
        "scene.render_start": (SideEffect.NONE, False, "never"),
        "scene.render_cancel": (SideEffect.NONE, False, "never"),
        "code.write_file": (SideEffect.DESTRUCTIVE, False, "destructive"),
        "code.patch": (SideEffect.WRITE, False, "never"),
        "codelink.scaffold": (SideEffect.WRITE, False, "never"),
        "snapshot.branch": (SideEffect.NONE, False, "never"),
        "snapshot.restore": (SideEffect.DESTRUCTIVE, True, "destructive"),
    }
    actual = {name: (t.side_effect, t.undoable, t.requires_confirmation)
              for name in expected for t in [REGISTRY.get(name)] if t is not None}
    assert actual == expected
    # Lasso helpers may append an overlay placement, so they stay writes.
    for name in ("mesh.lasso_tip_pct", "image.lasso_left_wing_tip_pct", "image.lasso_corner_pct"):
        assert REGISTRY.get(name).side_effect is SideEffect.WRITE


def test_none_tools_skip_checkpoint_and_undo(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "none.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    ops = execution.Operations(d, lambda: session)
    receipt = ops.submit({"name": "animation.play", "args": {}})[1].result()
    assert receipt["status"] == "committed" and receipt["snapshot"] is None
    assert receipt["revision"] == 0 and d._undo_stack == [] and d.playing is True
    assert session.snapshots.list() == []


def test_dev_eval_exceptions_report_failure(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "eval.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    res = REGISTRY.dispatch(ToolCall("a", "dev.eval", {"code": "1/0"}), session)
    assert not res.ok and res.error.startswith("eval_failed: ZeroDivisionError")
    assert res.value["error"]["code"] == "eval_failed"
    assert "ZeroDivisionError" in res.value["error"]["details"]["traceback"]
    res = REGISTRY.dispatch(ToolCall("b", "dev.eval", {"code": "def ("}), session)
    assert not res.ok and res.error.startswith("syntax_error:") and "(line 1)" in res.error
    assert res.value["error"]["details"]["offset"] is not None
    res = REGISTRY.dispatch(ToolCall("c", "dev.eval", {"code": "len(designer.placements)"}), session)
    assert res.ok and res.value == {"value": "0"}
    res = REGISTRY.dispatch(ToolCall("d", "dev.eval", {"code": "x = 1\ny = x + 1"}), session)
    assert res.ok and res.value["value"] == "<exec ok>" and "y" in res.value["locals_keys"]
    # Mutation then raise under Operations: DESTRUCTIVE -> rollback.
    ops = execution.Operations(d, lambda: session)
    card = {"kind": "Card", "x": 1, "y": 1, "w": 10, "h": 10}
    assert ops.submit({"name": "placement.add", "args": card})[1].result()["status"] == "committed"
    denied = ops.submit({"name": "dev.eval", "args": {"code": "1"}})[1].result()
    assert denied["status"] == "failed" and "confirmation_required" in denied["error"]
    receipt = ops.submit({"name": "dev.eval", "args": {"code": "designer.placements.clear() or 1/0"},
                          "confirm": True})[1].result()
    assert receipt["status"] == "failed" and receipt["error"].startswith("eval_failed")
    assert receipt["snapshot"].startswith("snap-") and receipt["revision"] == 1
    assert len(d.placements) == 1 and d._document_revision == 1


def test_codelink_goto_missing_handler_is_structured(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS
    from elysium import aether, codelink
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "goto.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    monkeypatch.setattr(codelink, "goto_handler", lambda *a, **k: None)
    res = REGISTRY.dispatch(ToolCall("g", "codelink.goto", {"hook": "save"}), session)
    assert not res.ok and res.error == "handler_not_found: no handler for hook 'save'"
    assert res.value == {"error": {"code": "handler_not_found",
                                   "message": "no handler for hook 'save'", "details": {}}}


def test_snapshot_restore_creates_revision_for_designers_without_one(tmp_path, monkeypatch):
    from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "norev.esk")
    del d._document_revision                  # shaped like the shipped GUI Designer
    session = aether.Session(designer=d, designer_models=MODELS)
    snap = session.snapshots.capture(session, action="a")
    d.placements.append(Placement(kind="Card", name="Extra"))
    report = session.snapshots.restore(snap, session)
    assert report["restored"] == snap.id and d.placements == []
    assert d._document_revision == 1


def test_dispatch_fences_base_exceptions_from_handler_code():
    # The handler boundary turns *everything* a tool raises into a failed
    # result — SystemExit/KeyboardInterrupt included — so transactions
    # always roll back and the caller's future always resolves.
    registry = Registry()
    def bail():
        raise SystemExit(2)
    registry.add(Tool("t.bail", "d", {"type": "object"}, bail,
                      side_effect=SideEffect.READ, undoable=False))
    res = registry.dispatch(ToolCall("x", "t.bail", {}), _session())
    assert res.ok is False and res.error == "SystemExit: 2" and res.value is None


def test_snapshot_restore_keeps_the_checkpoint_its_own_capture_would_evict(tmp_path, monkeypatch):
    # At `cap`, the pre-restore capture rolls the oldest entries off and
    # unlinks their tarballs — the target must not be one of them, or the
    # restore reports an id the store no longer has.
    from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "cap.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    store = session.snapshots
    store.cap = 3
    d.placements.append(Placement(kind="Card", name="Original"))
    target = store.capture(session, action="target")
    d.placements.append(Placement(kind="Card", name="Later"))
    store.capture(session, action="fill-1")
    store.capture(session, action="fill-2")          # run_transaction's own capture
    assert len(store.list()) == store.cap and store.list()[0].id == target.id
    assert target.path.is_file()
    report = store.restore(target, session)
    assert report["restored"] == target.id
    assert [p.name for p in d.placements] == ["Original"]
    assert len(store.list()) <= store.cap
    # The reported checkpoint still exists: the capture rolled a younger
    # entry off instead, so `snapshot.list` still offers it...
    assert store.get(target.id) is not None and target.path.is_file()
    assert [s.action for s in store.list()] == ["target", "fill-2",
                                                f"pre-restore({target.id})"]
    # ...and restoring it a second time still works.
    d.placements.append(Placement(kind="Card", name="Later again"))
    assert store.restore(target, session)["restored"] == target.id
    assert [p.name for p in d.placements] == ["Original"]


def test_restore_through_a_transaction_keeps_the_target_the_wrapper_would_evict(tmp_path,
                                                                                monkeypatch):
    # The live path for every caller (bridge, daemon, headless) is
    # `run_transaction`, whose own checkpoint is taken *before* dispatch and
    # so cannot name the restore target. At `cap` that checkpoint used to
    # evict and unlink the very tarball `snapshot.restore` was about to read.
    from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "txn.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    store = session.snapshots
    store.cap = 3
    d.placements.append(Placement(kind="Card", name="Original"))
    target = store.capture(session, action="target")
    d.placements.append(Placement(kind="Card", name="Later"))
    store.capture(session, action="A")
    store.capture(session, action="B")               # store is now exactly at cap
    tool = REGISTRY.get("snapshot.restore")
    call = ToolCall("c1", "snapshot.restore", {"id": target.id})
    res = execution.run_transaction(d, session, tool, call, registry=REGISTRY,
                                    persist=False, confirmed=True)
    assert res.ok and res.error is None
    assert res.value["restored"] == target.id
    assert [p.name for p in d.placements] == ["Original"]
    # The checkpoint is still listable, still on disk, and still restorable;
    # the wrapper's own checkpoint (the undo entry) survives too.
    assert store.get(target.id) is not None and target.path.is_file()
    assert [s.action for s in store.list()][0] == "target"
    assert "snapshot.restore" in [s.action for s in store.list()]
    assert len(store.list()) <= store.cap
    d.placements.append(Placement(kind="Card", name="Later again"))
    again = execution.run_transaction(d, session, tool,
                                      ToolCall("c2", "snapshot.restore", {"id": target.id}),
                                      registry=REGISTRY, persist=False, confirmed=True)
    assert again.ok and [p.name for p in d.placements] == ["Original"]


def test_bridge_labelled_restore_transaction_also_spares_its_target(tmp_path, monkeypatch):
    # The bridge labels the wrapper `bridge:<tool>`; the store must recognise
    # the prefixed label too, or the HTTP path keeps the old bug.
    from elysium.aether._headless import HeadlessDesigner, MODELS, Placement
    from elysium import aether
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "bridge.esk")
    session = aether.Session(designer=d, designer_models=MODELS)
    store = session.snapshots
    store.cap = 2
    d.placements.append(Placement(kind="Card", name="Original"))
    target = store.capture(session, action="target")
    d.placements.append(Placement(kind="Card", name="Later"))
    store.capture(session, action="A")
    tool = REGISTRY.get("snapshot.restore")
    res = execution.run_transaction(d, session, tool,
                                    ToolCall("b1", "snapshot.restore", {"id": target.id}),
                                    registry=REGISTRY, persist=False, confirmed=True,
                                    action=f"bridge:{tool.name}")
    assert res.ok and res.value["restored"] == target.id
    assert store.get(target.id) is not None and target.path.is_file()
    assert [p.name for p in d.placements] == ["Original"]
