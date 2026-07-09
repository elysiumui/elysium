"""Input Probe — an OS-level keyboard/mouse test target.

Why this exists
---------------
The CI smoke test proves the app *launches* (the Aether bridge comes up) but
cannot prove *input works* — which is how a Windows-only "typing is dead" bug
(winit enabled IME → typed text arrived only via `Ime::Commit`, and the
Designer's hand-rolled key loop ignored it) shipped green.

Catching that class of bug needs input injected at the **OS level** (real
events through the OS → winit → framework), and verified at the **app level**.
Injecting via `on_key()` or the Aether bridge would bypass the exact winit/IME
layer the bug lived in and pass while users are broken.

This app is the deterministic verification target: it records the *raw*
`poll_key_event` stream (code + text, straight off the native queue — no
`InputRouter`, which would mask the bug by also handling `on_ime_commit`) plus
mouse clicks, and serves them over HTTP. A test (`tests/test_os_input.py`)
launches it, injects real OS input per platform (xdotool on Linux, pywinauto on
Windows), and asserts the round-trip — e.g. typing "hello" must yield
`KeyEvent.text == "hello"`, which went red on Windows before the IME fix.

Run:  ELYSIUM_PROBE_PORT=8199 python -m examples.input-probe
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading

import elysium as ely
from elysium import anim
from elysium._native import _native as _n

HOST = "127.0.0.1"
PORT = int(os.environ.get("ELYSIUM_PROBE_PORT", "8199"))
WIDTH, HEIGHT = 400, 300
# A visible click target the mouse test aims at (window-logical coords).
TARGET = (200, 150, 40)  # cx, cy, radius


class ProbeState:
    """Everything the OS input delivered, guarded by a lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.frames = 0
        self.text = ""                       # printable text from ANY source
        # Text delivered specifically via `KeyboardInput` (code != "ImeCommit").
        # THIS is the field that catches the Windows IME bug: when IME is on,
        # Windows routes typed text only through `Ime::Commit`, leaving
        # KeyboardInput's `text` empty, so `kbd_text` comes back empty while the
        # all-sources `text` still fills. Asserting on `kbd_text` reproduces the
        # exact regression; asserting on `text` would not.
        self.kbd_text = ""
        self.raw_events: list[dict] = []     # every poll_key_event, verbatim
        self.clicks: list[dict] = []         # left-click positions
        self.right_clicks = 0

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "ready": self.frames > 3,    # window is live + painting
                "frames": self.frames,
                "text": self.text,
                "kbd_text": self.kbd_text,
                "raw_events": list(self.raw_events),
                "key_event_count": len(self.raw_events),
                "clicks": list(self.clicks),
                "right_clicks": self.right_clicks,
            }

    def reset(self) -> None:
        with self.lock:
            self.text = ""
            self.kbd_text = ""
            self.raw_events.clear()
            self.clicks.clear()
            self.right_clicks = 0


STATE = ProbeState()


def _start_http(app: ely.App) -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a):  # silence access logging
            pass

        def _send(self, code: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._send(200, STATE.snapshot())

        def do_POST(self):
            if self.path.rstrip("/") == "/reset":
                STATE.reset()
                self._send(200, {"ok": True})
            elif self.path.rstrip("/") == "/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=app.quit, daemon=True).start()
            else:
                self._send(404, {"error": "not found"})

    class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = Threaded((HOST, PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="probe-http").start()


class Probe:
    def __init__(self) -> None:
        self.app = ely.App(title="Elysium Input Probe",
                           identifier="dev.elysium.inputprobe")
        # A plain decorated, opaque, fixed-size window: easiest thing for a CI
        # injector to find by title, foreground, and aim clicks at.
        self.win = self.app.window(transparent=False, title_bar=True,
                                   resizable=False, initial_size=(WIDTH, HEIGHT))
        self.clock = anim.AnimationClock()
        self._press_count = 0
        self._right_press_count = 0

    def on_frame(self) -> None:
        # 1) Drain the raw native key queue — record code + text exactly as the
        #    OS/winit delivered it. This is the layer the Windows IME bug broke.
        while True:
            ev = self.win.poll_key_event()
            if ev is None:
                break
            code, pressed, mods, text = ev
            with STATE.lock:
                STATE.raw_events.append(
                    {"code": code, "pressed": pressed, "mods": mods, "text": text})
                if pressed and text:
                    STATE.text += text
                    if code != "ImeCommit":
                        STATE.kbd_text += text

        # 2) Left clicks — press_count is a monotonic press-transition counter.
        pc = self.win.press_count
        if pc != self._press_count:
            self._press_count = pc
            cur = self.win.cursor_position
            with STATE.lock:
                STATE.clicks.append({"x": cur[0] if cur else None,
                                     "y": cur[1] if cur else None,
                                     "n": pc})

        # 3) Right clicks.
        rpc = self.win.right_press_count
        if rpc != self._right_press_count:
            self._right_press_count = rpc
            with STATE.lock:
                STATE.right_clicks += 1

        # 4) Paint something opaque so it's a real, visible, focusable window,
        #    with a marker at the click target for debugging.
        dl = _n.DisplayList()
        dl.clear(0.11, 0.13, 0.18, 1.0)
        dl.filled_circle(TARGET[0], TARGET[1], TARGET[2], (120, 140, 255, 255))
        self.win.publish_display_list(dl)

        with STATE.lock:
            STATE.frames += 1

    def run(self) -> None:
        _start_http(self.app)
        # is_busy=True keeps a steady 60 Hz so input drains promptly (no idle
        # decay to 4 Hz mid-test).
        anim.run_animation_thread(self.clock, self.on_frame,
                                  target_hz=60.0, is_busy=lambda: True)
        print(f"input-probe ready host={HOST} port={PORT}", flush=True)
        self.app.run()


def main() -> int:
    Probe().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
