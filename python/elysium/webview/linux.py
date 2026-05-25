"""WebKitGTK 6.0 backend via gi (GObject Introspection).

Requires::

    sudo apt-get install gir1.2-webkit-6.0 python3-gi

Falls back to a clear runtime error if PyGObject + WebKit aren't
installed.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any


class WebKitGtkBackend:
    def __init__(self, view) -> None:
        try:
            import gi  # type: ignore
            gi.require_version("WebKit", "6.0")
            gi.require_version("Gtk", "4.0")
            from gi.repository import WebKit, Gtk  # type: ignore
        except (ImportError, ValueError) as e:
            raise RuntimeError(
                "WebKitGTK backend needs `gir1.2-webkit-6.0` + PyGObject."
            ) from e
        self.view = view
        self._WebKit = WebKit
        self._Gtk    = Gtk

        # Offscreen native view — we drive painting via Cairo, then read
        # back to RGBA for compositing inside the parent SkiaLayer.
        self._wv = WebKit.WebView()
        self._wv.set_size_request(view.width, view.height)
        self._settings = self._wv.get_settings()
        if view.user_agent:
            self._settings.set_user_agent(view.user_agent)

        # Bridge: register a UserContentManager handler under the
        # script-message name "elysium". Handler fires Python dispatch.
        self._ucm = self._wv.get_user_content_manager()
        self._ucm.register_script_message_handler("elysium", None)
        self._ucm.connect("script-message-received::elysium",
                          self._on_message)

    def load_url(self, url: str) -> None:  self._wv.load_uri(url)
    def load_html(self, html: str, base_url: str | None = None) -> None:
        self._wv.load_html(html, base_url)
    def reload(self) -> None:  self._wv.reload()
    def back(self) -> None:    self._wv.go_back()
    def forward(self) -> None: self._wv.go_forward()

    async def evaluate_js(self, code: str) -> Any:
        loop = asyncio.get_event_loop()
        fut  = loop.create_future()

        def cb(_view, async_result):
            try:
                value = self._wv.evaluate_javascript_finish(async_result)
                fut.set_result(value.to_string() if value else None)
            except Exception as e:
                fut.set_exception(e)

        self._wv.evaluate_javascript(code, -1, None, None, None, cb)
        return await fut

    def refresh_bridge(self, names: list[str]) -> None:
        UserScript = self._WebKit.UserScript
        # Re-install shim.
        self._ucm.remove_all_scripts()
        js = (
            "(function(){"
            "window.elysium=window.elysium||{};"
            "const C={i:0};const P=new Map();"
            "window.elysium._send=(name,args)=>new Promise((res,rej)=>{"
            "  const id=++C.i;P.set(id,{res,rej});"
            "  window.webkit.messageHandlers.elysium.postMessage("
            "    JSON.stringify({id,name,args}));"
            "});"
            "window.elysium._resolve=(id,val)=>{const p=P.get(id);"
            "if(p){P.delete(id);p.res(val);}};"
        )
        for n in names:
            js += f"window.elysium.{n}=(...a)=>window.elysium._send({n!r},a);"
        js += "})();"
        script = UserScript.new(js,
                                self._WebKit.UserContentInjectedFrames.ALL_FRAMES,
                                self._WebKit.UserScriptInjectionTime.START,
                                None, None)
        self._ucm.add_script(script)

    def _on_message(self, _ucm, message) -> None:
        body = message.get_js_value().to_string()
        async def go():
            reply = await self.view._dispatch(body)
            payload = json.loads(reply)
            id_ = payload.get("id")
            if id_ is not None:
                js = f"window.elysium._resolve({id_}, {json.dumps(payload.get('result'))});"
                await self.evaluate_js(js)
        asyncio.ensure_future(go())

    def snapshot_rgba(self) -> bytes:
        from gi.repository import GLib  # type: ignore
        # WebKit.SnapshotRegion.FULL_DOCUMENT, no options.
        try:
            loop = asyncio.get_event_loop()
            fut  = loop.create_future()
            def done(_view, async_result):
                try:
                    surf = self._wv.get_snapshot_finish(async_result)
                    # surface is a Cairo ImageSurface in BGRA32 — flip
                    # bytes to RGBA.
                    import array
                    data = surf.get_data()
                    buf = array.array("B", bytes(data))
                    for i in range(0, len(buf), 4):
                        buf[i], buf[i+2] = buf[i+2], buf[i]
                    fut.set_result(bytes(buf))
                except Exception as e:
                    fut.set_exception(e)
            self._wv.get_snapshot(
                self._WebKit.SnapshotRegion.VISIBLE,
                self._WebKit.SnapshotOptions.NONE,
                None, done)
            return loop.run_until_complete(fut)
        except Exception:
            return b""
