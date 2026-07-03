"""Threading → UI marshalling — Tier-2 Qt parity (QMetaObject::invokeMethod
/ QThread, signals-across-threads).

Elysium's UI runs on one thread (the frame-loop thread that polls input,
updates, paints, and publishes the display list). Touching widget state from a
worker thread is a data race. This module marshals work back onto the UI
thread:

* :class:`UiDispatcher` — a thread-safe queue drained once per frame on the UI
  thread. ``post(fn)`` fire-and-forget; ``invoke(fn) -> Future`` for a result.
* :func:`call_on_ui_thread` / :func:`post` — module-level convenience over a
  default dispatcher (also reachable as ``window.invoke`` / ``window.post``).
* :func:`ui_thread` — decorator that re-dispatches a call onto the UI thread
  when invoked from a worker (returns a ``Future``); runs inline if already on
  the UI thread.
* :class:`AsyncRunner` / :func:`run_async` — run ``asyncio`` coroutines on a
  background loop and marshal their results back to the UI thread.
* :class:`FrameLoop` — standardizes the per-frame drain so apps stop
  hand-rolling daemon threads: drain dispatcher → on_frame(dt).
"""
from __future__ import annotations

import threading
import traceback
from collections import deque
from concurrent.futures import Future
from functools import wraps
from typing import Any, Callable, Optional


class UiDispatcher:
    """A thread-safe queue of callables run on the UI thread. Workers call
    :meth:`post` / :meth:`invoke`; the frame loop calls :meth:`drain` each
    tick (which also marks the calling thread as *the* UI thread)."""

    def __init__(self) -> None:
        self._q: deque[tuple[Callable, tuple, dict, Optional[Future]]] = deque()
        self._lock = threading.Lock()
        self._ui_thread_id: Optional[int] = None
        self._wake: Optional[Callable[[], None]] = None

    def set_wake(self, fn: Optional[Callable[[], None]]) -> None:
        """Optional callback invoked after enqueue to wake an idle UI loop
        (with dirty-rect, an idle UI produces no frames)."""
        self._wake = fn

    def is_ui_thread(self) -> bool:
        return (self._ui_thread_id is not None
                and threading.get_ident() == self._ui_thread_id)

    def _enqueue(self, fn, args, kwargs, fut) -> None:
        with self._lock:
            self._q.append((fn, args, kwargs, fut))
        if self._wake is not None:
            try: self._wake()
            except Exception: pass

    def post(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        """Queue ``fn(*args, **kwargs)`` to run on the next UI tick."""
        self._enqueue(fn, args, kwargs, None)

    def invoke(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        """Queue ``fn`` and return a :class:`~concurrent.futures.Future`
        resolved (or excepted) when it runs on the UI thread."""
        fut: Future = Future()
        self._enqueue(fn, args, kwargs, fut)
        return fut

    def pending(self) -> int:
        with self._lock:
            return len(self._q)

    def drain(self, max_items: Optional[int] = None) -> int:
        """Run queued callables on the current (UI) thread, in order.
        Returns how many ran. Re-entrant-safe: only items present at entry
        are run when ``max_items`` is None (new posts wait for next tick)."""
        self._ui_thread_id = threading.get_ident()
        with self._lock:
            budget = len(self._q) if max_items is None else min(max_items, len(self._q))
        n = 0
        while n < budget:
            with self._lock:
                if not self._q:
                    break
                fn, args, kwargs, fut = self._q.popleft()
            if fut is not None and not fut.set_running_or_notify_cancel():
                n += 1
                continue
            try:
                res = fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                if fut is not None:
                    fut.set_exception(e)
                else:
                    print(f"[elysium] posted callable raised:\n{traceback.format_exc()}",
                          flush=True)
            else:
                if fut is not None:
                    fut.set_result(res)
            n += 1
        return n


# --- module-level default dispatcher ---------------------------------------

_default: Optional[UiDispatcher] = None


def get_default_dispatcher() -> UiDispatcher:
    global _default
    if _default is None:
        _default = UiDispatcher()
    return _default


def set_default_dispatcher(d: UiDispatcher) -> None:
    global _default
    _default = d


def call_on_ui_thread(fn: Callable, *args: Any, **kwargs: Any) -> Future:
    """Marshal ``fn`` onto the UI thread; returns a Future for the result."""
    return get_default_dispatcher().invoke(fn, *args, **kwargs)


def post(fn: Callable, *args: Any, **kwargs: Any) -> None:
    """Fire-and-forget marshal onto the UI thread."""
    get_default_dispatcher().post(fn, *args, **kwargs)


def ui_thread(fn: Callable) -> Callable:
    """Decorator: calls run inline when already on the UI thread, else are
    re-dispatched onto it (returning a Future). Use for handlers that touch
    widget state but may be called from workers."""
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        d = get_default_dispatcher()
        if d.is_ui_thread():
            return fn(*args, **kwargs)
        return d.invoke(fn, *args, **kwargs)
    return wrapper


# --- asyncio integration ---------------------------------------------------

class AsyncRunner:
    """Owns a background thread running an asyncio event loop. Submit
    coroutines from anywhere; marshal results back to the UI thread."""

    def __init__(self) -> None:
        import asyncio
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="elysium-async",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import asyncio
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro) -> Future:
        """Schedule ``coro`` on the background loop; returns a
        concurrent.futures.Future."""
        import asyncio
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def then(self, coro, on_result: Callable[[Any], None],
             on_error: Optional[Callable[[BaseException], None]] = None,
             dispatcher: Optional[UiDispatcher] = None) -> Future:
        """Run ``coro``; deliver its result (or error) to ``on_result`` /
        ``on_error`` *on the UI thread* via ``dispatcher``."""
        d = dispatcher or get_default_dispatcher()
        fut = self.submit(coro)

        def _done(f: Future) -> None:
            try:
                res = f.result()
            except BaseException as e:  # noqa: BLE001
                if on_error is not None:
                    d.post(on_error, e)
            else:
                d.post(on_result, res)

        fut.add_done_callback(_done)
        return fut

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)


