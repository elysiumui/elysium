"""Aether — the autonomous design + code agent for Elysium UI.

See :doc:`/specs/agent` for the design spec. This module exposes the
public surface: ``Daemon``, ``Session``, ``Provider``, ``Tool``,
``Snapshot``, and the ``register_tool`` decorator used to add new
operations to the registry.
"""
from __future__ import annotations

from .types import (
    Message, ToolCall, ToolResult, StreamEvent,
    ThinkingDelta, MessageDelta, Done,
    TrustMode, SideEffect,
)
from .session import Session, Snapshot
from .tools import Tool, Registry, register_tool, REGISTRY
from .daemon import Daemon
from .providers import Provider, AnthropicProvider, OllamaProvider, StubProvider
from .capabilities import build_manifest
from .feedback import report_capability_gap


__all__ = [
    "Daemon", "Session", "Snapshot",
    "Provider", "AnthropicProvider", "OllamaProvider", "StubProvider",
    "Tool", "Registry", "REGISTRY", "register_tool",
    "Message", "ToolCall", "ToolResult", "StreamEvent",
    "ThinkingDelta", "MessageDelta", "Done",
    "TrustMode", "SideEffect",
    "build_manifest", "report_capability_gap",
]
