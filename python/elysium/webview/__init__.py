"""Embedded webview component.

Wraps the platform-native browser:
  * macOS — ``WKWebView`` via the Objective-C runtime (objc2 backend
    when available, ctypes fallback otherwise).
  * Windows — WebView2 via the Edge runtime; requires the Evergreen
    runtime to be present (ships with Windows 11; auto-installed by the
    Edge Updater on Windows 10).
  * Linux — WebKitGTK 6.0 via GIRepository; pulls in
    ``gir1.2-webkit-6.0`` on Debian/Ubuntu.

Public API
----------

.. code-block:: python

    from elysium.webview import WebView

    wv = WebView(width=800, height=600)
    wv.load_url("https://example.com")
    wv.expose("greet", lambda name: f"hi, {name}")

    # later from JS:
    #   const reply = await window.elysium.greet("kenley");

The webview composites *inside* a skin layer — the framework hands it a
Skia-backed texture each frame so the embedded content inherits the
parent window's rounding, blur, and animation state.
"""
from __future__ import annotations

import inspect
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


_Handler = Callable[..., Any | Awaitable[Any]]


@dataclass
class WebView:
    width:  int = 800
    height: int = 600
    user_agent: str | None = None
    background: tuple[int, int, int, int] = (0, 0, 0, 0)
    _exposed: dict[str, _Handler] = field(default_factory=dict)
    _backend: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._backend = _resolve_backend(self)

    def load_url(self, url: str) -> None: self._backend.load_url(url)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        self._backend.load_html(html, base_url)

    def reload(self) -> None:  self._backend.reload()
    def back(self) -> None:    self._backend.back()
    def forward(self) -> None: self._backend.forward()

    async def evaluate_js(self, code: str) -> Any:
        return await self._backend.evaluate_js(code)

    def expose(self, name: str, fn: _Handler) -> None:
        """Surface a Python callable as ``window.elysium.<name>(...)``."""
        if not name.isidentifier():
            raise ValueError(f"webview.expose: bad name {name!r}")
        self._exposed[name] = fn
        self._backend.refresh_bridge(list(self._exposed.keys()))

    async def _dispatch(self, payload: str) -> str:
        """Backend → Python message dispatch."""
        try:
            msg  = json.loads(payload)
            name = msg["name"]
            args = msg.get("args", [])
            fn = self._exposed.get(name)
            if fn is None:
                return json.dumps({"error": f"no such handler: {name}"})
            result = fn(*args)
            if inspect.isawaitable(result):
                result = await result
            return json.dumps({"id": msg.get("id"), "result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def snapshot_rgba(self) -> bytes:
        """Render the current page into a premul RGBA buffer suitable for
        ``DisplayList::draw_image_bytes``."""
        return self._backend.snapshot_rgba()

    def paint(self, dl, x: float, y: float,
              w: float | None = None, h: float | None = None) -> bool:
        """Composite the latest webview snapshot into ``dl`` at
        ``(x, y, w, h)``. Skipped when the backend can't produce pixels
        (headless test mode). Returns True on success."""
        rgba = self.snapshot_rgba()
        if not rgba: return False
        w = w if w is not None else float(self.width)
        h = h if h is not None else float(self.height)
        dl.draw_image_bytes(rgba, self.width, self.height, x, y, w, h)
        return True


def _resolve_backend(view: "WebView"):
    if sys.platform == "darwin":
        try:
            from .macos import WkWebViewBackend
            return WkWebViewBackend(view)
        except Exception as e:
            print(f"WebView macOS backend unavailable: {e}", file=sys.stderr)
    elif sys.platform == "win32":
        try:
            from .windows import WebView2Backend
            return WebView2Backend(view)
        except Exception as e:
            print(f"WebView2 backend unavailable: {e}", file=sys.stderr)
    elif sys.platform.startswith("linux"):
        try:
            from .linux import WebKitGtkBackend
            return WebKitGtkBackend(view)
        except Exception as e:
            print(f"WebKitGTK backend unavailable: {e}", file=sys.stderr)
    return _NullBackend()


class _NullBackend:
    """Headless fallback. Every call is a no-op so tests and unsupported
    platforms can still construct a WebView without crashing."""
    def load_url(self, url: str) -> None: pass
    def load_html(self, html: str, base_url: str | None = None) -> None: pass
    def reload(self) -> None: pass
    def back(self) -> None: pass
    def forward(self) -> None: pass
    async def evaluate_js(self, code: str) -> Any: return None
    def refresh_bridge(self, names: list[str]) -> None: pass
    def snapshot_rgba(self) -> bytes: return b""


__all__ = ["WebView"]
