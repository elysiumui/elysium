"""NP-01 over HTTP: every /tool call is an acknowledged, idempotent receipt."""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from elysium.aether._headless import HeadlessDesigner
from elysium.aether.bridge import AetherBridge
from elysium.aether.tools import REGISTRY, Tool
from elysium.aether.types import SideEffect, TrustMode
from elysium.concurrency import FrameLoop, UiDispatcher

CARD = {"kind": "Card", "x": 10, "y": 10, "w": 100, "h": 50}


class Harness(SimpleNamespace):
    def req(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def tool(self, name, args, **extra):
        return self.req("POST", "/tool", {"name": name, "args": args, **extra})

    def events(self):
        out = []
        while True:
            try: out.append(self.bridge.event_queue.get_nowait())
            except queue.Empty: return out

    def pause_frame_loop(self):
        self.loop.stop()
        self.loop._thread.join(timeout=5)

    def resume_frame_loop(self):
        self.loop.start()

    def wait_terminal(self, rid, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code, doc = self.req("GET", f"/operations/{rid}")
            if doc.get("status") in ("committed", "failed", "cancelled"):
                return doc
            time.sleep(0.01)
        raise AssertionError(f"operation {rid} never reached a terminal state")


def _make(tmp_path, monkeypatch, *, inline):
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    d = HeadlessDesigner.from_skin(tmp_path / "b.esk")
    loop = None
    if not inline:
        d._aether_dispatcher = UiDispatcher()
        loop = FrameLoop(dispatcher=d._aether_dispatcher, fps=500)
        loop.start()
    bridge = AetherBridge(d, port=0)
    bridge.start()
    assert bridge.started and bridge.port != 0
    h = Harness(bridge=bridge, d=d, loop=loop, base=f"http://127.0.0.1:{bridge.port}")
    return h


@pytest.fixture
def h(tmp_path, monkeypatch):
    harness = _make(tmp_path, monkeypatch, inline=False)
    yield harness
    harness.bridge.stop()
    harness.loop.stop()


@pytest.fixture
def inline(tmp_path, monkeypatch):
    harness = _make(tmp_path, monkeypatch, inline=True)
    yield harness
    harness.bridge.stop()


@pytest.fixture
def slow_tool():
    stamps = []
    def slow(session, seconds: float = 0.3):
        stamps.append(time.monotonic())
        time.sleep(seconds)
        return {"slept": seconds, "thread": threading.get_ident()}
    REGISTRY.add(Tool("test.slow", "sleep", {"type": "object", "properties": {
        "seconds": {"type": "number"}}}, slow, side_effect=SideEffect.NONE, undoable=False))
    yield stamps
    REGISTRY._tools.pop("test.slow", None)


# --- receipts ----------------------------------------------------------------

def test_tool_commits_on_frame_thread_and_returns_200_with_revision(h):
    frame_thread = h.loop._thread.ident
    code, doc = h.tool("placement.add", CARD)
    assert code == 200
    assert doc["status"] == "committed" and doc["ok"] is True
    assert doc["revision"] == 1 and doc["attempts"] == 1
    assert doc["snapshot"].startswith("snap-") and doc["warnings"] == []
    assert doc["feedback_observed"] == []
    assert doc["_bridge"]["paused"] is False
    assert len(h.d.placements) == 1
    code, state = h.req("GET", "/state")
    assert code == 200 and state["revision"] == 1 and len(state["placements"]) == 1
    # A second, non-mutating call proves the frame thread does the work.
    REGISTRY.add(Tool("test.thread", "t", {"type": "object"}, lambda: {"thread": threading.get_ident()},
                      side_effect=SideEffect.READ, undoable=False))
    try:
        code, doc = h.tool("test.thread", {})
        assert code == 200 and doc["value"]["thread"] == frame_thread
        assert doc["revision"] == 1 and doc["snapshot"] is None
    finally:
        REGISTRY._tools.pop("test.thread", None)


def test_invalid_args_return_400_and_leave_revision_unchanged(h):
    code, doc = h.tool("placement.add", {"kind": 12})
    assert code == 400 and doc["status"] == "failed" and doc["ok"] is False
    assert "invalid arguments for placement.add" in doc["error"]
    assert doc["revision"] == 0 and h.d._document_revision == 0
    assert h.d.placements == []
    code, doc = h.tool("no.such_tool", {})
    assert code == 400 and "unknown tool" in doc["error"]
    code, doc = h.req("POST", "/tool", {"name": 5})
    assert code == 400 and doc["ok"] is False and "name must be a string" in doc["error"]
    code, doc = h.req("POST", "/tool", {"name": "placement.add", "args": CARD, "wait": "soon"})
    assert code == 400 and "wait" in doc["error"]


def test_retried_request_id_executes_once(h):
    body = {"id": "once", "name": "placement.add", "args": CARD}
    code1, first = h.req("POST", "/tool", body)
    code2, second = h.req("POST", "/tool", body)
    assert code1 == code2 == 200
    assert first["attempts"] == 1 and second["attempts"] == 2
    assert first["revision"] == second["revision"] == 1
    assert second["value"] == first["value"]
    assert len(h.d.placements) == 1
    code, receipt = h.req("GET", "/operations/once")
    assert code == 200 and receipt["attempts"] == 2 and receipt["status"] == "committed"


def test_conflicting_reuse_of_request_id_is_400(h):
    assert h.req("POST", "/tool", {"id": "dup", "name": "placement.add", "args": CARD})[0] == 200
    code, doc = h.req("POST", "/tool", {"id": "dup", "name": "placement.add", "args": {**CARD, "x": 99}})
    assert code == 400 and doc["ok"] is False
    assert "different operation" in doc["error"]
    assert len(h.d.placements) == 1
    assert h.req("GET", "/operations/nope")[0] == 404


def test_long_operation_returns_202_then_receipt_is_readable(h, slow_tool):
    code, doc = h.req("POST", "/tool", {"id": "slow", "name": "test.slow",
                                        "args": {"seconds": 0.3}, "wait": 0.05})
    assert code == 202 and doc["status"] in ("queued", "running")
    assert "value" not in doc and doc["attempts"] == 1
    final = h.wait_terminal("slow")
    assert final["status"] == "committed" and final["value"]["slept"] == 0.3
    assert final["value"]["thread"] == h.loop._thread.ident
    # Re-posting the same id after completion is a plain receipt read.
    code, again = h.req("POST", "/tool", {"id": "slow", "name": "test.slow",
                                          "args": {"seconds": 0.3}, "wait": 0.05})
    assert code == 200 and again["attempts"] == 2 and len(slow_tool) == 1


def test_cautious_trust_requires_confirmation_409_then_confirm_succeeds(h):
    h.bridge._ensure_session().trust = TrustMode.CAUTIOUS
    code, doc = h.tool("placement.add", CARD)
    assert code == 409 and doc["status"] == "failed"
    assert doc["error"].startswith("confirmation_required")
    assert doc["snapshot"] is None and h.d.placements == []
    code, doc = h.tool("placement.add", CARD, confirm=True)
    assert code == 200 and doc["status"] == "committed" and len(h.d.placements) == 1
    # Reads never need confirmation.
    assert h.tool("placement.list", {})[0] == 200


# --- pause / stop / cancel ---------------------------------------------------

def test_stop_returns_423_with_hint_and_cancels_queued_ops(h):
    h.pause_frame_loop()
    code, doc = h.req("POST", "/tool", {"id": "stuck", "name": "placement.add", "args": CARD, "wait": 0})
    assert code == 202 and doc["status"] == "queued"
    assert h.bridge.is_busy is True
    assert h.req("POST", "/stop")[0] == 200
    code, receipt = h.req("GET", "/operations/stuck")
    assert code == 200 and receipt["status"] == "cancelled"
    assert receipt["reason"] == "aether_stopped" and receipt["error"] == "cancelled: aether_stopped"
    assert h.bridge.is_busy is False
    code, doc = h.tool("placement.add", CARD)
    assert code == 423 and doc["error"] == "aether_stopped"
    assert doc["hint"] == "POST /resume to give control back"
    assert doc["_bridge"]["stopped"] is True
    # The stuck client can still learn its fate; cancelling again is
    # idempotent and keeps the original reason.
    code, receipt = h.req("POST", "/operations/stuck/cancel")
    assert code == 200 and receipt["reason"] == "aether_stopped"
    h.resume_frame_loop()
    assert h.req("POST", "/resume")[0] == 200
    assert h.d.placements == []
    code, doc = h.tool("placement.add", CARD)
    assert code == 200 and len(h.d.placements) == 1


def test_pause_returns_423_with_since_last_call_s(h):
    assert h.tool("placement.add", CARD)[0] == 200
    assert h.req("POST", "/pause")[0] == 200
    time.sleep(0.05)
    code, doc = h.tool("placement.add", CARD)
    assert code == 423 and doc["error"] == "aether_paused"
    assert doc["hint"] == "POST /resume to continue"
    assert 0.05 <= doc["since_last_call_s"] < 10
    code, state = h.req("GET", "/state")
    assert code == 423 and state["error"] == "aether_paused"
    assert len(h.d.placements) == 1
    assert h.req("POST", "/resume")[0] == 200
    assert h.tool("placement.add", CARD)[0] == 200


def test_pause_423_remains_hands_off_for_state_and_snapshot(h):
    rid = "before-pause"
    assert h.req("POST", "/tool", {"id": rid, "name": "placement.add", "args": CARD})[0] == 200
    assert h.req("POST", "/pause")[0] == 200
    assert h.req("GET", "/state")[0] == 423
    assert h.req("GET", "/snapshot")[0] == 423
    assert h.tool("placement.list", {})[0] == 423
    # Bridge-local metadata stays reachable.
    code, receipt = h.req("GET", f"/operations/{rid}")
    assert code == 200 and receipt["status"] == "committed"
    assert h.req("GET", "/status")[0] == 200
    assert h.req("GET", "/tools")[0] == 200
    assert h.req("GET", "/health")[0] == 200
    # A queued command survives the pause; the frame thread checks the
    # control state when it actually runs.
    h.pause_frame_loop()
    assert h.req("POST", "/resume")[0] == 200
    code, doc = h.req("POST", "/tool", {"id": "later", "name": "placement.add", "args": CARD, "wait": 0})
    assert code == 202
    assert h.req("POST", "/pause")[0] == 200
    h.resume_frame_loop()
    final = h.wait_terminal("later")
    assert final["status"] == "failed" and final["error"] == "aether_paused"
    assert final["reason"] == "aether_paused" and len(h.d.placements) == 1
    assert h.req("POST", "/resume")[0] == 200


def test_cancel_endpoint_200_then_409_after_execution(h):
    h.pause_frame_loop()
    code, doc = h.req("POST", "/tool", {"id": "c1", "name": "placement.add", "args": CARD, "wait": 0})
    assert code == 202
    code, receipt = h.req("POST", "/operations/c1/cancel")
    assert code == 200 and receipt["status"] == "cancelled" and receipt["reason"] == "client"
    h.resume_frame_loop()
    assert h.wait_terminal("c1")["status"] == "cancelled"
    assert h.d.placements == []
    assert h.req("POST", "/tool", {"id": "c2", "name": "placement.add", "args": CARD})[0] == 200
    code, receipt = h.req("POST", "/operations/c2/cancel")
    assert code == 409 and receipt["status"] == "committed"
    assert h.req("POST", "/operations/missing/cancel")[0] == 404
    assert len(h.d.placements) == 1


# --- feedback, pacing, status --------------------------------------------------

def test_feedback_is_drained_into_tool_call_event_and_response(h):
    assert h.req("POST", "/feedback", {"text": "make it warmer"})[0] == 200
    code, doc = h.req("POST", "/tool", {"id": "fb", "name": "placement.add", "args": {**CARD, "name": "Hot"}})
    assert code == 200 and doc["feedback_observed"] == ["make it warmer"]
    events = h.events()
    kinds = [e["kind"] for e in events]
    assert kinds == ["user_feedback", "feedback_observed", "tool_call", "tool_result"]
    by_kind = {e["kind"]: e["payload"] for e in events}
    assert by_kind["feedback_observed"] == {"messages": ["make it warmer"]}
    assert by_kind["tool_call"]["id"] == "fb" and by_kind["tool_call"]["name"] == "placement.add"
    assert by_kind["tool_call"]["pending_feedback"] == ["make it warmer"]
    assert by_kind["tool_result"]["status"] == "committed"
    assert h.bridge.last_call_name == "placement.add"
    # A retry neither re-drains nor re-announces.
    assert h.req("POST", "/feedback", {"text": "second"})[0] == 200
    code, doc = h.req("POST", "/tool", {"id": "fb", "name": "placement.add", "args": {**CARD, "name": "Hot"}})
    assert code == 200 and doc["feedback_observed"] == [] and doc["attempts"] == 2
    assert [e["kind"] for e in h.events()] == ["user_feedback"]
    assert h.bridge.feedback_inbox == ["second"]
    # The target placement id is surfaced for the canvas overlay.
    pid = h.d.placements[0].entity_id
    assert h.tool("placement.move", {"id": pid, "x": 1, "y": 2})[0] == 200
    assert h.bridge.last_call_target == pid


def test_pace_ms_delays_response_not_execution(h, slow_tool):
    assert h.req("POST", "/pace", {"ms": 200})[0] == 200
    start = time.monotonic()
    code, doc = h.tool("test.slow", {"seconds": 0.0})
    latency = time.monotonic() - start
    assert code == 200 and doc["status"] == "committed"
    assert slow_tool[0] - start < 0.1
    assert latency >= 0.2
    assert h.req("POST", "/pace", {"ms": 0})[0] == 200


def test_status_reports_operations_and_busy(h, slow_tool):
    code, status = h.req("GET", "/status")
    assert code == 200 and status["busy"] is False
    assert status["operations"] == {"queued": 0, "running": 0, "total": 0, "inline": False}
    code, doc = h.req("POST", "/tool", {"id": "busy", "name": "test.slow", "args": {"seconds": 0.4}, "wait": 0.05})
    assert code == 202
    code, status = h.req("GET", "/status")
    assert status["busy"] is True
    assert status["operations"]["total"] == 1
    assert status["operations"]["queued"] + status["operations"]["running"] == 1
    h.wait_terminal("busy")
    code, status = h.req("GET", "/status")
    assert status["busy"] is False and status["operations"]["running"] == 0
    assert status["last_call"]["name"] == "test.slow"


def test_submit_runtime_error_maps_to_503(h, monkeypatch):
    def full(payload):
        raise RuntimeError("operation journal full; start a new bridge session")
    monkeypatch.setattr(h.bridge.operations, "submit", full)
    code, doc = h.tool("placement.add", CARD)
    assert code == 503 and doc["ok"] is False
    assert "journal full" in doc["error"] and doc["retry_after_s"] == 5
    assert h.d.placements == []


def test_bridge_works_without_designer_dispatcher_inline(inline):
    assert not hasattr(inline.d, "_aether_dispatcher")
    code, doc = inline.tool("placement.add", CARD)
    assert code == 200 and doc["status"] == "committed" and doc["revision"] == 1
    assert len(inline.d.placements) == 1
    code, state = inline.req("GET", "/state")
    assert code == 200 and state["revision"] == 1
    code, status = inline.req("GET", "/status")
    assert status["operations"]["inline"] is True and status["busy"] is False
    code, doc = inline.tool("placement.add", {"kind": 3})
    assert code == 400 and inline.d._document_revision == 1
    assert (inline.d.skin_path / "designer_layout.json").is_file()


# --- CLI client --------------------------------------------------------------

def _cli_args(h, action, **over):
    base = dict(action=action, message=None, args="{}", out=None, skin=None, provider=None,
                bridge=h.base, repo="", apply=False, id=None, confirm=False, wait=5.0)
    base.update(over)
    return SimpleNamespace(**base)


def test_cli_call_polls_after_202_and_never_resubmits(h, slow_tool, monkeypatch, capsys):
    from elysium import cli
    monkeypatch.setattr(cli, "_BRIDGE_ACK_WAIT_S", 0.05)
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="test.slow",
                                          args='{"seconds": 0.3}', id="cli-1", wait=5))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "committed" and out["attempts"] == 1
    assert len(slow_tool) == 1
    # Same id again: a receipt read, still exactly one execution.
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="test.slow",
                                          args='{"seconds": 0.3}', id="cli-1", wait=5))
    assert rc == 0 and json.loads(capsys.readouterr().out)["attempts"] == 2
    assert len(slow_tool) == 1
    # Budget exhausted: exit 3, the op is still pending and later commits.
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="test.slow",
                                          args='{"seconds": 0.4}', id="cli-2", wait=0.1))
    assert rc == 3 and json.loads(capsys.readouterr().out)["status"] in ("queued", "running")
    assert h.wait_terminal("cli-2")["status"] == "committed" and len(slow_tool) == 2


