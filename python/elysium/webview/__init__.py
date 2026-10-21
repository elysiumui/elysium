"""Embedded webview component.

Wraps the platform-native browser engine:
  * macOS — ``WKWebView`` through the Objective-C runtime (pure ctypes),
    hosted in an off-screen window so pages keep animating.
  * Linux — WebKitGTK 6.0 (GTK 4) through PyGObject, on its own GTK
    thread (``gir1.2-webkit-6.0``).
  * Elsewhere a no-op backend stands in (``WebView.available`` is False).

Public API
----------

.. code-block:: python

    from elysium.webview import WebView

    wv = WebView(width=800, height=600)
    wv.load_url("https://example.com")
    wv.expose("greet", lambda name: f"hi, {name}")
    await wv.wait_loaded()
    title = await wv.evaluate_js("document.title")

    # from JS:
    #   const reply = await window.elysium.greet("kenley");

The page is rendered off-screen and composited into a display list as an
image (``paint``), so it inherits the skin layer's rounding, blur and
animation like any other element. It is display and scripting only:
mouse and keyboard input are not forwarded to the page.

Threading: every call may be made from any thread. On macOS the engine
lives on the main thread; inside a running ``elysium.App`` that thread is
already pumped, and in a plain script the blocking calls pump it
themselves (see ``pump``).
"""
from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import inspect
import json
import sys
import threading
import time
import weakref
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, NamedTuple


_Handler = Callable[..., Any | Awaitable[Any]]


class WebViewError(RuntimeError):
    """A webview operation failed (engine error, closed view, crashed
    web content process)."""


class WebViewJSError(WebViewError):
    """The evaluated JavaScript threw. The message is the JS error's."""


class WebViewTimeout(WebViewError, TimeoutError):
    """The engine did not answer within the timeout."""


class Frame(NamedTuple):
    """One rendered page image: premultiplied RGBA8, top-down rows, at
    the engine's native pixel size (``scale`` × the view size on HiDPI)."""
    rgba: bytes
    width: int
    height: int
    scale: float
    seq: int


