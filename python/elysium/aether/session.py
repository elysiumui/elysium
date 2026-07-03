"""Per-developer session — message history, snapshot store, designer
handle, simulated-event journal."""
from __future__ import annotations

import datetime as _dt
import difflib
import json
import os
import shutil
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .types import Message, TrustMode


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

    def capture(self, session, action: str) -> Snapshot:
        sid = f"snap-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        out = self.base / f"{sid}.tar.gz"
        # Persist in-memory state to disk first so the tarball reflects
        # the live canvas + paired Python file.
        try: session.designer.save_layout()
        except Exception: pass
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
            info = tarfile.TarInfo("history.json")
            info.size = len(mh)
            tar.addfile(info, fileobj=__import__("io").BytesIO(mh.encode()))
        parent = self._index[-1].id if self._index else None
        snap = Snapshot(id=sid, ts=__import__("time").time(),
                         action=action, parent=parent, path=out)
        self._index.append(snap)
        # Roll forward when cap is exceeded.
        while len(self._index) > self.cap:
            old = self._index.pop(0)
            if old.path and old.path.exists(): old.path.unlink()
        self._save_index()
        return snap

    def list(self) -> list[Snapshot]: return list(self._index)

    def get(self, id: str) -> Snapshot | None:
        for s in self._index:
            if s.id == id: return s
        return None

    def restore(self, snap: Snapshot, session) -> None:
        if not snap.path or not snap.path.is_file():
            raise FileNotFoundError(snap.path)
        # Capture pre-restore state so the user can re-restore.
        self.capture(session, action=f"pre-restore({snap.id})")
        with tarfile.open(snap.path, "r:gz") as tar:
            tmp = Path(tempfile.mkdtemp(prefix="aether-restore-"))
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
        shutil.rmtree(tmp, ignore_errors=True)

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
        key = id(placement)
        if key in self._rev_id_table:
            return self._rev_id_table[key]
        new = f"p{len(self._id_table) + 1}"
        self._id_table[new] = placement
        self._rev_id_table[key] = new
        return new

    def lookup(self, ident: str):
        # Try cached id first; fall back to name match.
        p = self._id_table.get(ident)
        if p is not None and p in self.designer.placements: return p
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


__all__ = ["Session", "Snapshot", "SnapshotStore"]