def test_cli_confirm_op_and_cancel_actions(h, capsys):
    from elysium import cli
    h.bridge._ensure_session().trust = TrustMode.CAUTIOUS
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="placement.add",
                                          args=json.dumps(CARD), id="need-confirm"))
    assert rc == 2 and "confirmation_required" in capsys.readouterr().out
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="placement.add",
                                          args=json.dumps(CARD), id="confirmed", confirm=True))
    assert rc == 0 and len(h.d.placements) == 1
    capsys.readouterr()
    rc = cli._aether_bridge_cli(_cli_args(h, "op", id="confirmed"))
    assert rc == 0 and json.loads(capsys.readouterr().out)["status"] == "committed"
    assert cli._aether_bridge_cli(_cli_args(h, "op", id="missing")) == 1
    capsys.readouterr()
    h.pause_frame_loop()
    rc = cli._aether_bridge_cli(_cli_args(h, "call", message="placement.add",
                                          args=json.dumps(CARD), id="to-cancel", confirm=True, wait=0))
    assert rc == 3
    capsys.readouterr()
    assert cli._aether_bridge_cli(_cli_args(h, "cancel", message="to-cancel")) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    assert cli._aether_bridge_cli(_cli_args(h, "cancel", id="confirmed")) == 2
    h.resume_frame_loop()
    assert h.wait_terminal("to-cancel")["status"] == "cancelled" and len(h.d.placements) == 1