@dataclass(eq=False)
class WebView:
    width:  int = 800
    height: int = 600
    user_agent: str | None = None
    #: RGBA drawn behind the page wherever it is transparent; alpha 0
    #: gives a transparent webview.
    background: tuple[int, int, int, int] = (255, 255, 255, 255)
    _exposed: dict[str, _Handler] = field(default_factory=dict, init=False, repr=False)
    _backend: Any = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _frame: Frame | None = field(default=None, init=False, repr=False)
    _frame_seq: int = field(default=0, init=False, repr=False)
    _snapshot_in_flight: bool = field(default=False, init=False, repr=False)
    _lock: Any = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"WebView size must be positive, got {self.width}x{self.height}")
        self._backend = _resolve_backend(self)
        _live_views.add(self)

    # --- lifecycle ----------------------------------------------------------

    @property
    def available(self) -> bool:
        """False when no engine could be loaded and every call is a no-op
        (headless test runs, a missing WebKitGTK, no display)."""
        return not isinstance(self._backend, _NullBackend)

    def close(self) -> None:
        """Destroy the engine view. Pending calls fail with
        ``WebViewError``; later calls raise. Idempotent."""
        if self._closed:
            return
        self._closed = True
        _live_views.discard(self)
        self._backend.close()

    def __enter__(self) -> "WebView":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def _check_open(self) -> None:
        if self._closed:
            raise WebViewError("WebView is closed")

    # --- navigation ---------------------------------------------------------

    def load_url(self, url: str) -> None:
        self._check_open()
        self._backend.load_url(url)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        self._check_open()
        self._backend.load_html(html, base_url)

    def reload(self) -> None:
        self._check_open()
        self._backend.reload()

    def back(self) -> None:
        self._check_open()
        self._backend.back()

    def forward(self) -> None:
        self._check_open()
        self._backend.forward()

    async def wait_loaded(self, timeout: float = 10.0) -> None:
        """Wait until the most recent ``load_*``/``reload`` finished.
        Raises ``WebViewError`` if it failed, ``WebViewTimeout`` if it is
        still loading after ``timeout`` seconds."""
        self._check_open()
        await self._await(self._backend.load_future(), timeout)

    def resize(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"WebView size must be positive, got {width}x{height}")
        self._check_open()
        self.width, self.height = int(width), int(height)
        self._backend.resize(self.width, self.height)

    # --- scripting ----------------------------------------------------------

    async def evaluate_js(self, code: str, timeout: float = 5.0) -> Any:
        """Evaluate ``code`` in the page and return its completion value
        as JSON-compatible Python (``undefined`` and ``null`` → ``None``,
        integral numbers → ``int``). A thrown error raises
        ``WebViewJSError``. Promises are not awaited. A page that is still
        loading is waited for first, within the same ``timeout``."""
        self._check_open()
        deadline = time.monotonic() + timeout
        await self._settle_load(timeout)
        return await self._await(self._backend.evaluate(code),
                                 max(0.0, deadline - time.monotonic()))

    def expose(self, name: str, fn: _Handler) -> None:
        """Surface a Python callable as ``window.elysium.<name>(...)``,
        which returns a Promise. Arguments and the return value travel as
        JSON. Sync handlers run on a worker thread, coroutines on
        Elysium's background event loop; a raised exception rejects the
        Promise. Takes effect in the current page and every later one."""
        if not name.isidentifier() or name.startswith("_"):
            raise ValueError(f"webview.expose: bad name {name!r}")
        self._check_open()
        self._exposed[name] = fn
        self._backend.refresh_bridge(list(self._exposed))

    async def _dispatch(self, payload: str) -> dict[str, Any]:
        """Run the handler for one bridge message; returns the reply."""
        msg_id = None
        try:
            msg = json.loads(payload)
            msg_id = msg.get("id")
            name = msg["name"]
            args = msg.get("args", [])
            fn = self._exposed.get(name)
            if fn is None:
                return {"id": msg_id, "error": f"no such handler: {name}"}
            if inspect.iscoroutinefunction(fn):
                result = await fn(*args)
            else:
                result = await asyncio.to_thread(fn, *args)
                if inspect.isawaitable(result):
                    result = await result
            json.dumps(result)   # reject unserialisable results here, not in JS
            return {"id": msg_id, "result": result}
        except Exception as e:  # noqa: BLE001 — becomes a rejected Promise
            return {"id": msg_id, "error": f"{type(e).__name__}: {e}"}

    def _on_bridge_message(self, payload: str, reply: Callable[[str], None]) -> None:
        """Backend hook: a page posted ``payload``. ``reply(js)`` runs the
        settling script on the backend's own thread."""
        from elysium.concurrency import run_async

        def done(fut: concurrent.futures.Future) -> None:
            try:
                script = _reply_script(fut.result())
            except Exception as e:  # noqa: BLE001
                print(f"webview bridge: {e}", file=sys.stderr)
                return
            if script and not self._closed:
                reply(script)

        run_async(self._dispatch(payload)).add_done_callback(done)

    # --- pixels -------------------------------------------------------------

    def snapshot_rgba(self, timeout: float = 2.0) -> bytes:
        """Render the page now and return premultiplied RGBA8 of exactly
        ``width*height*4`` bytes (top-down rows), suitable for
        ``DisplayList.draw_image_bytes``. Blocks until the engine has
        drawn (and any page still loading has loaded); ``b""`` without an
        engine."""
        self._check_open()
        if not self.available:
            return b""
        deadline = time.monotonic() + timeout
        load = self._backend.load_future()
        if not load.done():
            try:
                self._await_sync(load, timeout)
            except WebViewTimeout:
                raise
            except WebViewError:
                pass   # a failed load still renders (an error page); wait_loaded reports it
        frame = self._await_sync(self._backend.snapshot(after_updates=True),
                                 max(0.0, deadline - time.monotonic()))
        self._store_frame(frame)
        return _fit(frame, self.width, self.height)

    def latest_frame(self) -> Frame | None:
        """The most recent page image, without blocking (``None`` until
        the first snapshot completes)."""
        return self._frame

    def request_snapshot(self) -> None:
        """Start rendering a new frame in the background unless one is
        already on its way; ``latest_frame`` picks it up when done."""
        if self._closed or not self.available:
            return
        with self._lock:
            if self._snapshot_in_flight:
                return
            self._snapshot_in_flight = True
        try:
            fut = self._backend.snapshot(after_updates=False)
        except Exception:
            with self._lock:
                self._snapshot_in_flight = False
            raise

        def done(f: concurrent.futures.Future) -> None:
            with self._lock:
                self._snapshot_in_flight = False
            if f.exception() is None:
                self._store_frame(f.result())

        fut.add_done_callback(done)

    def _store_frame(self, frame: Frame) -> None:
        with self._lock:
            self._frame_seq += 1
            self._frame = frame._replace(seq=self._frame_seq)

    def paint(self, dl, x: float, y: float,
              w: float | None = None, h: float | None = None) -> bool:
        """Composite the latest page image into ``dl`` at ``(x, y, w, h)``
        (logical pixels; defaults to the view size) and request a fresh
        one for the next paint. Never blocks. Returns False until a first
        frame exists."""
        frame = self._frame
        self.request_snapshot()
        if frame is None:
            return False
        w = w if w is not None else float(self.width)
        h = h if h is not None else float(self.height)
        dl.draw_image_bytes(frame.rgba, frame.width, frame.height, x, y, w, h)
        return True

    # --- waiting ------------------------------------------------------------

    async def _settle_load(self, timeout: float) -> None:
        """Wait out an in-flight navigation; its failure is reported by
        ``wait_loaded``, not here."""
        load = self._backend.load_future()
        if load.done():
            return
        try:
            await self._await(load, timeout)
        except WebViewTimeout:
            raise
        except WebViewError:
            pass

    async def _await(self, fut: concurrent.futures.Future, timeout: float) -> Any:
        try:
            return await self._backend.wait_async(fut, timeout)
        except TimeoutError:
            raise WebViewTimeout(f"no answer from the web engine within {timeout:g}s") from None

    def _await_sync(self, fut: concurrent.futures.Future, timeout: float) -> Any:
        try:
            return self._backend.wait(fut, timeout)
        except TimeoutError:
            raise WebViewTimeout(f"no answer from the web engine within {timeout:g}s") from None


