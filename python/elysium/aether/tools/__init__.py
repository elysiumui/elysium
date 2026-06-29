"""Tool registry: every operation the agent can perform.

Tools are pure functions with JSONSchema-typed signatures. The
registry validates incoming calls, dispatches them against the live
``Session`` (which holds the Designer reference), and returns a
typed ``ToolResult``.
"""
from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from ..types import SideEffect, ToolCall, ToolResult


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]
    side_effect: SideEffect = SideEffect.WRITE
    undoable: bool = True
    requires_confirmation: str = "never"        # never | destructive | always
    output_schema: dict | None = None

    def to_provider_format(self) -> dict:
        """Anthropic / OpenAI tool-call schema shape."""
        return {
            "name":        self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        # Last write wins. This makes `dev.reload_module` work: a re-import
        # of any tools/*.py re-runs the @register_tool decorators, which
        # would otherwise fail with "duplicate tool" on the second pass.
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def dispatch(self, call: ToolCall, session) -> ToolResult:
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(id=call.id, ok=False,
                              error=f"tool_not_found: {call.name}")
        try:
            # Session-aware tools receive `session` as their first arg;
            # plain tools just get the unpacked kwargs.
            sig = inspect.signature(tool.fn)
            kwargs = dict(call.args)
            if "session" in sig.parameters:
                value = tool.fn(session=session, **kwargs)
            else:
                value = tool.fn(**kwargs)
            return ToolResult(id=call.id, ok=True, value=value)
        except Exception as e:
            return ToolResult(id=call.id, ok=False, error=f"{type(e).__name__}: {e}")


REGISTRY = Registry()


def register_tool(
    name: str,
    description: str,
    input_schema: dict,
    *,
    side_effect: SideEffect = SideEffect.WRITE,
    undoable: bool = True,
    requires_confirmation: str = "never",
):
    """Decorator: register the wrapped function as an Aether tool."""
    def deco(fn):
        REGISTRY.add(Tool(
            name=name, description=description,
            input_schema=input_schema, fn=fn,
            side_effect=side_effect, undoable=undoable,
            requires_confirmation=requires_confirmation,
        ))
        return fn
    return deco


# Trigger registration by importing every tool module.
from . import (                                       # noqa: F401  pragma: no cover
    placement, window, shape, material, texture, animation,
    mesh, hook, codelink, code, run, snapshot, meta, tester, brush,
)


__all__ = ["Tool", "Registry", "REGISTRY", "register_tool"]
