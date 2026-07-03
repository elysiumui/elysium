"""snapshot.*: list / restore / diff / branch checkpoints."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="snapshot.list",
    description="List every snapshot in the current session.",
    input_schema={"type": "object", "properties": {}},
    side_effect=SideEffect.READ,
    undoable=False,
)
def snapshot_list(session) -> dict:
    return {"snapshots": [s.to_dict() for s in session.snapshots.list()]}


@register_tool(
    name="snapshot.restore",
    description="Roll the project back to the named snapshot.",
    input_schema={"type": "object",
                   "properties": {"id": {"type":"string"}},
                   "required": ["id"]},
    side_effect=SideEffect.DESTRUCTIVE,
    requires_confirmation="destructive",
    undoable=False,
)
def snapshot_restore(session, id: str) -> dict:
    snap = session.snapshots.get(id)
    if not snap: raise KeyError(f"snapshot {id} not found")
    session.snapshots.restore(snap, session)
    return {"restored": id}


@register_tool(
    name="snapshot.diff",
    description="Unified diff of the document.json between two snapshots.",
    input_schema={"type": "object",
                   "properties": {"a":{"type":"string"},
                                   "b":{"type":"string"}},
                   "required": ["a","b"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def snapshot_diff(session, a: str, b: str) -> dict:
    sa = session.snapshots.get(a)
    sb = session.snapshots.get(b)
    if not sa or not sb: raise KeyError("snapshot not found")
    return {"diff": session.snapshots.diff(sa, sb)}


@register_tool(
    name="snapshot.branch",
    description="Label the current point as a branch the user can revisit.",
    input_schema={"type": "object",
                   "properties": {"id":{"type":"string"},
                                   "label":{"type":"string"}},
                   "required": ["id","label"]},
)
def snapshot_branch(session, id: str, label: str) -> dict:
    snap = session.snapshots.get(id)
    if not snap: raise KeyError(f"snapshot {id} not found")
    snap.branch_label = label
    return {"branched": id, "label": label}
