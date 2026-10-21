"""Minimal Objective-C runtime bridge over ctypes (macOS only).

Just enough of the runtime for the WKWebView backend, built so that no
call site ever mutates shared ctypes state:

* ``send`` casts ``objc_msgSend`` to a prototype cached per signature
  (the pattern ``elysium.dock`` uses) instead of rewriting the shared
  function's ``argtypes``/``restype`` on every call.
* ``Block`` builds real Objective-C blocks the way libclosure lays them
  out: a stack-block literal with copy/dispose helpers and a type
  signature. ``Block_copy`` moves it to the heap and the helpers keep
  the Python callable alive until the runtime disposes of the last copy,
  however long WebKit holds on to it.
* ``on_main`` posts work to the main dispatch queue with
  ``dispatch_async_f``. AppKit and WebKit objects are only touched there.
  ``wait`` / ``wait_async`` block for the result, pumping the main run
  loop themselves when the caller *is* the main thread and no
  ``NSApplication`` is running it.
* ``new_class`` registers an ``NSObject`` subclass with Python method
  implementations, for delegates and script-message handlers.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import ctypes
import itertools
import math
import threading
import time
from ctypes import (
    CFUNCTYPE, POINTER, Structure, c_bool, c_char, c_char_p, c_double,
    c_int, c_long, c_size_t, c_ulong, c_void_p,
)
from ctypes.util import find_library
from typing import Any, Callable


def _lib(name: str) -> ctypes.CDLL:
    path = find_library(name)
    if not path:
        raise OSError(f"{name} framework not found")
    return ctypes.CDLL(path)


objc = _lib("objc")
libsystem = _lib("System")
cf = _lib("CoreFoundation")
cg = _lib("CoreGraphics")
foundation = _lib("Foundation")
appkit = _lib("AppKit")
webkit = _lib("WebKit")

objc.objc_getClass.restype = c_void_p
objc.objc_getClass.argtypes = [c_char_p]
objc.objc_getProtocol.restype = c_void_p
objc.objc_getProtocol.argtypes = [c_char_p]
objc.sel_registerName.restype = c_void_p
objc.sel_registerName.argtypes = [c_char_p]
objc.class_getName.restype = c_char_p
objc.class_getName.argtypes = [c_void_p]
objc.object_getClass.restype = c_void_p
objc.object_getClass.argtypes = [c_void_p]
objc.objc_allocateClassPair.restype = c_void_p
objc.objc_allocateClassPair.argtypes = [c_void_p, c_char_p, c_size_t]
objc.objc_registerClassPair.restype = None
objc.objc_registerClassPair.argtypes = [c_void_p]
objc.class_addMethod.restype = c_bool
objc.class_addMethod.argtypes = [c_void_p, c_void_p, c_void_p, c_char_p]
objc.class_replaceMethod.restype = c_void_p
objc.class_replaceMethod.argtypes = [c_void_p, c_void_p, c_void_p, c_char_p]
objc.class_addProtocol.restype = c_bool
objc.class_addProtocol.argtypes = [c_void_p, c_void_p]
objc.objc_retain.restype = c_void_p
objc.objc_retain.argtypes = [c_void_p]
objc.objc_release.restype = None
objc.objc_release.argtypes = [c_void_p]
objc.objc_autoreleasePoolPush.restype = c_void_p
objc.objc_autoreleasePoolPush.argtypes = []
objc.objc_autoreleasePoolPop.restype = None
objc.objc_autoreleasePoolPop.argtypes = [c_void_p]

libsystem.pthread_main_np.restype = c_int
libsystem.pthread_main_np.argtypes = []
libsystem.dispatch_async_f.restype = None
libsystem.dispatch_async_f.argtypes = [c_void_p, c_void_p, c_void_p]

cf.CFRunLoopRunInMode.restype = c_int
cf.CFRunLoopRunInMode.argtypes = [c_void_p, c_double, c_bool]
cf.CFGetTypeID.restype = c_ulong
cf.CFGetTypeID.argtypes = [c_void_p]
cf.CFBooleanGetTypeID.restype = c_ulong
cf.CFBooleanGetTypeID.argtypes = []

_kCFRunLoopDefaultMode = c_void_p.in_dll(cf, "kCFRunLoopDefaultMode").value
# `_dispatch_main_q` is the queue object itself; its *address* is the
# dispatch_queue_t, exactly like `&_dispatch_main_q` in C.
_MAIN_QUEUE = ctypes.addressof(c_char.in_dll(libsystem, "_dispatch_main_q"))


class CGPoint(Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class CGSize(Structure):
    _fields_ = [("width", c_double), ("height", c_double)]


class CGRect(Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


def rect(x: float, y: float, w: float, h: float) -> CGRect:
    return CGRect(CGPoint(x, y), CGSize(w, h))


# --- messaging ---------------------------------------------------------------

_MSG_SEND = ctypes.cast(objc.objc_msgSend, c_void_p).value
_prototypes: dict[tuple, Any] = {}
_selectors: dict[str, int] = {}


def cls(name: str) -> int | None:
    return objc.objc_getClass(name.encode())


def sel(name: str) -> int:
    s = _selectors.get(name)
    if s is None:
        s = _selectors[name] = objc.sel_registerName(name.encode())
    return s


def send(obj, selector: str, *args, restype=c_void_p, argtypes=None):
    """``[obj selector...]``. ``argtypes`` defaults to one ``id`` per
    argument; pass it explicitly for scalars and structs. Never use this
    for methods that return a struct larger than 16 bytes (x86_64 would
    need ``objc_msgSend_stret``)."""
    if argtypes is None:
        argtypes = (c_void_p,) * len(args)
    key = (restype, tuple(argtypes))
    fn = _prototypes.get(key)
    if fn is None:
        fn = _prototypes[key] = CFUNCTYPE(restype, c_void_p, c_void_p, *argtypes)(_MSG_SEND)
    return fn(obj, sel(selector), *args)


def responds(obj, selector: str) -> bool:
    return bool(send(obj, "respondsToSelector:", sel(selector),
                     restype=c_bool, argtypes=(c_void_p,)))


def class_name(obj) -> str:
    return objc.class_getName(objc.object_getClass(obj)).decode()


def is_kind(obj, class_: str) -> bool:
    c = cls(class_)
    return bool(c) and bool(send(obj, "isKindOfClass:", c, restype=c_bool))


def retain(obj) -> int | None:
    return objc.objc_retain(obj) if obj else obj


def release(obj) -> None:
    if obj:
        objc.objc_release(obj)


def alloc_init(class_: str) -> int:
    """``[[class_ alloc] init]``, returned at +1."""
    return send(send(cls(class_), "alloc"), "init")


class autorelease_pool:
    def __enter__(self):
        self._pool = objc.objc_autoreleasePoolPush()
        return self

    def __exit__(self, *exc):
        objc.objc_autoreleasePoolPop(self._pool)
        return False


# --- Foundation values ---------------------------------------------------------

def nsstring(s: str) -> int:
    """An autoreleased ``NSString``. Call inside an autorelease pool."""
    return send(cls("NSString"), "stringWithUTF8String:", s.encode("utf-8"),
                argtypes=(c_char_p,))


def pystring(ns) -> str | None:
    if not ns:
        return None
    raw = send(ns, "UTF8String", restype=c_char_p)
    return raw.decode("utf-8") if raw is not None else None


def nsurl(s: str) -> int:
    return send(cls("NSURL"), "URLWithString:", nsstring(s))


_CF_BOOLEAN_TYPE = cf.CFBooleanGetTypeID()
_INT_TYPES = set(b"cislqCISLQB")


def to_python(obj) -> Any:
    """Convert a WebKit JavaScript result (a Foundation object graph) to
    the value ``json.loads(JSON.stringify(x))`` would give: integral
    numbers come back as ``int``, dates as ISO-8601 strings."""
    if not obj:
        return None
    if cf.CFGetTypeID(obj) == _CF_BOOLEAN_TYPE:
        return bool(send(obj, "boolValue", restype=c_bool))
    if is_kind(obj, "NSString"):
        return pystring(obj)
    if is_kind(obj, "NSNumber"):
        kind = send(obj, "objCType", restype=c_char_p) or b"d"
        if kind[0] in _INT_TYPES:
            return int(send(obj, "longLongValue", restype=ctypes.c_longlong))
        value = float(send(obj, "doubleValue", restype=c_double))
        if not math.isfinite(value):
            return None          # JSON.stringify(NaN / ±Infinity) is null
        if value.is_integer() and abs(value) < 2 ** 53:
            return int(value)
        return value
    if is_kind(obj, "NSNull"):
        return None
    if is_kind(obj, "NSArray"):
        n = send(obj, "count", restype=c_ulong)
        return [to_python(send(obj, "objectAtIndex:", i, argtypes=(c_ulong,)))
                for i in range(n)]
    if is_kind(obj, "NSDictionary"):
        keys = send(obj, "allKeys")
        out = {}
        for i in range(send(keys, "count", restype=c_ulong)):
            k = send(keys, "objectAtIndex:", i, argtypes=(c_ulong,))
            out[str(to_python(k))] = to_python(send(obj, "objectForKey:", k))
        return out
    if is_kind(obj, "NSDate"):
        import datetime
        ts = send(obj, "timeIntervalSince1970", restype=c_double)
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return pystring(send(obj, "description"))


def error_info(err) -> tuple[str, int, str, dict[str, Any]]:
    """``(domain, code, localizedDescription, userInfo)`` of an NSError."""
    domain = pystring(send(err, "domain")) or ""
    code = int(send(err, "code", restype=c_long))
    desc = pystring(send(err, "localizedDescription")) or ""
    info = to_python(send(err, "userInfo")) or {}
    return domain, code, desc, info if isinstance(info, dict) else {}


# --- blocks --------------------------------------------------------------------
# Layout from libclosure's Block_private.h. A block is created on the
# "stack" (Python-owned memory); when WebKit keeps it, Block_copy moves a
# copy to the heap and calls copy_helper, and the final release calls
# dispose_helper. The helpers count references to a token stored in the
# block's captured field, so the Python callable lives exactly as long
# as some copy of the block does.

_BLOCK_HAS_COPY_DISPOSE = 1 << 25
_BLOCK_HAS_SIGNATURE = 1 << 30

_NSConcreteStackBlock = ctypes.addressof(c_void_p.in_dll(libsystem, "_NSConcreteStackBlock"))


class _BlockDescriptor(Structure):
    _fields_ = [
        ("reserved", c_ulong),
        ("size", c_ulong),
        ("copy_helper", c_void_p),
        ("dispose_helper", c_void_p),
        ("signature", c_char_p),
        ("layout", c_char_p),
    ]


class _BlockLiteral(Structure):
    _fields_ = [
        ("isa", c_void_p),
        ("flags", c_int),
        ("reserved", c_int),
        ("invoke", c_void_p),
        ("descriptor", POINTER(_BlockDescriptor)),
        ("token", c_void_p),
    ]


_block_lock = threading.Lock()
_block_refs: dict[int, list] = {}     # token -> [refcount, callable]
_block_tokens = itertools.count(1)


def _token_of(block_ptr) -> int:
    return _BlockLiteral.from_address(block_ptr).token


@CFUNCTYPE(None, c_void_p, c_void_p)
def _block_copy_helper(dst, src):
    with _block_lock:
        entry = _block_refs.get(_token_of(src))
        if entry is not None:
            entry[0] += 1


@CFUNCTYPE(None, c_void_p)
def _block_dispose_helper(block):
    token = _token_of(block)
    with _block_lock:
        entry = _block_refs.get(token)
        if entry is not None:
            entry[0] -= 1
            if entry[0] <= 0:
                del _block_refs[token]


def _callable_for(block_ptr) -> Callable | None:
    with _block_lock:
        entry = _block_refs.get(_token_of(block_ptr))
    return entry[1] if entry else None


class BlockType:
    """One block signature: the C invoke prototype plus its ObjC type
    encoding. Invoke trampolines are created once per type and live for
    the life of the process."""

    def __init__(self, encoding: bytes, *argtypes):
        self.argtypes = argtypes
        proto = CFUNCTYPE(None, c_void_p, *argtypes)

        def invoke(block_ptr, *args):
            fn = _callable_for(block_ptr)
            if fn is None:
                return
            try:
                with autorelease_pool():
                    fn(*args)
            except Exception:  # noqa: BLE001 — never unwind into ObjC
                import traceback
                traceback.print_exc()

        self._invoke = proto(invoke)
        self.descriptor = _BlockDescriptor(
            0, ctypes.sizeof(_BlockLiteral),
            ctypes.cast(_block_copy_helper, c_void_p),
            ctypes.cast(_block_dispose_helper, c_void_p),
            encoding, None,
        )


class Block:
    """A block literal to pass as a method argument. Keep the instance
    alive until the method call returns; after that the runtime's own
    copies (if any) keep the callable alive."""

    def __init__(self, block_type: BlockType, fn: Callable):
        self._token = next(_block_tokens)
        with _block_lock:
            _block_refs[self._token] = [1, fn]
        self._literal = _BlockLiteral(
            _NSConcreteStackBlock,
            _BLOCK_HAS_COPY_DISPOSE | _BLOCK_HAS_SIGNATURE,
            0,
            ctypes.cast(block_type._invoke, c_void_p),
            ctypes.pointer(block_type.descriptor),
            self._token,
        )

    @property
    def ptr(self) -> int:
        return ctypes.addressof(self._literal)

    def __enter__(self) -> "Block":
        return self

    def __exit__(self, *exc) -> bool:
        self.release()
        return False

    def release(self) -> None:
        """Drop the stack reference (call once the method has returned)."""
        with _block_lock:
            entry = _block_refs.get(self._token)
            if entry is not None:
                entry[0] -= 1
                if entry[0] <= 0:
                    del _block_refs[self._token]

    @staticmethod
    def live_count() -> int:
        with _block_lock:
            return len(_block_refs)


# void (^)(id, id) — WKWebView's evaluate/snapshot completion handlers.
BLOCK_ID_ID = BlockType(b"v24@?0@8@16", c_void_p, c_void_p)


# --- classes -------------------------------------------------------------------

_class_imps: list = []   # IMPs must outlive the class


def new_class(name: str, methods: dict[str, tuple[bytes, Callable]],
              protocols: tuple[str, ...] = (), superclass: str = "NSObject") -> int:
    """Register (or refresh) an Objective-C class whose methods call
    Python. ``methods`` maps selector → (type encoding, python fn); the
    python fn receives ``(self, *args)`` without ``_cmd``. Re-running
    with the same name replaces the implementations, so a reloaded
    module never leaves stale IMPs behind."""
    existing = cls(name)
    new = existing or objc.objc_allocateClassPair(cls(superclass), name.encode(), 0)
    if not new:
        raise RuntimeError(f"cannot create Objective-C class {name}")
    for selector, (encoding, fn) in methods.items():
        n_args = selector.count(":")
        proto = CFUNCTYPE(None, c_void_p, c_void_p, *([c_void_p] * n_args))

        def imp(self_ptr, _cmd, *args, _fn=fn):
            try:
                with autorelease_pool():
                    _fn(self_ptr, *args)
            except Exception:  # noqa: BLE001 — never unwind into ObjC
                import traceback
                traceback.print_exc()

        cimp = proto(imp)
        _class_imps.append(cimp)
        if existing:
            objc.class_replaceMethod(new, sel(selector), ctypes.cast(cimp, c_void_p), encoding)
        else:
            objc.class_addMethod(new, sel(selector), ctypes.cast(cimp, c_void_p), encoding)
    if not existing:
        for proto_name in protocols:
            p = objc.objc_getProtocol(proto_name.encode())
            if p:
                objc.class_addProtocol(new, p)
        objc.objc_registerClassPair(new)
    return new


# --- main thread -----------------------------------------------------------------

class MainThreadError(RuntimeError):
    pass


def is_main_thread() -> bool:
    return libsystem.pthread_main_np() == 1


def ns_app() -> int | None:
    """The ``NSApp`` global, read without creating the application."""
    return c_void_p.in_dll(appkit, "NSApp").value


def app_running() -> bool:
    app = ns_app()
    return bool(app) and bool(send(app, "isRunning", restype=c_bool))


_main_lock = threading.Lock()
_main_calls: dict[int, Callable[[], None]] = {}
_main_keys = itertools.count(1)


@CFUNCTYPE(None, c_void_p)
def _main_thunk(ctx):
    with _main_lock:
        fn = _main_calls.pop(ctx or 0, None)
    if fn is None:
        return
    with autorelease_pool():
        fn()


def on_main(fn: Callable[[], Any]) -> concurrent.futures.Future:
    """Run ``fn`` on the main thread's dispatch queue, always
    asynchronously (also when called *from* the main thread), and return
    a Future for its result. Nothing runs until the main run loop turns:
    ``NSApplication.run`` does that in an app, ``wait`` does it in a
    script."""
    fut: concurrent.futures.Future = concurrent.futures.Future()

    def call() -> None:
        if not fut.set_running_or_notify_cancel():
            return
        try:
            fut.set_result(fn())
        except BaseException as e:  # noqa: BLE001
            fut.set_exception(e)

    key = next(_main_keys)
    with _main_lock:
        _main_calls[key] = call
    libsystem.dispatch_async_f(_MAIN_QUEUE, key, ctypes.cast(_main_thunk, c_void_p))
    return fut


def pump(seconds: float) -> None:
    """Turn the main run loop for up to ``seconds``. Only valid on the
    main thread while no ``NSApplication`` is running it."""
    if not is_main_thread():
        raise MainThreadError("pump() must be called on the main thread")
    if app_running():
        raise MainThreadError("pump() cannot run inside a running App; the app already pumps")
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        cf.CFRunLoopRunInMode(_kCFRunLoopDefaultMode, 0.01, True)
        if time.monotonic() >= deadline:
            return


def _needs_pump() -> bool:
    if not is_main_thread():
        return False
    if app_running():
        raise MainThreadError(
            "a WebView call cannot block the main thread while the App is running; "
            "call it from a worker thread (frame callbacks already are)")
    return True


def wait(fut: concurrent.futures.Future, timeout: float) -> Any:
    """Block until ``fut`` resolves. Raises ``TimeoutError`` after
    ``timeout`` seconds."""
    if _needs_pump():
        deadline = time.monotonic() + timeout
        while not fut.done():
            if time.monotonic() >= deadline:
                raise TimeoutError
            cf.CFRunLoopRunInMode(_kCFRunLoopDefaultMode, 0.01, True)
        return fut.result()
    try:
        return fut.result(timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError from None


async def wait_async(fut: concurrent.futures.Future, timeout: float) -> Any:
    """``wait`` for coroutines: pumps between event-loop turns when on
    the main thread, otherwise awaits the future without blocking."""
    if _needs_pump():
        deadline = time.monotonic() + timeout
        while not fut.done():
            if time.monotonic() >= deadline:
                raise TimeoutError
            cf.CFRunLoopRunInMode(_kCFRunLoopDefaultMode, 0.01, True)
            await asyncio.sleep(0)
        return fut.result()
    try:
        return await asyncio.wait_for(asyncio.wrap_future(fut), timeout)
    except asyncio.TimeoutError:
        raise TimeoutError from None


#: True once ``ensure_application`` created the NSApplication itself; an
#: ``elysium.App`` can no longer start after that (winit must own it).
created_application = False


def ensure_application() -> None:
    """Create the shared ``NSApplication`` for a script that never runs
    an ``elysium.App``. Main thread only; a no-op when one exists, so an
    App's own (winit) application is never replaced."""
    global created_application
    if ns_app():
        return
    created_application = True
    app = send(cls("NSApplication"), "sharedApplication")
    # NSApplicationActivationPolicyAccessory: no Dock icon, no menu bar.
    send(app, "setActivationPolicy:", 1, restype=c_bool, argtypes=(c_long,))
    send(app, "finishLaunching", restype=None)
