"""Acknowledgements describe actual serialized outcomes, including failed writes."""
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest
from elysium.aether import execution
from elysium.aether.tools import Registry, Tool
from elysium.aether.types import TrustMode
from elysium.concurrency import UiDispatcher


@pytest.fixture
def setup(monkeypatch):
    d = SimpleNamespace(_aether_dispatcher=UiDispatcher(), value=0,
                        _undo_stack=[{"old": 1}], _redo_stack=[{"redo": 2}],
                        _undo_limit=2, _document_revision=0)
    d._snapshot = lambda: {"value": d.value}
    d._restore = lambda snap: setattr(d, "value", snap["value"])
    captures = []
    def capture(*a, **kw):
        captures.append(d.value)
        return SimpleNamespace(id="checkpoint")
    session = SimpleNamespace(trust=TrustMode.COLLABORATIVE,
                              snapshots=SimpleNamespace(capture=capture), audit=lambda _: None)
    registry = Registry()
    monkeypatch.setattr(execution, "REGISTRY", registry)
    def add(fn, **kwargs):
        registry.add(Tool("set", "test", {"type": "object", "properties": {
            "value": {"type": "integer"}}, "required": ["value"]}, fn, **kwargs))
    add(lambda value: setattr(d, "value", value))
    return d, session, execution.Operations(d, lambda: session), captures, add


def test_retries_share_one_future_and_commit_on_owner_thread(setup):
    d, _, ops, captures, add = setup
    executed = []
    def update(value):
        executed.append(threading.get_ident())
        d.value = value
    add(update)
    payload = {"id": "retry", "name": "set", "args": {"value": 7}}
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: ops.submit(payload), range(30)))
    assert len({id(f) for _, f in responses}) == 1
    assert d.value == 0
    assert ops.read("retry")["status"] == "queued"
    d._aether_dispatcher.drain()
    assert executed == [threading.get_ident()]
    assert captures == [0]
    assert responses[0][1].result()["status"] == "committed"
    assert d._document_revision == 1
    assert d._undo_stack == [{"old": 1}, {"value": 0}]
    assert d._redo_stack == []
    assert ops.submit(payload)[1].done()
    with pytest.raises(ValueError, match="different operation"):
        ops.submit({**payload, "args": {"value": 8}})


def test_failed_handler_restores_document_and_complete_history(setup):
    d, _, ops, _, add = setup
    before = deepcopy((d._undo_stack, d._redo_stack))
    def broken(value):
        d.value = value
        d._undo_stack[:] = [{"partial": 1}]
        d._redo_stack.clear()
        return {"error": "could not finish"}
    add(broken)
    _, future = ops.submit({"name": "set", "args": {"value": 4}})
    d._aether_dispatcher.drain()
    assert future.result()["status"] == "failed"
    assert d.value == 0
    assert (d._undo_stack, d._redo_stack) == before
    assert d._document_revision == 0


def test_schema_failure_has_no_checkpoint_or_mutation(setup):
    d, _, ops, captures, _ = setup
    _, future = ops.submit({"name": "set", "args": {"value": "bad"}})
    d._aether_dispatcher.drain()
    assert not future.result()["ok"]
    assert captures == []
    assert d.value == 0


def test_pause_is_checked_when_queued_operation_runs(setup):
    d, _, ops, captures, _ = setup
    _, future = ops.submit({"name": "set", "args": {"value": 3}})
    ops.control_check = lambda: True
    d._aether_dispatcher.drain()
    assert "paused" in future.result()["error"]
    assert captures == []
    assert d.value == 0


def test_checkpoint_failure_prevents_mutation(setup):
    d, session, ops, _, _ = setup
    def failed(*a, **kw):
        raise OSError("disk full")
    session.snapshots.capture = failed
    _, future = ops.submit({"name": "set", "args": {"value": 3}})
    d._aether_dispatcher.drain()
    assert "disk full" in future.result()["error"]
    assert d.value == 0


