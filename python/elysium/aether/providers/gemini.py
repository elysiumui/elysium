"""Google Gemini provider — streams via the v1beta generateContent API.

Uses the stdlib `urllib` so we don't depend on `google-generativeai`.
Tool-use is mapped through Gemini's `functionDeclarations` /
`functionCall` schema. Streaming is line-delimited JSON via the
`streamGenerateContent` endpoint with `alt=sse`.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import AsyncIterator

from ..types import (Done, Message, MessageDelta, StreamEvent,
                       ToolCall, ToolCallEvent)
from ..tools import Tool


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str = "gemini-1.5-flash",
                  api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GeminiProvider: GEMINI_API_KEY not set")

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]:
        url = (f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{self.model}:streamGenerateContent"
                f"?alt=sse&key={self.api_key}")
        payload: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": _to_gemini(messages),
        }
        if tools:
            payload["tools"] = [{
                "functionDeclarations": [_tool_to_gemini(t) for t in tools],
            }]
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode(errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[len("data:"):].strip()
                if body == "[DONE]":
                    yield Done(stop_reason="end_turn"); return
                try: doc = json.loads(body)
                except Exception: continue
                # candidates[].content.parts[]: text | functionCall
                for cand in doc.get("candidates", []) or []:
                    parts = (cand.get("content", {}) or {}
                              ).get("parts", []) or []
                    for part in parts:
                        if "text" in part and part["text"]:
                            yield MessageDelta(text=part["text"])
                        fc = part.get("functionCall")
                        if fc:
                            yield ToolCallEvent(call=ToolCall(
                                id=f"gemini-{fc.get('name','')}",
                                name=fc.get("name", ""),
                                args=fc.get("args", {}) or {}))
                    fr = cand.get("finishReason")
                    if fr:
                        yield Done(stop_reason=str(fr).lower())
                        return


def _to_gemini(messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = "user" if m.role == "user" else "model"
        if m.role == "tool":
            # Tool results ride on a user turn with a functionResponse part.
            out.append({"role": "user", "parts": [{
                "functionResponse": {
                    "name": m.name or "tool",
                    "response": (m.content if isinstance(m.content, dict)
                                  else {"value": m.content}),
                }
            }]})
            continue
        content = (m.content if isinstance(m.content, str)
                    else json.dumps(m.content))
        out.append({"role": role, "parts": [{"text": content}]})
    return out


def _tool_to_gemini(tool: Tool) -> dict:
    """Translate our internal Tool to Gemini's functionDeclaration shape."""
    base = tool.to_provider_format()
    return {
        "name": base.get("name", ""),
        "description": base.get("description", ""),
        "parameters": base.get("input_schema",
                                base.get("parameters", {})),
    }
