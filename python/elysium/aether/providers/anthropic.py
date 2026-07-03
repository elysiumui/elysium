"""Anthropic provider — Claude with native tool use + streaming."""
from __future__ import annotations

import json
import os
from typing import AsyncIterator

from ..types import (Done, Message, MessageDelta, StreamEvent,
                       ThinkingDelta, ToolCall, ToolCallEvent)
from ..tools import Tool


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = "claude-opus-4-7",
                  api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("AnthropicProvider: ANTHROPIC_API_KEY not set")

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "AnthropicProvider needs `pip install anthropic`.") from e

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        api_messages = _to_anthropic(messages)
        api_tools = [t.to_provider_format() for t in tools]

        async with client.messages.stream(
            model=self.model,
            system=system,
            messages=api_messages,
            tools=api_tools,
            max_tokens=8192,
        ) as stream:
            current_tool: dict | None = None
            json_acc = ""
            async for event in stream:
                t = event.type
                if t == "content_block_start":
                    cb = event.content_block
                    if cb.type == "tool_use":
                        current_tool = {"id": cb.id, "name": cb.name}
                        json_acc = ""
                elif t == "content_block_delta":
                    d = event.delta
                    if d.type == "text_delta":
                        yield MessageDelta(text=d.text)
                    elif d.type == "input_json_delta":
                        json_acc += d.partial_json
                    elif d.type == "thinking_delta":
                        yield ThinkingDelta(text=d.thinking)
                elif t == "content_block_stop":
                    if current_tool is not None:
                        try: args = json.loads(json_acc or "{}")
                        except json.JSONDecodeError: args = {}
                        yield ToolCallEvent(call=ToolCall(
                            id=current_tool["id"],
                            name=current_tool["name"],
                            args=args))
                        current_tool = None
                        json_acc = ""
                elif t == "message_stop":
                    msg = await stream.get_final_message()
                    yield Done(
                        stop_reason=msg.stop_reason or "end_turn",
                        usage={"input_tokens": msg.usage.input_tokens,
                                "output_tokens": msg.usage.output_tokens})


def _to_anthropic(messages: list[Message]) -> list[dict]:
    """Translate our internal Message list to Anthropic's wire format."""
    out: list[dict] = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": _to_blocks(m)})
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": _to_blocks(m)})
        elif m.role == "tool":
            out.append({"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": m.tool_use_id,
                "content": m.content if isinstance(m.content, str)
                            else json.dumps(m.content),
            }]})
    return out


def _to_blocks(m: Message) -> list[dict] | str:
    if isinstance(m.content, list): return m.content
    return [{"type": "text", "text": str(m.content)}]