def test_audit_failure_does_not_lose_committed_acknowledgement(setup):
    d, session, ops, _, _ = setup
    def failed(*a):
        raise OSError("audit unavailable")
    session.audit = failed
    key, future = ops.submit({"name": "set", "args": {"value": 3}})
    d._aether_dispatcher.drain()
    assert future.result()["status"] == "committed"
    assert ops.read(key)["audit_error"] == "audit unavailable"
    assert d.value == 3


def test_confirmation_required_before_checkpoint(setup):
    d, session, ops, captures, _ = setup
    session.trust = TrustMode.CAUTIOUS
    _, future = ops.submit({"name": "set", "args": {"value": 3}})
    d._aether_dispatcher.drain()
    assert "confirmation_required" in future.result()["error"]
    assert captures == []
    _, confirmed = ops.submit({"name": "set", "args": {"value": 3}, "confirm": True})
    d._aether_dispatcher.drain()
    assert confirmed.result()["ok"]
    assert d.value == 3


# --- NP-01: receipts, cancellation, inline fallback, wake, activity ----------

def _inline_designer():
    d = SimpleNamespace(value=0, _undo_stack=[], _redo_stack=[], _undo_limit=5,
                        _document_revision=0)
    d._snapshot = lambda: {"value": d.value}
    d._restore = lambda snap: setattr(d, "value", snap["value"])
    return d


def test_receipt_updates_are_locked_against_concurrent_reads(setup):
    d, _, ops, _, _ = setup
    ids = [ops.submit({"id": f"op-{i}", "name": "set", "args": {"value": i}})[0]
           for i in range(200)]
    stop = threading.Event()
    errors = []
    def hammer():
        while not stop.is_set():
            for rid in ids:
                try:
                    ops.read(rid)
                except Exception as exc:  # noqa: BLE001 — any failure is the bug
                    errors.append(exc)
                    return
    readers = [threading.Thread(target=hammer) for _ in range(8)]
    for t in readers: t.start()
    d._aether_dispatcher.drain()
    stop.set()
    for t in readers: t.join(timeout=5)
    assert errors == []
    receipts = [ops.read(rid) for rid in ids]
    assert all(r["status"] == "committed" for r in receipts)
    assert all("revision" in r and r["revision"] is not None and "completed_at" in r
               for r in receipts)
    assert [r["revision"] for r in receipts] == list(range(1, 201))


def test_cancel_queued_operation_marks_receipt_cancelled_and_skips_execution(setup):
    d, _, ops, captures, add = setup
    called = []
    add(lambda value: called.append(value))
    rid, future = ops.submit({"name": "set", "args": {"value": 9}})
    receipt = ops.cancel(rid, "client")
    assert receipt["status"] == "cancelled" and receipt["reason"] == "client"
    assert receipt["error"] == "cancelled: client"
    d._aether_dispatcher.drain()
    assert called == [] and captures == []
    assert future.cancelled()
    assert ops.read(rid)["status"] == "cancelled"
    assert d.value == 0 and d._document_revision == 0
    with pytest.raises(KeyError):
        ops.cancel("unknown-id")


def test_cancel_running_or_finished_operation_is_refused(setup):
    d, _, ops, _, add = setup
    seen = []
    def slow(value):
        seen.append(ops.cancel(rid, "mid-flight")["status"])
        d.value = value
    add(slow)
    rid, future = ops.submit({"name": "set", "args": {"value": 5}})
    d._aether_dispatcher.drain()
    assert seen == ["running"]
    assert future.result()["status"] == "committed"
    assert ops.cancel(rid, "too-late")["status"] == "committed"
    assert d.value == 5


def test_cancel_all_on_stop_reports_reason(setup):
    d, _, ops, _, _ = setup
    ids = [ops.submit({"id": f"q{i}", "name": "set", "args": {"value": i}})[0] for i in range(3)]
    assert sorted(ops.cancel_all("aether_stopped")) == sorted(ids)
    d._aether_dispatcher.drain()
    for rid in ids:
        r = ops.read(rid)
        assert r["status"] == "cancelled" and r["reason"] == "aether_stopped"
    assert ops.cancel_all("again") == []
    assert d.value == 0