_async_runner: Optional[AsyncRunner] = None


def get_async_runner() -> AsyncRunner:
    global _async_runner
    if _async_runner is None:
        _async_runner = AsyncRunner()
    return _async_runner


def run_async(coro) -> Future:
    """Run an asyncio coroutine on the shared background loop. Returns a
    concurrent.futures.Future (``.result(timeout=...)`` blocks)."""
    return get_async_runner().submit(coro)


# --- frame loop ------------------------------------------------------------

class FrameLoop:
    """Standardizes the per-frame cycle so apps stop hand-rolling daemon
    threads: each tick drains the dispatcher (applying any posted work) then
    calls ``on_frame(dt)``. Run synchronously (drive :meth:`tick` yourself)
    or via :meth:`start` (spawns a daemon thread)."""

    def __init__(self, window: Any = None, on_frame: Optional[Callable[[float], None]] = None,
                 fps: float = 60.0, dispatcher: Optional[UiDispatcher] = None) -> None:
        self.window = window
        self.on_frame = on_frame
        self.fps = fps
        if dispatcher is not None:
            self.dispatcher = dispatcher
        elif window is not None and hasattr(window, "ui_dispatcher"):
            self.dispatcher = window.ui_dispatcher()
        else:
            self.dispatcher = get_default_dispatcher()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def tick(self, dt: float) -> None:
        self.dispatcher.drain()
        if self.on_frame is not None:
            self.on_frame(dt)

    def start(self) -> None:
        import time
        self._running = True

        def _loop() -> None:
            last = time.monotonic()
            frame = 1.0 / self.fps if self.fps > 0 else 0.0
            while self._running:
                now = time.monotonic()
                dt = now - last
                last = now
                try:
                    self.tick(dt)
                except Exception:  # noqa: BLE001
                    print(f"[elysium] frame error:\n{traceback.format_exc()}", flush=True)
                slack = frame - (time.monotonic() - now)
                if slack > 0:
                    time.sleep(slack)

        self._thread = threading.Thread(target=_loop, name="elysium-frame", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False


__all__ = [
    "UiDispatcher", "get_default_dispatcher", "set_default_dispatcher",
    "call_on_ui_thread", "post", "ui_thread",
    "AsyncRunner", "get_async_runner", "run_async",
    "FrameLoop",
]
