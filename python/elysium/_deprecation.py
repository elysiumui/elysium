"""Deprecation utilities — the forward-compatibility path for Elysium's
strict-semver public API (see ``docs/guides/api-stability.md``).

From 1.0, public API is removed only on a major bump and only after being
deprecated for at least one minor release. Mark the outgoing surface with
:func:`deprecated` (functions/classes) or :func:`deprecated_alias` (renames);
both emit a :class:`DeprecationWarning` pointing at the replacement.

    from elysium._deprecation import deprecated, deprecated_alias

    @deprecated(since="1.2", removal="2.0", alt="new_thing")
    def old_thing(...): ...

    new_name = real_impl
    old_name = deprecated_alias("old_name", new_name, since="1.2", removal="2.0")
"""
from __future__ import annotations

import functools
import warnings
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _message(name: str, since: str, removal: str | None, alt: str | None) -> str:
    msg = f"{name} is deprecated since Elysium {since}"
    if removal:
        msg += f" and will be removed in {removal}"
    if alt:
        msg += f"; use {alt} instead"
    return msg + "."


def deprecated(*, since: str, removal: str | None = None,
               alt: str | None = None) -> Callable[[T], T]:
    """Decorate a function or class as deprecated. Emits a
    :class:`DeprecationWarning` (stacklevel pointing at the caller) the first
    time each call site invokes it.

    Args:
        since: version the deprecation started (e.g. ``"1.2"``).
        removal: version it will be removed in (e.g. ``"2.0"``), if known.
        alt: the replacement API to use instead.
    """
    def wrap(obj: T) -> T:
        name = getattr(obj, "__qualname__", getattr(obj, "__name__", str(obj)))
        msg = _message(name, since, removal, alt)

        if isinstance(obj, type):
            orig_init = obj.__init__

            @functools.wraps(orig_init)
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                orig_init(self, *args, **kwargs)

            obj.__init__ = __init__  # type: ignore[misc]
            doc = (obj.__doc__ or "").rstrip()
            obj.__doc__ = f"{doc}\n\n.. deprecated:: {since}\n   {msg}"
            return obj  # type: ignore[return-value]

        @functools.wraps(obj)  # type: ignore[arg-type]
        def fn(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            return obj(*args, **kwargs)  # type: ignore[operator]

        fn.__deprecated__ = msg  # type: ignore[attr-defined]
        return fn  # type: ignore[return-value]

    return wrap


def deprecated_alias(name: str, target: T, *, since: str,
                     removal: str | None = None) -> T:
    """Create a deprecated alias ``name`` for ``target`` (a renamed function
    or class). Calling the alias warns and forwards to ``target``."""
    alt = getattr(target, "__qualname__", getattr(target, "__name__", str(target)))
    msg = _message(name, since, removal, alt)

    if isinstance(target, type):
        @deprecated(since=since, removal=removal, alt=alt)
        class _Alias(target):  # type: ignore[misc, valid-type]
            pass
        _Alias.__name__ = name
        _Alias.__qualname__ = name
        return _Alias  # type: ignore[return-value]

    @functools.wraps(target)  # type: ignore[arg-type]
    def fn(*args: Any, **kwargs: Any) -> Any:
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        return target(*args, **kwargs)  # type: ignore[operator]

    fn.__name__ = name
    fn.__qualname__ = name
    fn.__deprecated__ = msg  # type: ignore[attr-defined]
    return fn  # type: ignore[return-value]


__all__ = ["deprecated", "deprecated_alias"]
