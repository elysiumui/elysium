"""Aether external control bridge.

The Designer process opens a tiny localhost HTTP server (port 8183 by
default) when ``ELYSIUM_AETHER_BRIDGE=1`` is in its env. Anything
outside the Designer — a CLI, the IDE plugin, a Claude Code session
operating from a shell — can drive the live canvas through it.

Endpoints (all 127.0.0.1-only)
------------------------------
``GET  /state``            placement list + window doc summary
``GET  /tools``            tool registry catalog
``GET  /snapshot``         current canvas as PNG
``GET  /logs?n=200``       recent menu_status + audit log entries
``GET  /events`` (SSE)     stream of bridge activity
``POST /tool``             {name, args} → invoke a registered tool
``POST /chat``             {message, provider?} → run an Aether turn

Safety: bind on loopback only; no authentication beyond that (the user
owns every process listening on their loopback). When you ship the
Designer behind a server you turn the bridge off.
"""
from __future__ import annotations

import http.server
import json
import os
import queue
import socketserver
import threading
import time
import traceback
from pathlib import Path
from typing import Any


class AetherBridge:
    def __init__(self, designer, port: int = 8183) -> None:
        self.designer = designer
        self.port = port
        self.session = None        # lazy — only when first request lands
        from .execution import Operations
        self.operations = Operations(designer, self._ensure_session,
                                     lambda: self.paused or self.stopped)
        self.daemon  = None
        self.event_queue: queue.Queue = queue.Queue(maxsize=2000)
        self.started = False
        self._models = None
        # --- user-controllable run state ------------------------------
        # `paused` halts NEW tool calls but lets in-flight ones finish.
        # `stopped` is a hard abort: also drains the queued chat turn.
        # `pace_ms` is an optional inter-call sleep so the user can see
        # each step happen on the canvas.
        self.paused:   bool = False
        self.stopped:  bool = False
        self.pace_ms:  int  = 0
        # Visual feedback the Designer paints on top of the canvas.
        self.last_call_name:   str = ""
        self.last_call_target: str = ""       # placement id we touched
        self.last_call_ts:     float = 0.0
        self.is_busy:          bool = False
        # User-typed feedback inbox — the agent picks these up between
        # tool calls and surfaces them as observations to the LLM (or
        # to the human driver via the SSE event stream).
        self.feedback_inbox: list[str] = []
        self._feedback_lock = threading.Lock()
        # Last control event the user issued — pause / resume / stop —
        # surfaced on every response so the agent always knows the
        # current state without polling /status.
        self.last_control_action: str | None = None
        self.last_control_ts: float = 0.0

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.started: return
        self.started = True
        threading.Thread(target=self._serve, daemon=True,
                          name="aether-bridge").start()
        print(f"aether-bridge: listening on http://127.0.0.1:{self.port}",
              flush=True)

    def stop(self) -> None:
        srv = getattr(self, "_srv", None)
        if srv is not None: srv.shutdown()

    # --- user-controlled run state ----------------------------------
    def set_paused(self, value: bool) -> None:
        self.paused = bool(value)
        action = "pause" if value else "resume"
        self.last_control_action = action
        self.last_control_ts     = time.time()
        self._push_event({"kind": "control",
                           "payload": {"action": action},
                           "ts": self.last_control_ts})

    def hard_stop(self) -> None:
        """Abort everything — drain feedback inbox, cancel chat turn."""
        self.stopped = True
        self.paused  = True
        with self._feedback_lock: self.feedback_inbox.clear()
        if self.daemon: self.daemon.pause()
        self.last_control_action = "stop"
        self.last_control_ts     = time.time()
        self._push_event({"kind": "control",
                           "payload": {"action": "stop"},
                           "ts": self.last_control_ts})

    def control_snapshot(self) -> dict:
        """Compact dict embedded in every response so the agent can't
        miss a pause/stop. Drop it onto the wire alongside the actual
        return value."""
        return {
            "paused": self.paused,
            "stopped": self.stopped,
            "last_action": getattr(self, "last_control_action", None),
            "last_ts":     getattr(self, "last_control_ts", 0.0),
            "feedback_pending": len(self.feedback_inbox),
        }

    def add_feedback(self, text: str) -> None:
        """The user typed mid-stream feedback. Goes into the inbox the
        next tool dispatch sees, and is broadcast on the SSE so any
        external driver (this Claude Code shell) picks it up too."""
        if not text.strip(): return
        with self._feedback_lock: self.feedback_inbox.append(text)
        self._push_event({"kind": "user_feedback",
                           "payload": {"text": text},
                           "ts": time.time()})

    def drain_feedback(self) -> list[str]:
        with self._feedback_lock:
            out = list(self.feedback_inbox)
            self.feedback_inbox.clear()
        return out

    # ------------------------------------------------------------------
    def _ensure_session(self):
        if self.session is not None: return self.session
        # Stitch the live designer's dataclasses into a Models holder
        # the tool registry can use.
        from elysium import aether
        d = self.designer
        mod = __import__(type(d).__module__)
        # Pull Placement / AnimState / AppWindow from the running module.
        Placement = getattr(d.__class__.__module__, "Placement", None)
        if Placement is None:
            import importlib, sys
            mod_obj = sys.modules[d.__class__.__module__]
            Placement = getattr(mod_obj, "Placement")
            AnimState = getattr(mod_obj, "AnimState")
            AppWindow = getattr(mod_obj, "AppWindow")
        class _M:
            pass
        _M.Placement = Placement
        _M.AnimState = AnimState
        _M.AppWindow = AppWindow
        self._models = _M
        self.session = aether.Session(designer=d, designer_models=_M)
        return self.session

    def _ensure_daemon(self, provider: str | None = None):
        from elysium import aether
        self._ensure_session()
        if self.daemon is None or (provider and provider != getattr(
                self.daemon, "_provider_spec", None)):
            self.daemon = aether.Daemon(self.session, provider=provider)
            self.daemon._provider_spec = provider
            # Subscribe so we mirror events into the bridge's SSE stream.
            q = self.daemon.subscribe()
            threading.Thread(target=self._mirror_events, args=(q,),
                              daemon=True).start()
        return self.daemon

    def _mirror_events(self, q) -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            try:
                ev = loop.run_until_complete(q.get())
            except Exception:
                return
            self._push_event({"kind": ev.kind, "payload": ev.payload,
                                "ts": time.time()})

    def _push_event(self, ev: dict) -> None:
        try: self.event_queue.put_nowait(ev)
        except queue.Full: pass

    # ------------------------------------------------------------------
    def _serve(self) -> None:
        bridge = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a, **k): pass

            def _json(self, code: int, body) -> None:
                # Inject the bridge's current control state into EVERY
                # JSON response so callers (CLIs, IDE plugins, this
                # session) can never miss a pause/stop/resume between
                # requests. Tucked under `_bridge` so it doesn't
                # collide with a tool's normal value.
                if isinstance(body, dict):
                    body = dict(body)
                    body.setdefault("_bridge", bridge.control_snapshot())
                payload = json.dumps(body, default=str).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                # Also surface the key fields as response headers so a
                # `curl -i` or quick HEAD check shows them too.
                self.send_header("X-Aether-Paused",  "1" if bridge.paused else "0")
                self.send_header("X-Aether-Stopped", "1" if bridge.stopped else "0")
                self.end_headers()
                self.wfile.write(payload)

            def _png(self, raw: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            # --- GET --------------------------------------------------
            def do_GET(self):
                try:
                    if self.path.startswith("/operations/"):
                        if bridge.paused or bridge.stopped:
                            return self._json(423, {"error": "aether_paused_or_stopped"})
                        from urllib.parse import unquote
                        try:
                            result = bridge.operations.read(unquote(self.path[len("/operations/"):]))
                        except KeyError:
                            return self._json(404, {"error": "unknown operation"})
                        return self._json(200, result)
                    if self.path == "/state":     return self._state()
                    if self.path == "/tools":     return self._tools()
                    if self.path == "/snapshot":  return self._snapshot()
                    if self.path.startswith("/logs"):
                        return self._logs()
                    if self.path == "/events":    return self._events()
                    if self.path == "/health":    return self._json(200, {"ok": True})
                    if self.path == "/status":    return self._status()
                    if self.path == "/feedback":  return self._feedback_drain()
                    if self.path == "/_debug/transcript":
                        # Drain pending events first so we return the
                        # freshest possible transcript.
                        d = bridge.designer
                        try: d._drain_aether_events()
                        except Exception: pass
                        return self._json(200, {
                            "open": getattr(d, "aether_open", False),
                            "busy": getattr(d, "aether_busy", False),
                            "input": getattr(d, "aether_input", ""),
                            "daemon_present": getattr(d, "aether_daemon",
                                                       None) is not None,
                            "loop_running": (
                                bool(getattr(d, "_aether_loop", None)
                                       and d._aether_loop.is_running())),
                            "transcript": getattr(d, "aether_transcript",
                                                    []),
                        })
                    self.send_error(404)
                except Exception as e:
                    self._json(500, {"error": str(e),
                                       "trace": traceback.format_exc()})

            # --- POST -------------------------------------------------
            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(n).decode("utf-8") if n else "{}"
                    payload = json.loads(body or "{}")
                    if self.path == "/tool":      return self._tool(payload)
                    if self.path == "/chat":      return self._chat(payload)
                    if self.path == "/_debug/in_app_chat":
                        # Drive the Designer's IN-APP _send_aether_prompt
                        # path end-to-end (different from /chat, which
                        # uses the bridge's own daemon). This is the
                        # path the user hits when typing into the
                        # Aether panel; exposing it lets us validate
                        # the chat round-trip without a UI driver.
                        d = bridge.designer
                        msg = payload.get("message", "")
                        try:
                            d._open_aether_panel()
                            d.aether_input = msg
                            d._send_aether_prompt()
                        except Exception as exc:
                            return self._json(500, {"error": str(exc),
                                "trace": traceback.format_exc()})
                        return self._json(202, {
                            "sent": msg,
                            "daemon_present": d.aether_daemon is not None,
                            "loop_running": (
                                bool(d._aether_loop
                                       and d._aether_loop.is_running())
                                if hasattr(d, "_aether_loop") else False),
                        })
                    if self.path == "/pause":     return self._control("pause")
                    if self.path == "/resume":    return self._control("resume")
                    if self.path == "/stop":      return self._control("stop")
                    if self.path == "/pace":      return self._pace(payload)
                    if self.path == "/feedback":  return self._feedback_post(payload)
                    self.send_error(404)
                except Exception as e:
                    self._json(500, {"error": str(e),
                                       "trace": traceback.format_exc()})

            # --- handlers ---------------------------------------------
            def _state(self):
                def collect():
                    d = bridge.designer
                    session = bridge._ensure_session()
                    return {
                        "skin_path": str(d.skin_path),
                        "window": d.window_doc.to_json(),
                        "placements": [{"id": session.id_for(p), "kind": p.kind,
                            "name": p.name, "x": p.x, "y": p.y, "w": p.w, "h": p.h,
                            "hook": (p.props or {}).get("hook"),
                            "states": [state.name for state in p.states]}
                            for p in d.placements],
                        "selection": {"kind": d.sel_kind, "idx": d.sel_idx},
                        "playing": d.playing,
                        "revision": getattr(d, "_document_revision", 0),
                        "menu_status": getattr(d, "menu_status", ""),
                    }
                if bridge.paused or bridge.stopped:
                    return self._json(423, {"error": "aether_paused_or_stopped"})
                return self._json(200, bridge.operations.invoke_read(collect))

            def _tools(self):
                from elysium import aether
                cat = [{"name": t.name, "description": t.description,
                         "input_schema": t.input_schema,
                         "side_effect": t.side_effect.value,
                         "undoable": t.undoable,
                         "requires_confirmation": t.requires_confirmation}
                        for t in aether.REGISTRY.all()]
                return self._json(200, {"tools": cat, "count": len(cat)})

            def _snapshot(self):
                if bridge.paused or bridge.stopped:
                    return self._json(423, {"error": "aether_paused_or_stopped"})
                from elysium.render.designer_preview import paint_designer_png
                png = bridge.operations.invoke_read(lambda: paint_designer_png(bridge.designer))
                self._png(png)

            def _logs(self):
                bridge._ensure_session()
                from urllib.parse import urlparse, parse_qs
                n = int(parse_qs(urlparse(self.path).query).get("n", ["200"])[0])
                audit = []
                if bridge.session.audit_path and bridge.session.audit_path.is_file():
                    lines = bridge.session.audit_path.read_text().splitlines()[-n:]
                    for l in lines:
                        try: audit.append(json.loads(l))
                        except Exception: pass
                return self._json(200, {
                    "menu_status": getattr(bridge.designer, "menu_status", ""),
                    "audit": audit,
                })

            def _events(self):
                """Server-sent events stream of every tool call + result
                + chat delta — anything pushed via `_push_event`."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        try: ev = bridge.event_queue.get(timeout=10.0)
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        line = f"data: {json.dumps(ev, default=str)}\n\n"
                        self.wfile.write(line.encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _tool(self, payload):
                from concurrent.futures import TimeoutError
                if bridge.paused or bridge.stopped:
                    return self._json(423, {"error": "aether_paused_or_stopped"})
                try:
                    request_id, future = bridge.operations.submit(payload)
                    bridge.last_call_name = payload.get("name", "")
                    bridge.last_call_ts = time.time()
                    bridge.is_busy = True
                    try:
                        result = future.result(timeout=120)
                    except TimeoutError:
                        # Operation remains queryable and idempotent. A client
                        # must not blindly retry a mutation with a new id.
                        return self._json(202, bridge.operations.read(request_id))
                    status = 200 if result.get("ok") else 400
                    if "confirmation_required" in (result.get("error") or ""):
                        status = 409
                    if "aether_paused_or_stopped" in (result.get("error") or ""):
                        status = 423
                    bridge._push_event({"kind": "tool_result", "payload": result,
                                        "ts": time.time()})
                    return self._json(status, result)
                except (ValueError, TypeError) as exc:
                    return self._json(400, {"ok": False, "error": str(exc)})
                finally:
                    bridge.is_busy = False

            # --- control / introspection ----------------------------
            def _status(self):
                return self._json(200, {
                    "paused": bridge.paused,
                    "stopped": bridge.stopped,
                    "busy":   bridge.is_busy,
                    "pace_ms": bridge.pace_ms,
                    "last_call": {
                        "name":   bridge.last_call_name,
                        "target": bridge.last_call_target,
                        "ts":     bridge.last_call_ts,
                    },
                    "feedback_pending": len(bridge.feedback_inbox),
                })

            def _control(self, action):
                if action == "pause": bridge.set_paused(True)
                elif action == "resume":
                    bridge.set_paused(False); bridge.stopped = False
                elif action == "stop":  bridge.hard_stop()
                return self._json(200, {"action": action,
                                          "paused": bridge.paused,
                                          "stopped": bridge.stopped})

            def _pace(self, payload):
                bridge.pace_ms = max(0, int(payload.get("ms", 0)))
                return self._json(200, {"pace_ms": bridge.pace_ms})

            def _feedback_post(self, payload):
                text = payload.get("text", "")
                bridge.add_feedback(text)
                return self._json(200, {"queued": text})

            def _feedback_drain(self):
                msgs = bridge.drain_feedback()
                return self._json(200, {"messages": msgs})

            def _chat(self, payload):
                import asyncio
                msg = payload.get("message", "")
                provider = payload.get("provider")
                daemon = bridge._ensure_daemon(provider)
                # Fire-and-stream — turn runs on a worker thread so the
                # request returns immediately; events land on the SSE.
                loop = asyncio.new_event_loop()
                def worker():
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(daemon.turn(msg))
                threading.Thread(target=worker, daemon=True).start()
                return self._json(202, {"queued": True, "message": msg})

        class _Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        try:
            self._srv = _Server(("127.0.0.1", self.port), H)
            self._srv.serve_forever()
        except OSError as e:
            print(f"aether-bridge: port {self.port} unavailable: {e}",
                  flush=True)
