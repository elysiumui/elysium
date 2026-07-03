"""Text editing core for Tier-1 Qt-parity editable widgets.

`elysium.text.edit.EditableText` is a pure, geometry-agnostic text model
(caret, selection, undo/redo, word navigation, IME composition). Widgets
(`TextField`, `TextArea`, editable table cells, spin boxes) embed it and
supply geometry via the native shaping primitives in `elysium._native`.

`elysium.text.validate` provides Qt-`QValidator`-style validators and input
masks.
"""
from __future__ import annotations

from elysium.text.edit import EditableText
from elysium.text.validate import (
    Acceptable,
    Intermediate,
    Invalid,
    IntValidator,
    DoubleValidator,
    RegexValidator,
    Mask,
)

__all__ = [
    "EditableText",
    "Acceptable",
    "Intermediate",
    "Invalid",
    "IntValidator",
    "DoubleValidator",
    "RegexValidator",
    "Mask",
]
