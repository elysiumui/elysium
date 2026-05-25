"""Snapshot Relay — Elysium demo + headless screenshot service.

Why this exists
---------------
macOS gates `screencapture` (and CoreGraphics' `CGWindowListCreateImage`)
behind the Screen Recording entitlement. The permission is bound to a
specific bundle identifier — terminal sessions and ad-hoc scripts can't
hold it persistently. This app is a stable target the user grants the
entitlement *to once*, and that holds across runs and reboots.

What it does
------------
  • Runs an Elysium-rendered UI showing:
      - The relay's HTTP endpoint
      - Permission state (green when the last capture succeeded)
      - Live count + most-recent thumbnail
      - Capture / Clear / Quit buttons
  • Listens on http://127.0.0.1:8181 with a tiny REST API:
      GET    /                         status JSON
      POST   /capture[?delay=N]        full-screen PNG → returns path
      POST   /capture/region?x=&y=&w=&h=
      GET    /captures                 list of currently saved files
      GET    /captures/<filename>      serves a PNG
      DELETE /captures                 deletes all
      DELETE /captures/<filename>      deletes one

Saved files live in /tmp/elysium-shots/ so anything that can read /tmp
(Claude's Read tool, an LLM agent, your own scripts) can pick them up.

Usage
-----
    .venv/bin/python -m examples.snapshot-relay
    # or, for a permission-grantable bundle:
    open examples/snapshot-relay/SnapshotRelay.app
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import elysium as ely
from elysium import anim, components as ui, reactive, theme as themes
from elysium._native import _native as _n


SHOTS_DIR = Path("/tmp/elysium-shots")
SHOTS_DIR.mkdir(exist_ok=True)
PORT = int(os.environ.get("ELYSIUM_SNAPSHOT_PORT", "8181"))
HOST = "127.0.0.1"

WIDTH, HEIGHT = 760, 540

# Shared state between HTTP thread + UI thread.
class State:
    def __init__(self) -> None:
        self.last_capture_path: str | None = None
        self.last_capture_t:    float = 0.0
        self.capture_count:     int = 0
        self.last_error:        str | None = None
        self.permission_ok:     bool = False
        self.requests_total:    int = 0
        self.lock = threading.Lock()

STATE = State()


# --- Screenshot primitives -------------------------------------------------

def _next_path() -> Path:
    ts = int(time.time() * 1000)
    return SHOTS_DIR / f"shot-{ts}.png"


def capture_full_screen(delay: float = 0.0) -> Path:
    """Capture the entire main display. Raises on failure."""
    if delay > 0:
        time.sleep(delay)
    out = _next_path()
    # -x = no sound, -C = capture cursor, -t png = format.
    proc = subprocess.run(
        ["screencapture", "-x", "-C", "-t", "png", str(out)],
        check=False, capture_output=True, timeout=15,
    )
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        err = proc.stderr.decode("utf-8", "ignore").strip()
        raise RuntimeError(
            "screencapture failed — likely Screen Recording permission is "
            f"missing for this app. Grant it in System Settings → Privacy & "
            f"Security → Screen Recording, then retry. ({err})")
    return out


def capture_region(x: int, y: int, w: int, h: int) -> Path:
    out = _next_path()
    proc = subprocess.run(
        ["screencapture", "-x", "-t", "png",
         "-R", f"{x},{y},{w},{h}", str(out)],
        check=False, capture_output=True, timeout=15,
    )
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(
            f"screencapture failed: {proc.stderr.decode('utf-8','ignore')}")
    return out


def clear_all() -> int:
    n = 0
    for f in SHOTS_DIR.glob("shot-*.png"):
        try: f.unlink(); n += 1
        except FileNotFoundError: pass
    return n


# --- HTTP server -----------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *a): pass    # silence stdout

    def _json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        STATE.requests_total += 1
        url = urlparse(self.path)
        if url.path == "/":
            with STATE.lock:
                self._json(200, {
                    "ok": True,
                    "endpoint": f"http://{HOST}:{PORT}",
                    "shots_dir": str(SHOTS_DIR),
                    "capture_count": STATE.capture_count,
                    "last_capture": STATE.last_capture_path,
                    "last_capture_t": STATE.last_capture_t,
                    "permission_ok": STATE.permission_ok,
                    "last_error": STATE.last_error,
                })
            return
        if url.path == "/captures":
            files = sorted(p.name for p in SHOTS_DIR.glob("shot-*.png"))
            self._json(200, {"count": len(files), "files": files})
            return
        if url.path.startswith("/captures/"):
            name = url.path[len("/captures/"):]
            p = SHOTS_DIR / name
            if not p.is_file():
                self._json(404, {"ok": False, "error": "not found"}); return
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json(404, {"ok": False, "error": "unknown route"})

    def do_POST(self) -> None:
        STATE.requests_total += 1
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/capture":
                delay = float(q.get("delay", "0"))
                p = capture_full_screen(delay)
            elif url.path == "/capture/region":
                p = capture_region(int(q["x"]), int(q["y"]),
                                   int(q["w"]), int(q["h"]))
            else:
                self._json(404, {"ok": False, "error": "unknown route"}); return
        except Exception as e:
            with STATE.lock:
                STATE.last_error = str(e)
                STATE.permission_ok = False
            self._json(500, {"ok": False, "error": str(e)}); return
        with STATE.lock:
            STATE.last_capture_path = str(p)
            STATE.last_capture_t = time.time()
            STATE.capture_count += 1
            STATE.last_error = None
            STATE.permission_ok = True
        self._json(200, {"ok": True, "path": str(p),
                         "size_bytes": p.stat().st_size})

    def do_DELETE(self) -> None:
        STATE.requests_total += 1
        url = urlparse(self.path)
        if url.path == "/captures":
            n = clear_all()
            with STATE.lock:
                STATE.last_capture_path = None
            self._json(200, {"ok": True, "deleted": n})
            return
        if url.path.startswith("/captures/"):
            name = url.path[len("/captures/"):]
            p = SHOTS_DIR / name
            if p.is_file():
                p.unlink()
                self._json(200, {"ok": True, "deleted": 1})
            else:
                self._json(404, {"ok": False, "error": "not found"})
            return
        self._json(404, {"ok": False, "error": "unknown route"})


def start_http_server() -> threading.Thread:
    class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True
    srv = Threaded((HOST, PORT), Handler)

    def loop() -> None:
        srv.serve_forever()

    t = threading.Thread(target=loop, daemon=True, name="snapshot-relay-http")
    t.start()
    return t


# --- Elysium UI ------------------------------------------------------------

class SnapshotApp:
    def __init__(self) -> None:
        self.app = ely.App(title="Snapshot Relay", identifier="dev.elysium.snapshot")
        self.win = self.app.window(transparent=False, title_bar=True,
                                   resizable=True, initial_size=(WIDTH, HEIGHT))
        themes.set_theme(themes.midnight_glass())

        self.capture_btn = ui.Button(w=180, h=44, label="Capture now",
                                     variant="solid", on_click=self._do_capture)
        self.clear_btn   = ui.Button(w=180, h=44, label="Clear all",
                                     variant="outline", on_click=self._do_clear)
        self.copy_btn    = ui.Button(w=180, h=44, label="Copy endpoint",
                                     variant="ghost", on_click=self._copy_endpoint)

        self.clock = anim.AnimationClock()
        self.running = {"v": True}
        self._was_pressed = False
        self._press_count = 0

    def _do_capture(self) -> None:
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self) -> None:
        try:
            p = capture_full_screen()
            with STATE.lock:
                STATE.last_capture_path = str(p)
                STATE.last_capture_t = time.time()
                STATE.capture_count += 1
                STATE.last_error = None
                STATE.permission_ok = True
        except Exception as e:
            with STATE.lock:
                STATE.last_error = str(e)
                STATE.permission_ok = False

    def _do_clear(self) -> None:
        clear_all()
        with STATE.lock:
            STATE.last_capture_path = None

    def _copy_endpoint(self) -> None:
        try:
            subprocess.run(["pbcopy"], input=f"http://{HOST}:{PORT}".encode(),
                           check=False)
        except Exception:
            pass

    def on_frame(self) -> None:
        cur = self.win.cursor_position
        pressed = self.win.mouse_pressed
        pc = self.win.press_count
        click_just = pc != self._press_count and pressed
        self._press_count = pc; self._was_pressed = pressed

        for btn in (self.capture_btn, self.clear_btn, self.copy_btn):
            hov = cur is not None and btn.hit_test(*cur)
            btn.update(0.016, {"hover": hov, "pressed": hov and pressed})
            if click_just and hov:
                btn.fire_click()

        dl = _n.DisplayList()
        self._paint(dl)
        self.win.publish_display_list(dl)

    def _paint(self, dl) -> None:
        t = themes.current_theme()
        dl.clear_color(*[c / 255.0 for c in t.surface])

        # Header.
        dl.draw_text("Snapshot Relay", 28, 44, 24, t.on_surface)
        dl.draw_text("Headless screenshot service for the Elysium framework",
                     28, 70, 12, t.on_surface_muted)

        # Status card.
        ui.Card(x=24, y=92, w=WIDTH - 48, h=120, elevation="medium",
                material="elevated").paint(dl)

        with STATE.lock:
            cap_count = STATE.capture_count
            last_path = STATE.last_capture_path
            ok = STATE.permission_ok
            err = STATE.last_error
            requests = STATE.requests_total
            last_t = STATE.last_capture_t

        # Dot + label.
        dot_color = (52, 199, 89, 255) if ok else (255, 159, 10, 255) if cap_count == 0 else (255, 69, 58, 255)
        dl.filled_circle(56, 130, 7, dot_color)
        status_text = "Ready — grant Screen Recording on first capture" if cap_count == 0 else \
                      "Permission granted ✓" if ok else "Last capture failed"
        dl.draw_text(status_text, 76, 134, 13, t.on_surface)

        dl.draw_text(f"Endpoint:", 44, 168, 11, t.on_surface_muted)
        dl.draw_text(f"http://{HOST}:{PORT}", 110, 168, 12, t.primary)
        dl.draw_text(f"Saves to:", 44, 188, 11, t.on_surface_muted)
        dl.draw_text(str(SHOTS_DIR), 110, 188, 12, t.on_surface)

        # Counters row.
        dl.draw_text(f"{cap_count}", WIDTH - 200, 138, 26, t.primary)
        dl.draw_text("captures", WIDTH - 200, 158, 11, t.on_surface_muted)
        dl.draw_text(f"{requests}", WIDTH - 110, 138, 26, t.accent)
        dl.draw_text("requests", WIDTH - 110, 158, 11, t.on_surface_muted)

        # Error banner (if any).
        if err:
            ui.Card(x=24, y=224, w=WIDTH - 48, h=46, elevation="close",
                    fill=(255, 69, 58, 60)).paint(dl)
            dl.draw_text("⚠  " + err[:88], 40, 252, 11, (255, 200, 200, 255))

        # Recent capture thumbnail.
        thumb_y = 290
        if last_path and Path(last_path).is_file():
            ui.Card(x=24, y=thumb_y, w=WIDTH - 48, h=160,
                    elevation="medium", material="elevated").paint(dl)
            dl.draw_text("Most recent", 40, thumb_y + 24, 12, t.on_surface_muted)
            dl.draw_text(Path(last_path).name, 40, thumb_y + 44, 11, t.on_surface)
            age = time.time() - last_t
            dl.draw_text(f"{age:.1f}s ago", 40, thumb_y + 62, 11, t.on_surface_muted)
            # Inline thumbnail (Skia decodes + scales).
            try:
                dl.draw_image_file(last_path, WIDTH - 248, thumb_y + 16, 224, 126)
            except Exception:
                pass
        else:
            ui.Card(x=24, y=thumb_y, w=WIDTH - 48, h=160,
                    elevation="close", fill=themes.with_alpha(t.surface_variant, 0.4)
                    ).paint(dl)
            dl.draw_text("No captures yet — click 'Capture now' to test.",
                         44, thumb_y + 90, 12, t.on_surface_muted)

        # Buttons row.
        by = HEIGHT - 70
        self.capture_btn.x = 24;                                 self.capture_btn.y = by
        self.clear_btn.x   = 24 + self.capture_btn.w + 12;       self.clear_btn.y   = by
        self.copy_btn.x    = 24 + (self.capture_btn.w + 12) * 2; self.copy_btn.y    = by
        self.capture_btn.paint(dl); self.clear_btn.paint(dl); self.copy_btn.paint(dl)

    def run(self) -> None:
        anim.run_animation_thread(self.clock, self.on_frame, target_hz=30.0,
                                  idle_hz=2.0, idle_after=1.0,
                                  running=lambda: self.running["v"])
        try:
            self.app.run()
        finally:
            self.running["v"] = False


def main() -> int:
    start_http_server()
    print(f"snapshot-relay listening on http://{HOST}:{PORT}", flush=True)
    print(f"shots dir: {SHOTS_DIR}", flush=True)
    SnapshotApp().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