def pump(seconds: float = 0.0) -> None:
    """Let the web engine process pending work for ``seconds``.

    Only needed on macOS by a script that never runs an ``elysium.App``
    and keeps its main thread busy elsewhere: the engine's callbacks are
    delivered on the main thread, which only turns while a WebView call is
    blocking on it, an App is running, or this function is called. On
    other platforms the engine has its own thread and this just sleeps."""
    if sys.platform == "darwin" and "elysium.webview.macos" in sys.modules:
        from . import _objc
        if _objc.is_main_thread() and not _objc.app_running():
            _objc.pump(seconds)
            return
    time.sleep(max(0.0, seconds))


# --- bridge script -----------------------------------------------------------

_POST_WEBKIT = "window.webkit.messageHandlers.elysium.postMessage(m)"
_POST_WEBVIEW2 = "window.chrome.webview.postMessage(m)"


def _bridge_script(names: list[str], post: str) -> str:
    """The ``window.elysium`` shim. Safe to run any number of times in
    the same page: the plumbing is created once, and every exposed name
    is (re)bound on each run."""
    return (
        "(function(){"
        "var e=window.elysium=window.elysium||{};"
        "if(!e._pending){"
        "e._pending=new Map();e._next=0;"
        "e._send=function(name,args){return new Promise(function(res,rej){"
        "var id=++e._next;e._pending.set(id,{res:res,rej:rej});"
        "var m=JSON.stringify({id:id,name:name,args:args});"
        f"{post};"
        "});};"
        "e._resolve=function(id,v){var p=e._pending.get(id);"
        "if(p){e._pending.delete(id);p.res(v);}};"
        "e._reject=function(id,msg){var p=e._pending.get(id);"
        "if(p){e._pending.delete(id);p.rej(new Error(msg));}};"
        "}"
        f"{json.dumps(names)}.forEach(function(n){{"
        "e[n]=function(){return e._send(n,Array.prototype.slice.call(arguments));};"
        "});"
        "})();"
    )


def _reply_script(reply: dict[str, Any]) -> str | None:
    msg_id = reply.get("id")
    if not isinstance(msg_id, int):
        return None
    if "error" in reply:
        return f"window.elysium._reject({msg_id},{json.dumps(str(reply['error']))});"
    return f"window.elysium._resolve({msg_id},{json.dumps(reply.get('result'))});"


# --- pixels ------------------------------------------------------------------

def _fit(frame: Frame, width: int, height: int) -> bytes:
    """``frame`` resampled to exactly ``width``×``height`` (premultiplied
    stays premultiplied: Pillow's ``RGBa`` mode)."""
    if (frame.width, frame.height) == (width, height):
        return frame.rgba
    from PIL import Image
    img = Image.frombuffer("RGBa", (frame.width, frame.height), frame.rgba, "raw", "RGBa", 0, 1)
    return img.resize((width, height), Image.Resampling.LANCZOS).tobytes()


