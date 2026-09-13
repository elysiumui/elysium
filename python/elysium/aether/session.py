"""Per-developer session — message history, snapshot store, designer
handle, simulated-event journal."""
from __future__ import annotations

import datetime as _dt
import difflib
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .types import Message, TrustMode


# ---------------------------------------------------------------------------
# External asset manifest.
#
# Library textures live in ~/.elysium/textures, are shared between projects
# and can be large, so a checkpoint records them as content hashes instead of
# embedding them. Restore compares the manifest against disk and reports
# `missing_assets` / `changed_assets`. (Material slot images are already
# embedded in the document as png_base64 + sha256.)
# ---------------------------------------------------------------------------

_ASSET_FIELDS = ("image_path", "texture_path", "pbr_albedo_map",
                 "pbr_metallic_rough_map", "pbr_normal_map", "pbr_ao_map",
                 "pbr_emissive_map")
_HASH_LIMIT = 32 * 1024 * 1024


def external_asset_refs(designer) -> list[str]:
    """Every file path a placement references outside the document:
    image/texture bindings, PBR maps, texture layers, per-part textures and
    ``file:`` mesh imports. De-duplicated, in placement order."""
    seen: list[str] = []

    def add(value):
        if isinstance(value, str) and value and value not in seen:
            seen.append(value)

    for p in getattr(designer, "placements", []) or []:
        for name in _ASSET_FIELDS:
            add(getattr(p, name, ""))
        for layer in getattr(p, "texture_layers", None) or []:
            if isinstance(layer, dict):
                add(layer.get("path"))
        parts = getattr(p, "mesh_part_textures", None) or {}
        if isinstance(parts, dict):
            for value in parts.values():
                if isinstance(value, dict):
                    add(value.get("path"))
                else:
                    add(value)
        for key in (getattr(p, "mesh_kind", ""),
                    (getattr(p, "props", None) or {}).get("skin_source_mesh")):
            if isinstance(key, str) and key.startswith("file:"):
                add(key[5:])
    return seen


def _asset_manifest(paths) -> list[dict]:
    out = []
    for raw in paths:
        path = Path(raw).expanduser()
        entry = {"path": str(raw), "exists": path.is_file(), "size": None, "sha256": None}
        if entry["exists"]:
            try:
                size = path.stat().st_size
                entry["size"] = size
                if size <= _HASH_LIMIT:
                    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                entry["exists"] = False
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Snapshot store.
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    id: str
    ts: float
    action: str
    parent: str | None = None
    branch_label: str | None = None
    path: Path | None = None   # tarball location

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path) if self.path else None
        return d


#: Tool whose transaction checkpoint must not evict the checkpoint it is
#: about to restore. Front ends label that checkpoint with the tool name,
#: optionally prefixed by the caller (``bridge:snapshot.restore``).
_RESTORE_TOOL = "snapshot.restore"


def _restores(action: str | None) -> bool:
    """True when ``action`` labels the transaction around ``snapshot.restore``."""
    return bool(action) and str(action).rsplit(":", 1)[-1] == _RESTORE_TOOL


