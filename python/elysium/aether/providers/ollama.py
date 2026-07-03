"""Ollama provider — local llama.cpp / etc. via the standard /api/chat
endpoint. Streams over HTTP using the stdlib only so no extra dep."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import AsyncIterator

from ..types import (Done, Message, MessageDelta, StreamEvent,
                       ToolCall, ToolCallEvent)
from ..tools import Tool


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str = "llama3.1",
                  host: str | None = None) -> None:
        self.model = model
        self.host = host or os.environ.get("OLLAMA_HOST",
                                              "http://127.0.0.1:11434")

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]:
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "system", "content": system}]
                         + _to_ollama(messages),
            "tools": [{"type": "function",
                        "function": t.to_provider_format()} for t in tools],
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode(errors="replace").strip()
                if not line: continue
                try: doc = json.loads(line)
                except Exception: continue
                msg = doc.get("message", {})
                if "content" in msg and msg["content"]:
                    yield MessageDelta(text=msg["content"])
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    yield ToolCallEvent(call=ToolCall(
                        id=tc.get("id", "ollama"),
                        name=fn.get("name", ""),
                        args=fn.get("arguments", {})))
                if doc.get("done"):
                    yield Done(stop_reason="end_turn",
                                usage={"prompt": doc.get("prompt_eval_count", 0),
                                        "response": doc.get("eval_count", 0)})
                    return


def _to_ollama(messages: list[Message]) -> list[dict]:
    out = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user",
                        "content": m.content if isinstance(m.content, str)
                                    else json.dumps(m.content)})
        elif m.role == "assistant":
            out.append({"role": "assistant",
                        "content": m.content if isinstance(m.content, str)
                                    else json.dumps(m.content)})
        elif m.role == "tool":
            out.append({"role": "tool", "name": m.name or "tool",
                        "content": m.content if isinstance(m.content, str)
                                    else json.dumps(m.content)})
    return out