def _composite(rgba: bytes, background: tuple[int, int, int, int]) -> bytes:
    """Premultiplied ``rgba`` drawn over ``background`` (straight RGBA)."""
    r, g, b, a = (int(c) for c in background)
    if a == 0:
        return rgba
    import numpy as np
    src = np.frombuffer(rgba, dtype=np.uint8).reshape(-1, 4).astype(np.uint16)
    bg = np.array([r * a // 255, g * a // 255, b * a // 255, a], dtype=np.uint16)
    inv = 255 - src[:, 3:4]
    out = src + (bg * inv + 127) // 255
    return out.clip(0, 255).astype(np.uint8).tobytes()


# --- backends ------------------------------------------------------------------

def _settle(fut: concurrent.futures.Future, value: Any = None,
            error: BaseException | None = None) -> None:
    """Resolve ``fut`` unless something (close, a crash) already did."""
    try:
        if error is not None:
            fut.set_exception(error)
        else:
            fut.set_result(value)
    except concurrent.futures.InvalidStateError:
        pass


class _Backend:
    """Shared plumbing for the engine backends. Every operation returns a
    ``concurrent.futures.Future`` resolved on the engine's thread;
    ``WebView`` turns waits into ``WebViewTimeout``."""

    def __init__(self, view: WebView) -> None:
        self.view = view
        self._pending: set[concurrent.futures.Future] = set()
        self._pending_lock = threading.Lock()
        self._load: concurrent.futures.Future = concurrent.futures.Future()
        self._load.set_result(None)

    def _future(self) -> concurrent.futures.Future:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        with self._pending_lock:
            self._pending.add(fut)

        def forget(f: concurrent.futures.Future) -> None:
            with self._pending_lock:
                self._pending.discard(f)
        fut.add_done_callback(forget)
        return fut

    def _new_load(self) -> concurrent.futures.Future:
        self._load = self._future()
        return self._load

    def load_future(self) -> concurrent.futures.Future:
        return self._load

    def _fail_pending(self, error: BaseException) -> None:
        with self._pending_lock:
            pending = list(self._pending)
        for fut in pending:
            _settle(fut, error=error)

    def wait(self, fut: concurrent.futures.Future, timeout: float) -> Any:
        try:
            return fut.result(timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError from None

    async def wait_async(self, fut: concurrent.futures.Future, timeout: float) -> Any:
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError from None


def _resolve_backend(view: WebView):
    if sys.platform == "darwin":
        try:
            from .macos import WkWebViewBackend
            return WkWebViewBackend(view)
        except Exception as e:
            print(f"WebView macOS backend unavailable: {e}", file=sys.stderr)
    elif sys.platform.startswith("linux"):
        try:
            from .linux import WebKitGtkBackend
            return WebKitGtkBackend(view)
        except Exception as e:
            print(f"WebKitGTK backend unavailable: {e}", file=sys.stderr)
    else:
        print(f"WebView: no engine backend for {sys.platform} yet; "
              "the view renders nothing", file=sys.stderr)
    return _NullBackend(view)


class _NullBackend(_Backend):
    """Headless fallback. Every call is a no-op so tests and unsupported
    platforms can still construct a WebView without crashing."""

    def _done(self, value: Any = None) -> concurrent.futures.Future:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        fut.set_result(value)
        return fut

    def load_url(self, url: str) -> None: pass
    def load_html(self, html: str, base_url: str | None = None) -> None: pass
    def reload(self) -> None: pass
    def back(self) -> None: pass
    def forward(self) -> None: pass
    def resize(self, width: int, height: int) -> None: pass
    def evaluate(self, code: str) -> concurrent.futures.Future: return self._done()
    def refresh_bridge(self, names: list[str]) -> None: pass
    def snapshot(self, after_updates: bool) -> concurrent.futures.Future:
        return self._done(Frame(b"", 0, 0, 1.0, 0))
    def close(self) -> None: pass


_live_views: "weakref.WeakSet[WebView]" = weakref.WeakSet()
#: Run after every view is closed at exit (backends stop their engine threads).
_shutdown_hooks: list[Callable[[], None]] = []


@atexit.register
def _close_all() -> None:
    # Engine callbacks must never arrive after the interpreter is gone.
    for view in list(_live_views):
        try:
            view.close()
        except Exception:  # noqa: BLE001
            pass
    for hook in _shutdown_hooks:
        try:
            hook()
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "WebView", "Frame", "WebViewError", "WebViewJSError", "WebViewTimeout", "pump",
]