def test_cli_call_reports_transport_failure(tmp_path, capsys):
    import socket
    from elysium import cli
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    dead = SimpleNamespace(base=f"http://127.0.0.1:{port}")
    rc = cli._aether_bridge_cli(_cli_args(dead, "call", message="placement.add",
                                          args=json.dumps(CARD), wait=0.3))
    assert rc == 1
    assert "unreachable" in capsys.readouterr().err


# --- CLI client: lost replies ------------------------------------------------
#
# A stalled bridge is one that accepted the submit but never answers the
# /tool request within the socket timeout. The client must then read the
# receipt it may already hold — never resubmit — and report the last
# receipt it saw (exit 3) rather than "unreachable" (exit 1).

class _StalledBridge:
    """POST /tool records the body and never replies in time; GET
    /operations/<id> plays ``receipts`` in order (the last one repeats;
    ``None`` = that read stalls as well)."""

    def __init__(self, receipts):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.receipts, self.posts, self.gets = list(receipts), [], 0
        self.release = threading.Event()
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _json(self, code, doc):
                body = json.dumps(doc).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                stub.posts.append(json.loads(self.rfile.read(n) or b"{}"))
                stub.release.wait(10)          # the client's socket times out first
            def do_GET(self):
                stub.gets += 1
                answer = (stub.receipts[min(stub.gets, len(stub.receipts)) - 1]
                          if stub.receipts else None)
                if answer is None:
                    stub.release.wait(10); return
                self._json(*answer)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.release.set(); self.server.shutdown(); self.server.server_close()


