"""WebView2 backend (pure ctypes COM).

Needs the Evergreen WebView2 Runtime (ships with Windows 11; installed
by the Edge updater on Windows 10) and ``WebView2Loader.dll``, which the
wheel carries in ``_win/<arch>/`` (``scripts/fetch-webview2-loader.py``
puts it there in a source checkout).

WebView2 is apartment-threaded: one daemon thread (``elysium-webview2``)
initialises COM as an STA, runs a Win32 message loop and owns every
WebView2 object. Calls are queued for it and wake it with a message to a
message-only window; answers come back through COM completion handlers
into ``concurrent.futures.Future`` objects.

Each view is a parented controller inside a borderless tool window parked
far off-screen and never activated. Chromium's occlusion tracking and
background throttling are switched off so the page keeps rendering, and
``CapturePreview`` reads its pixels. The vtable slots used here are
checked against the pinned SDK header (``_webview2_abi``).
"""
from __future__ import annotations

import concurrent.futures
import ctypes
import io
import json
import os
import platform
import sys
import tempfile
import threading
import traceback
import uuid
from collections import deque
from ctypes import (
    POINTER, WINFUNCTYPE, Structure, byref, c_double, c_int, c_int64, c_size_t, c_ssize_t,
    c_ubyte, c_uint, c_ulong, c_void_p, c_wchar_p,
)
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from . import (
    Frame, WebViewError, WebViewJSError, _Backend, _POST_WEBVIEW2, _bridge_script,
    _composite, _settle, _shutdown_hooks,
)
from ._webview2_abi import IIDS, SLOTS


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32")
shlwapi = ctypes.WinDLL("shlwapi")

LRESULT = c_ssize_t
WNDPROC = WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", c_int), ("cbWndExtra", c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class COREWEBVIEW2_COLOR(Structure):
    _fields_ = [("A", c_ubyte), ("R", c_ubyte), ("G", c_ubyte), ("B", c_ubyte)]


