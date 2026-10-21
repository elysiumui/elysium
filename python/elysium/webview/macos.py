"""macOS WKWebView backend (pure ctypes; see ``_objc``).

The web view lives in a borderless window parked far off-screen: WebKit
only runs ``requestAnimationFrame`` and composites (WebGL included) for
a view that is in a window, and an off-screen window is never seen.
Occlusion detection and hidden-page throttling are switched off so the
page keeps its full frame rate.

Every WebKit call runs on the main thread, posted with
``dispatch_async_f``; nothing touches AppKit while the ``WebView`` is
constructed, so an ``elysium.App`` started afterwards still creates the
application object itself. Results come back through Objective-C blocks
into ``concurrent.futures.Future`` objects.

The ``window.elysium.<name>(...)`` bridge is a ``WKUserScript`` that
posts JSON to a ``WKScriptMessageHandler`` registered as ``"elysium"``.
"""
from __future__ import annotations

import concurrent.futures
import sys
import weakref
from ctypes import c_bool, c_double, c_long, c_size_t, c_uint32, c_uint8, c_ulong, c_void_p
from typing import Any, Callable

from . import (
    Frame, WebViewError, WebViewJSError, _Backend, _POST_WEBKIT, _bridge_script, _settle,
)
from . import _objc as O
from ._objc import cls, nsstring, nsurl, rect, release, responds, send


_cg = O.cg
_cg.CGImageGetWidth.restype = c_size_t
_cg.CGImageGetWidth.argtypes = [c_void_p]
_cg.CGImageGetHeight.restype = c_size_t
_cg.CGImageGetHeight.argtypes = [c_void_p]
_cg.CGColorSpaceCreateWithName.restype = c_void_p
_cg.CGColorSpaceCreateWithName.argtypes = [c_void_p]
_cg.CGColorSpaceRelease.restype = None
_cg.CGColorSpaceRelease.argtypes = [c_void_p]
_cg.CGBitmapContextCreate.restype = c_void_p
_cg.CGBitmapContextCreate.argtypes = [c_void_p, c_size_t, c_size_t, c_size_t, c_size_t,
                                      c_void_p, c_uint32]
_cg.CGContextRelease.restype = None
_cg.CGContextRelease.argtypes = [c_void_p]
_cg.CGContextDrawImage.restype = None
_cg.CGContextDrawImage.argtypes = [c_void_p, O.CGRect, c_void_p]
_cg.CGContextSetRGBFillColor.restype = None
_cg.CGContextSetRGBFillColor.argtypes = [c_void_p, c_double, c_double, c_double, c_double]
_cg.CGContextFillRect.restype = None
_cg.CGContextFillRect.argtypes = [c_void_p, O.CGRect]

_kCGColorSpaceSRGB = c_void_p.in_dll(_cg, "kCGColorSpaceSRGB").value
# RGBA8, premultiplied, R first in memory — the DisplayList's format.
_RGBA_PREMUL = 1 | (4 << 12)   # kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big

_WK_ERROR_JS_EXCEPTION = 4
_WK_ERROR_UNSUPPORTED_RESULT = 5
_NSURL_ERROR_CANCELLED = -999

_PARKED_ORIGIN = (-20000.0, -20000.0)
# Transient | Stationary | IgnoresCycle: kept out of Mission Control and ⌘`.
_COLLECTION_BEHAVIOR = (1 << 3) | (1 << 4) | (1 << 6)


# Delegate / handler instance pointer → owning backend.
_owners: dict[int, "weakref.ref[WkWebViewBackend]"] = {}
_classes: dict[str, int] = {}


def _owner(instance) -> "WkWebViewBackend | None":
    ref = _owners.get(instance)
    return ref() if ref else None


def _on_script_message(handler, _ucc, message) -> None:
    backend = _owner(handler)
    if backend is None:
        return
    frame = send(message, "frameInfo")
    if not frame or not send(frame, "isMainFrame", restype=c_bool):
        return
    body = O.to_python(send(message, "body"))
    if isinstance(body, str):
        backend.view._on_bridge_message(body, backend._run_script)


def _on_finish(delegate, _webview, navigation) -> None:
    backend = _owner(delegate)
    if backend is not None:
        backend._navigation_done(navigation, None)


def _on_fail(delegate, _webview, navigation, error) -> None:
    backend = _owner(delegate)
    if backend is not None:
        backend._navigation_done(navigation, error)


