"""Phase 2.2 reactive layer — fine-grained signal / computed / effect.

Design follows the Solid.js / Vue 3 model: reads inside a tracking
scope register dependencies automatically; writes invalidate
downstream subscribers and re-run them.

    v = signal(1)
    doubled = computed(lambda: v() * 2)
    @effect
    def log_doubled():
        print("doubled =", doubled())   # prints "doubled = 2"
    v.set(5)                              # prints "doubled = 10"
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")

# Each thread has its own dependency-tracking stack. Inside a Signal's
# __call__, the current observer (if any) is recorded as a dependent.
_local = threading.local()


def _stack() -> list["_Subscriber"]:
    s = getattr(_local, "stack", None)
    if s is None:
        s = []
        _local.stack = s
    return s


def _current_subscriber() -> "_Subscriber | None":
    s = _stack()
    return s[-1] if s else None


class _Subscriber:
    """Anything that re-runs when one of its observed signals changes."""
    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn
        # `_sources` is the set of signals we currently observe. We use
        # a "swap on re-run" pattern so a re-run that no longer reads a
        # signal unsubscribes from it.
        self._sources: set["Signal[Any]"] = set()
        self._scheduled = False

    def _bind(self, sig: "Signal[Any]") -> None:
        self._sources.add(sig)
        sig._subs.add(self)

    def _unbind_all(self) -> None:
        for sig in list(self._sources):
            sig._subs.discard(self)
        self._sources.clear()

    def run(self) -> Any:
        self._scheduled = False
        # Drop old dependencies; we'll re-collect them as the fn runs.
        self._unbind_all()
        _stack().append(self)
        try:
            return self._fn()
        finally:
            assert _stack().pop() is self

    def schedule(self) -> None:
        if self._scheduled: return
        self._scheduled = True
        self.run()


class Signal(Generic[T]):
    """A reactive cell. Reads inside an `effect` / `computed` register
    a subscription; `set()` notifies every subscriber."""
    __slots__ = ("_value", "_subs", "_eq")

    def __init__(self, value: T, *, eq: Callable[[T, T], bool] | None = None) -> None:
        self._value = value
        self._subs: set[_Subscriber] = set()
        # Identity for cheap default; user can pass a deep-equal for tuples/etc.
        self._eq = eq or (lambda a, b: a == b)

    def __call__(self) -> T:
        # Track read.
        obs = _current_subscriber()
        if obs is not None:
            obs._bind(self)
        return self._value

    def peek(self) -> T:
        """Read without subscribing — useful inside effects that don't
        want to depend on this signal."""
        return self._value

    def set(self, value: T) -> None:
        if self._eq(self._value, value):
            return
        self._value = value
        for sub in list(self._subs):
            sub.schedule()

    def update(self, fn: Callable[[T], T]) -> None:
        self.set(fn(self._value))


def signal(value: T) -> Signal[T]:
    return Signal(value)


class _ComputedSubscriber(_Subscriber):
    """Subscriber for a computed value: also exposes its current result
    as a signal-like object so other computeds / effects can depend on
    it transitively."""
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__(self._evaluate)
        self._user_fn = fn
        self._value: Any = None
        self._dirty = True
        self._listeners: set[_Subscriber] = set()

    def _evaluate(self) -> Any:
        new = self._user_fn()
        if self._dirty or new != self._value:
            self._value = new
            self._dirty = False
            for L in list(self._listeners):
                L.schedule()
        return new

    def get(self) -> Any:
        obs = _current_subscriber()
        if obs is not None:
            self._listeners.add(obs)
        if self._dirty:
            self.run()
        return self._value


def computed(fn: Callable[[], T]) -> Callable[[], T]:
    """Memoized derived value. Returns a callable; call it to read,
    and computed values transparently propagate dependencies."""
    cs = _ComputedSubscriber(fn)
    # Run once to populate dependencies.
    cs.run()
    return cs.get  # type: ignore[return-value]


def effect(fn: Callable[[], None]) -> Callable[[], None]:
    """Run `fn` immediately and re-run whenever any signal it read changes.
    Returns a `dispose` callable that unsubscribes the effect."""
    sub = _Subscriber(fn)
    sub.run()

    def dispose() -> None:
        sub._unbind_all()
    return dispose


__all__ = ["signal", "computed", "effect", "Signal"]
