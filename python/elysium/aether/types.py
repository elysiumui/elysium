"""Shared dataclasses + protocols. Kept in one file so every other
module imports from a single source of truth (no circular surprises)."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Literal


class TrustMode(enum.Enum):
    CAUTIOUS      = "cautious"        # every write needs ack
    COLLABORATIVE = "collaborative"   # writes auto, destructive needs ack
    AUTONOMOUS    = "autonomous"      # destructive auto except git push


class SideEffect(enum.Enum):
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
    """Result of dispatching one tool call."""
    id: str
    ok: bool
    value: Any = None
    error: str | None = None
    snapshot_id: str | None = None


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
    "Message", "ToolCall", "ToolResult",
    "ThinkingDelta", "MessageDelta", "ToolCallEvent", "Done",
    "StreamEvent",
]
