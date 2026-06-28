"""Validators and input masks for editable text — Qt QValidator parity.

A validator answers, for a *proposed* field value, one of three states:

* :data:`Acceptable` — a complete, valid value (the field may be committed).
* :data:`Intermediate` — not valid yet but could become valid with more
  typing (e.g. ``"-"`` while typing a negative number). Editing is allowed
  to pass through these so the user can keep typing.
* :data:`Invalid` — can never be valid; the edit that produced it is rejected.

`EditableText` consults the validator on every mutation and rolls back edits
that would make the value :data:`Invalid`.

Masks (:class:`Mask`) are the orthogonal feature: a fixed template like
``"000-000"`` or ``"AA-0000"`` that constrains *which* characters may go in
*which* slot and auto-types the literal separators.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

# Validation states (ints so they're cheap + ordered: Invalid < Intermediate < Acceptable).
Invalid = 0
Intermediate = 1
Acceptable = 2


class Validator(Protocol):
    def validate(self, text: str) -> int:
        """Return Invalid / Intermediate / Acceptable for ``text``."""


@dataclass
class IntValidator:
    """Accepts integers in ``[minimum, maximum]``. A lone ``"-"`` (when the
    range allows negatives) and the empty string are Intermediate so the
    user can type."""
    minimum: int = -(2**31)
    maximum: int = 2**31 - 1

    def validate(self, text: str) -> int:
        if text == "" or (text == "-" and self.minimum < 0):
            return Intermediate
        if not re.fullmatch(r"-?\d+", text):
            return Invalid
        v = int(text)
        if v < self.minimum or v > self.maximum:
            # Could still be intermediate if a prefix of a longer in-range
            # number — but for simplicity treat out-of-range as Invalid
            # unless it's a sign/prefix case handled above.
            return Invalid
        return Acceptable


@dataclass
class DoubleValidator:
    """Accepts decimals in ``[minimum, maximum]`` with up to ``decimals``
    fractional digits. Partial inputs (``""``, ``"-"``, ``"1."``) are
    Intermediate."""
    minimum: float = -1e308
    maximum: float = 1e308
    decimals: int = 6

    def validate(self, text: str) -> int:
        if text in ("", "-", "+", ".", "-.", "+."):
            return Intermediate
        if not re.fullmatch(r"[-+]?\d*\.?\d*", text) or text in (".",):
            return Invalid
        # Trailing dot or no digits yet → intermediate.
        if text.endswith(".") or not re.search(r"\d", text):
            return Intermediate
        frac = text.split(".")[1] if "." in text else ""
        if len(frac) > self.decimals:
            return Invalid
        try:
            v = float(text)
        except ValueError:
            return Invalid
        if v < self.minimum or v > self.maximum:
            return Invalid
        return Acceptable


@dataclass
class RegexValidator:
    """Accepts strings fully matching ``pattern``. A string that is a proper
    prefix of some accepted string is Intermediate (best-effort: we treat a
    partial match anchored at the start as Intermediate)."""
    pattern: str

    def __post_init__(self) -> None:
        self._full = re.compile(self.pattern)

    def validate(self, text: str) -> int:
        if self._full.fullmatch(text):
            return Acceptable
        if text == "":
            return Intermediate
        # An anchored match that consumes the whole (still-short) input is a
        # plausible prefix → Intermediate so the user can keep typing.
        # Python's `re` has no DFA partial-match, so this is best-effort.
        m = self._full.match(text)
        if m and m.end() == len(text):
            return Intermediate
        return Invalid


# --- Input masks ------------------------------------------------------------

# Mask metacharacters (subset of Qt's QLineEdit inputMask):
#   0  required digit (0-9)
#   9  optional digit
#   A  required ASCII letter (a-z A-Z)
#   a  optional ASCII letter
#   N  required alphanumeric
#   n  optional alphanumeric
#   X  required any printable
# Anything else is a literal that is auto-inserted and skipped over.
_MASK_REQUIRED = set("0A NX".replace(" ", ""))
_MASK_OPTIONAL = set("9an")


def _slot_accepts(slot: str, ch: str) -> bool:
    if slot in ("0", "9"):
        return ch.isdigit()
    if slot in ("A", "a"):
        return ch.isascii() and ch.isalpha()
    if slot in ("N", "n"):
        return ch.isascii() and ch.isalnum()
    if slot == "X":
        return ch.isprintable()
    return False


@dataclass
class Mask:
    """A fixed-template input mask, e.g. ``Mask("000-000")`` for a 6-digit
    code with a literal dash. Use :meth:`apply` to fold raw user input into
    the masked form; :meth:`is_complete` reports whether all required slots
    are filled."""
    spec: str

    def literals_positions(self) -> set[int]:
        return {i for i, c in enumerate(self.spec) if not _is_meta(c)}

    def apply(self, raw: str) -> str:
        """Map a stream of user-typed characters onto the mask, inserting
        literals automatically and dropping characters that don't fit the
        next available slot. Returns the formatted string (may be partial)."""
        out: list[str] = []
        chars = [c for c in raw if c]  # consume positionally
        ci = 0
        for slot in self.spec:
            if not _is_meta(slot):
                out.append(slot)  # literal: auto-insert
                # If the user typed the literal explicitly, swallow it.
                if ci < len(chars) and chars[ci] == slot:
                    ci += 1
                continue
            # Find the next user char that fits this slot.
            placed = False
            while ci < len(chars):
                ch = chars[ci]
                ci += 1
                if _slot_accepts(slot, ch):
                    out.append(ch)
                    placed = True
                    break
                # else skip a char that can't go here
            if not placed:
                break  # ran out of input for this slot
        # Trim a trailing run of pure literals we appended past real input.
        s = "".join(out)
        return s

    def is_complete(self, text: str) -> bool:
        if len(text) != len(self.spec):
            return False
        for slot, ch in zip(self.spec, text):
            if not _is_meta(slot):
                if ch != slot:
                    return False
            elif slot in _MASK_REQUIRED and not _slot_accepts(slot, ch):
                return False
        return True


def _is_meta(c: str) -> bool:
    return c in _MASK_REQUIRED or c in _MASK_OPTIONAL


__all__ = [
    "Invalid",
    "Intermediate",
    "Acceptable",
    "Validator",
    "IntValidator",
    "DoubleValidator",
    "RegexValidator",
    "Mask",
]