def test_control_reason_string_is_reported_verbatim(setup):
    d, _, ops, captures, _ = setup
    ops.control_check = lambda: "aether_stopped"
    _, future = ops.submit({"name": "set", "args": {"value": 3}})
    d._aether_dispatcher.drain()
    r = future.result()
    assert r["status"] == "failed" and r["error"] == "aether_stopped"
    assert r["reason"] == "aether_stopped"
    assert captures == [] and d.value == 0
    with pytest.raises(PermissionError, match="aether_stopped"):
        ops.invoke_read(lambda: 1)


def test_missing_designer_dispatcher_executes_inline_serialized(monkeypatch, capsys):
    d = _inline_designer()
    session = SimpleNamespace(trust=TrustMode.COLLABORATIVE,
                              snapshots=SimpleNamespace(capture=lambda *a, **k: SimpleNamespace(id="c")),
                              audit=lambda _: None)
    registry = Registry()
    monkeypatch.setattr(execution, "REGISTRY", registry)
    in_handler = threading.Lock()
    overlap = []
    def update(value):
        if not in_handler.acquire(blocking=False):
            overlap.append(value)
            return
        try:
            d.value = value
            import time; time.sleep(0.002)
        finally:
            in_handler.release()
    registry.add(Tool("set", "test", {"type": "object", "properties": {
        "value": {"type": "integer"}}, "required": ["value"]}, update))
    ops = execution.Operations(d, lambda: session)
    def go(i):
        rid, fut = ops.submit({"id": f"inline-{i}", "name": "set", "args": {"value": i}})
        return fut.done(), fut.result(timeout=0)["status"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(go, range(30)))
    assert outcomes == [(True, "committed")] * 30
    assert overlap == []
    assert d._document_revision == 30
    assert ops.stats() == {"queued": 0, "running": 0, "total": 30, "inline": True}
    assert ops.invoke_read(lambda: d.value) == d.value
    assert "executing operations inline" in capsys.readouterr().out


def test_supplied_dispatcher_defers_execution_to_drain(setup):
    d, _, ops, _, _ = setup
    rid, future = ops.submit({"name": "set", "args": {"value": 2}})
    assert ops.read(rid)["status"] == "queued" and not future.done()
    assert ops.stats() == {"queued": 1, "running": 0, "total": 1, "inline": False}
    assert d.value == 0
    d._aether_dispatcher.drain()
    assert future.result()["status"] == "committed" and d.value == 2
    assert ops.stats()["queued"] == 0


def test_wake_fires_on_submit_and_invoke_read(setup):
    d, session, ops, _, _ = setup
    fired = {"dispatcher": 0, "explicit": 0, "designer": 0}
    d._aether_dispatcher.set_wake(lambda: fired.__setitem__("dispatcher", fired["dispatcher"] + 1))
    ops.submit({"id": "w1", "name": "set", "args": {"value": 1}})
    assert fired["dispatcher"] == 1
    explicit = execution.Operations(d, lambda: session, wake=lambda: fired.__setitem__("explicit", fired["explicit"] + 1))
    explicit.submit({"id": "w2", "name": "set", "args": {"value": 1}})
    assert fired["explicit"] == 1 and fired["dispatcher"] == 2
    d._aether_wake = lambda: fired.__setitem__("designer", fired["designer"] + 1)
    ops.submit({"id": "w3", "name": "set", "args": {"value": 1}})
    assert fired["designer"] == 1
    d._aether_dispatcher.drain()
    def broken():
        raise RuntimeError("no waker")
    d._aether_wake = broken
    rid, future = ops.submit({"id": "w4", "name": "set", "args": {"value": 4}})
    d._aether_dispatcher.drain()
    assert future.result()["status"] == "committed"
    # invoke_read wakes too (the read is enqueued on the same dispatcher).
    d._aether_wake = lambda: fired.__setitem__("designer", fired["designer"] + 1)
    t = threading.Thread(target=lambda: ops.invoke_read(lambda: 1, timeout=5))
    t.start()
    import time
    for _ in range(200):
        if fired["designer"] >= 2: break
        time.sleep(0.005)
    d._aether_dispatcher.drain(); t.join(timeout=5)
    assert fired["designer"] == 2


