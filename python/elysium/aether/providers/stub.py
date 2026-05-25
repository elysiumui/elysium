"""Deterministic stub provider for offline / no-API-key use.

When the Designer has no LLM API key configured, this provider is the
default. Instead of echoing the user's prompt back (which felt
broken to first-time users), it replies with a friendly onboarding
message that explains how to set up a real provider.

The text is intentionally a one-time-style message — same content every
turn — so it works even when the user types multiple messages without
having set a key yet. As soon as they save a key via
``File > Insert API Key > <Provider>``, the Designer switches
`aether_provider` to that provider and subsequent turns route to the
real LLM.
"""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

from ..types import (Done, Message, MessageDelta, StreamEvent,
                       ToolCall, ToolCallEvent)
from ..tools import Tool


_DIRECTIVE = re.compile(r"^/tool\s+(\S+)\s*(\{.*\})?\s*$", re.DOTALL)

_ONBOARDING_TEXT = (
    "I'm not connected to an LLM yet. To start chatting for real, "
    "add an API key for any of these providers:\n\n"
    "  • Anthropic (Claude)  →  File > Insert API Key > Anthropic\n"
    "  • OpenAI (GPT)         →  File > Insert API Key > OpenAI\n"
    "  • Google (Gemini)      →  File > Insert API Key > Gemini\n"
    "  • DeepSeek             →  File > Insert API Key > DeepSeek\n\n"
    "You can also set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
    "GEMINI_API_KEY, or DEEPSEEK_API_KEY in your shell environment "
    "and relaunch.\n\n"
    "Once a key is saved I'll switch providers automatically and "
    "respond for real on the next message."
)


class StubProvider:
    name = "stub"
    model = "stub"

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]:
        # If the most recent message is a tool result the previous turn
        # already fired its tool — close with a plain reply so the
        # tool-use loop doesn't spin.
        if messages and messages[-1].role == "tool":
            yield MessageDelta(text="(stub) tool result observed; done.")
            yield Done(stop_reason="end_turn")
            return
        last_user = next((m for m in reversed(messages)
                           if m.role == "user"), None)
        text = ""
        if last_user and isinstance(last_user.content, str):
            text = last_user.content.strip()
        # Tool-test directive escape hatch — used by integration tests
        # that drive the stub with a `/tool name {...}` prompt.
        m = _DIRECTIVE.match(text)
        if m:
            name, args_json = m.group(1), m.group(2) or "{}"
            try: args = json.loads(args_json)
            except json.JSONDecodeError: args = {}
            yield MessageDelta(text=f"(stub) calling {name}\n")
            yield ToolCallEvent(call=ToolCall(
                id=f"stub-{name}", name=name, args=args))
            yield Done(stop_reason="tool_use")
            return
        # Default: onboarding instructions.
        yield MessageDelta(text=_ONBOARDING_TEXT)
        yield Done(stop_reason="end_turn")
