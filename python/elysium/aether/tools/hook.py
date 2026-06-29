"""hook.*: declare and annotate skin hooks."""
from __future__ import annotations

from . import register_tool
from ..types import SideEffect


@register_tool(
    name="hook.declare",
    description="Declare a hook on a placement (event / text / value / "
                "state / image / slot / style). For state hooks pass "
                "`options.states`; for value hooks pass `options.range`.",
    input_schema={
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "name": {"type": "string"},
            "kind": {"type": "string"},
            "options": {"type": "object"},
        },
        "required": ["id", "name", "kind"],
    },
)
def hook_declare(session, id: str, name: str, kind: str,
                  options: dict | None = None) -> dict:
    p = session.lookup(id)
    p.props = dict(p.props or {})
    p.props["hook"] = name
    p.props["hook_kind"] = kind
    if options:
        p.props["hook_options"] = options
    return {"hook": name, "kind": kind}


@register_tool(
    name="hook.set_accessible",
    description="Set the accessibility role / label / description on a "
                "placement's hook so screen readers (VoiceOver / JAWS / "
                "Orca) announce it correctly.",
    input_schema={
        "type": "object",
        "properties": {
            "id":          {"type": "string"},
            "role":        {"type": "string"},
            "label":       {"type": "string"},
            "description": {"type": "string"},
            "shortcut":    {"type": "string"},
        },
        "required": ["id", "role"],
    },
)
def hook_set_accessible(session, id: str, role: str,
                         label: str = "", description: str = "",
                         shortcut: str = "") -> dict:
    p = session.lookup(id)
    p.props = dict(p.props or {})
    p.props["accessible"] = {
        "role": role, "label": label,
        "description": description, "keyboard_shortcut": shortcut,
    }
    return {"role": role}


@register_tool(
    name="hook.read",
    description="Read the hook + accessibility metadata for a placement.",
    input_schema={"type": "object",
                   "properties": {"id": {"type": "string"}},
                   "required": ["id"]},
    side_effect=SideEffect.READ,
    undoable=False,
)
def hook_read(session, id: str) -> dict:
    p = session.lookup(id)
    props = p.props or {}
    return {
        "hook":       props.get("hook"),
        "kind":       props.get("hook_kind"),
        "options":    props.get("hook_options"),
        "accessible": props.get("accessible"),
    }
