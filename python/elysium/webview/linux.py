"""WebKitGTK 6.0 backend (GTK 4) through PyGObject.

Requires the system packages (Debian/Ubuntu 24.04 and later)::

    sudo apt-get install gir1.2-webkit-6.0 gir1.2-gtk-4.0 python3-gi

GTK is single-threaded, so one daemon thread (``elysium-webkitgtk``)
initialises it and runs the default GLib main loop; every WebKit call is
marshalled there with ``GLib.idle_add`` and answers through a
``concurrent.futures.Future``. The application's own event loop never
has to know about GLib.

The web view sits in an undecorated, fully transparent, input-less
window: WebKitGTK only lays out, animates (``requestAnimationFrame``)
and renders WebGL for a mapped widget. On X11 and in Xvfb that window is
invisible; a Wayland compositor may still list it.
"""
from __future__ import annotations

import concurrent.futures
import json
import threading
from typing import Any, Callable

from . import (
    Frame, WebViewError, WebViewJSError, _Backend, _POST_WEBKIT, _bridge_script,
    _composite, _settle, _shutdown_hooks,
)


def _import_gi():
    try:
        import gi  # type: ignore[import-not-found]
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("WebKit", "6.0")
        from gi.repository import GLib, Gdk, Gtk, WebKit  # type: ignore[import-not-found]
    except (ImportError, ValueError) as e:
        raise RuntimeError(
            "WebKitGTK backend needs PyGObject and gir1.2-webkit-6.0 "
            "(apt-get install gir1.2-webkit-6.0 gir1.2-gtk-4.0 python3-gi)") from e
    return GLib, Gdk, Gtk, WebKit


class _GtkThread:
    """The one thread that owns GTK and the default GLib main context."""

    _instance: "_GtkThread | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_GtkThread":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self.GLib, self.Gdk, self.Gtk, self.WebKit = _import_gi()
        ready: concurrent.futures.Future = concurrent.futures.Future()
        self._loop = None
        self._thread = threading.Thread(target=self._run, args=(ready,),
                                        name="elysium-webkitgtk", daemon=True)
        self._thread.start()
        ready.result(30)   # re-raises "no display" here, on the caller's thread
        _shutdown_hooks.append(self.stop)

    def _run(self, ready: concurrent.futures.Future) -> None:
        try:
            if not self.Gtk.init_check():
                raise RuntimeError("GTK could not open a display (is DISPLAY or WAYLAND_DISPLAY set?)")
            self._loop = self.GLib.MainLoop.new(None, False)
        except BaseException as e:  # noqa: BLE001
            ready.set_exception(e)
            return
        ready.set_result(None)
        self._loop.run()

    def call(self, fn: Callable[[], Any], fut: concurrent.futures.Future | None = None) -> None:
        """Run ``fn`` on the GTK thread. An exception it raises settles
        ``fut``, or is printed when nobody is waiting."""
        def run() -> bool:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                if fut is not None:
                    _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))
                else:
                    import sys
                    print(f"WebView (WebKitGTK): {e}", file=sys.stderr)
            return False   # GLib.SOURCE_REMOVE
        self.GLib.idle_add(run)

    def stop(self) -> None:
        if self._loop is not None:
            self.GLib.idle_add(lambda: self._loop.quit() and False)
            self._thread.join(2.0)


