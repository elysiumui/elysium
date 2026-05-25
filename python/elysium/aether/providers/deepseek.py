"""DeepSeek provider — OpenAI-compatible chat-completions endpoint.

DeepSeek exposes an OpenAI-compatible API at
``https://api.deepseek.com/v1/chat/completions``. We hit it directly
with stdlib `urllib` (line-delimited SSE) so we don't need the openai
package as a dependency.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import AsyncIterator

from ..types import (Done, Message, MessageDelta, StreamEvent,
                       ToolCall, ToolCallEvent)
from ..tools import Tool


class _OpenAIChatCompletionsProvider:
    """Shared base for any provider that speaks OpenAI-compatible chat
    completions over HTTP. Subclasses set `name`, `_env_var`, and the
    default `host`/`model`."""
    name: str = ""
    _env_var: str = ""
    _default_host: str = ""
    _default_model: str = ""

    def __init__(self, model: str | None = None,
                  api_key: str | None = None,
                  host: str | None = None) -> None:
        self.model = model or self._default_model
        self.api_key = api_key or os.environ.get(self._env_var)
        self.host = host or os.environ.get(
            f"{self.name.upper()}_HOST", self._default_host)
        if not self.api_key:
            raise RuntimeError(
                f"{type(self).__name__}: {self._env_var} not set")


class DeepSeekProvider(_OpenAIChatCompletionsProvider):
    name = "deepseek"
    _env_var = "DEEPSEEK_API_KEY"
    _default_host = "https://api.deepseek.com"
    _default_model = "deepseek-chat"

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]:
        payload: dict = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "system", "content": system}]
                          + _to_openai(messages),
        }
        if tools:
            payload["tools"] = [{"type": "function",
                                   "function": t.to_provider_format()}
                                  for t in tools]
        req = urllib.request.Request(
            f"{self.host.rstrip('/')}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                       "Authorization": f"Bearer {self.api_key}"})
        # In-flight tool call accumulators — OpenAI's stream splits
        # tool name / arguments across multiple deltas.
        pending: dict[int, dict] = {}
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode(errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[len("data:"):].strip()
                if body == "[DONE]":
                    # Flush any pending tool call before closing.
                    for entry in pending.values():
                        try: args = json.loads(entry.get("args", "") or "{}")
                        except json.JSONDecodeError: args = {}
                        yield ToolCallEvent(call=ToolCall(
                            id=entry.get("id", "deepseek"),
                            name=entry.get("name", ""), args=args))
                    yield Done(stop_reason="end_turn")
                    return
                try: doc = json.loads(body)
                except Exception: continue
                for choice in doc.get("choices", []) or []:
                    delta = choice.get("delta", {}) or {}
                    if delta.get("content"):
                        yield MessageDelta(text=delta["content"])
                    for tc in delta.get("tool_calls", []) or []:
                        idx = tc.get("index", 0)
                        entry = pending.setdefault(idx, {})
                        if "id" in tc:
                            entry["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if "name" in fn:
                            entry["name"] = fn["name"]
                        if "arguments" in fn:
                            entry["args"] = entry.get("args", "") + fn["arguments"]
                    if choice.get("finish_reason"):
                        for entry in pending.values():
                            try: args = json.loads(entry.get("args", "") or "{}")
                            except json.JSONDecodeError: args = {}
                            yield ToolCallEvent(call=ToolCall(
                                id=entry.get("id", "deepseek"),
                                name=entry.get("name", ""), args=args))
                        yield Done(stop_reason=str(choice["finish_reason"]))
                        return


def _to_openai(messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": m.tool_use_id or "",
                "content": (m.content if isinstance(m.content, str)
                             else json.dumps(m.content)),
            })
            continue
        out.append({
            "role": m.role,
            "content": (m.content if isinstance(m.content, str)
                         else json.dumps(m.content)),
        })
    return out
