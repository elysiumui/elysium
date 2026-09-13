"""Shared dataclasses + protocols. Kept in one file so every other
module imports from a single source of truth (no circular surprises)."""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any, Literal


class TrustMode(enum.Enum):
    CAUTIOUS      = "cautious"        # every write needs ack
    COLLABORATIVE = "collaborative"   # writes auto, destructive needs ack
    AUTONOMOUS    = "autonomous"      # destructive auto except git push


class SideEffect(enum.Enum):
    """What a tool may touch. The classification drives checkpointing,
    undo publication, revision bumps and the confirmation policy:

    * ``READ`` — no mutation anywhere.
    * ``NONE`` — no *document* mutation; may touch transient view/playback
      state, session journals, out-of-project caches or logs. No
      checkpoint, no undo entry, no revision bump.
    * ``WRITE`` — mutates the document (placements/window/mesh/material/
      animation) or the paired code file. Checkpoint + undo entry +
      revision bump.
    * ``DESTRUCTIVE`` — irrecoverable outside the document checkpoint
      (file delete/overwrite, process kill, arbitrary code, module reload).
      Checkpoint + confirmation per policy.
    """
    NONE         = "none"
    READ         = "read"
    WRITE        = "write"
    DESTRUCTIVE  = "destructive"


@dataclass
class Message:
    """One turn in the LLM conversation."""
    role: Literal["user", "assistant", "tool"]
    content: str | list[dict] = ""
    name: str | None = None        # for tool messages: tool name
    tool_use_id: str | None = None  # for tool messages: which call


@dataclass
class ToolCall:
    """A model-issued call to a registered tool."""
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    """Result of dispatching one tool call.

    ``warnings`` collects nested ``error`` keys a handler reported for
    individual items (see :func:`normalize_tool_value`); they never flip
    ``ok``. ``rollback_error`` is set when a failed transaction could not
    restore the pre-call document.
    """
    id: str
    ok: bool
    value: Any = None
    error: str | None = None
    snapshot_id: str | None = None
    warnings: list[dict] = field(default_factory=list)
    rollback_error: str | None = None


class ToolError(Exception):
    """Structured failure a tool handler raises on purpose.

    The registry turns it into a failed :class:`ToolResult` whose value is
    ``{"error": {"code", "message", "details"}}`` so clients can branch on
    ``code`` instead of parsing prose.
    """

    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


_WARN_MAX_DEPTH = 8
_WARN_MAX_ENTRIES = 50


def normalize_tool_value(value: Any) -> tuple[bool, str | None, list[dict]]:
    """Decide whether a handler's return value is a failure.

    Returns ``(ok, error, warnings)``. Only a *top-level* truthy ``error``
    key or a top-level ``ok is False`` fails the call. ``error`` keys nested
    deeper (per-item reports such as ``textures[3].error`` or a render
    job's ``job.error``) are collected as warnings — bounded to a depth of
    8 and 50 entries — and never flip ``ok``.
    """
    if not isinstance(value, dict):
        return True, None, []
    err = value.get("error")
    if err:
        if isinstance(err, str):
            message = err
        elif isinstance(err, dict):
            message = err.get("message") or json.dumps(err, default=str)
        else:
            message = json.dumps(err, default=str)
        return False, str(message), []
    if value.get("ok") is False:
        return False, "tool reported ok=false", []
    warnings: list[dict] = []

    def walk(node, path, depth):
        if len(warnings) >= _WARN_MAX_ENTRIES or depth > _WARN_MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key == "error" and child:
                    warnings.append({"path": child_path, "message": str(child)[:200]})
                    if len(warnings) >= _WARN_MAX_ENTRIES:
                        return
                elif isinstance(child, (dict, list)):
                    walk(child, child_path, depth + 1)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                if isinstance(child, (dict, list)):
                    walk(child, f"{path}[{index}]", depth + 1)

    for key, child in value.items():
        if isinstance(child, (dict, list)):
            walk(child, str(key), 1)
    return True, None, warnings


# --- Streaming events emitted by Provider.stream() ------------------------

@dataclass
class ThinkingDelta:
    text: str


@dataclass
class MessageDelta:
    text: str


@dataclass
class ToolCallEvent:
    call: ToolCall


@dataclass
class Done:
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)


StreamEvent = ThinkingDelta | MessageDelta | ToolCallEvent | Done


__all__ = [
    "TrustMode", "SideEffect",
    "Message", "ToolCall", "ToolResult", "ToolError", "normalize_tool_value",
    "ThinkingDelta", "MessageDelta", "ToolCallEvent", "Done",
    "StreamEvent",
]