def _on_terminate(delegate, _webview) -> None:
    backend = _owner(delegate)
    if backend is not None:
        backend._fail_pending(WebViewError("the web content process terminated"))


def _register_classes() -> None:
    if _classes:
        return
    _classes["handler"] = O.new_class(
        "ElysiumWebViewScriptHandler",
        {"userContentController:didReceiveScriptMessage:": (b"v32@0:8@16@24", _on_script_message)},
        protocols=("WKScriptMessageHandler",),
    )
    _classes["navigation"] = O.new_class(
        "ElysiumWebViewNavigationDelegate",
        {
            "webView:didFinishNavigation:": (b"v32@0:8@16@24", _on_finish),
            "webView:didFailNavigation:withError:": (b"v40@0:8@16@24@32", _on_fail),
            "webView:didFailProvisionalNavigation:withError:": (b"v40@0:8@16@24@32", _on_fail),
            "webViewWebContentProcessDidTerminate:": (b"v24@0:8@16", _on_terminate),
        },
        protocols=("WKNavigationDelegate",),
    )


def _set_bool(obj, selector: str, value: bool) -> None:
    if responds(obj, selector):
        send(obj, selector, value, restype=None, argtypes=(c_bool,))


class WkWebViewBackend(_Backend):
    def __init__(self, view) -> None:
        if not cls("WKWebView"):
            raise RuntimeError("WKWebView class not available; is WebKit loaded?")
        super().__init__(view)
        self._closed = False
        self._wk = None
        self._window = None
        self._handler = None
        self._navigation_delegate = None
        self._navigations: dict[int, concurrent.futures.Future] = {}
        self._post(self._create)

    # --- main-thread plumbing ---------------------------------------------

    def _post(self, fn: Callable[[], Any], fut: concurrent.futures.Future | None = None) -> None:
        """Run ``fn`` on the main thread. An exception it raises settles
        ``fut`` (or is printed when nobody is waiting)."""
        def run() -> None:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                if fut is not None:
                    _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))
                else:
                    print(f"WebView (macOS): {e}", file=sys.stderr)
        O.on_main(run)

    def _webview(self):
        if self._closed or not self._wk:
            raise WebViewError("WebView is closed")
        return self._wk

    def wait(self, fut, timeout):
        try:
            return O.wait(fut, timeout)
        except O.MainThreadError as e:
            raise WebViewError(str(e)) from None

    async def wait_async(self, fut, timeout):
        try:
            return await O.wait_async(fut, timeout)
        except O.MainThreadError as e:
            raise WebViewError(str(e)) from None

    # --- setup / teardown (main thread) --------------------------------------

    def _create(self) -> None:
        if self._closed:
            return
        O.ensure_application()
        _register_classes()
        view = self.view

        config = O.alloc_init("WKWebViewConfiguration")
        prefs = send(config, "preferences")
        # Private switches (guarded): an off-screen page must not be
        # throttled or suspended as "hidden".
        _set_bool(prefs, "_setHiddenPageDOMTimerThrottlingEnabled:", False)
        _set_bool(prefs, "_setPageVisibilityBasedProcessSuppressionEnabled:", False)

        handler = O.alloc_init("ElysiumWebViewScriptHandler")
        _owners[handler] = weakref.ref(self)
        send(send(config, "userContentController"), "addScriptMessageHandler:name:",
             handler, nsstring("elysium"), restype=None)

        wk = send(send(cls("WKWebView"), "alloc"), "initWithFrame:configuration:",
                  rect(0, 0, view.width, view.height), config, argtypes=(O.CGRect, c_void_p))
        release(config)
        if not wk:
            raise WebViewError("could not create WKWebView")
        _set_bool(wk, "_setWindowOcclusionDetectionEnabled:", False)
        # The page is composited over `background` when snapshots are taken.
        send(wk, "setValue:forKey:",
             send(cls("NSNumber"), "numberWithBool:", False, argtypes=(c_bool,)),
             nsstring("drawsBackground"), restype=None)
        if view.user_agent:
            send(wk, "setCustomUserAgent:", nsstring(view.user_agent), restype=None)

        navigation = O.alloc_init("ElysiumWebViewNavigationDelegate")
        _owners[navigation] = weakref.ref(self)
        send(wk, "setNavigationDelegate:", navigation, restype=None)   # weak in WebKit

        x, y = _PARKED_ORIGIN
        window = send(send(cls("NSWindow"), "alloc"), "initWithContentRect:styleMask:backing:defer:",
                      rect(x, y, view.width, view.height), 0, 2, False,
                      argtypes=(O.CGRect, c_ulong, c_ulong, c_bool))
        send(window, "setReleasedWhenClosed:", False, restype=None, argtypes=(c_bool,))
        send(window, "setIgnoresMouseEvents:", True, restype=None, argtypes=(c_bool,))
        send(window, "setExcludedFromWindowsMenu:", True, restype=None, argtypes=(c_bool,))
        send(window, "setHasShadow:", False, restype=None, argtypes=(c_bool,))
        send(window, "setCollectionBehavior:", _COLLECTION_BEHAVIOR,
             restype=None, argtypes=(c_ulong,))
        send(window, "setContentView:", wk, restype=None)
        send(window, "orderFrontRegardless", restype=None)

        self._wk, self._window = wk, window
        self._handler, self._navigation_delegate = handler, navigation

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._fail_pending(WebViewError("WebView is closed"))
        if O.is_main_thread() and not O.app_running():
            # Interpreter exit or a script's own teardown: nothing would
            # turn the run loop for a posted call any more.
            self._teardown()
        else:
            O.on_main(self._teardown)

    def _teardown(self) -> None:
        wk, window = self._wk, self._window
        handler, navigation = self._handler, self._navigation_delegate
        self._wk = self._window = self._handler = self._navigation_delegate = None
        with O.autorelease_pool():
            if wk:
                ucc = send(send(wk, "configuration"), "userContentController")
                # The controller retains its handler: break the cycle.
                send(ucc, "removeScriptMessageHandlerForName:", nsstring("elysium"), restype=None)
                send(ucc, "removeAllUserScripts", restype=None)
                send(wk, "setNavigationDelegate:", None, restype=None)
                send(wk, "stopLoading", restype=None)
            if window:
                send(window, "setContentView:", None, restype=None)
                send(window, "orderOut:", None, restype=None)
                send(window, "close", restype=None)
            for nav in self._navigations:
                release(nav)
            self._navigations.clear()
            for obj in (wk, window, handler, navigation):
                _owners.pop(obj, None)
                release(obj)

    # --- navigation -----------------------------------------------------------

    def _track_navigation(self, fut: concurrent.futures.Future, navigation) -> None:
        if navigation:
            self._navigations[O.retain(navigation)] = fut
        else:
            _settle(fut)

    def _navigation_done(self, navigation, error) -> None:
        fut = self._navigations.pop(navigation, None)
        if fut is None:
            return
        release(navigation)
        if error:
            domain, code, desc, _ = O.error_info(error)
            reason = "navigation cancelled" if code == _NSURL_ERROR_CANCELLED else desc
            _settle(fut, error=WebViewError(f"{reason} ({domain} {code})"))
        else:
            _settle(fut)

    def load_url(self, url: str) -> None:
        fut = self._new_load()

        def run() -> None:
            ns_url = nsurl(url)
            if not ns_url:
                raise WebViewError(f"invalid URL: {url!r}")
            request = send(cls("NSURLRequest"), "requestWithURL:", ns_url)
            self._track_navigation(fut, send(self._webview(), "loadRequest:", request))
        self._post(run, fut)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        fut = self._new_load()

        def run() -> None:
            base = nsurl(base_url) if base_url else None
            self._track_navigation(
                fut, send(self._webview(), "loadHTMLString:baseURL:", nsstring(html), base))
        self._post(run, fut)

    def _navigate(self, selector: str) -> None:
        fut = self._new_load()
        self._post(lambda: self._track_navigation(fut, send(self._webview(), selector)), fut)

    def reload(self) -> None:  self._navigate("reload")
    def back(self) -> None:    self._navigate("goBack")
    def forward(self) -> None: self._navigate("goForward")

    def resize(self, width: int, height: int) -> None:
        def run() -> None:
            send(self._window, "setContentSize:", O.CGSize(width, height),
                 restype=None, argtypes=(O.CGSize,))
            send(self._webview(), "setFrameSize:", O.CGSize(width, height),
                 restype=None, argtypes=(O.CGSize,))
        self._post(run)

    # --- scripting --------------------------------------------------------------

    def evaluate(self, code: str) -> concurrent.futures.Future:
        fut = self._future()

        def done(result, error) -> None:
            if not error:
                _settle(fut, O.to_python(result))
                return
            domain, err_code, desc, info = O.error_info(error)
            if domain == "WKErrorDomain" and err_code == _WK_ERROR_UNSUPPORTED_RESULT:
                _settle(fut, None)          # undefined, functions, symbols…
            elif domain == "WKErrorDomain" and err_code == _WK_ERROR_JS_EXCEPTION:
                _settle(fut, error=WebViewJSError(info.get("WKJavaScriptExceptionMessage") or desc))
            else:
                _settle(fut, error=WebViewError(f"{desc} ({domain} {err_code})"))

        def run() -> None:
            with O.Block(O.BLOCK_ID_ID, done) as block:
                send(self._webview(), "evaluateJavaScript:completionHandler:",
                     nsstring(code), block.ptr, restype=None)
        self._post(run, fut)
        return fut

    def _run_script(self, code: str) -> None:
        """Fire-and-forget evaluation (bridge replies)."""
        def run() -> None:
            if self._wk and not self._closed:
                send(self._wk, "evaluateJavaScript:completionHandler:",
                     nsstring(code), None, restype=None)
        self._post(run)

    def refresh_bridge(self, names: list[str]) -> None:
        source = _bridge_script(names, _POST_WEBKIT)

        def run() -> None:
            wk = self._webview()
            ucc = send(send(wk, "configuration"), "userContentController")
            send(ucc, "removeAllUserScripts", restype=None)
            # WKUserScriptInjectionTimeAtDocumentStart = 0, main frame only.
            script = send(send(cls("WKUserScript"), "alloc"),
                          "initWithSource:injectionTime:forMainFrameOnly:",
                          nsstring(source), 0, True, argtypes=(c_void_p, c_long, c_bool))
            send(ucc, "addUserScript:", script, restype=None)
            release(script)
            # …and bind the names in the page that is already loaded.
            send(wk, "evaluateJavaScript:completionHandler:", nsstring(source), None, restype=None)
        self._post(run)

    # --- pixels -------------------------------------------------------------------

    def snapshot(self, after_updates: bool) -> concurrent.futures.Future:
        fut = self._future()

        def done(image, error) -> None:
            if error:
                _, _, desc, _ = O.error_info(error)
                _settle(fut, error=WebViewError(f"snapshot failed: {desc}"))
                return
            try:
                _settle(fut, self._image_to_frame(image))
            except Exception as e:  # noqa: BLE001
                _settle(fut, error=WebViewError(f"snapshot failed: {e}"))

        def run() -> None:
            wk = self._webview()
            config = O.alloc_init("WKSnapshotConfiguration")
            _set_bool(config, "setAfterScreenUpdates:", after_updates)
            try:
                with O.Block(O.BLOCK_ID_ID, done) as block:
                    send(wk, "takeSnapshotWithConfiguration:completionHandler:",
                         config, block.ptr, restype=None)
            finally:
                release(config)
        self._post(run, fut)
        return fut

    def _image_to_frame(self, image) -> Frame:
        """NSImage → premultiplied RGBA8 at its native pixel size, drawn
        over ``background`` in sRGB. Main thread; the CGImage is borrowed
        from the NSImage and not released here."""
        if not image:
            raise WebViewError("no image")
        cg_image = send(image, "CGImageForProposedRect:context:hints:", None, None, None)
        if not cg_image:
            raise WebViewError("no CGImage")
        width, height = _cg.CGImageGetWidth(cg_image), _cg.CGImageGetHeight(cg_image)
        pixels = (c_uint8 * (width * height * 4))()
        space = _cg.CGColorSpaceCreateWithName(_kCGColorSpaceSRGB)
        ctx = _cg.CGBitmapContextCreate(pixels, width, height, 8, width * 4, space, _RGBA_PREMUL)
        _cg.CGColorSpaceRelease(space)
        if not ctx:
            raise WebViewError("CGBitmapContextCreate failed")
        try:
            bounds = rect(0, 0, width, height)
            r, g, b, a = self.view.background
            if a:
                _cg.CGContextSetRGBFillColor(ctx, r / 255, g / 255, b / 255, a / 255)
                _cg.CGContextFillRect(ctx, bounds)
            _cg.CGContextDrawImage(ctx, bounds, cg_image)
        finally:
            _cg.CGContextRelease(ctx)
        return Frame(bytes(pixels), width, height, width / max(1, self.view.width), 0)
