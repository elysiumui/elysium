"""code.*: read / write / patch arbitrary Python source in the project."""
from __future__ import annotations

from pathlib import Path

from . import register_tool
from ..types import SideEffect


def _safe_path(session, path: str) -> Path:
    p = Path(path).resolve()
    root = session.project_root.resolve()
    if root not in p.parents and p != root:
        raise PermissionError(
            f"refusing path outside project root: {p}")
    return p


@register_tool(
    name="code.read_file",
    description="Read a UTF-8 text file from inside the project root.",
    input_schema={"type": "object",
                   "properties": {"path": {"type":"string"}},
                   "required": ["path"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def code_read_file(session, path: str) -> dict:
    p = _safe_path(session, path)
    return {"path": str(p), "content": p.read_text(encoding="utf-8")}


@register_tool(
    name="code.write_file",
    description="Write a file inside the project root. `mode` is "
                "'overwrite' (default, destructive) or 'append'.",
    input_schema={"type": "object",
                   "properties": {"path":   {"type":"string"},
                                   "content":{"type":"string"},
                                   "mode":   {"type":"string"}},
                   "required": ["path", "content"]},
    side_effect=SideEffect.DESTRUCTIVE,
    requires_confirmation="destructive",
)
def code_write_file(session, path: str, content: str,
                     mode: str = "overwrite") -> dict:
    p = _safe_path(session, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        existing = p.read_text(encoding="utf-8") if p.is_file() else ""
        p.write_text(existing + content, encoding="utf-8")
    else:
        p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes": len(content.encode())}


@register_tool(
    name="code.patch",
    description="Replace the first occurrence of `find` with `replace`. "
                "Fails when `find` is not unique unless `count` is set.",
    input_schema={"type": "object",
                   "properties": {"path":{"type":"string"},
                                   "find":{"type":"string"},
                                   "replace":{"type":"string"},
                                   "count":{"type":"integer"}},
                   "required": ["path","find","replace"]},
)
def code_patch(session, path: str, find: str, replace: str,
                count: int = 1) -> dict:
    p = _safe_path(session, path)
    text = p.read_text(encoding="utf-8")
    occurrences = text.count(find)
    if occurrences == 0:
        raise ValueError(f"find pattern not found in {path}")
    if occurrences > 1 and count == 1:
        raise ValueError(
            f"find pattern occurs {occurrences} times; pass count to "
            f"disambiguate or use a longer find string")
    new = text.replace(find, replace, count if count > 0 else -1)
    p.write_text(new, encoding="utf-8")
    return {"replaced": occurrences if count <= 0 else count}