@pytest.fixture
def stalled():
    made = []
    def make(receipts):
        made.append(_StalledBridge(receipts)); return made[-1]
    yield make
    for s in made: s.close()


def _fast_cli(monkeypatch, ack=0.05):
    from elysium import cli
    monkeypatch.setattr(cli, "_BRIDGE_ACK_WAIT_S", ack)
    monkeypatch.setattr(cli, "_BRIDGE_TRANSPORT_GRACE_S", 0.2)
    monkeypatch.setattr(cli, "_BRIDGE_POLL_INTERVAL_S", 0.05)
    return cli


def _call(cli, bridge, rid, wait):
    return cli._aether_bridge_cli(_cli_args(bridge, "call", message="placement.add",
                                            args=json.dumps(CARD), id=rid, wait=wait))


def test_cli_lost_reply_polls_receipt_and_exits_3_with_last_receipt(stalled, monkeypatch, capsys):
    cli = _fast_cli(monkeypatch)
    running = {"id": "stalled", "name": "placement.add", "status": "running", "attempts": 1,
               "revision": None}
    bridge = stalled([(200, running)])
    t0 = time.monotonic()
    rc = _call(cli, bridge, "stalled", wait=0.6)
    elapsed = time.monotonic() - t0
    out, err = capsys.readouterr()
    assert rc == 3 and json.loads(out) == running
    # Exactly one submit, carrying the id and a transport-only wait: never resubmitted.
    assert bridge.posts == [{"id": "stalled", "name": "placement.add", "args": CARD, "wait": 0.05}]
    assert bridge.gets >= 2
    assert "polling receipt stalled instead of resubmitting" in err and "unreachable" not in err
    assert elapsed < 3


