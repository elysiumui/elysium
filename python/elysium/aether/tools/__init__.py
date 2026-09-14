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

from ..types import SideEffect, ToolCall, ToolError, ToolResult, normalize_tool_value

_CONFIRMATION_POLICIES = ("never", "destructive", "always")


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
        # Contract checks happen at registration so a broken tool fails
        # `import elysium.aether` loudly instead of failing its first call.
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
        try:
            Draft202012Validator.check_schema(tool.input_schema)
        except SchemaError as e:
            raise ValueError(f"tool {tool.name!r}: invalid input_schema: {e.message}") from e
        if tool.requires_confirmation not in _CONFIRMATION_POLICIES:
            raise ValueError(f"tool {tool.name!r}: requires_confirmation must be one of "
                             f"{_CONFIRMATION_POLICIES}, got {tool.requires_confirmation!r}")
        if not isinstance(tool.side_effect, SideEffect):
            raise ValueError(f"tool {tool.name!r}: side_effect must be a SideEffect, "
                             f"got {tool.side_effect!r}")
        # Last write wins. This makes `dev.reload_module` work: a re-import
        # of any tools/*.py re-runs the @register_tool decorators, which
        # would otherwise fail with "duplicate tool" on the second pass.
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def dispatch(self, call: ToolCall, session, *, confirmed: bool | None = None) -> ToolResult:
        """Validate ``call.args`` against the tool's schema and run it.

        ``confirmed`` opts into the shared confirmation policy
        (:func:`elysium.aether.execution.confirmation_required`): pass
        ``True``/``False`` to enforce it against ``session.trust``; leave it
        ``None`` for callers that already gated the call themselves.
        """
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(id=call.id, ok=False,
                              error=f"tool_not_found: {call.name}")
        try:
            # Lazy: execution imports this module for REGISTRY.
            from ..execution import confirmation_required, validate_args
            validate_args(tool, call.args)
            if confirmed is not None:
                from ..types import TrustMode
                trust = getattr(session, "trust", TrustMode.COLLABORATIVE)
                if confirmation_required(tool, trust, confirmed):
                    return ToolResult(id=call.id, ok=False,
                                      error="confirmation_required: resubmit with confirm=true and a new id")
            # Session-aware tools receive `session` as their first arg;
            # plain tools just get the unpacked kwargs.
            sig = inspect.signature(tool.fn)
            kwargs = dict(call.args)
            if "session" in sig.parameters:
                value = tool.fn(session=session, **kwargs)
            else:
                value = tool.fn(**kwargs)
            ok, error, warnings = normalize_tool_value(value)
            return ToolResult(id=call.id, ok=ok, value=value, error=error, warnings=warnings)
        except ToolError as e:
            return ToolResult(id=call.id, ok=False, error=str(e), value={"error": e.to_dict()})
        except BaseException as e:  # noqa: BLE001 — the handler boundary
            # Nothing a handler raises escapes as an exception, SystemExit
            # and KeyboardInterrupt included (``exit()`` inside dev.eval,
            # say): escaping would skip the transaction's rollback, leave
            # the operation's future unresolved and end the frame loop. A
            # failed result keeps every caller's contract instead.
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
    mesh, hook, codelink, code, run, snapshot, meta, tester, brush, primitives, scene,
)


__all__ = ["Tool", "Registry", "REGISTRY", "register_tool"]
