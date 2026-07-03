"""WKScriptMessageHandler registration without objc2.

Synthesises a real Objective-C class at runtime via the Objective-C
runtime's ``objc_allocateClassPair`` + ``class_addMethod`` API so JS
``window.webkit.messageHandlers.elysium.postMessage(json)`` lands in
the Python dispatcher with a return-channel for the JS Promise.
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import sys
from ctypes import c_void_p, c_char_p
from ctypes.util import find_library
from typing import Any


_obj = ctypes.CDLL(find_library("objc"))
_obj.objc_getClass.restype  = c_void_p
_obj.objc_getClass.argtypes = [c_char_p]
_obj.sel_registerName.restype  = c_void_p
_obj.sel_registerName.argtypes = [c_char_p]
_obj.objc_msgSend.restype  = c_void_p

_obj.objc_allocateClassPair.restype = c_void_p
_obj.objc_allocateClassPair.argtypes = [c_void_p, c_char_p, ctypes.c_size_t]
_obj.objc_registerClassPair.argtypes = [c_void_p]
_obj.class_addMethod.restype = ctypes.c_bool
_obj.class_addMethod.argtypes = [c_void_p, c_void_p, c_void_p, c_char_p]


def _cls(name: str) -> c_void_p:  return _obj.objc_getClass(name.encode())
def _sel(s: str)  -> c_void_p:  return _obj.sel_registerName(s.encode())


_HandlerProto = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p, c_void_p)
_REGISTERED: dict[int, Any] = {}


def register_handler(user_content_controller, view) -> bool:
    """Add a real WKScriptMessageHandler subclass under the name
    ``"elysium"``. The implementation dispatches to ``view._dispatch``
    on the event loop and (when a request id is present) injects the
    return value back into the page via ``window.elysium._resolve``."""
    key = id(view)
    if key in _REGISTERED:
        # Idempotent: re-register against the same view is a no-op.
        return True

    class_name = f"ElysiumScriptHandler_{key:x}".encode()
    nsobject = _cls("NSObject")
    if not nsobject:
        return False
    new_cls = _obj.objc_allocateClassPair(nsobject, class_name, 0)
    if not new_cls:
        return False

    def trampoline(_self, _sel, _ucc, message):
        try:
            body_ptr = _msg(message, "body")
            body = _objc_to_str(body_ptr)
            if body is None: return
            async def go():
                reply = await view._dispatch(body)
                payload = json.loads(reply)
                rid = payload.get("id")
                if rid is None: return
                # Push result back into the page.
                from .macos import WkWebViewBackend, _ns_string  # avoid cycle
                wkv = view._backend
                if isinstance(wkv, WkWebViewBackend):
                    js = f"window.elysium._resolve({rid}, {json.dumps(payload.get('result'))});"
                    _msg(wkv._view, "evaluateJavaScript:completionHandler:",
                         _ns_string(js), c_void_p(0),
                         arg_types=[c_void_p, c_void_p])
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(go())
                else:
                    loop.run_until_complete(go())
            except RuntimeError:
                asyncio.new_event_loop().run_until_complete(go())
        except Exception as e:
            print(f"elysium WKScriptMessageHandler trampoline: {e}",
                  file=sys.stderr)

    impl = _HandlerProto(trampoline)
    sel = _sel("userContentController:didReceiveScriptMessage:")
    # Type encoding: v@:@@ → void, self, _cmd, id, id.
    type_enc = b"v@:@@"
    if not _obj.class_addMethod(new_cls, sel, ctypes.cast(impl, c_void_p),
                                  type_enc):
        return False
    _obj.objc_registerClassPair(new_cls)

    instance = _msg(new_cls, "alloc")
    instance = _msg(instance, "init")
    _msg(user_content_controller,
         "addScriptMessageHandler:name:",
         instance, _ns_string_local("elysium"),
         arg_types=[c_void_p, c_void_p])
    _REGISTERED[key] = (new_cls, impl, instance)
    return True


def snapshot_to_bytes(wk_view, width: int, height: int) -> bytes:
    """objc2-flavoured snapshot — delegates to the ctypes path now that
    the latter is fully functional, so callers don't need objc2."""
    from .macos import _snapshot_via_cg
    return _snapshot_via_cg(wk_view, width, height)


# --- helpers ---------------------------------------------------------------

def _msg(target: c_void_p, selector: str, *args,
         arg_types=None, ret=c_void_p):
    fn = _obj.objc_msgSend
    fn.restype = ret
    fn.argtypes = [c_void_p, c_void_p] + (list(arg_types) if arg_types else [])
    return fn(target, _sel(selector), *args)


def _ns_string_local(s: str) -> c_void_p:
    return _msg(_cls("NSString"), "stringWithUTF8String:", s.encode(),
                arg_types=[c_char_p])


def _objc_to_str(obj_ptr) -> str | None:
    if not obj_ptr: return None
    cls = _msg(obj_ptr, "class")
    _obj.class_getName.restype = c_char_p
    _obj.class_getName.argtypes = [c_void_p]
    name = _obj.class_getName(cls).decode()
    if "String" in name:
        cstr = _msg(obj_ptr, "UTF8String", ret=c_char_p)
        return ctypes.string_at(cstr).decode() if cstr else ""
    # Try `description` as a fallback.
    desc = _msg(obj_ptr, "description")
    cstr = _msg(desc, "UTF8String", ret=c_char_p)
    return ctypes.string_at(cstr).decode() if cstr else None