def test_on_activity_toggles_busy_across_queue_lifetime(setup):
    d, session, _, _, _ = setup
    toggles = []
    ops = execution.Operations(d, lambda: session, on_activity=toggles.append)
    ops.submit({"id": "a1", "name": "set", "args": {"value": 1}})
    assert toggles == [True]
    ops.submit({"id": "a2", "name": "set", "args": {"value": 2}})
    assert toggles == [True]
    d._aether_dispatcher.drain(max_items=1)
    assert toggles == [True]
    d._aether_dispatcher.drain()
    assert toggles == [True, False]
    rid, _ = ops.submit({"id": "a3", "name": "set", "args": {"value": 3}})
    ops.cancel(rid, "user")
    assert toggles == [True, False, True, False]


def test_retry_increments_attempts_without_re_execution(setup):
    d, _, ops, _, add = setup
    runs = []
    add(lambda value: runs.append(value))
    payload = {"id": "again", "name": "set", "args": {"value": 1}}
    ops.submit(payload)
    d._aether_dispatcher.drain()
    ops.submit(payload); ops.submit(payload)
    d._aether_dispatcher.drain()
    r = ops.read("again")
    assert r["attempts"] == 3 and r["status"] == "committed"
    assert runs == [1]


def test_ui_input_and_operations_interleave_in_enqueue_order_on_one_thread(setup):
    from elysium.concurrency import FrameLoop
    d, _, ops, _, add = setup
    log, threads = [], []
    def handler(value):
        log.append(f"op{value}"); threads.append(threading.get_ident())
    add(handler)
    def ui(tag):
        log.append(tag); threads.append(threading.get_ident())
    enqueued = []
    order_lock = threading.Lock()
    barrier = threading.Barrier(2)
    def worker(n):
        barrier.wait()
        with order_lock:
            d._aether_dispatcher.post(ui, f"ui{n}"); enqueued.append(f"ui{n}")
        with order_lock:
            ops.submit({"id": f"op{n}", "name": "set", "args": {"value": n}}); enqueued.append(f"op{n}")
    workers = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
    for w in workers: w.start()
    for w in workers: w.join(timeout=5)
    frame_thread = []
    d._aether_dispatcher.post(lambda: frame_thread.append(threading.get_ident()))
    loop = FrameLoop(dispatcher=d._aether_dispatcher, fps=500)
    loop.start()
    import time
    for _ in range(400):
        if len(log) == 4 and frame_thread: break
        time.sleep(0.005)
    loop.stop()
    assert log == enqueued and len(log) == 4
    assert set(threads) == {frame_thread[0]} and frame_thread[0] != threading.get_ident()


def test_failed_operation_receipt_carries_unchanged_revision(setup):
    d, _, ops, _, _ = setup
    ops.submit({"id": "good", "name": "set", "args": {"value": 1}})
    d._aether_dispatcher.drain()
    rid, future = ops.submit({"name": "set", "args": {"value": "bad"}})
    assert ops.read(rid)["revision"] is None
    d._aether_dispatcher.drain()
    r = future.result()
    assert r["status"] == "failed" and r["revision"] == 1 == d._document_revision
    assert "invalid arguments for set" in r["error"]
    fresh = SimpleNamespace(**{k: v for k, v in vars(d).items()})
    fresh._document_revision = 0
    ops2 = execution.Operations(fresh, ops.session_factory)
    _, fut2 = ops2.submit({"name": "set", "args": {"value": "bad"}})
    d._aether_dispatcher.drain()
    assert fut2.result()["revision"] == 0 and fresh._document_revision == 0


