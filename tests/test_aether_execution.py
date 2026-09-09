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
