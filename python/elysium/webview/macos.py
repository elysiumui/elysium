"""macOS WKWebView backend.

Uses ``objc2`` when available, falls back to a thin ``ctypes`` wrapper
otherwise. The view is allocated off-screen (no NSWindow) and snapshot
into a Skia atlas so the framework can composite it inside a skin
layer with rounding / blur / animation applied uniformly.

The ``window.elysium.<name>(...)`` JS bridge is installed by injecting
a ``WKUserScript`` that wires a ``WKScriptMessageHandler`` for every
exposed handler name.
"""
from __future__ import annotations

import asyncio
import ctypes
import sys
from ctypes import c_void_p, c_char_p, c_double, c_int, c_uint, c_uint64
from ctypes.util import find_library
from typing import Any


_cf  = ctypes.CDLL(find_library("CoreFoundation"))
_obj = ctypes.CDLL(find_library("objc"))
_wk  = ctypes.CDLL(find_library("WebKit"))   # framework load

_obj.objc_getClass.restype  = c_void_p
_obj.objc_getClass.argtypes = [c_char_p]
_obj.sel_registerName.restype  = c_void_p
_obj.sel_registerName.argtypes = [c_char_p]
_obj.objc_msgSend.restype  = c_void_p


def _cls(name: str) -> c_void_p:
    return _obj.objc_getClass(name.encode())

def _sel(s: str) -> c_void_p:
    return _obj.sel_registerName(s.encode())

def _send(obj, sel: str, *args, restype=c_void_p, argtypes=None):
    fn = _obj.objc_msgSend
    fn.restype = restype
    fn.argtypes = [c_void_p, c_void_p] + (list(argtypes) if argtypes else [])
    return fn(obj, _sel(sel), *args)


def _ns_string(s: str) -> c_void_p:
    cls = _cls("NSString")
    return _send(cls, "stringWithUTF8String:", s.encode(),
                 argtypes=[c_char_p])


def _ns_url(s: str) -> c_void_p:
    cls = _cls("NSURL")
    return _send(cls, "URLWithString:", _ns_string(s))