def test_cli_lost_reply_finds_committed_receipt_and_exits_0(stalled, monkeypatch, capsys):
    cli = _fast_cli(monkeypatch)
    committed = {"id": "done", "name": "placement.add", "status": "committed", "ok": True,
                 "attempts": 1, "revision": 7}
    bridge = stalled([(200, committed)])
    rc = _call(cli, bridge, "done", wait=0.0)      # budget already spent: still one poll
    out, err = capsys.readouterr()
    assert rc == 0 and json.loads(out) == committed
    assert len(bridge.posts) == 1 and bridge.gets == 1
    assert "polling receipt done" in err


def test_cli_lost_reply_unknown_operation_is_not_journaled(stalled, monkeypatch, capsys):
    cli = _fast_cli(monkeypatch)
    bridge = stalled([(404, {"error": "unknown operation"})])
    rc = _call(cli, bridge, "never-arrived", wait=1.0)
    out, err = capsys.readouterr()
    assert rc == 1 and out == ""
    assert "never-arrived is not journaled" in err and "safe to resubmit" in err
    assert len(bridge.posts) == 1 and bridge.gets == 1


def test_cli_lost_reply_and_unreachable_receipt_reports_may_be_journaled(stalled, monkeypatch, capsys):
    cli = _fast_cli(monkeypatch)
    bridge = stalled([None])                         # the receipt read stalls too
    t0 = time.monotonic()
    rc = _call(cli, bridge, "unknown-fate", wait=0.0)
    elapsed = time.monotonic() - t0
    out, err = capsys.readouterr()
    assert rc == 1 and out == ""
    assert "may still be journaled" in err and "same --id" in err
    assert len(bridge.posts) == 1 and bridge.gets >= 1
    # One stalled submit + one stalled poll, each capped at the transport grace.
    assert elapsed < 2


