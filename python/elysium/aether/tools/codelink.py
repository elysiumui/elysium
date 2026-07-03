"""codelink.*: bridge Designer hook names to Python handler functions."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="codelink.scaffold",
    description="Append a Python handler stub for a hook into the "
                "skin's paired source file. Idempotent.",
    input_schema={"type": "object",
                   "properties": {"hook":       {"type":"string"},
                                   "window_var": {"type":"string"}},
                   "required": ["hook"]},
)
def codelink_scaffold(session, hook: str, window_var: str = "win") -> dict:
    from elysium import codelink
    code_file = session.code_file()
    loc = codelink.scaffold_handler(code_file, hook, window_var=window_var)
    return {"file": str(loc.file), "line": loc.line, "function": loc.function}


@register_tool(
    name="codelink.goto",
    description="Open the user's editor at the handler for the given "
                "hook (scaffolds it first if missing).",
    input_schema={"type": "object",
                   "properties": {"hook": {"type":"string"}},
                   "required": ["hook"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def codelink_goto(session, hook: str) -> dict:
    from elysium import codelink
    code_file = session.code_file()
    loc = codelink.goto_handler(code_file, hook,
                                 scaffold_if_missing=True,
                                 known_hooks=session.designer._all_skin_hooks(),
                                 window_var="win")
    return {"file": str(loc.file), "line": loc.line} if loc else {"ok": False}


@register_tool(
    name="codelink.read_handler",
    description="Return the source of the handler function for a hook.",
    input_schema={"type": "object",
                   "properties": {"hook": {"type":"string"}},
                   "required": ["hook"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def codelink_read_handler(session, hook: str) -> dict:
    from elysium import codelink
    code_file = session.code_file()
    idx = codelink.index_handlers(code_file, known_hooks=[hook])
    loc = idx.get(hook)
    if not loc: return {"found": False}
    text = code_file.read_text().splitlines()
    # Slurp lines until indentation returns to column 0 after the def.
    out = [text[loc.line - 1]]
    for line in text[loc.line:]:
        if line and not line[0].isspace() and not line.startswith("@"):
            break
        out.append(line)
    return {"found": True, "source": "\n".join(out),
            "file": str(loc.file), "line": loc.line}