def test_revision_is_created_on_first_commit_for_designers_without_one(monkeypatch):
    # The shipped GUI Designer defines the undo stacks and _snapshot/_restore
    # but never _document_revision; every receipt and GET /state report it,
    # so the first commit must create it (main's create-on-first-write).
    d = SimpleNamespace(value=0, _undo_stack=[], _redo_stack=[], _undo_limit=5)
    d._snapshot = lambda: {"value": d.value}
    d._restore = lambda snap: setattr(d, "value", snap["value"])
    session = SimpleNamespace(trust=TrustMode.COLLABORATIVE,
                              snapshots=SimpleNamespace(capture=lambda *a, **k: SimpleNamespace(id="c")),
                              audit=lambda _: None)
    registry = Registry()
    monkeypatch.setattr(execution, "REGISTRY", registry)
    registry.add(Tool("set", "test", {"type": "object", "properties": {
        "value": {"type": "integer"}}, "required": ["value"]},
        lambda value: setattr(d, "value", value)))
    ops = execution.Operations(d, lambda: session)
    assert not hasattr(d, "_document_revision")
    receipts = [ops.submit({"name": "set", "args": {"value": v}})[1].result() for v in (1, 2, 3)]
    assert [r["status"] for r in receipts] == ["committed"] * 3
    assert [r["revision"] for r in receipts] == [1, 2, 3]
    assert d._document_revision == 3 and len(d._undo_stack) == 3
    failed = ops.submit({"name": "set", "args": {"value": "bad"}})[1].result()
    assert failed["status"] == "failed" and failed["revision"] == 3 == d._document_revision


# --- inline execution shares the undo history with the frame thread ----------
#
# The shipped GUI Designer supplies no _aether_dispatcher, so Operations runs
# the transaction on the HTTP thread while the frame thread keeps servicing
# the user's _undo/_redo/_push_undo (elysium-designer __main__.py). The
# transaction may therefore never rewrite a history stack wholesale: that
# resurrected the entry a user had just undone and dropped its redo entry.

def _gui_designer(*, value=0, undo=(), redo=()):
    """The shipped Designer's history shape (raw lists, whole-document
    snapshots, _push_undo/_undo/_redo as in __main__.py), no dispatcher."""
    d = SimpleNamespace(value=value, _undo_stack=list(undo), _redo_stack=list(redo),
                        _undo_limit=100)
    d._snapshot = lambda: {"value": d.value}
    d._restore = lambda snap: setattr(d, "value", snap["value"])
    def push_undo():
        d._undo_stack.append(d._snapshot())
        if len(d._undo_stack) > d._undo_limit:
            d._undo_stack.pop(0)
        d._redo_stack.clear()
    def undo():
        d._redo_stack.append(d._snapshot()); d._restore(d._undo_stack.pop())
    def redo():
        d._undo_stack.append(d._snapshot()); d._restore(d._redo_stack.pop())
    d._push_undo, d._undo, d._redo = push_undo, undo, redo
    return d


class _RacingCommand:
    """A ``set`` command submitted from a bridge thread that parks inside its
    handler (``park`` = before or after its mutation) until the test has
    played the user's action on this, the frame, thread."""

    def __init__(self, monkeypatch, d):
        session = SimpleNamespace(trust=TrustMode.COLLABORATIVE,
                                  snapshots=SimpleNamespace(capture=lambda *a, **k: SimpleNamespace(id="c")),
                                  audit=lambda _: None)
        registry = Registry()
        monkeypatch.setattr(execution, "REGISTRY", registry)
        self.d = d
        self.park = self.outcome = None
        self.self_push = False
        self.in_handler, self.release = threading.Event(), threading.Event()
        def set_value(value):
            if self.self_push:
                d._push_undo()              # a GUI handler publishing its own entry
            if self.park == "before":
                self._wait()
            d.value = value
            if self.park == "after":
                self._wait()
            return self.outcome
        registry.add(Tool("set", "test", {"type": "object", "properties": {
            "value": {"type": "integer"}}, "required": ["value"]}, set_value))
        self.ops = execution.Operations(d, lambda: session)

    def _wait(self):
        self.in_handler.set()
        assert self.release.wait(5), "the test never released the handler"

    def run(self, rid, value, *, park=None, outcome=None, user_action=None, self_push=False):
        self.park, self.outcome, self.self_push = park, outcome, self_push
        self.in_handler.clear(); self.release.clear()
        payload = {"id": rid, "name": "set", "args": {"value": value}}
        if park is None:
            self.ops.submit(payload)
            return self.ops.read(rid)
        t = threading.Thread(target=self.ops.submit, args=(payload,))
        t.start()
        assert self.in_handler.wait(5), "handler never started"
        user_action()
        self.release.set()
        t.join(5)
        assert not t.is_alive()
        return self.ops.read(rid)


