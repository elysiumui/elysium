"""Agent Cursor — Elysium-built mouse/keyboard relay with an emergency stop.

Lets me (the AI agent) drive the mouse + keyboard via HTTP while the user
keeps a literal "STOP" button on-screen at all times. Clicking STOP
immediately disarms the relay; any new input commands are rejected with
423 Locked until the user clicks ARM again.

Usage
-----
    .venv/bin/python -m examples.agent-cursor

The window stays floating (NSWindow level = floating) so it's always
visible above the apps I'm driving.

HTTP API on http://127.0.0.1:8182
---------------------------------
    GET    /             status JSON
    POST   /move?x=&y=               move cursor (allowed even disarmed)
    POST   /click?x=&y=[&button=]    click at coords (armed only)
    POST   /drag?fx=&fy=&tx=&ty=     press → drag → release (armed only)
    POST   /key?code=                tap a key (armed only)
    POST   /arm                      re-enable from any source
    POST   /disarm                   same as the STOP button
"""
from __future__ import annotations

import ctypes
import http.server
import json
import socketserver
import threading
import time
from ctypes import c_double, c_int, c_uint32, c_void_p
from ctypes.util import find_library
from typing import Any
from urllib.parse import parse_qs, urlparse

import elysium as ely
from elysium import anim, components as ui, reactive, theme as themes
from elysium._native import _native as _n


# --- macOS CoreGraphics input bindings -------------------------------------

class CGPoint(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


_cg = ctypes.CDLL(find_library("ApplicationServices"))
_cf = ctypes.CDLL(find_library("CoreFoundation"))

_cg.CGWarpMouseCursorPosition.argtypes = [CGPoint]
_cg.CGWarpMouseCursorPosition.restype = c_int
_cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_uint32, CGPoint, c_uint32]
_cg.CGEventCreateMouseEvent.restype = c_void_p
_cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint32, ctypes.c_bool]
_cg.CGEventCreateKeyboardEvent.restype = c_void_p
_cg.CGEventPost.argtypes = [c_uint32, c_void_p]
_cg.CGEventPost.restype = None
_cf.CFRelease.argtypes = [c_void_p]
_cf.CFRelease.restype = None

_kCGEventLeftMouseDown   = 1
_kCGEventLeftMouseUp     = 2
_kCGEventRightMouseDown  = 3
_kCGEventRightMouseUp    = 4
_kCGEventMouseMoved      = 5
_kCGEventLeftMouseDragged = 6
_kCGMouseButtonLeft  = 0
_kCGMouseButtonRight = 1
_kCGHIDEventTap = 0


def _post_mouse(event_type: int, x: float, y: float, button: int) -> None:
    pt = CGPoint(x, y)
    ev = _cg.CGEventCreateMouseEvent(None, event_type, pt, button)
    if ev:
        _cg.CGEventPost(_kCGHIDEventTap, ev)
        _cf.CFRelease(ev)


def warp(x: float, y: float) -> None:
    _cg.CGWarpMouseCursorPosition(CGPoint(x, y))


def click(x: float, y: float, button: str = "left") -> None:
    btn = _kCGMouseButtonRight if button == "right" else _kCGMouseButtonLeft
    down = _kCGEventRightMouseDown if button == "right" else _kCGEventLeftMouseDown
    up   = _kCGEventRightMouseUp   if button == "right" else _kCGEventLeftMouseUp
    warp(x, y)
    time.sleep(0.02)
    _post_mouse(down, x, y, btn)
    time.sleep(0.05)
    _post_mouse(up,   x, y, btn)


def drag(fx: float, fy: float, tx: float, ty: float, steps: int = 12) -> None:
    warp(fx, fy)
    time.sleep(0.02)
    _post_mouse(_kCGEventLeftMouseDown, fx, fy, _kCGMouseButtonLeft)
    # Hold briefly after the press so the target app's frame loop notices
    # `pressed=True` at the start position — important when the target is
    # in idle-decay (4 Hz) polling.
    time.sleep(0.30)
    for i in range(1, steps + 1):
        u = i / steps
        x = fx + (tx - fx) * u
        y = fy + (ty - fy) * u
        _post_mouse(_kCGEventLeftMouseDragged, x, y, _kCGMouseButtonLeft)
        time.sleep(0.025)
    # Linger at the end too so the target sees the final drag position
    # before the release transitions `pressed=False`.
    time.sleep(0.20)
    _post_mouse(_kCGEventLeftMouseUp, tx, ty, _kCGMouseButtonLeft)


def key_tap(code: int) -> None:
    down = _cg.CGEventCreateKeyboardEvent(None, code, True)
    up   = _cg.CGEventCreateKeyboardEvent(None, code, False)
    _cg.CGEventPost(_kCGHIDEventTap, down); _cf.CFRelease(down)
    time.sleep(0.02)
    _cg.CGEventPost(_kCGHIDEventTap, up);   _cf.CFRelease(up)


# --- Shared armed state ----------------------------------------------------

class State:
    def __init__(self) -> None:
        self.armed:        bool = True
        self.last_op:      str = ""
        self.last_t:       float = 0.0
        self.ops_total:    int = 0
        self.blocked_total: int = 0
        self.lock = threading.Lock()

STATE = State()
PORT  = 8182
HOST  = "127.0.0.1"
WIDTH, HEIGHT = 300, 168