class SnapshotStore:
    """Compressed tarballs of (`.esk` directory + paired Python file +
    agent message log) — one per `write`/`destructive` tool call."""

    def __init__(self, base: Path, cap: int = 200) -> None:
        self.base = base
        self.cap = cap
        self.base.mkdir(parents=True, exist_ok=True)
        self._index: list[Snapshot] = []
        self._load_index()

    def _load_index(self) -> None:
        idx = self.base / "index.json"
        if not idx.is_file(): return
        try:
            raw = json.loads(idx.read_text())
            self._index = [
                Snapshot(id=e["id"], ts=e["ts"], action=e["action"],
                          parent=e.get("parent"),
                          branch_label=e.get("branch_label"),
                          path=Path(e["path"]) if e.get("path") else None)
                for e in raw
            ]
        except Exception: pass

    def _save_index(self) -> None:
        (self.base / "index.json").write_text(
            json.dumps([s.to_dict() for s in self._index], indent=2))

    def _evict(self, keep: str | None = None) -> None:
        """Roll entries off the front until the store is back at ``cap``.

        ``keep`` names one snapshot that must survive: ``restore`` protects
        the checkpoint it is restoring from, so the pre-restore capture rolls
        a younger entry off instead of deleting the very state it reports.
        """
        while len(self._index) > self.cap:
            victim = next((i for i, s in enumerate(self._index) if s.id != keep), None)
            if victim is None:
                break            # only the protected entry is left — keep it
            old = self._index.pop(victim)
            if old.path and old.path.exists(): old.path.unlink()

    def capture(self, session, action: str, *, keep: str | None = None) -> Snapshot:
        """Checkpoint the project and roll old entries off at ``cap``.

        ``keep`` names one entry eviction must not take. A transaction around
        ``snapshot.restore`` cannot name it — the target id lives in the tool
        call, which is dispatched *after* this checkpoint — so a capture whose
        ``action`` labels that transaction defers eviction entirely and the
        store sits one entry over ``cap`` until the next capture. That next
        capture is ``restore``'s own pre-restore one, which does name the
        target, so the checkpoint being restored survives both.
        """
        sid = f"snap-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        out = self.base / f"{sid}.tar.gz"
        # Persist in-memory state to disk first so the tarball reflects
        # the live canvas + paired Python file.
        if session.designer.save_layout() is False:
            raise RuntimeError("Cannot checkpoint: Designer save failed")
        skin = session.designer.skin_path
        code = session.code_file()
        with tarfile.open(out, "w:gz") as tar:
            if skin.is_dir():
                tar.add(skin, arcname=f"skin/{skin.name}")
            if code and Path(code).is_file():
                tar.add(code, arcname=f"code/{Path(code).name}")
            # Pickle the message history alongside the project state.
            mh = json.dumps([{"role": m.role, "content": m.content,
                                "name": m.name, "tool_use_id": m.tool_use_id}
                                for m in session.messages], indent=2)
            _add_member(tar, "history.json", mh)
            # External assets are recorded by hash, not embedded (see above).
            manifest = _asset_manifest(external_asset_refs(session.designer))
            _add_member(tar, "assets.json", json.dumps(manifest, indent=2))
        parent = self._index[-1].id if self._index else None
        snap = Snapshot(id=sid, ts=time.time(),
                         action=action, parent=parent, path=out)
        self._index.append(snap)
        # Roll forward when cap is exceeded — except ahead of a restore whose
        # target is still unknown here; see the docstring.
        if not _restores(action):
            self._evict(keep=keep)
        self._save_index()
        return snap

    def list(self) -> list[Snapshot]: return list(self._index)

    def get(self, id: str) -> Snapshot | None:
        for s in self._index:
            if s.id == id: return s
        return None

    def restore(self, snap: Snapshot, session) -> dict:
        """Roll the project back to ``snap``.

        Copies the skin directory + paired code file back, reloads the
        layout (which restores embedded mesh assets), restores the message
        history, bumps ``_document_revision`` (creating it at 1 for a
        designer that never defined it) and returns ``{"restored", "missing_assets", "changed_assets"}``
        from the external-asset manifest. ``snap`` itself survives both
        checkpoints the call takes — the calling transaction's and the
        pre-restore one below — so restoring it a second time works.
        Undo publication is the calling transaction's job
        (``snapshot.restore`` runs inside one)."""
        if not snap.path or not snap.path.is_file():
            raise FileNotFoundError(snap.path)
        tmp = Path(tempfile.mkdtemp(prefix="aether-restore-"))
        try:
            # Capture pre-restore state so the user can re-restore — without
            # letting that capture evict its own target. A capture at ``cap``
            # rolls the oldest entries off and unlinks their tarballs, and the
            # target is one of them whenever the store is full and the
            # checkpoint is old. ``keep`` rolls off the next entries instead,
            # so the id this restore reports stays listable and restorable.
            # This is also the capture that pays off the eviction the calling
            # transaction's own checkpoint deferred (see ``capture``), so it
            # may roll off two entries — never the target.
            self.capture(session, action=f"pre-restore({snap.id})", keep=snap.id)
            with tarfile.open(snap.path, "r:gz") as tar:
                if sys.version_info >= (3, 12):
                    tar.extractall(tmp, filter="data")
                else:
                    tar.extractall(tmp)
            skin_root = next((tmp / "skin").glob("*"), None)
            if skin_root and skin_root.is_dir():
                shutil.rmtree(session.designer.skin_path, ignore_errors=True)
                shutil.copytree(skin_root, session.designer.skin_path)
                session.designer.load_layout()
            code_dir = tmp / "code"
            code_file = session.code_file()
            if code_dir.is_dir() and code_file:
                for f in code_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(f, Path(code_file))
            history_path = tmp / "history.json"
            if history_path.is_file():
                session.messages = [
                    Message(role=m["role"], content=m["content"],
                             name=m.get("name"),
                             tool_use_id=m.get("tool_use_id"))
                    for m in json.loads(history_path.read_text())
                ]
            manifest_path = tmp / "assets.json"
            recorded = json.loads(manifest_path.read_text()) if manifest_path.is_file() else []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        designer = session.designer
        designer._document_revision = getattr(designer, "_document_revision", 0) + 1
        missing, changed = [], []
        for entry in recorded:
            if not entry.get("exists"):
                continue          # was already absent when captured
            current = _asset_manifest([entry["path"]])[0]
            if not current["exists"]:
                missing.append(entry["path"])
            elif (entry.get("sha256") and current["sha256"]
                  and entry["sha256"] != current["sha256"]):
                changed.append(entry["path"])
        return {"restored": snap.id, "missing_assets": missing, "changed_assets": changed}

    def diff(self, a: Snapshot, b: Snapshot) -> str:
        def _extract(s: Snapshot) -> str:
            with tarfile.open(s.path, "r:gz") as tar:
                for m in tar.getmembers():
                    if m.name.endswith("document.json"):
                        return tar.extractfile(m).read().decode()
            return ""
        ta, tb = _extract(a).splitlines(), _extract(b).splitlines()
        return "\n".join(difflib.unified_diff(
            ta, tb, fromfile=a.id, tofile=b.id, lineterm="", n=2))