user32.RegisterClassExW.argtypes = [POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, c_int, c_int, c_int, c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.GetMessageW.argtypes = [POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [c_int]
user32.PostQuitMessage.restype = None
user32.ShowWindow.argtypes = [wintypes.HWND, c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, c_int, c_int, c_int, c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = c_size_t
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.SetEnvironmentVariableW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
kernel32.SetEnvironmentVariableW.restype = wintypes.BOOL
ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = c_ulong
ole32.CoTaskMemFree.argtypes = [c_void_p]
ole32.CoTaskMemFree.restype = None
ole32.CreateStreamOnHGlobal.argtypes = [c_void_p, wintypes.BOOL, POINTER(c_void_p)]
ole32.CreateStreamOnHGlobal.restype = c_int
ole32.GetHGlobalFromStream.argtypes = [c_void_p, POINTER(c_void_p)]
ole32.GetHGlobalFromStream.restype = c_int
shlwapi.SHCreateMemStream.argtypes = [ctypes.c_char_p, c_uint]
shlwapi.SHCreateMemStream.restype = c_void_p

_COINIT_APARTMENTTHREADED = 0x2
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_WM_APP = 0x8000
_HWND_MESSAGE = -3
_WS_POPUP = 0x80000000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_SW_SHOWNOACTIVATE = 4
_SWP_NOZORDER, _SWP_NOACTIVATE = 0x0004, 0x0010
_ERROR_CLASS_ALREADY_EXISTS = 1410
_E_NOINTERFACE = -2147467262                      # 0x80004002
_PARKED = (-30000, -30000)
_CLASS = "ElysiumWebView2Host"

_WEB_ERROR_OPERATION_CANCELED = 14
_WEB_RESOURCE_CONTEXT_DOCUMENT = 1
_CAPTURE_FORMAT_PNG = 0
_BOUNDS_MODE_USE_RAW_PIXELS = 0
_PROCESS_FAILED_BROWSER, _PROCESS_FAILED_RENDER = 0, 1

_BROWSER_ARGS = ("--disable-features=CalculateNativeWinOcclusion "
                 "--disable-backgrounding-occluded-windows --disable-renderer-backgrounding")


# --- COM calls -------------------------------------------------------------------

_prototypes: dict[tuple, Any] = {}


def _vcall(obj, slot: int, *args, argtypes: tuple = (), restype=c_int):
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    key = (restype, argtypes)
    proto = _prototypes.get(key)
    if proto is None:
        proto = _prototypes[key] = WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(vtbl[slot])(obj, *args)


def _hresult(hr: int) -> str:
    return f"0x{hr & 0xFFFFFFFF:08X}"


def _call(obj, iface: str, method: str, *args, argtypes: tuple = ()) -> int:
    hr = _vcall(obj, SLOTS[iface][method], *args, argtypes=argtypes)
    if hr < 0:
        raise WebViewError(f"{iface}.{method} failed: HRESULT {_hresult(hr)}")
    return hr


def _out_ptr(obj, iface: str, method: str) -> int | None:
    out = c_void_p()
    _call(obj, iface, method, byref(out), argtypes=(POINTER(c_void_p),))
    return out.value


def _out_string(obj, iface: str, method: str) -> str | None:
    return _take_string(_out_ptr(obj, iface, method))


def _out_int(obj, iface: str, method: str) -> int:
    out = c_int()
    _call(obj, iface, method, byref(out), argtypes=(POINTER(c_int),))
    return out.value


def _take_string(ptr) -> str | None:
    """A CoTaskMem-allocated LPWSTR out-parameter: read it, then free it."""
    if not ptr:
        return None
    try:
        return ctypes.wstring_at(ptr)
    finally:
        ole32.CoTaskMemFree(ptr)


def _iid(text: str) -> bytes:
    return uuid.UUID(text).bytes_le


def _query(obj, iface: str) -> int | None:
    iid = ctypes.create_string_buffer(_iid(IIDS[iface]), 16)
    out = c_void_p()
    hr = _vcall(obj, 0, ctypes.addressof(iid), byref(out), argtypes=(c_void_p, POINTER(c_void_p)))
    return out.value if hr == 0 else None


def _addref(obj) -> None:
    if obj:
        _vcall(obj, 1, restype=c_ulong)


def _release(obj) -> None:
    if obj:
        _vcall(obj, 2, restype=c_ulong)


# --- COM objects implemented in Python ------------------------------------------
# Completion and event handlers are one-method COM interfaces. Each is a
# struct whose first field points at a shared vtable; the thunks find the
# Python side by the object's address and keep it alive while WebView2
# holds references.

_IID_IUNKNOWN = _iid("00000000-0000-0000-c000-000000000046")


class _Vtbl(Structure):
    _fields_ = [("QueryInterface", c_void_p), ("AddRef", c_void_p),
                ("Release", c_void_p), ("Invoke", c_void_p)]


class _Object(Structure):
    _fields_ = [("vtbl", POINTER(_Vtbl))]


_objects: dict[int, "_Handler"] = {}
_objects_lock = threading.Lock()


@WINFUNCTYPE(c_int, c_void_p, c_void_p, POINTER(c_void_p))
def _object_qi(this, riid, ppv):
    handler = _objects.get(this)
    iid = ctypes.string_at(riid, 16)
    if handler is not None and iid in (_IID_IUNKNOWN, handler.iid):
        _object_addref(this)
        ppv[0] = this
        return 0
    ppv[0] = None
    return _E_NOINTERFACE


@WINFUNCTYPE(c_ulong, c_void_p)
def _object_addref(this):
    with _objects_lock:
        handler = _objects.get(this)
        if handler is None:
            return 0
        handler.refs += 1
        return handler.refs


@WINFUNCTYPE(c_ulong, c_void_p)
def _object_release(this):
    with _objects_lock:
        handler = _objects.get(this)
        if handler is None:
            return 0
        handler.refs -= 1
        if handler.refs <= 0:
            del _objects[this]
            return 0
        return handler.refs


def _invoke_thunk(proto):
    def invoke(this, *args):
        handler = _objects.get(this)
        if handler is not None:
            try:
                handler.fn(*args)
            except Exception:  # noqa: BLE001 — never unwind into WebView2
                traceback.print_exc()
        return 0
    return proto(invoke)


_INVOKE = {
    # (HRESULT errorCode, <pointer>) — completion handlers with a result.
    "hr_ptr": _invoke_thunk(WINFUNCTYPE(c_int, c_void_p, c_int, c_void_p)),
    # (HRESULT errorCode) — CapturePreview.
    "hr": _invoke_thunk(WINFUNCTYPE(c_int, c_void_p, c_int)),
    # (ICoreWebView2* sender, <event args>) — event handlers.
    "ptr_ptr": _invoke_thunk(WINFUNCTYPE(c_int, c_void_p, c_void_p, c_void_p)),
}
_VTBLS = {
    kind: _Vtbl(ctypes.cast(_object_qi, c_void_p), ctypes.cast(_object_addref, c_void_p),
                ctypes.cast(_object_release, c_void_p), ctypes.cast(thunk, c_void_p))
    for kind, thunk in _INVOKE.items()
}


class _Handler:
    """One COM handler object. Starts with one reference (ours): pass
    ``ptr`` to WebView2, then call ``release`` once the call returned."""

    def __init__(self, iface: str, kind: str, fn: Callable[..., None]) -> None:
        self.iid = _iid(IIDS[iface])
        self.fn = fn
        self.refs = 1
        self._object = _Object(ctypes.pointer(_VTBLS[kind]))
        self.ptr = ctypes.addressof(self._object)
        with _objects_lock:
            _objects[self.ptr] = self

    def release(self) -> None:
        _object_release(self.ptr)


# --- loader / runtime ---------------------------------------------------------------

_loader_lib = None


def _loader():
    global _loader_lib
    if _loader_lib is not None:
        return _loader_lib
    arch = {"AMD64": "x64", "X86_64": "x64", "ARM64": "arm64", "AARCH64": "arm64"}.get(
        platform.machine().upper())
    bundled = Path(__file__).with_name("_win") / (arch or "x64") / "WebView2Loader.dll"
    try:
        lib = ctypes.WinDLL(str(bundled) if bundled.is_file() else "WebView2Loader.dll")
    except OSError as e:
        raise RuntimeError(
            "WebView2Loader.dll not found (in a source checkout, run "
            "scripts/fetch-webview2-loader.py)") from e
    lib.CreateCoreWebView2EnvironmentWithOptions.argtypes = [c_wchar_p, c_wchar_p, c_void_p, c_void_p]
    lib.CreateCoreWebView2EnvironmentWithOptions.restype = c_int
    lib.GetAvailableCoreWebView2BrowserVersionString.argtypes = [c_wchar_p, POINTER(c_void_p)]
    lib.GetAvailableCoreWebView2BrowserVersionString.restype = c_int
    version = c_void_p()
    hr = lib.GetAvailableCoreWebView2BrowserVersionString(None, byref(version))
    if hr < 0 or not _take_string(version.value):
        raise RuntimeError("the Microsoft Edge WebView2 Runtime is not installed")
    _loader_lib = lib
    return lib


def _user_data_folder() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    folder = Path(base) / "Elysium" / "WebView2" / (Path(sys.executable).stem or "python")
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def _normalize(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/",
                       parts.query, ""))


# --- the STA thread --------------------------------------------------------------------

class _Sta:
    """The thread that owns COM, the message loop and the WebView2
    environment shared by every view."""

    _instance: "_Sta | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_Sta":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(_loader())
            return cls._instance

    def __init__(self, loader) -> None:
        self.loader = loader
        self.env = None
        self._env_error: WebViewError | None = None
        self._env_waiters: list[Callable] = []
        self._queue: deque = deque()
        self._queue_lock = threading.Lock()
        self.hwnd = None
        ready: concurrent.futures.Future = concurrent.futures.Future()
        self.thread = threading.Thread(target=self._run, args=(ready,),
                                       name="elysium-webview2", daemon=True)
        self.thread.start()
        ready.result(30)
        _shutdown_hooks.append(self.stop)

    def _run(self, ready: concurrent.futures.Future) -> None:
        try:
            ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
            if hasattr(user32, "SetThreadDpiAwarenessContext"):
                user32.SetThreadDpiAwarenessContext.argtypes = [c_void_p]
                user32.SetThreadDpiAwarenessContext.restype = c_void_p
                user32.SetThreadDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            self.hinstance = kernel32.GetModuleHandleW(None)
            self._wndproc = WNDPROC(self._window_proc)
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = self.hinstance
            wc.lpszClassName = _CLASS
            if not user32.RegisterClassExW(byref(wc)) and \
                    ctypes.get_last_error() != _ERROR_CLASS_ALREADY_EXISTS:
                raise ctypes.WinError(ctypes.get_last_error())
            self.hwnd = user32.CreateWindowExW(0, _CLASS, "", 0, 0, 0, 0, 0,
                                               _HWND_MESSAGE, None, self.hinstance, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException as e:  # noqa: BLE001
            ready.set_exception(e)
            return
        ready.set_result(None)
        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_APP and hwnd == self.hwnd:
            self._drain()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def call(self, fn: Callable[[], Any], fut: concurrent.futures.Future | None = None) -> None:
        """Run ``fn`` on the STA thread. An exception it raises settles
        ``fut``, or is printed when nobody is waiting."""
        with self._queue_lock:
            self._queue.append((fn, fut))
        user32.PostMessageW(self.hwnd, _WM_APP, 0, 0)

    def _drain(self) -> None:
        while True:
            with self._queue_lock:
                if not self._queue:
                    return
                fn, fut = self._queue.popleft()
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                if fut is not None:
                    _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))
                else:
                    print(f"WebView (WebView2): {e}", file=sys.stderr)

    def on_thread(self) -> bool:
        return threading.current_thread() is self.thread

    def stop(self) -> None:
        self.call(lambda: user32.PostQuitMessage(0))
        self.thread.join(2.0)

    # --- environment (STA thread) ---

    def with_environment(self, callback: Callable[[Any, WebViewError | None], None]) -> None:
        if self.env or self._env_error:
            callback(self.env, self._env_error)
            return
        self._env_waiters.append(callback)
        if len(self._env_waiters) > 1:
            return
        args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS")
        args = f"{args} {_BROWSER_ARGS}" if args else _BROWSER_ARGS
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = args
        kernel32.SetEnvironmentVariableW("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", args)
        handler = _Handler("ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler",
                           "hr_ptr", self._on_environment)
        try:
            hr = self.loader.CreateCoreWebView2EnvironmentWithOptions(
                None, _user_data_folder(), None, handler.ptr)
        finally:
            handler.release()
        if hr < 0:
            self._on_environment(hr, None)

    def _on_environment(self, hr: int, env) -> None:
        if hr >= 0 and env:
            _addref(env)
            self.env = env
        else:
            self._env_error = WebViewError(f"could not start WebView2 (HRESULT {_hresult(hr)})")
        waiters, self._env_waiters = self._env_waiters, []
        for callback in waiters:
            callback(self.env, self._env_error)


# --- the backend ----------------------------------------------------------------------

_WV = "ICoreWebView2"
_CONTROLLER = "ICoreWebView2Controller"


class WebView2Backend(_Backend):
    def __init__(self, view) -> None:
        self._sta = _Sta.get()
        super().__init__(view)
        self._closed = False
        self._failure: WebViewError | None = None
        self._ready = False
        self._deferred: list[tuple[Callable[[], None], concurrent.futures.Future | None]] = []
        self._host = None
        self._controller = None
        self._webview = None
        self._webview21 = None
        self._loading: concurrent.futures.Future | None = None
        self._serving: tuple[str, str] | None = None
        self._filters: set[str] = set()
        self._script_ids: list[str] = []
        self._script_generation = 0
        self._sta.call(self._create)

    # --- scheduling -------------------------------------------------------------------

    def _run(self, fn: Callable[[], None], fut: concurrent.futures.Future | None = None) -> None:
        """Run ``fn`` on the STA thread once the controller exists."""
        def run() -> None:
            if self._closed:
                raise WebViewError("WebView is closed")
            if self._failure is not None:
                raise self._failure
            if not self._ready:
                self._deferred.append((fn, fut))
                return
            fn()
        self._sta.call(run, fut)

    def _fail(self, error: WebViewError) -> None:
        self._failure = error
        deferred, self._deferred = self._deferred, []
        for _, fut in deferred:
            if fut is not None:
                _settle(fut, error=error)
        self._fail_pending(error)

    # --- setup / teardown (STA thread) --------------------------------------------------

    def _create(self) -> None:
        view = self.view
        self._host = user32.CreateWindowExW(
            _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE, _CLASS, "Elysium WebView", _WS_POPUP,
            _PARKED[0], _PARKED[1], view.width, view.height, None, None, self._sta.hinstance, None)
        if not self._host:
            self._fail(WebViewError(f"CreateWindowExW failed ({ctypes.get_last_error()})"))
            return
        user32.ShowWindow(self._host, _SW_SHOWNOACTIVATE)
        self._sta.with_environment(self._on_environment)

    def _on_environment(self, env, error: WebViewError | None) -> None:
        if self._closed:
            return
        if error is not None:
            self._fail(error)
            return
        handler = _Handler("ICoreWebView2CreateCoreWebView2ControllerCompletedHandler",
                           "hr_ptr", self._on_controller)
        try:
            _call(env, "ICoreWebView2Environment", "CreateCoreWebView2Controller",
                  self._host, handler.ptr, argtypes=(wintypes.HWND, c_void_p))
        except WebViewError as e:
            self._fail(e)
        finally:
            handler.release()

    def _on_controller(self, hr: int, controller) -> None:
        if hr < 0 or not controller:
            self._fail(WebViewError(f"could not create the WebView2 controller (HRESULT {_hresult(hr)})"))
            return
        _addref(controller)
        if self._closed:
            _vcall(controller, SLOTS[_CONTROLLER]["Close"])
            _release(controller)
            return
        try:
            self._setup(controller)
        except WebViewError as e:
            self._fail(e)
            return
        self._ready = True
        deferred, self._deferred = self._deferred, []
        for fn, fut in deferred:
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                if fut is not None:
                    _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))

    def _setup(self, controller) -> None:
        view = self.view
        self._controller = controller
        c3 = _query(controller, "ICoreWebView2Controller3")
        if c3:
            # One page pixel per output pixel, whatever the monitor's scale.
            _call(c3, "ICoreWebView2Controller3", "put_ShouldDetectMonitorScaleChanges", False,
                  argtypes=(wintypes.BOOL,))
            _call(c3, "ICoreWebView2Controller3", "put_BoundsMode", _BOUNDS_MODE_USE_RAW_PIXELS,
                  argtypes=(c_int,))
            _call(c3, "ICoreWebView2Controller3", "put_RasterizationScale", 1.0, argtypes=(c_double,))
            _release(c3)
        c2 = _query(controller, "ICoreWebView2Controller2")
        if c2:
            # WebView2 only takes an opaque or a fully transparent default
            # background; partial alpha is composited after capture.
            r, g, b, a = view.background
            color = COREWEBVIEW2_COLOR(255, r, g, b) if a == 255 else COREWEBVIEW2_COLOR(0, 0, 0, 0)
            _call(c2, "ICoreWebView2Controller2", "put_DefaultBackgroundColor", color,
                  argtypes=(COREWEBVIEW2_COLOR,))
            _release(c2)
        _call(controller, _CONTROLLER, "put_Bounds", wintypes.RECT(0, 0, view.width, view.height),
              argtypes=(wintypes.RECT,))
        _call(controller, _CONTROLLER, "put_IsVisible", True, argtypes=(wintypes.BOOL,))

        webview = self._webview = _out_ptr(controller, _CONTROLLER, "get_CoreWebView2")
        self._webview21 = _query(webview, "ICoreWebView2_21")
        settings = _out_ptr(webview, _WV, "get_Settings")
        for method in ("put_IsStatusBarEnabled", "put_AreDefaultContextMenusEnabled",
                       "put_IsZoomControlEnabled"):
            _call(settings, "ICoreWebView2Settings", method, False, argtypes=(wintypes.BOOL,))
        if view.user_agent:
            settings2 = _query(settings, "ICoreWebView2Settings2")
            if settings2:
                _call(settings2, "ICoreWebView2Settings2", "put_UserAgent", view.user_agent,
                      argtypes=(c_wchar_p,))
                _release(settings2)
        _release(settings)

        self._subscribe("add_NavigationCompleted", "ICoreWebView2NavigationCompletedEventHandler",
                        self._on_navigation_completed)
        self._subscribe("add_WebMessageReceived", "ICoreWebView2WebMessageReceivedEventHandler",
                        self._on_web_message)
        self._subscribe("add_ProcessFailed", "ICoreWebView2ProcessFailedEventHandler",
                        self._on_process_failed)
        self._subscribe("add_WebResourceRequested", "ICoreWebView2WebResourceRequestedEventHandler",
                        self._on_resource_requested)

    def _subscribe(self, method: str, iface: str, fn: Callable[[Any, Any], None]) -> None:
        handler = _Handler(iface, "ptr_ptr", fn)
        token = c_int64()
        try:
            _call(self._webview, _WV, method, handler.ptr, byref(token),
                  argtypes=(c_void_p, POINTER(c_int64)))
        finally:
            handler.release()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._fail_pending(WebViewError("WebView is closed"))
        done: concurrent.futures.Future = concurrent.futures.Future()

        def teardown() -> None:
            try:
                deferred, self._deferred = self._deferred, []
                for _, fut in deferred:
                    if fut is not None:
                        _settle(fut, error=WebViewError("WebView is closed"))
                if self._controller:
                    _vcall(self._controller, SLOTS[_CONTROLLER]["Close"])
                for obj in (self._webview21, self._webview, self._controller):
                    _release(obj)
                self._webview21 = self._webview = self._controller = None
                if self._host:
                    user32.DestroyWindow(self._host)
                    self._host = None
            finally:
                done.set_result(None)

        if self._sta.on_thread():
            teardown()
            return
        self._sta.call(teardown)
        try:
            done.result(5.0)
        except Exception:  # noqa: BLE001 — the STA thread may already be gone at exit
            pass

    # --- navigation ---------------------------------------------------------------------

    def _begin_load(self, fut: concurrent.futures.Future) -> None:
        if self._loading is not None:
            _settle(self._loading, error=WebViewError("navigation superseded"))
        self._loading = fut

    def _on_navigation_completed(self, _sender, args) -> None:
        ok = wintypes.BOOL()
        _call(args, "ICoreWebView2NavigationCompletedEventArgs", "get_IsSuccess", byref(ok),
              argtypes=(POINTER(wintypes.BOOL),))
        if ok.value:
            error = None
        else:
            status = _out_int(args, "ICoreWebView2NavigationCompletedEventArgs", "get_WebErrorStatus")
            if status == _WEB_ERROR_OPERATION_CANCELED:
                return                       # superseded by a newer navigation
            error = WebViewError(f"navigation failed (WebView2 web error status {status})")
        if self._loading is not None:
            _settle(self._loading, error=error)
            self._loading = None

    def _on_resource_requested(self, _sender, args) -> None:
        """Serve ``load_html``'s document at its ``base_url`` so the page
        gets that origin (``NavigateToString`` pages have none)."""
        serving = self._serving
        if serving is None:
            return
        request = _out_ptr(args, "ICoreWebView2WebResourceRequestedEventArgs", "get_Request")
        try:
            uri = _out_string(request, "ICoreWebView2WebResourceRequest", "get_Uri")
        finally:
            _release(request)
        if not uri or _normalize(uri) != serving[0]:
            return
        data = serving[1].encode("utf-8")
        stream = shlwapi.SHCreateMemStream(data, len(data))
        if not stream:
            return
        response = c_void_p()
        try:
            _call(self._sta.env, "ICoreWebView2Environment", "CreateWebResourceResponse",
                  stream, 200, "OK", "Content-Type: text/html; charset=utf-8", byref(response),
                  argtypes=(c_void_p, c_int, c_wchar_p, c_wchar_p, POINTER(c_void_p)))
            _call(args, "ICoreWebView2WebResourceRequestedEventArgs", "put_Response",
                  response.value, argtypes=(c_void_p,))
        finally:
            _release(response.value)
            _release(stream)

    def load_url(self, url: str) -> None:
        fut = self._new_load()

        def run() -> None:
            self._begin_load(fut)
            self._serving = None
            _call(self._webview, _WV, "Navigate", url, argtypes=(c_wchar_p,))
        self._run(run, fut)

    def load_html(self, html: str, base_url: str | None = None) -> None:
        fut = self._new_load()

        def run() -> None:
            self._begin_load(fut)
            if base_url:
                target = _normalize(base_url)
                self._serving = (target, html)
                if target not in self._filters:
                    _call(self._webview, _WV, "AddWebResourceRequestedFilter",
                          target, _WEB_RESOURCE_CONTEXT_DOCUMENT, argtypes=(c_wchar_p, c_int))
                    self._filters.add(target)
                _call(self._webview, _WV, "Navigate", target, argtypes=(c_wchar_p,))
            else:
                self._serving = None
                _call(self._webview, _WV, "NavigateToString", html, argtypes=(c_wchar_p,))
        self._run(run, fut)

    def _navigate(self, method: str, allowed: str | None = None) -> None:
        fut = self._new_load()

        def run() -> None:
            if allowed is not None:
                ok = wintypes.BOOL()
                _call(self._webview, _WV, allowed, byref(ok), argtypes=(POINTER(wintypes.BOOL),))
                if not ok.value:
                    _settle(fut)             # nowhere to go: nothing to wait for
                    return
            self._begin_load(fut)
            _call(self._webview, _WV, method)
        self._run(run, fut)

    def reload(self) -> None:  self._navigate("Reload")
    def back(self) -> None:    self._navigate("GoBack", "get_CanGoBack")
    def forward(self) -> None: self._navigate("GoForward", "get_CanGoForward")

    def resize(self, width: int, height: int) -> None:
        def run() -> None:
            user32.SetWindowPos(self._host, None, _PARKED[0], _PARKED[1], width, height,
                                _SWP_NOZORDER | _SWP_NOACTIVATE)
            _call(self._controller, _CONTROLLER, "put_Bounds", wintypes.RECT(0, 0, width, height),
                  argtypes=(wintypes.RECT,))
        self._run(run)

    def _on_process_failed(self, _sender, args) -> None:
        kind = _out_int(args, "ICoreWebView2ProcessFailedEventArgs", "get_ProcessFailedKind")
        if kind in (_PROCESS_FAILED_BROWSER, _PROCESS_FAILED_RENDER):
            which = "browser" if kind == _PROCESS_FAILED_BROWSER else "web content"
            self._fail_pending(WebViewError(f"the WebView2 {which} process terminated"))

    # --- scripting -----------------------------------------------------------------------

    def evaluate(self, code: str) -> concurrent.futures.Future:
        fut = self._future()

        def with_result(hr: int, result) -> None:
            try:
                if hr < 0:
                    raise WebViewError(f"ExecuteScriptWithResult failed: HRESULT {_hresult(hr)}")
                iface = "ICoreWebView2ExecuteScriptResult"
                ok = wintypes.BOOL()
                _call(result, iface, "get_Succeeded", byref(ok), argtypes=(POINTER(wintypes.BOOL),))
                if ok.value:
                    _settle(fut, _from_json(_out_string(result, iface, "get_ResultAsJson")))
                    return
                exception = _out_ptr(result, iface, "get_Exception")
                try:
                    name = _out_string(exception, "ICoreWebView2ScriptException", "get_Name")
                    message = _out_string(exception, "ICoreWebView2ScriptException", "get_Message")
                finally:
                    _release(exception)
                _settle(fut, error=WebViewJSError(f"{name}: {message}" if name else (message or "")))
            except Exception as e:  # noqa: BLE001
                _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))

        def with_json(hr: int, text) -> None:
            if hr < 0:
                _settle(fut, error=WebViewError(f"ExecuteScript failed: HRESULT {_hresult(hr)}"))
            else:
                _settle(fut, _from_json(ctypes.wstring_at(text) if text else None))

        def run() -> None:
            if self._webview21:
                handler = _Handler("ICoreWebView2ExecuteScriptWithResultCompletedHandler",
                                   "hr_ptr", with_result)
                target, iface, method = self._webview21, "ICoreWebView2_21", "ExecuteScriptWithResult"
            else:
                # Runtimes before ExecuteScriptWithResult report a thrown
                # error as null, like an undefined result.
                handler = _Handler("ICoreWebView2ExecuteScriptCompletedHandler", "hr_ptr", with_json)
                target, iface, method = self._webview, _WV, "ExecuteScript"
            try:
                _call(target, iface, method, code, handler.ptr, argtypes=(c_wchar_p, c_void_p))
            finally:
                handler.release()
        self._run(run, fut)
        return fut

    def _execute(self, code: str) -> None:
        """Fire-and-forget script (STA thread)."""
        handler = _Handler("ICoreWebView2ExecuteScriptCompletedHandler", "hr_ptr", lambda hr, r: None)
        try:
            _call(self._webview, _WV, "ExecuteScript", code, handler.ptr, argtypes=(c_wchar_p, c_void_p))
        finally:
            handler.release()

    def _run_script(self, code: str) -> None:
        def run() -> None:
            if self._webview:
                self._execute(code)
        self._run(run)

    def _on_web_message(self, _sender, args) -> None:
        out = c_void_p()
        hr = _vcall(args, SLOTS["ICoreWebView2WebMessageReceivedEventArgs"]["TryGetWebMessageAsString"],
                    byref(out), argtypes=(POINTER(c_void_p),))
        body = _take_string(out.value) if hr >= 0 else None
        if body:
            self.view._on_bridge_message(body, self._run_script)

    def refresh_bridge(self, names: list[str]) -> None:
        source = _bridge_script(names, _POST_WEBVIEW2)

        def run() -> None:
            self._script_generation += 1
            generation = self._script_generation
            for script_id in self._script_ids:
                _call(self._webview, _WV, "RemoveScriptToExecuteOnDocumentCreated", script_id,
                      argtypes=(c_wchar_p,))
            self._script_ids = []

            def added(hr: int, script_id) -> None:
                if hr < 0 or not script_id or not self._webview:
                    return
                script_id = ctypes.wstring_at(script_id)
                if generation == self._script_generation:
                    self._script_ids.append(script_id)
                else:                       # a newer refresh already replaced it
                    _call(self._webview, _WV, "RemoveScriptToExecuteOnDocumentCreated", script_id,
                          argtypes=(c_wchar_p,))

            handler = _Handler("ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler",
                               "hr_ptr", added)
            try:
                _call(self._webview, _WV, "AddScriptToExecuteOnDocumentCreated", source, handler.ptr,
                      argtypes=(c_wchar_p, c_void_p))
            finally:
                handler.release()
            # …and bind the names in the page that is already loaded.
            self._execute(source)
        self._run(run)

    # --- pixels -------------------------------------------------------------------------------

    def snapshot(self, after_updates: bool) -> concurrent.futures.Future:
        fut = self._future()

        def run() -> None:
            stream = c_void_p()
            hr = ole32.CreateStreamOnHGlobal(None, True, byref(stream))
            if hr < 0:
                raise WebViewError(f"CreateStreamOnHGlobal failed: HRESULT {_hresult(hr)}")

            def captured(hr: int) -> None:
                try:
                    if hr < 0:
                        raise WebViewError(f"CapturePreview failed: HRESULT {_hresult(hr)}")
                    _settle(fut, self._stream_to_frame(stream.value))
                except Exception as e:  # noqa: BLE001
                    _settle(fut, error=e if isinstance(e, WebViewError) else WebViewError(str(e)))
                finally:
                    _release(stream.value)

            handler = _Handler("ICoreWebView2CapturePreviewCompletedHandler", "hr", captured)
            try:
                _call(self._webview, _WV, "CapturePreview", _CAPTURE_FORMAT_PNG, stream.value,
                      handler.ptr, argtypes=(c_int, c_void_p, c_void_p))
            except Exception:
                _release(stream.value)
                raise
            finally:
                handler.release()
        self._run(run, fut)
        return fut

    def _stream_to_frame(self, stream) -> Frame:
        from PIL import Image
        hglobal = c_void_p()
        hr = ole32.GetHGlobalFromStream(stream, byref(hglobal))
        if hr < 0:
            raise WebViewError(f"GetHGlobalFromStream failed: HRESULT {_hresult(hr)}")
        size = kernel32.GlobalSize(hglobal)
        data = kernel32.GlobalLock(hglobal)
        try:
            png = ctypes.string_at(data, size)
        finally:
            kernel32.GlobalUnlock(hglobal)
        image = Image.open(io.BytesIO(png))
        image.load()
        rgba = _composite(image.convert("RGBA").convert("RGBa").tobytes(), self.view.background)
        return Frame(rgba, image.width, image.height, image.width / max(1, self.view.width), 0)


def _from_json(text: str | None) -> Any:
    return json.loads(text) if text else None