def _ordered(stack, key="value"):
    """The undo stack read as the states it can walk back to, oldest first."""
    return [entry[key] for entry in stack]


def test_inline_commit_reports_a_user_undo_it_had_to_discard(monkeypatch):
    d = _gui_designer()
    cmd = _RacingCommand(monkeypatch, d)
    assert [cmd.run(rid, v)["status"] for rid, v in (("a", 1), ("b", 2))] == ["committed"] * 2
    assert (d.value, d._undo_stack, d._redo_stack) == (2, [{"value": 0}, {"value": 1}], [])
    def user_undo():
        d._undo()
        assert (d.value, d._undo_stack, d._redo_stack) == (1, [{"value": 0}], [{"value": 2}])
    receipt = cmd.run("c", 3, park="before", user_action=user_undo)
    assert receipt["status"] == "committed" and d.value == 3
    # History follows the document: the command publishes the state it began
    # from, so undo walks 3 -> 2 -> 1 -> 0 with nothing skipped or repeated.
    assert _ordered(d._undo_stack) == [0, 1, 2]
    assert d._redo_stack == []                    # a committed edit clears redo, like _push_undo
    assert d._document_revision == 3
    # The user's undo is gone, and the receipt says so rather than hiding it.
    assert [w["path"] for w in receipt["warnings"]] == ["history"]
    assert "_aether_dispatcher" in receipt["warnings"][0]["message"]


def test_inline_rollback_puts_history_back_in_step_with_the_document(monkeypatch):
    d = _gui_designer(value=2, undo=[{"value": 0}, {"value": 1}])
    cmd = _RacingCommand(monkeypatch, d)
    receipt = cmd.run("c", 3, park="before", outcome={"error": "nope"}, user_action=d._undo)
    assert receipt["status"] == "failed" and receipt.get("rollback_error") is None
    # _restore(before) takes the document past the user's undo, so the stacks
    # go back with it: every state stays reachable and in order.
    assert d.value == 2
    assert _ordered(d._undo_stack) == [0, 1] and d._redo_stack == []
    assert [w["path"] for w in receipt["warnings"]] == ["history"]
    assert not hasattr(d, "_document_revision")


def test_inline_commit_after_a_user_undo_and_redo_keeps_the_order(monkeypatch):
    # The ordering case a heuristic cannot get right: _redo pushes a *new*
    # object for a state that pre-dates the command, so identity says
    # "after" while time says "before".
    d = _gui_designer(value=2, undo=[{"value": 0}, {"value": 1}])
    cmd = _RacingCommand(monkeypatch, d)
    def user_undo_then_redo():
        d._undo(); d._redo()                      # document back where it was
        assert d.value == 2 and _ordered(d._undo_stack) == [0, 1]
    receipt = cmd.run("c", 3, park="before", user_action=user_undo_then_redo)
    assert receipt["status"] == "committed" and d.value == 3
    assert _ordered(d._undo_stack) == [0, 1, 2]   # never [0, 2, 1]
    assert d._redo_stack == []


