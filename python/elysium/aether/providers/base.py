"""Provider protocol — async streaming, Anthropic-shaped tool use."""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from ..types import Message, StreamEvent
from ..tools import Tool


@runtime_checkable
class Provider(Protocol):
    name: str
    model: str

    async def stream(self, system: str, messages: list[Message],
                      tools: list[Tool]) -> AsyncIterator[StreamEvent]: ...
