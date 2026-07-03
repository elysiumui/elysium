"""Aether daemon — the long-running conversation host.

v1 embeds in the Designer's process; clients subscribe via in-process
streaming. v2 (Phase 4.2) lifts the daemon into a standalone process
behind the JSON-RPC-over-UDS transport already documented in the spec —
the public surface stays identical so the lift is transparent.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable

from .providers import Provider, make_provider
from .session import Session
from .system_prompt import build as build_system_prompt
from .tools import REGISTRY
from .types import (Done, Message, MessageDelta, SideEffect, StreamEvent,
                      ThinkingDelta, ToolCall, ToolCallEvent, ToolResult,
                      TrustMode)


@dataclass
class StepEvent:
    """Daemon-side surface. Wraps low-level StreamEvents + ToolResults
    into one stream a client can consume."""
    kind: str   # thinking | text | tool_call | tool_result | done | error
    payload: dict


class Daemon:
    """One daemon per session. Holds the provider, the registry, and the
    tool-use loop. Concurrent client subscriptions get the same stream."""

    def __init__(self, session: Session, provider: str | Provider | None = None,
                  approve_callback: Callable[[ToolCall, str], bool] | None = None) -> None:
        self.session = session
        self.provider: Provider = make_provider(provider)
        self.subscribers: list[asyncio.Queue] = []
        self._paused = asyncio.Event(); self._paused.set()    # set = running
        self.approve_callback = approve_callback or (lambda *_: True)

    # ----- public ------------------------------------------------------
    async def turn(self, user_text: str) -> None:
        """Process one user message: stream from provider, dispatch tools,
        loop until the model emits a final assistant message."""
        self.session.messages.append(Message(role="user", content=user_text))
        self._broadcast(StepEvent("user_message", {"text": user_text}))
        await self._loop()

    def pause(self) -> None:  self._paused.clear()
    def resume(self) -> None: self._paused.set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers: self.subscribers.remove(q)

    # ----- internal ----------------------------------------------------
    async def _loop(self) -> None:
        while True:
            await self._paused.wait()
            system = build_system_prompt(self.session)
            tools = REGISTRY.all()
            assistant_text_buf: list[str] = []
            pending_tool_calls: list[ToolCall] = []
            stop_reason = "end_turn"

            try:
                async for ev in self.provider.stream(
                        system, self.session.messages, tools):
                    if isinstance(ev, ThinkingDelta):
                        self._broadcast(StepEvent("thinking", {"text": ev.text}))
                    elif isinstance(ev, MessageDelta):
                        assistant_text_buf.append(ev.text)
                        self._broadcast(StepEvent("text", {"text": ev.text}))
                    elif isinstance(ev, ToolCallEvent):
                        pending_tool_calls.append(ev.call)
                        self._broadcast(StepEvent("tool_call", {
                            "id": ev.call.id, "name": ev.call.name,
                            "args": ev.call.args,
                        }))
                    elif isinstance(ev, Done):
                        stop_reason = ev.stop_reason
            except Exception as e:
                self._broadcast(StepEvent("error",
                    {"where": "provider", "msg": str(e)}))
                return

            # Materialise the assistant turn into the message history.
            assistant_content = []
            if assistant_text_buf:
                assistant_content.append(
                    {"type": "text", "text": "".join(assistant_text_buf)})
            for tc in pending_tool_calls:
                assistant_content.append({"type": "tool_use",
                    "id": tc.id, "name": tc.name, "input": tc.args})
            if assistant_content:
                self.session.messages.append(
                    Message(role="assistant", content=assistant_content))

            # Dispatch any tool calls; surface results back into the loop.
            if pending_tool_calls:
                for call in pending_tool_calls:
                    res = await self._dispatch(call)
                    self.session.messages.append(Message(
                        role="tool",
                        tool_use_id=call.id,
                        name=call.name,
                        content=_serialize_result(res)))
                # Continue the loop — model needs to react to the
                # results before emitting a final message.
                continue

            self._broadcast(StepEvent("done", {"stop_reason": stop_reason}))
            return

    async def _dispatch(self, call: ToolCall) -> ToolResult:
        tool = REGISTRY.get(call.name)
        if tool is None:
            res = ToolResult(id=call.id, ok=False,
                              error=f"tool_not_found: {call.name}")
            self._broadcast(StepEvent("tool_result", _serialize_event(res)))
            self.session.audit({"kind": "tool_call", "tool": call.name,
                                  "args": call.args, "ok": False,
                                  "error": res.error,
                                  "ts": time.time()})
            return res

        # Confirmation gate.
        needs_confirm = (
            tool.requires_confirmation == "always" or
            (tool.requires_confirmation == "destructive"
             and tool.side_effect == SideEffect.DESTRUCTIVE) or
            (self.session.trust == TrustMode.CAUTIOUS
             and tool.side_effect in (SideEffect.WRITE, SideEffect.DESTRUCTIVE))
        )
        if needs_confirm and not self.approve_callback(call, tool.requires_confirmation):
            res = ToolResult(id=call.id, ok=False,
                              error="user_rejected")
            self._broadcast(StepEvent("tool_result", _serialize_event(res)))
            return res

        # Auto-snapshot before write/destructive.
        snap_id = None
        if tool.side_effect in (SideEffect.WRITE, SideEffect.DESTRUCTIVE):
            try:
                snap = self.session.snapshots.capture(
                    self.session, action=call.name)
                snap_id = snap.id
            except Exception: pass

        res = REGISTRY.dispatch(call, self.session)
        if snap_id: res.snapshot_id = snap_id
        self._broadcast(StepEvent("tool_result", _serialize_event(res)))
        self.session.audit({"kind": "tool_call", "tool": call.name,
                              "args": call.args, "ok": res.ok,
                              "value": _truncate(res.value),
                              "error": res.error,
                              "snapshot_id": snap_id,
                              "ts": time.time()})
        return res

    def _broadcast(self, event: StepEvent) -> None:
        for q in list(self.subscribers):
            try: q.put_nowait(event)
            except asyncio.QueueFull: pass


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _serialize_result(res: ToolResult) -> str:
    if res.ok:
        return json.dumps({"ok": True, "value": _truncate(res.value),
                            "snapshot": res.snapshot_id})
    return json.dumps({"ok": False, "error": res.error})


def _serialize_event(res: ToolResult) -> dict:
    return {"id": res.id, "ok": res.ok,
            "value": _truncate(res.value),
            "error": res.error, "snapshot": res.snapshot_id}


def _truncate(v, limit: int = 4000):
    """Don't ship huge blobs (PNG bytes, decoded skin trees) into the
    LLM's context — replace with a summary."""
    if v is None: return None
    try:
        s = json.dumps(v, default=str)
        if len(s) <= limit: return v
        return {"_truncated": True, "preview": s[:512] + "…",
                "size_bytes": len(s)}
    except Exception:
        return str(v)[:limit]


__all__ = ["Daemon", "StepEvent"]