def test_inline_rollback_after_a_user_redo_keeps_the_redo_target(monkeypatch):
    d = _gui_designer(value=1, undo=[{"value": 0}], redo=[{"value": 2}])
    cmd = _RacingCommand(monkeypatch, d)
    def user_redo():
        d._redo()
        assert (d.value, _ordered(d._undo_stack), d._redo_stack) == (2, [0, 1], [])
    receipt = cmd.run("c", 3, park="before", outcome={"error": "nope"},
                      user_action=user_redo)
    assert receipt["status"] == "failed" and d.value == 1
    # The redo entry is still there and still means something: redoing moves
    # the document, it is not a no-op copy of the current state.
    assert d._redo_stack == [{"value": 2}] and d._redo_stack[-1] != d._snapshot()
    assert _ordered(d._undo_stack) == [0]
    assert [w["path"] for w in receipt["warnings"]] == ["history"]


def test_inline_commit_reports_a_user_edit_that_raced_it(monkeypatch):
    d = _gui_designer(value=2, undo=[{"value": 0}, {"value": 1}])
    cmd = _RacingCommand(monkeypatch, d)
    def user_edit():                              # frame thread: _push_undo() then mutate
        d._push_undo(); d.value = 7
    receipt = cmd.run("c", 3, park="after", user_action=user_edit)
    assert receipt["status"] == "committed" and d.value == 7
    # One entry per command, in order; the user's own undo point is not
    # separately recoverable, which the warning names.
    assert _ordered(d._undo_stack) == [0, 1, 2] and d._redo_stack == []
    assert [w["path"] for w in receipt["warnings"]] == ["history"]


def test_inline_handler_that_publishes_its_own_entry_is_one_undo_step(monkeypatch):
    d = _gui_designer(value=2, undo=[{"value": 0}, {"value": 1}], redo=[{"value": 9}])
    cmd = _RacingCommand(monkeypatch, d)
    assert cmd.run("c", 3, self_push=True)["status"] == "committed"
    assert d.value == 3 and d._undo_stack == [{"value": 0}, {"value": 1}, {"value": 2}]
    assert d._redo_stack == []
    # On failure the handler's own copy of the pre-command document is
    # taken back: the document is already there, so it was a no-op step.
    assert cmd.run("d", 4, self_push=True, outcome={"error": "nope"})["status"] == "failed"
    assert d.value == 3 and d._undo_stack == [{"value": 0}, {"value": 1}, {"value": 2}]


def test_inline_undo_limit_trims_the_oldest_entries(monkeypatch):
    d = _inline_designer()                        # _undo_limit=5, no dispatcher
    cmd = _RacingCommand(monkeypatch, d)
    assert [cmd.run(f"op{i}", i)["status"] for i in range(1, 8)] == ["committed"] * 7
    assert d._undo_stack == [{"value": v} for v in range(2, 7)]


@pytest.mark.parametrize("exclusive", [True, False], ids=["frame-thread", "shared"])
def test_run_transaction_puts_both_stacks_back_on_failure(exclusive):
    # Operations passes exclusive_history=True only for a supplied (frame
    # thread) dispatcher; HeadlessDesigner.dispatch_persistent_tool and the
    # daemon take the shared default. Either way a failed command leaves the
    # history exactly as it found it — the document is restored to the same
    # point, so the two cannot disagree.
    d = _gui_designer(value=2, undo=[{"value": 0}, {"value": 1}], redo=[{"value": 9}])
    session = SimpleNamespace(trust=TrustMode.COLLABORATIVE,
                              snapshots=SimpleNamespace(capture=lambda *a, **k: SimpleNamespace(id="c")))
    registry = Registry()
    def clobber(value):
        d.value = value
        d._undo_stack[:] = [{"partial": 1}]
        d._redo_stack.clear()
        return {"error": "could not finish"}
    tool = Tool("set", "test", {"type": "object", "properties": {"value": {"type": "integer"}}}, clobber)
    registry.add(tool)
    from elysium.aether.types import ToolCall
    result = execution.run_transaction(d, session, tool, ToolCall("x", "set", {"value": 5}),
                                       registry=registry, exclusive_history=exclusive)
    assert not result.ok and d.value == 2
    assert (d._undo_stack, d._redo_stack) == ([{"value": 0}, {"value": 1}], [{"value": 9}])
    # Shared mode cannot tell the handler's rewrite from a user edit, so it
    # says a concurrent write was discarded; the frame thread knows better.
    assert [w["path"] for w in result.warnings] == ([] if exclusive else ["history"])