def test_cli_receipt_then_lost_journal_keeps_last_receipt(stalled, monkeypatch, capsys):
    cli = _fast_cli(monkeypatch)
    running = {"id": "restarted", "name": "placement.add", "status": "running", "attempts": 1,
               "revision": None}
    bridge = stalled([(200, running), (404, {"error": "unknown operation"})])
    rc = _call(cli, bridge, "restarted", wait=1.0)
    out, err = capsys.readouterr()
    assert rc == 3 and json.loads(out) == running
    assert "no longer journals restarted" in err and "safe to resubmit" not in err
    assert len(bridge.posts) == 1 and bridge.gets == 2


def test_cli_receipt_then_vanished_bridge_exits_3_with_last_receipt(stalled, monkeypatch, capsys):
    # The operation may well be journaled and running: the client already
    # holds its receipt when the bridge stops answering receipt reads. The
    # last receipt is the answer (exit 3), never "unreachable" (exit 1)
    # and never a resubmit.
    cli = _fast_cli(monkeypatch)
    running = {"id": "vanished", "name": "placement.add", "status": "running", "attempts": 1,
               "revision": None}
    bridge = stalled([(200, running), None])         # one receipt, then every read stalls
    t0 = time.monotonic()
    rc = _call(cli, bridge, "vanished", wait=0.6)
    elapsed = time.monotonic() - t0
    out, err = capsys.readouterr()
    assert rc == 3 and json.loads(out) == running
    assert len(bridge.posts) == 1 and bridge.gets >= 2
    assert "polling receipt vanished instead of resubmitting" in err
    assert "unreachable" not in err and "safe to resubmit" not in err
    assert elapsed < 3


