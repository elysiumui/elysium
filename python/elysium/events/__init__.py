"""Event payload types & gesture recognition. Phase 1.5."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClickEvent:
    x: float
    y: float
    modifiers: int = 0
    context: object | None = None

    _stopped: bool = False
    _defaulted: bool = False

    def stop_propagation(self) -> None: self._stopped = True
    def prevent_default(self) -> None: self._defaulted = True