# --- interrupts and settled receipts ------------------------------------------

@pytest.mark.parametrize("exc", [SystemExit(3), KeyboardInterrupt()],
                         ids=["SystemExit", "KeyboardInterrupt"])
def test_base_exception_from_handler_is_a_failed_call_with_rollback(setup, exc):
    # ``exit()`` / ``sys.exit()`` in dev.eval raise SystemExit, which is not
    # an Exception: it used to skip the rollback, leave the future pending
    # (every retry a 202 forever) and end the frame loop.
    d, _, ops, captures, add = setup
    before = deepcopy((d._undo_stack, d._redo_stack))
    def interrupted(value):
        d.value = value
        d._undo_stack[:] = [{"partial": 1}]
        raise exc
    add(interrupted)
    _, future = ops.submit({"id": "boom", "name": "set", "args": {"value": 5}})
    d._aether_dispatcher.drain()
    assert future.done() and not future.cancelled()
    receipt = future.result()
    assert receipt["status"] == "failed" and receipt["ok"] is False
    assert receipt["error"].startswith(type(exc).__name__)
    assert receipt["snapshot"] == "checkpoint" and receipt["revision"] == 0
    assert "completed_at" in receipt
    assert d.value == 0 and (d._undo_stack, d._redo_stack) == before
    assert d._document_revision == 0 and captures == [0]
    # The dispatcher is still serviceable: the next command commits.
    add(lambda value: setattr(d, "value", value))
    _, future = ops.submit({"id": "after", "name": "set", "args": {"value": 6}})
    d._aether_dispatcher.drain()
    assert future.result()["status"] == "committed" and d.value == 6


def test_interrupt_outside_the_handler_still_settles_the_receipt(setup):
    d, session, ops, captures, _ = setup
    def interrupted_session():
        raise KeyboardInterrupt
    ops.session_factory = interrupted_session
    _, future = ops.submit({"id": "ctrl-c", "name": "set", "args": {"value": 5}})
    d._aether_dispatcher.drain()
    receipt = future.result(timeout=1)
    assert receipt["status"] == "failed" and receipt["error"] == "KeyboardInterrupt: "
    assert captures == [] and d.value == 0
    assert ops.stats()["running"] == 0


def test_on_terminal_fires_exactly_once_per_operation(setup):
    d, _, ops, _, _ = setup
    seen = []
    rid, _ = ops.submit({"id": "t1", "name": "set", "args": {"value": 1}})
    ops.on_terminal(rid, lambda r: seen.append(("early", r["status"])))
    ops.on_terminal(rid, lambda r: 1 / 0)                      # a broken observer is dropped
    assert seen == []
    d._aether_dispatcher.drain()
    assert seen == [("early", "committed")]
    # Already terminal: fires right away, with the settled receipt.
    ops.on_terminal(rid, lambda r: seen.append(("late", r["status"], r["revision"], "completed_at" in r)))
    assert seen[-1] == ("late", "committed", 1, True)
    rid2, _ = ops.submit({"id": "t2", "name": "set", "args": {"value": 2}})
    ops.on_terminal(rid2, lambda r: seen.append(("cancel", r["status"], r["reason"])))
    assert ops.cancel(rid2, "client")["status"] == "cancelled"
    assert seen[-1] == ("cancel", "cancelled", "client")
    ops.cancel(rid2, "again")
    d._aether_dispatcher.drain()
    assert len(seen) == 3
    assert "listeners" not in ops.read(rid) and "listeners" not in ops.read(rid2)
    with pytest.raises(KeyError):
        ops.on_terminal("nope", lambda r: None)