# ---------------------------------------------------------------------------
# Session.
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """One developer's live conversation with Aether."""
    designer: Any                                # the Designer instance
    designer_models: Any                         # holds Placement, AnimState classes
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[Message] = field(default_factory=list)
    snapshots: SnapshotStore | None = None
    trust:    TrustMode = TrustMode.COLLABORATIVE
    project_root: Path = field(default_factory=lambda: Path.cwd())
    run_pid: int | None = None
    simulated_events: list[dict] = field(default_factory=list)
    _id_table: dict[str, Any] = field(default_factory=dict)
    _rev_id_table: dict[int, str] = field(default_factory=dict)
    audit_path: Path | None = None

    def __post_init__(self) -> None:
        base = Path.home() / ".elysium" / "aether" / "sessions" / self.id
        base.mkdir(parents=True, exist_ok=True)
        self.snapshots = SnapshotStore(base / "snapshots")
        self.audit_path = base / "audit.jsonl"
        # Project root is the directory holding the skin.
        if hasattr(self.designer, "skin_path"):
            self.project_root = Path(self.designer.skin_path).parent

    # --- placement id ↔ object table ---------------------------------
    def id_for(self, placement) -> str:
        stable = getattr(placement, "entity_id", None)
        if stable is not None:
            from ..scene_identity import parse
            return parse(stable)
        key = id(placement)
        if key in self._rev_id_table:
            return self._rev_id_table[key]
        new = f"p{len(self._id_table) + 1}"
        self._id_table[new] = placement
        self._rev_id_table[key] = new
        return new

    def lookup(self, ident: str):
        # Resolve against the current document, never a pre-undo/rollback copy.
        matches = [p for p in self.designer.placements
                   if getattr(p, "entity_id", None) == ident]
        if len(matches) > 1:
            raise ValueError(f"duplicate scene entity_id: {ident}")
        if matches:
            return matches[0]
        if ident.startswith("entity:"):
            raise KeyError(f"no placement matches scene id {ident!r}")
        # Compatibility for legacy hosts without persistent scene identities.
        p = self._id_table.get(ident)
        if p is not None and any(p is live for live in self.designer.placements):
            return p
        for pl in self.designer.placements:
            if pl.name == ident:
                return pl
        # Fall back to integer index.
        try:
            return self.designer.placements[int(ident)]
        except Exception:
            raise KeyError(f"no placement matches id/name {ident!r}")

    def code_file(self) -> Path:
        path = getattr(self.designer.window_doc, "code_file", "") or ""
        if not path:
            stem = self.designer.skin_path.stem
            path = str(self.designer.skin_path.parent / f"{stem}.py")
            self.designer.window_doc.code_file = path
        return Path(path)

    def audit(self, entry: dict) -> None:
        if not self.audit_path: return
        with self.audit_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def _add_member(tar: tarfile.TarFile, name: str, text: str) -> None:
    payload = text.encode()
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mtime = int(time.time())
    tar.addfile(info, fileobj=io.BytesIO(payload))


__all__ = ["Session", "Snapshot", "SnapshotStore", "external_asset_refs"]