class WebKitGtkBackend(_Backend):
    def __init__(self, view) -> None:
        self._gtk = _GtkThread.get()
        super().__init__(view)
        self._closed = False
        self._wv = None
        self._window = None
        self._loading: concurrent.futures.Future | None = None
        self._skip_finish = False
        created = self._future()
        self._gtk.call(self._create, created)
        self._gtk.call(lambda: _settle(created), created)
        created.result(30)

    # --- setup / teardown (GTK thread) -----------------------------------------

    def _create(self) -> None:
        Gdk, Gtk, WebKit = self._gtk.Gdk, self._gtk.Gtk, self._gtk.WebKit
        view = self.view
        wv = WebKit.WebView()
        settings = wv.get_settings()
        settings.set_enable_webgl(True)
        if view.user_agent:
            settings.set_user_agent(view.user_agent)
        # The page is composited over `background` when snapshots are taken.
        clear = Gdk.RGBA()
        clear.parse("rgba(0,0,0,0)")
        wv.set_background_color(clear)
        wv.set_size_request(view.width, view.height)

        ucm = wv.get_user_content_manager()
        ucm.register_script_message_handler("elysium", None)
        ucm.connect("script-message-received::elysium", self._on_message)
        wv.connect("load-changed", self._on_load_changed)
        wv.connect("load-failed", self._on_load_failed)
        wv.connect("web-process-terminated", self._on_terminated)

        window = Gtk.Window()
        window.set_decorated(False)
        window.set_default_size(view.width, view.height)
        window.set_opacity(0.0)
        window.set_can_target(False)
        window.set_focusable(False)
        window.set_child(wv)
        window.present()
        self._wv, self._window = wv, window

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._fail_pending(WebViewError("WebView is closed"))
        done: concurrent.futures.Future = concurrent.futures.Future()

        def teardown() -> None:
            if self._window is not None:
                self._window.destroy()
            self._wv = self._window = None
            done.set_result(None)
        self._gtk.call(teardown, done)
        try:
            done.result(2.0)
        except Exception:  # noqa: BLE001 — the GTK thread may already be gone at exit
            pass

    def _webview(self):
        if self._closed or self._wv is None:
            raise WebViewError("WebView is closed")
        return self._wv

    # --- navigation -----------------------------------------------------------------

    def _start_load(self, start: Callable[[Any], None]) -> None:
        fut = self._new_load()

        def run() -> None:
            previous = self._loading
            if previous is not None:
                _settle(previous, error=WebViewError("navigation superseded"))
            self._loading = fut
            start(self._webview())
        self._gtk.call(run, fut)

    def _on_load_changed(self, _wv, event) -> None:
        if event != self._gtk.WebKit.LoadEvent.FINISHED:
            return
        if self._skip_finish:          # the FINISHED that follows a cancellation
            self._skip_finish = False
            return
        if self._loading is not None:
            _settle(self._loading)
            self._loading = None

    def _on_load_failed(self, _wv, _event, uri, error) -> bool:
        if error.matches(self._gtk.WebKit.NetworkError.quark(),
                         int(self._gtk.WebKit.NetworkError.CANCELLED)):
            self._skip_finish = True
            return False
        if self._loading is not None:
            _settle(self._loading, error=WebViewError(f"{error.message} ({uri})"))
            self._loading = None
        return False

    def _on_terminated(self, _wv, _reason) -> None:
        self._fail_pending(WebViewError("the web content process terminated"))

    def load_url(self, url: str) -> None:
        self._start_load(lambda wv: wv.load_uri(url))

    def load_html(self, html: str, base_url: str | None = None) -> None:
        self._start_load(lambda wv: wv.load_html(html, base_url))

    def reload(self) -> None:  self._start_load(lambda wv: wv.reload())
    def back(self) -> None:    self._start_load(lambda wv: wv.go_back())
    def forward(self) -> None: self._start_load(lambda wv: wv.go_forward())

    def resize(self, width: int, height: int) -> None:
        def run() -> None:
            self._webview().set_size_request(width, height)
            self._window.set_default_size(width, height)
        self._gtk.call(run)

    # --- scripting --------------------------------------------------------------------

    def evaluate(self, code: str) -> concurrent.futures.Future:
        fut = self._future()

        def done(wv, result) -> None:
            JavascriptError = self._gtk.WebKit.JavascriptError
            try:
                value = wv.evaluate_javascript_finish(result)
            except self._gtk.GLib.Error as e:
                if e.matches(JavascriptError.quark(), int(JavascriptError.INVALID_RESULT)):
                    _settle(fut, None)      # Promises, functions, symbols…
                elif e.matches(JavascriptError.quark(), int(JavascriptError.SCRIPT_FAILED)):
                    _settle(fut, error=WebViewJSError(e.message))
                else:
                    _settle(fut, error=WebViewError(e.message))
                return
            _settle(fut, _to_python(value))

        self._gtk.call(lambda: self._webview().evaluate_javascript(
            code, -1, None, None, None, done), fut)
        return fut

    def _run_script(self, code: str) -> None:
        def run() -> None:
            if self._wv is not None and not self._closed:
                self._wv.evaluate_javascript(code, -1, None, None, None, None)
        self._gtk.call(run)

    def _on_message(self, _ucm, value) -> None:
        body = value.to_string() if value is not None else None
        if body:
            self.view._on_bridge_message(body, self._run_script)

    def refresh_bridge(self, names: list[str]) -> None:
        WebKit = self._gtk.WebKit
        source = _bridge_script(names, _POST_WEBKIT)

        def run() -> None:
            wv = self._webview()
            ucm = wv.get_user_content_manager()
            ucm.remove_all_scripts()
            ucm.add_script(WebKit.UserScript.new(
                source, WebKit.UserContentInjectedFrames.TOP_FRAME,
                WebKit.UserScriptInjectionTime.START, None, None))
            # …and bind the names in the page that is already loaded.
            wv.evaluate_javascript(source, -1, None, None, None, None)
        self._gtk.call(run)

    # --- pixels -----------------------------------------------------------------------

    def snapshot(self, after_updates: bool) -> concurrent.futures.Future:
        WebKit = self._gtk.WebKit
        fut = self._future()

        def done(wv, result) -> None:
            try:
                texture = wv.get_snapshot_finish(result)
                _settle(fut, self._texture_to_frame(texture))
            except Exception as e:  # noqa: BLE001
                message = getattr(e, "message", None) or str(e)
                _settle(fut, error=WebViewError(f"snapshot failed: {message}"))

        self._gtk.call(lambda: self._webview().get_snapshot(
            WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.TRANSPARENT_BACKGROUND,
            None, done), fut)
        return fut

    def _texture_to_frame(self, texture) -> Frame:
        Gdk = self._gtk.Gdk
        width, height = texture.get_width(), texture.get_height()
        downloader = Gdk.TextureDownloader.new(texture)
        downloader.set_format(Gdk.MemoryFormat.R8G8B8A8_PREMULTIPLIED)
        data, stride = downloader.download_bytes()
        raw = data.get_data()
        row = width * 4
        if stride != row:
            raw = b"".join(raw[y * stride:y * stride + row] for y in range(height))
        rgba = _composite(bytes(raw[:row * height]), self.view.background)
        return Frame(rgba, width, height, width / max(1, self.view.width), 0)


def _to_python(value) -> Any:
    """A JSCValue as ``json.loads(JSON.stringify(x))`` would give it."""
    if value is None or value.is_undefined() or value.is_null():
        return None
    text = value.to_json(0)
    return json.loads(text) if text is not None else None