def test_cli_paced_reply_lost_polls_committed_receipt_without_resubmitting(h, monkeypatch, capsys):
    # pace_ms sleeps on the HTTP thread *after* the commit: the real bridge
    # stalls its reply while the receipt is already committed and readable.
    cli = _fast_cli(monkeypatch, ack=1.0)            # socket timeout 1.2 s < pace
    h.bridge.pace_ms = 3000
    try:
        t0 = time.monotonic()
        rc = _call(cli, h, "paced", wait=5)
        elapsed = time.monotonic() - t0
    finally:
        h.bridge.pace_ms = 0
    out, err = capsys.readouterr()
    receipt = json.loads(out)
    assert rc == 0 and receipt["status"] == "committed" and receipt["attempts"] == 1
    assert len(h.d.placements) == 1
    assert "polling receipt paced instead of resubmitting" in err
    assert elapsed < 2.7                             # did not wait for the paced reply


# --- settled receipts: interrupts, SSE tool_result, /status busy ---------------

def _next_event(h, kind, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try: ev = h.bridge.event_queue.get(timeout=0.05)
        except queue.Empty: continue
        if ev["kind"] == kind: return ev
    raise AssertionError(f"no {kind} event within {timeout}s")


@pytest.mark.parametrize("fixture", ["h", "inline"])
def test_dev_eval_exit_rolls_back_and_keeps_the_bridge_serving(request, fixture):
    b = request.getfixturevalue(fixture)
    assert b.tool("placement.add", CARD)[0] == 200
    # ``exit()`` / ``quit()`` / ``sys.exit()`` raise SystemExit, which is not
    # an Exception: it used to skip the rollback, leave the future pending
    # and end the frame loop (inline, it escaped the HTTP handler).
    code, doc = b.tool("dev.eval", {"code": "designer.placements.clear()\nraise SystemExit(4)"},
                       confirm=True, wait=3)
    assert code == 400 and doc["status"] == "failed" and doc["ok"] is False
    assert doc["error"].startswith("SystemExit")
    assert doc["revision"] == 1 and doc["snapshot"].startswith("snap-")
    assert len(b.d.placements) == 1 and b.d._document_revision == 1
    if b.loop is not None:
        assert b.loop._thread.is_alive()
    # The journal keeps serving: the next command commits on the same loop.
    code, doc = b.tool("placement.add", CARD)
    assert code == 200 and doc["revision"] == 2 and len(b.d.placements) == 2
    code, status = b.req("GET", "/status")
    assert status["busy"] is False and status["operations"]["running"] == 0


def test_tool_result_event_is_pushed_for_an_operation_that_outlives_wait(h, slow_tool):
    h.events()
    code, doc = h.req("POST", "/tool", {"id": "late", "name": "test.slow",
                                        "args": {"seconds": 0.3}, "wait": 0.05})
    assert code == 202
    assert [e["kind"] for e in h.events()] == ["tool_call"]
    assert h.wait_terminal("late")["status"] == "committed"
    payload = _next_event(h, "tool_result")["payload"]
    assert payload["id"] == "late" and payload["status"] == "committed"
    assert payload["value"]["slept"] == 0.3 and payload["feedback_observed"] == []
    # A retry is a receipt read: it re-announces nothing.
    code, again = h.req("POST", "/tool", {"id": "late", "name": "test.slow",
                                          "args": {"seconds": 0.3}, "wait": 0.05})
    assert code == 200 and again["attempts"] == 2
    assert h.events() == []


def test_tool_result_event_is_pushed_for_a_cancelled_operation(h):
    h.pause_frame_loop()
    h.events()
    assert h.req("POST", "/tool", {"id": "cx", "name": "placement.add", "args": CARD, "wait": 0})[0] == 202
    assert [e["kind"] for e in h.events()] == ["tool_call"]
    assert h.req("POST", "/operations/cx/cancel")[0] == 200
    events = h.events()
    assert [e["kind"] for e in events] == ["tool_result"]
    assert events[0]["payload"]["id"] == "cx" and events[0]["payload"]["status"] == "cancelled"
    assert events[0]["payload"]["reason"] == "client"
    # /stop announces its cancellations the same way.
    assert h.req("POST", "/tool", {"id": "sx", "name": "placement.add", "args": CARD, "wait": 0})[0] == 202
    h.events()
    assert h.req("POST", "/stop")[0] == 200
    by_kind = {e["kind"]: e["payload"] for e in h.events()}
    assert by_kind["tool_result"]["id"] == "sx" and by_kind["tool_result"]["reason"] == "aether_stopped"
    h.resume_frame_loop()
    assert h.req("POST", "/resume")[0] == 200
    assert h.d.placements == []


def test_status_busy_is_derived_from_the_journal_not_the_callback(h, slow_tool, monkeypatch):
    # The is_busy flag follows the receipt by a callback; /status must never
    # pair a stale flag with a settled queue. Freezing the callback makes
    # that window permanent.
    monkeypatch.setattr(h.bridge.operations, "_notify_activity", lambda: None)
    assert h.req("POST", "/tool", {"id": "b2", "name": "test.slow", "args": {"seconds": 0.0}})[0] == 200
    h.bridge.is_busy = True                     # what the frozen callback leaves behind
    code, status = h.req("GET", "/status")
    assert status["busy"] is False and status["operations"]["running"] == 0
    h.pause_frame_loop()
    assert h.req("POST", "/tool", {"id": "b3", "name": "test.slow", "args": {"seconds": 0.0}, "wait": 0})[0] == 202
    h.bridge.is_busy = False
    code, status = h.req("GET", "/status")
    assert status["busy"] is True and status["operations"]["queued"] == 1
    h.resume_frame_loop()
    assert h.wait_terminal("b3")["status"] == "committed"


@pytest.fixture
def gate_tool():
    """A tool that blocks inside the command until the test releases it."""
    gate, entered = threading.Event(), threading.Event()
    def gated(session):
        entered.set()
        gate.wait(10)
        return {"gated": True}
    REGISTRY.add(Tool("test.gate", "block", {"type": "object"}, gated,
                      side_effect=SideEffect.NONE, undoable=False))
    yield SimpleNamespace(gate=gate, entered=entered)
    gate.set()
    REGISTRY._tools.pop("test.gate", None)


@pytest.mark.parametrize("fixture", ["inline", "h"])
def test_duplicate_arriving_mid_command_still_announces_it_once(request, fixture, gate_tool):
    """A retry that lands *while the command runs* must not suppress the
    announcement: inline, submit() executes before it returns, so both
    requests would read attempts == 2 and neither would drain or announce."""
    b = request.getfixturevalue(fixture)
    assert b.req("POST", "/feedback", {"text": "warmer"})[0] == 200
    b.events()
    body = {"id": "mid", "name": "test.gate", "args": {}}
    out: dict[str, tuple] = {}
    def post(tag):
        out[tag] = b.req("POST", "/tool", body)
    threads = [threading.Thread(target=post, args=(tag,)) for tag in ("first", "second")]
    threads[0].start()
    assert gate_tool.entered.wait(5), "command never started"
    threads[1].start()
    deadline = time.monotonic() + 5
    while b.bridge.operations.read("mid")["attempts"] < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert b.bridge.operations.read("mid")["attempts"] == 2, "duplicate never landed mid-command"
    gate_tool.gate.set()
    for t in threads: t.join(10)
    assert {code for code, _ in out.values()} == {200}
    events = b.events()
    assert [e["kind"] for e in events] == ["feedback_observed", "tool_call", "tool_result"]
    assert events[1]["payload"]["id"] == "mid"
    assert events[1]["payload"]["pending_feedback"] == ["warmer"]
    assert events[2]["payload"]["status"] == "committed"
    assert events[2]["payload"]["feedback_observed"] == ["warmer"]
    # Exactly one of the two requests owns the drained feedback, and the
    # inbox really was emptied.
    assert sorted(doc["feedback_observed"] for _, doc in out.values()) == [[], ["warmer"]]
    assert b.bridge.feedback_inbox == []
