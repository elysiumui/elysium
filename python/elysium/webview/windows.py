"""WebView2 backend via the ``webview2`` Python bindings (or pywebview).

Uses pywebview's WebView2 backend when available — that gives us a
maintained Edge-Chromium binding without re-implementing the COM
interfaces by hand. Falls back to a clear runtime error otherwise.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


class WebView2Backend:
    def __init__(self, view) -> None:
        try:
            import webview  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "WebView2 backend needs `pip install pywebview` (Windows)."
            ) from e
        self.view = view
        self._w = webview
        self._window = webview.create_window(
            title="elysium-webview",
            html="",
            width=view.width,
            height=view.height,
            hidden=True,                  # we composite via snapshot
        )

    def load_url(self, url: str) -> None:
        self._window.load_url(url)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        self._window.load_html(html)

    def reload(self) -> None:
        self._window.evaluate_js("location.reload()")

    def back(self) -> None:    self._window.evaluate_js("history.back()")
    def forward(self) -> None: self._window.evaluate_js("history.forward()")

    async def evaluate_js(self, code: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None,
                                          lambda: self._window.evaluate_js(code))

    def refresh_bridge(self, names: list[str]) -> None:
        # pywebview exposes a window.pywebview.api.* bridge already;
        # we wrap it under window.elysium.* to keep the cross-platform
        # contract identical.
        bridge = "(function(){window.elysium=window.elysium||{};"
        for n in names:
            bridge += f"window.elysium.{n}=function(...a){{" \
                      f"return window.pywebview.api.{n}.apply(null,a);}};"
        bridge += "})();"
        try:
            self._window.evaluate_js(bridge)
        except Exception:
            pass

    def snapshot_rgba(self) -> bytes:
        # pywebview gives us a PNG via `get_screenshot()` (>=4.4); we
        # decode through PIL to RGBA bytes.
        try:
            from PIL import Image
            import io
            png = self._window.get_screenshot()
            img = Image.open(io.BytesIO(png)).convert("RGBA")
            return img.tobytes()
        except Exception:
            return b""
