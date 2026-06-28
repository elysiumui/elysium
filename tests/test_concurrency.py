"""Tier-2 Phase-4: threading → UI marshalling."""
from __future__ import annotations

import threading
import time

import pytest

from elysium.concurrency import (
    UiDispatcher, FrameLoop, ui_thread, run_async, get_async_runner,
    set_default_dispatcher, call_on_ui_thread,
)


# --- UiDispatcher -----------------------------------------------------------

def test_post_runs_on_drain_in_order():
    d = UiDispatcher()
    seen = []
    d.post(seen.append, 1)
    d.post(seen.append, 2)
    d.post(seen.append, 3)
    assert seen == []           # nothing runs until drained
    ran = d.drain()
    assert ran == 3 and seen == [1, 2, 3]


def test_invoke_returns_future_with_result():
    d = UiDispatcher()
    fut = d.invoke(lambda a, b: a + b, 2, 5)
    assert not fut.done()
    d.drain()
    assert fut.result(timeout=1) == 7


def test_invoke_propagates_exception():
    d = UiDispatcher()

    def boom():
        raise ValueError("nope")

    fut = d.invoke(boom)
    d.drain()
    with pytest.raises(ValueError, match="nope"):
        fut.result(timeout=1)


def test_post_from_worker_thread_marshals_to_drain_thread():
    d = UiDispatcher()
    d.drain()  # marks this (main) thread as the UI thread
    out = {}

    def worker():
        d.post(lambda: out.setdefault("tid", threading.get_ident()))

    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert "tid" not in out          # worker only enqueued
    d.drain()
    assert out["tid"] == threading.get_ident()  # ran on the UI (main) thread


def test_drain_only_runs_items_present_at_entry():
    d = UiDispatcher()
    log = []

    def reenter():
        log.append("a")
        d.post(log.append, "b")     # posted during drain → next tick

    d.post(reenter)
    d.drain()
    assert log == ["a"]             # "b" deferred
    d.drain()
    assert log == ["a", "b"]


def test_wake_callback_fires_on_enqueue():
    d = UiDispatcher()
    woke = []
    d.set_wake(lambda: woke.append(True))
    d.post(lambda: None)
    assert woke == [True]


# --- ui_thread decorator ----------------------------------------------------

def test_ui_thread_runs_inline_on_ui_thread():
    d = UiDispatcher()
    set_default_dispatcher(d)
    d.drain()  # this thread is now the UI thread

    @ui_thread
    def add(a, b):
        return a + b

    assert add(3, 4) == 7   # inline, real return value


def test_ui_thread_redispatches_from_worker():
    d = UiDispatcher()
    set_default_dispatcher(d)
    d.drain()  # main = UI thread
    results = []

    @ui_thread
    def record():
        results.append(threading.get_ident())

    holder = {}

    def worker():
        holder["ret"] = record()   # off-thread → returns a Future

    t = threading.Thread(target=worker); t.start(); t.join()
    assert hasattr(holder["ret"], "result")  # got a Future
    assert results == []                       # not run yet
    d.drain()
    assert results == [threading.get_ident()]  # ran on UI thread


# --- asyncio integration ----------------------------------------------------

def test_run_async_returns_result():
    async def compute():
        return 21 * 2

    fut = run_async(compute())
    assert fut.result(timeout=2) == 42


def test_async_then_marshals_to_ui_thread():
    d = UiDispatcher()
    set_default_dispatcher(d)
    d.drain()
    got = []

    async def work():
        return "hello"

    get_async_runner().then(work(), on_result=lambda r: got.append((r, threading.get_ident())),
                            dispatcher=d)
    # Wait for the coroutine to finish + post back.
    deadline = time.monotonic() + 2
    while d.pending() == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    d.drain()
    assert got and got[0][0] == "hello"
    assert got[0][1] == threading.get_ident()  # callback ran on UI thread


# --- FrameLoop --------------------------------------------------------------

def test_frameloop_tick_drains_then_calls_on_frame():
    d = UiDispatcher()
    order = []
    d.post(lambda: order.append("posted"))
    fl = FrameLoop(on_frame=lambda dt: order.append(f"frame:{dt}"), dispatcher=d)
    fl.tick(0.016)
    assert order[0] == "posted"
    assert order[1].startswith("frame:")


def test_frameloop_uses_default_dispatcher_when_none():
    d = UiDispatcher()
    set_default_dispatcher(d)
    fl = FrameLoop(on_frame=lambda dt: None)
    assert fl.dispatcher is d
