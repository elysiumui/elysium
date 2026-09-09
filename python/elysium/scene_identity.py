"""Persistent scene entity identities, independent of Python object lifetime."""
from __future__ import annotations

import re
import uuid

_PATTERN = re.compile(r"entity:[0-9a-f]{32}\Z")


def new_id() -> str:
    return "entity:" + uuid.uuid4().hex


def parse(value: str | None) -> str:
    # Legacy documents have no id. Once loaded, the next save persists one.
    if value is None:
        return new_id()
    if not isinstance(value, str) or not _PATTERN.fullmatch(value):
        raise ValueError("invalid scene entity_id")
    return value


def validate(placements) -> None:
    seen = set()
    for placement in placements:
        value = parse(placement.entity_id)
        if value in seen:
            raise ValueError(f"duplicate scene entity_id: {value}")
        seen.add(value)
