"""Authoring persists across interpreters: what a fresh process loads hashes
identically to what the authoring process saved (and checkpointed)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import elysium

PYTHON_DIR = str(Path(elysium.__file__).resolve().parents[1])

AUTHOR_SCRIPT = r'''
import json, sys
from elysium import aether
from elysium.aether._headless import HeadlessDesigner, MODELS
from elysium.aether.types import ToolCall
from elysium.render import mesh_document
skin, session_id = sys.argv[1], sys.argv[2]
d = HeadlessDesigner.from_skin(skin)
s = aether.Session(designer=d, designer_models=MODELS, id=session_id)
def call(name, args):
    r = aether.REGISTRY.dispatch(ToolCall(name, name, args), s)
    assert r.ok, (name, r.error)
    return r.value
call("placement.add", {"kind": "Card", "x": 10, "y": 20, "w": 120, "h": 40, "name": "Hero"})
cube = call("mesh.primitive_create", {"kind": "Cube", "parameters": {"size": 2.5}, "name": "Box"})
call("material.slot_add", {"id": cube["placement_id"], "name": "Base"})
call("scene.light_add", {"values": {}})
d.save_layout()
snap = s.snapshots.capture(s, action="authored")
before = {k: d._snapshot()[k] for k in ("window", "placements", "mesh_document")}
call("placement.move", {"id": cube["placement_id"], "x": 300, "y": 300})
call("placement.add", {"kind": "Button", "x": 1, "y": 1, "w": 10, "h": 10})
d.save_layout()
after = {k: d._snapshot()[k] for k in ("window", "placements", "mesh_document")}
print(json.dumps({"before": mesh_document.semantic_hash(before),
                  "after": mesh_document.semantic_hash(after),
                  "snapshot": snap.id,
                  "entity_ids": [p.entity_id for p in d.placements]}))
'''

REOPEN_SCRIPT = r'''
import json, sys
from elysium import aether
from elysium.aether._headless import HeadlessDesigner, MODELS
from elysium.render import mesh_document
skin, session_id, snapshot_id = sys.argv[1], sys.argv[2], sys.argv[3]
d = HeadlessDesigner.from_skin(skin)
s = aether.Session(designer=d, designer_models=MODELS, id=session_id)
def digest():
    return mesh_document.semantic_hash({k: d._snapshot()[k] for k in ("window", "placements", "mesh_document")})
out = {"loaded": digest(), "entity_ids": [p.entity_id for p in d.placements],
       "mesh_ok": all(mesh_document.resolve(p.mesh_kind) is not None for p in d.placements if p.kind == "Mesh3D")}
if snapshot_id:
    snap = s.snapshots.get(snapshot_id)
    assert snap is not None, "checkpoint index did not persist"
    out["report"] = s.snapshots.restore(snap, s)
    out["restored"] = digest()
    out["restored_entity_ids"] = [p.entity_id for p in d.placements]
    out["revision"] = d._document_revision
print(json.dumps(out))
'''


def _run(script, tmp_path, *args):
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
           "PYTHONPATH": os.pathsep.join(p for p in (PYTHON_DIR, os.environ.get("PYTHONPATH", "")) if p)}
    proc = subprocess.run([sys.executable, "-c", script, *args], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_author_save_reopen_in_fresh_interpreter_preserves_semantic_hash(tmp_path):
    skin = str(tmp_path / "fresh.esk")
    authored = _run(AUTHOR_SCRIPT, tmp_path, skin, "sessionA")
    assert (tmp_path / "fresh.esk" / "designer_layout.json").is_file()
    reopened = _run(REOPEN_SCRIPT, tmp_path, skin, "sessionB", "")
    assert reopened["loaded"] == authored["after"]
    assert reopened["entity_ids"] == authored["entity_ids"] and len(reopened["entity_ids"]) == 3
    assert reopened["mesh_ok"] is True


def test_checkpoint_restore_in_fresh_interpreter(tmp_path):
    skin = str(tmp_path / "ckpt.esk")
    authored = _run(AUTHOR_SCRIPT, tmp_path, skin, "shared")
    assert authored["before"] != authored["after"]
    reopened = _run(REOPEN_SCRIPT, tmp_path, skin, "shared", authored["snapshot"])
    assert reopened["loaded"] == authored["after"]
    assert reopened["restored"] == authored["before"]
    assert reopened["restored_entity_ids"] == authored["entity_ids"][:2]
    assert reopened["report"] == {"restored": authored["snapshot"], "missing_assets": [], "changed_assets": []}
    assert reopened["revision"] == 1