class WkWebViewBackend:
    def __init__(self, view) -> None:
        self.view = view
        cls_wkconf  = _cls("WKWebViewConfiguration")
        cls_wkview  = _cls("WKWebView")
        cls_cgrect  = _cls("NSValue")  # only used for sizing helper
        if not cls_wkview:
            raise RuntimeError("WKWebView class not available; is WebKit loaded?")
        self._config = _send(_send(cls_wkconf, "alloc"), "init")
        self._user_content = _send(self._config, "userContentController")

        # Allocate the view with the given frame.
        class CGRect(ctypes.Structure):
            _fields_ = [("x", c_double), ("y", c_double),
                        ("w", c_double), ("h", c_double)]
        frame = CGRect(0, 0, float(view.width), float(view.height))

        # Allocate the view first (this round-trip through `_send` would
        # otherwise clobber the typed argtypes we install just below).
        alloc = _send(cls_wkview, "alloc")
        fn = _obj.objc_msgSend
        fn.restype  = c_void_p
        fn.argtypes = [c_void_p, c_void_p, CGRect, c_void_p]
        self._view = fn(alloc, _sel("initWithFrame:configuration:"),
                        frame, self._config)
        if view.user_agent:
            _send(self._view, "setCustomUserAgent:", _ns_string(view.user_agent))

    def load_url(self, url: str) -> None:
        cls_req = _cls("NSURLRequest")
        req = _send(cls_req, "requestWithURL:", _ns_url(url))
        _send(self._view, "loadRequest:", req)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        base = _ns_url(base_url) if base_url else c_void_p(0)
        _send(self._view, "loadHTMLString:baseURL:",
              _ns_string(html), base,
              argtypes=[c_void_p, c_void_p])

    def reload(self) -> None:  _send(self._view, "reload")
    def back(self) -> None:    _send(self._view, "goBack")
    def forward(self) -> None: _send(self._view, "goForward")

    async def evaluate_js(self, code: str) -> Any:
        """Evaluate JS and return the result. We synthesize a completion
        block via libffi (mirrors how objc2 builds blocks) and pump
        the main run-loop until the block fires. Falls through to
        ``None`` if libffi isn't present."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        block = _make_completion_block(
            lambda result, err: fut.set_result(_objc_to_python(result)))
        _send(self._view, "evaluateJavaScript:completionHandler:",
              _ns_string(code), block,
              argtypes=[c_void_p, c_void_p])
        # Pump until the JS engine fires our callback. WKWebView dispatches
        # the block on the main thread, so iterate NSDefaultRunLoopMode
        # until done or until a 2s budget elapses.
        import time
        deadline = time.monotonic() + 2.0
        while not fut.done() and time.monotonic() < deadline:
            _run_runloop_once()
            await asyncio.sleep(0)
        return fut.result() if fut.done() else None

    def refresh_bridge(self, names: list[str]) -> None:
        # Inject a tiny shim that postMessages back to Python via
        # `webkit.messageHandlers.elysium.postMessage(...)`.
        js = """
        (function() {
          if (window.elysium) return;
          window.elysium = {};
          const counters = { id: 0 };
          const pending  = new Map();
          window.elysium._send = (name, args) => new Promise((res, rej) => {
            const id = ++counters.id;
            pending.set(id, { res, rej });
            window.webkit.messageHandlers.elysium.postMessage(JSON.stringify({
              id, name, args,
            }));
          });
          window.elysium._resolve = (id, value) => {
            const p = pending.get(id);
            if (!p) return;
            pending.delete(id);
            p.res(value);
          };
        """
        for n in names:
            js += f"\n  window.elysium.{n} = (...a) => window.elysium._send({n!r}, a);"
        js += "\n})();"

        cls_script = _cls("WKUserScript")
        # Allocate first; setting argtypes then re-invoking _send would
        # reset them. WKUserScriptInjectionTimeAtDocumentStart = 0.
        alloc = _send(cls_script, "alloc")
        src_str = _ns_string(js)
        fn = _obj.objc_msgSend
        fn.restype  = c_void_p
        fn.argtypes = [c_void_p, c_void_p, c_void_p, c_int, c_int]
        script = fn(alloc, _sel("initWithSource:injectionTime:forMainFrameOnly:"),
                    src_str, 0, 1)
        _send(self._user_content, "addUserScript:", script)
        # Register the message handler under the name "elysium".
        # The Python side hooks into the dispatch via webview._dispatch.
        # A real WKScriptMessageHandler requires a custom Objective-C
        # class; we use a one-off helper registered through objc2 when
        # available.
        try:
            from .macos_bridge import register_handler
            register_handler(self._user_content, self.view)
        except Exception:
            pass

    def snapshot_rgba(self) -> bytes:
        """Rasterise the current page into a CGBitmapContext and read
        out RGBA8 bytes. We bypass WKWebView's async snapshot API and
        ask the view to draw its layer hierarchy into a CGContext
        directly — synchronous, no run-loop pump required."""
        try:
            return _snapshot_via_cg(self._view,
                                     int(self.view.width),
                                     int(self.view.height))
        except Exception as e:
            print(f"WebView snapshot failed: {e}", file=__import__("sys").stderr)
            return b""


# --- Snapshot helper --------------------------------------------------------

_cg_lib = ctypes.CDLL(find_library("CoreGraphics") or "")
_qz_lib = ctypes.CDLL(find_library("QuartzCore") or "")

# kCGColorSpaceSRGB / kCGImageAlphaPremultipliedLast.
_kCGImageAlphaPremultipliedLast = 1
_kCGBitmapByteOrder32Big        = (4 << 12)


def _snapshot_via_cg(ns_view: ctypes.c_void_p, w: int, h: int) -> bytes:
    """Draw the NSView's CALayer hierarchy into a CGBitmapContext and
    return RGBA8 (premultiplied). Works synchronously without WKWebView's
    async snapshot block — uses the layer's `render_in_context:` method
    which composites on the calling thread."""
    if not ns_view or w <= 0 or h <= 0:
        return b""
    # Allocate the pixel buffer Python-side so the caller owns its
    # lifetime; CG draws into the same memory.
    buf = (ctypes.c_uint8 * (w * h * 4))()

    # CGColorSpaceCreateDeviceRGB.
    _cg_lib.CGColorSpaceCreateDeviceRGB.restype = c_void_p
    cs = _cg_lib.CGColorSpaceCreateDeviceRGB()
    if not cs:
        return b""

    # CGBitmapContextCreate.
    _cg_lib.CGBitmapContextCreate.argtypes = [
        c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t,
        ctypes.c_size_t, c_void_p, ctypes.c_uint,
    ]
    _cg_lib.CGBitmapContextCreate.restype = c_void_p
    ctx = _cg_lib.CGBitmapContextCreate(
        buf, w, h, 8, w * 4, cs,
        _kCGImageAlphaPremultipliedLast | _kCGBitmapByteOrder32Big,
    )
    _cg_lib.CGColorSpaceRelease.argtypes = [c_void_p]
    _cg_lib.CGColorSpaceRelease(cs)
    if not ctx:
        return b""

    # The view's layer renders into the context. CALayer renderInContext:
    # walks the sublayer tree synchronously.
    layer = _send(ns_view, "layer")
    if not layer:
        # Fall back: ask the view to draw itself rect-style.
        _cg_lib.CGContextRelease.argtypes = [c_void_p]
        _cg_lib.CGContextRelease(ctx)
        return b""

    _send(layer, "renderInContext:", ctx, argtypes=[c_void_p])
    _cg_lib.CGContextRelease.argtypes = [c_void_p]
    _cg_lib.CGContextRelease(ctx)
    return bytes(buf)


# --- Completion-block trampoline -------------------------------------------
# WKWebView.evaluateJavaScript:completionHandler: takes an Objective-C
# stack block — a struct with isa / flags / reserved / invoke pointer /
# descriptor. We build that struct in pure ctypes here so the call works
# without objc2. When the JS engine fires our block, ``_BlockInvoke``
# extracts the (id result, NSError* error) arguments and calls back into
# Python.

_NSConcreteStackBlock = ctypes.c_void_p.in_dll(
    ctypes.CDLL(find_library("System") or ""),
    "_NSConcreteStackBlock",
)

# Block descriptor.
class _BlockDescriptor(ctypes.Structure):
    _fields_ = [
        ("reserved",   ctypes.c_ulong),
        ("size",       ctypes.c_ulong),
        ("copy_helper",    c_void_p),
        ("dispose_helper", c_void_p),
    ]


class _Block(ctypes.Structure):
    _fields_ = [
        ("isa",        c_void_p),
        ("flags",      ctypes.c_int),
        ("reserved",   ctypes.c_int),
        ("invoke",     c_void_p),
        ("descriptor", ctypes.POINTER(_BlockDescriptor)),
        ("trampoline", c_void_p),    # we stash the callback id here
    ]


_BLOCK_DESCRIPTOR = _BlockDescriptor(0, ctypes.sizeof(_Block), None, None)
_LIVE_BLOCKS: list = []   # keep callback refs alive


# invoke signature: void (Block*, id result, NSError* error)
_InvokeProto = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p)


def _make_completion_block(py_callback):
    """Build a real Objective-C block that calls ``py_callback(result_id,
    err_id)`` when invoked. Keeps the trampoline alive in
    ``_LIVE_BLOCKS`` so the GC doesn't free it while WKWebView holds
    the pointer."""
    def trampoline(_block_self, result, err):
        try:
            py_callback(result, err)
        except Exception as e:
            print(f"webview block trampoline: {e}", file=sys.stderr)

    invoke_cfn = _InvokeProto(trampoline)
    block = _Block()
    block.isa = _NSConcreteStackBlock
    block.flags = (1 << 25)        # BLOCK_HAS_STRET = 0; BLOCK_IS_GLOBAL.
    block.reserved = 0
    block.invoke = ctypes.cast(invoke_cfn, c_void_p)
    block.descriptor = ctypes.pointer(_BLOCK_DESCRIPTOR)
    block.trampoline = c_void_p(0)
    _LIVE_BLOCKS.append((block, invoke_cfn, py_callback))
    return ctypes.cast(ctypes.pointer(block), c_void_p)


# --- Objective-C value → Python --------------------------------------------

def _objc_to_python(obj_ptr) -> Any:
    """Best-effort conversion of the JS engine's return value.
    NSString → str, NSNumber → int/float, NSNull → None, anything else
    falls through to the object's `description` string."""
    if not obj_ptr:
        return None
    # Class probe — NSNumber / NSString / NSNull / NSDictionary / NSArray.
    cls = _send(obj_ptr, "class")
    name = _obj.class_getName(cls).decode() if hasattr(_obj, "class_getName") else ""
    if not hasattr(_obj, "class_getName"):
        _obj.class_getName.restype = c_char_p
        _obj.class_getName.argtypes = [c_void_p]
        name = _obj.class_getName(cls).decode()
    if name.startswith("__NSCFString") or name == "NSString":
        cstr = _send(obj_ptr, "UTF8String", restype=c_char_p)
        return ctypes.string_at(cstr).decode() if cstr else ""
    if name.startswith("__NSCFNumber") or name == "NSNumber":
        # Try double first (covers JS numbers); int fallback.
        _obj.objc_msgSend.restype = c_double
        try:
            return float(_obj.objc_msgSend(obj_ptr, _sel("doubleValue")))
        finally:
            _obj.objc_msgSend.restype = c_void_p
    if name == "NSNull":
        return None
    # Anything else: stringify via -description for diagnostics.
    desc = _send(obj_ptr, "description")
    if desc:
        cstr = _send(desc, "UTF8String", restype=c_char_p)
        if cstr:
            return ctypes.string_at(cstr).decode()
    return None


# --- Runloop pump ----------------------------------------------------------

_cf.CFRunLoopGetMain.restype = c_void_p
_cf.CFRunLoopRunInMode.restype = c_int
_cf.CFRunLoopRunInMode.argtypes = [c_void_p, c_double, ctypes.c_bool]
_NSDefaultRunLoopMode = c_void_p.in_dll(_cf, "kCFRunLoopDefaultMode")


def _run_runloop_once() -> None:
    """Drain one pass of the main CFRunLoop with a tiny budget. Returns
    immediately if there's nothing to do."""
    _cf.CFRunLoopRunInMode(_NSDefaultRunLoopMode, 0.005, True)