# --- HTTP server -----------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k): pass

    def _json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/":
            with STATE.lock:
                self._json(200, {
                    "armed": STATE.armed,
                    "ops_total": STATE.ops_total,
                    "blocked_total": STATE.blocked_total,
                    "last_op": STATE.last_op,
                    "last_t": STATE.last_t,
                    "endpoint": f"http://{HOST}:{PORT}",
                })
            return
        self._json(404, {"ok": False})

    def do_POST(self) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        with STATE.lock:
            armed = STATE.armed
        # Always-allowed routes.
        if u.path == "/arm":
            with STATE.lock: STATE.armed = True
            self._json(200, {"ok": True, "armed": True}); return
        if u.path == "/disarm":
            with STATE.lock: STATE.armed = False
            self._json(200, {"ok": True, "armed": False}); return
        if u.path == "/move":
            try:
                warp(float(q["x"]), float(q["y"]))
                self._record(f"move {q['x']},{q['y']}")
                self._json(200, {"ok": True}); return
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)}); return
        # Armed-only routes.
        if not armed:
            with STATE.lock: STATE.blocked_total += 1
            self._json(423, {"ok": False, "error": "disarmed — user must arm"})
            return
        try:
            if u.path == "/click":
                click(float(q["x"]), float(q["y"]), q.get("button", "left"))
                self._record(f"click {q['x']},{q['y']}")
            elif u.path == "/drag":
                drag(float(q["fx"]), float(q["fy"]),
                     float(q["tx"]), float(q["ty"]),
                     int(q.get("steps", "12")))
                self._record(f"drag {q['fx']},{q['fy']} → {q['tx']},{q['ty']}")
            elif u.path == "/key":
                key_tap(int(q["code"]))
                self._record(f"key {q['code']}")
            else:
                self._json(404, {"ok": False}); return
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)}); return
        self._json(200, {"ok": True})

    def _record(self, op: str) -> None:
        with STATE.lock:
            STATE.last_op = op
            STATE.last_t = time.time()
            STATE.ops_total += 1


def start_http() -> threading.Thread:
    class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True
    srv = Threaded((HOST, PORT), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True,
                         name="agent-cursor-http")
    t.start()
    return t


# --- Elysium UI ------------------------------------------------------------

class AgentCursorApp:
    def __init__(self) -> None:
        self.app = ely.App(title="Agent Cursor", identifier="dev.elysium.agent-cursor")
        self.win = self.app.window(transparent=False, title_bar=True,
                                   resizable=False, initial_size=(WIDTH, HEIGHT))
        themes.set_theme(themes.midnight_glass())
        # Keep this window above everything I'm driving.
        try: self.win.set_window_level(3)         # 3 = floating
        except Exception: pass

        self.stop_btn = ui.Button(w=WIDTH - 28, h=44,
                                  label="■  STOP — disarm cursor",
                                  variant="danger",
                                  on_click=self._stop)
        self.arm_btn  = ui.Button(w=WIDTH - 28, h=44,
                                  label="▶  ARM cursor",
                                  variant="solid",
                                  on_click=self._arm)

        self.clock = anim.AnimationClock()
        self.running = {"v": True}
        self._press_count = 0
        self._was_pressed = False

    def _stop(self) -> None:
        with STATE.lock:
            STATE.armed = False

    def _arm(self) -> None:
        with STATE.lock:
            STATE.armed = True

    def on_frame(self) -> None:
        cur = self.win.cursor_position
        pressed = self.win.mouse_pressed
        pc = self.win.press_count
        press_just = pc != self._press_count
        self._press_count = pc; self._was_pressed = pressed

        with STATE.lock:
            armed = STATE.armed
        btn = self.stop_btn if armed else self.arm_btn
        hov = cur is not None and btn.hit_test(*cur)
        btn.update(0.016, {"hover": hov, "pressed": hov and pressed})
        if press_just and hov:
            btn.fire_click()

        dl = _n.DisplayList()
        self._paint(dl, armed)
        self.win.publish_display_list(dl)

    def _paint(self, dl, armed: bool) -> None:
        t = themes.current_theme()
        dl.clear_color(*[c / 255.0 for c in t.surface])

        # Header.
        dl.draw_text("Agent Cursor", 16, 30, 16, t.on_surface)
        with STATE.lock:
            ops = STATE.ops_total
            blocked = STATE.blocked_total
            last_op = STATE.last_op
            last_t = STATE.last_t

        # Status dot.
        dot = (52, 199, 89, 255) if armed else (255, 69, 58, 255)
        dl.filled_circle(WIDTH - 32, 28, 7, dot)
        dl.draw_text("ARMED" if armed else "DISARMED",
                     WIDTH - 100, 32, 11,
                     (180, 230, 200, 255) if armed else (255, 200, 200, 255))

        # Counters / last op.
        dl.draw_text(f"ops: {ops}    blocked: {blocked}",
                     16, 56, 11, t.on_surface_muted)
        if last_op:
            age = time.time() - last_t
            dl.draw_text(f"last: {last_op[:32]} · {age:.1f}s ago",
                         16, 74, 10, t.on_surface_muted)

        # Big button.
        btn = self.stop_btn if armed else self.arm_btn
        btn.x = 14; btn.y = HEIGHT - 60
        btn.paint(dl)

    def run(self) -> None:
        anim.run_animation_thread(self.clock, self.on_frame,
                                  target_hz=30.0, idle_hz=2.0, idle_after=1.0,
                                  running=lambda: self.running["v"])
        try:
            self.app.run()
        finally:
            self.running["v"] = False


def main() -> int:
    start_http()
    print(f"agent-cursor on http://{HOST}:{PORT} — ARMED at start", flush=True)
    AgentCursorApp().run()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
