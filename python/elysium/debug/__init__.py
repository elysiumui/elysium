"""Live inspector / profiler endpoint consumed by the PyCharm + VS Code
plugins.

The runtime opens a small JSON-over-TCP server on a fixed port (default
11434) when ``ELYSIUM_INSPECTOR=1`` is in the environment. Each
``get_stats`` request returns a snapshot of the recent frame timing
ring + the last N hook events. Stays dependency-free (stdlib socket).
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections import deque
from typing import Deque


class Inspector:
    """Per-process inspector singleton. Reuse via :func:`get`."""

    def __init__(self, port: int = 11434, ring: int = 256) -> None:
        self.port = port
        self.ring = ring
        self.frame_ms:    Deque[float] = deque(maxlen=ring)
        self.paint_ms:    float = 0.0
        self.composite_ms: float = 0.0
        self.swap_ms:     float = 0.0
        self.hooks_fired: Deque[dict] = deque(maxlen=64)
        self._lock = threading.Lock()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    # ---- producers ----
    def push_frame(self, total_ms: float, *,
                    paint_ms: float = 0.0, composite_ms: float = 0.0,
                    swap_ms: float = 0.0) -> None:
        with self._lock:
            self.frame_ms.append(total_ms)
            self.paint_ms     = paint_ms
            self.composite_ms = composite_ms
            self.swap_ms      = swap_ms

    def push_hook(self, name: str, dt_ms: float) -> None:
        with self._lock:
            self.hooks_fired.append({
                "name": name, "dt_ms": dt_ms, "ts": time.time(),
            })

    # ---- server ----
    def start(self) -> None:
        if self._thread is not None: return
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="elysium-inspector")
        self._thread.start()

    def _serve(self) -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", self.port))
            srv.listen(8)
            self._server = srv
        except OSError:
            return
        while True:
            try:
                conn, _ = srv.accept()
                threading.Thread(
                    target=self._handle, args=(conn,), daemon=True,
                ).start()
            except Exception:
                return

    def _handle(self, conn: socket.socket) -> None:
        try:
            buf = b""
            while True:
                chunk = conn.recv(64)
                if not chunk: return
                buf += chunk
                while b"\n" in buf:
                    line, _, buf = buf.partition(b"\n")
                    cmd = line.decode(errors="replace").strip()
                    if cmd == "get_stats":
                        conn.sendall((self._snapshot_json() + "\n").encode())
                    elif cmd == "ping":
                        conn.sendall(b"pong\n")
                    else:
                        conn.sendall(b'{"error":"unknown"}\n')
        except Exception:
            pass
        finally:
            try: conn.close()
            except Exception: pass

    def _snapshot_json(self) -> str:
        with self._lock:
            doc = {
                "frame_ms":     list(self.frame_ms),
                "paint_ms":     self.paint_ms,
                "composite_ms": self.composite_ms,
                "swap_ms":      self.swap_ms,
                "hooks_fired":  list(self.hooks_fired),
            }
            # Drain so the inspector sees each event exactly once.
            self.hooks_fired.clear()
        return json.dumps(doc)


_INSTANCE: Inspector | None = None


def get(port: int | None = None) -> Inspector:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Inspector(port=port or
                              int(os.environ.get("ELYSIUM_INSPECTOR_PORT", "11434")))
        if os.environ.get("ELYSIUM_INSPECTOR") == "1":
            _INSTANCE.start()
    return _INSTANCE


__all__ = ["Inspector", "get"]
