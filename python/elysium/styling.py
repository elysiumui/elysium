"""Declarative per-widget styling — a pragmatic QSS-like layer over the theme.

A :class:`StyleSheet` maps **selectors** to **property overrides**. Selectors
target a widget by type, ``#id``, ``.class``, and ``:state`` (``hover`` /
``focus`` / ``pressed`` / ``disabled`` / ``checked``), and combine —
``"Button.primary:hover"``. :meth:`StyleSheet.resolve` merges every matching
rule in CSS-like specificity order into one property dict; :meth:`apply` writes
those properties onto a widget instance.

This is *not* a full CSS engine — it's a selector→property resolver that layers
on top of the existing token reads, so a widget stays theme-driven by default
and only takes per-instance overrides where a rule matches.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Selector", "StyleSheet"]

_VALID_STATES = {"hover", "focus", "pressed", "disabled", "checked", "active"}
_TYPE_RE = re.compile(r"^(\*|[A-Za-z_][\w]*)")
_TOKEN_RE = re.compile(r"([#.:])([\w-]+)")
_TAIL_RE = re.compile(r"^([#.:][\w-]+)*$")


@dataclass(frozen=True)
class Selector:
    """A parsed selector. ``specificity`` orders matches: more specific wins
    (id ≫ class/state ≫ type), ties broken by source order."""

    type: str | None
    id: str | None
    classes: frozenset[str]
    states: frozenset[str]

    @classmethod
    def parse(cls, text: str) -> "Selector":
        text = text.strip()
        type_: str | None = None
        rest = text
        tm = _TYPE_RE.match(text)
        if tm:
            tok = tm.group(1)
            type_ = None if tok == "*" else tok
            rest = text[tm.end():]
        # The remainder must be a run of #id / .class / :state tokens in any
        # order — no stray characters.
        if not _TAIL_RE.match(rest):
            raise ValueError(f"invalid selector: {text!r}")
        id_: str | None = None
        classes: set[str] = set()
        states: set[str] = set()
        for kind, name in _TOKEN_RE.findall(rest):
            if kind == "#":
                id_ = name
            elif kind == ".":
                classes.add(name)
            else:  # ":"
                if name not in _VALID_STATES:
                    raise ValueError(f"unknown state {name!r} in {text!r}")
                states.add(name)
        return cls(type=type_, id=id_,
                   classes=frozenset(classes), states=frozenset(states))

    def matches(self, type_name: str, id: str | None,
                classes: frozenset[str], states: frozenset[str]) -> bool:
        if self.type is not None and self.type != type_name:
            return False
        if self.id is not None and self.id != id:
            return False
        if not self.classes <= classes:
            return False
        if not self.states <= states:
            return False
        return True

    @property
    def specificity(self) -> tuple[int, int, int]:
        return (1 if self.id else 0,
                len(self.classes) + len(self.states),
                1 if self.type else 0)


@dataclass
class StyleSheet:
    """A collection of ``selector -> {property: value}`` rules. Pass a dict to
    the constructor; later rules of equal specificity win (source order)."""

    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    _parsed: list[tuple[Selector, dict[str, Any], int]] = field(
        default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.recompile()

    def recompile(self) -> None:
        self._parsed = [
            (Selector.parse(sel), dict(props), order)
            for order, (sel, props) in enumerate(self.rules.items())
        ]

    def add(self, selector: str, props: dict[str, Any]) -> "StyleSheet":
        self.rules[selector] = {**self.rules.get(selector, {}), **props}
        self.recompile()
        return self

    def resolve(self, type_name: str, *, id: str | None = None,
                classes: Any = (), states: Any = ()) -> dict[str, Any]:
        """The merged property overrides for a widget. More-specific rules (and,
        on ties, later ones) win per property."""
        cls_set = frozenset(classes)
        st_set = frozenset(states)
        matched = [
            (sel.specificity, order, props)
            for sel, props, order in self._parsed
            if sel.matches(type_name, id, cls_set, st_set)
        ]
        matched.sort(key=lambda m: (m[0], m[1]))
        out: dict[str, Any] = {}
        for _spec, _order, props in matched:
            out.update(props)
        return out

    def apply(self, widget: Any, type_name: str | None = None, *,
              id: str | None = None, classes: Any = (),
              states: Any = ()) -> dict[str, Any]:
        """Resolve and write the overrides onto ``widget`` (``setattr`` for each
        property the widget already has). Returns the resolved dict.

        ``type_name`` defaults to the widget's class name; ``id`` / ``classes``
        default to the widget's ``style_id`` / ``style_classes`` if present."""
        tn = type_name or type(widget).__name__
        wid = id if id is not None else getattr(widget, "style_id", None)
        wcls = classes or getattr(widget, "style_classes", ())
        resolved = self.resolve(tn, id=wid, classes=wcls, states=states)
        for key, value in resolved.items():
            if hasattr(widget, key):
                setattr(widget, key, value)
        return resolved
