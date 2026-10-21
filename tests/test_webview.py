"""``elysium.webview`` without a real engine: the shared core (bridge
dispatch and script, frames, paint, lifecycle) against a fake backend,
plus the macOS runtime pieces that can be checked in-process. The live
engine scenarios are in ``test_webview_live.py``."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys

import pytest

import elysium.webview as webview
from elysium.webview import Frame, WebView, WebViewError, WebViewTimeout


class FakeBackend(webview._Backend):
    def __init__(self, view):
        super().__init__(view)
        self.snapshots = 0
        self.bridges: list[list[str]] = []
        self.closed = False
        self.evaluated: list[str] = []

    def _done(self, value):
        fut = concurrent.futures.Future()
        fut.set_result(value)
        return fut

    def load_url(self, url): self._new_load()
    def load_html(self, html, base_url=None): pass
    def reload(self): pass
    def back(self): pass
    def forward(self): pass
    def resize(self, width, height): pass
    def refresh_bridge(self, names): self.bridges.append(names)
    def close(self): self.closed = True

    def evaluate(self, code):
        self.evaluated.append(code)
        return self._done(len(code))

    def snapshot(self, after_updates):
        self.snapshots += 1
        return self._done(Frame(bytes([255, 0, 0, 255]) * 16, 4, 4, 2.0, 0))


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(webview, "_resolve_backend", FakeBackend)
    return WebView(width=2, height=2)


@pytest.fixture
def null_view(monkeypatch):
    monkeypatch.setattr(webview, "_resolve_backend", webview._NullBackend)
    return WebView(width=2, height=2)


# --- construction / lifecycle ---------------------------------------------------

def test_null_backend_is_reported_and_harmless(null_view):
    assert null_view.available is False
    assert null_view.snapshot_rgba() == b""
    assert asyncio.run(null_view.evaluate_js("1")) is None
    asyncio.run(null_view.wait_loaded())
    assert null_view.paint(object(), 0, 0) is False


def test_private_fields_are_not_constructor_arguments():
    with pytest.raises(TypeError):
        WebView(_exposed={})  # type: ignore[call-arg]


@pytest.mark.parametrize("size", [(0, 10), (10, -1)])
def test_size_must_be_positive(size, monkeypatch):
    monkeypatch.setattr(webview, "_resolve_backend", FakeBackend)
    with pytest.raises(ValueError):
        WebView(width=size[0], height=size[1])


def test_close_is_idempotent_and_final(fake):
    with fake:
        pass
    assert fake._backend.closed
    fake.close()
    with pytest.raises(WebViewError):
        fake.load_url("https://example.com")
    with pytest.raises(WebViewError):
        asyncio.run(fake.evaluate_js("1"))
    assert fake.paint(object(), 0, 0) is False


def test_wait_loaded_times_out_as_webview_timeout(fake):
    fake.load_url("https://example.com")       # the fake never finishes loading
    with pytest.raises(WebViewTimeout):
        asyncio.run(fake.wait_loaded(timeout=0.05))
    assert issubclass(WebViewTimeout, TimeoutError)


def test_evaluate_waits_for_a_pending_load_within_its_timeout(fake):
    fake.load_url("https://example.com")
    with pytest.raises(WebViewTimeout):
        asyncio.run(fake.evaluate_js("1", timeout=0.05))
    assert fake._backend.evaluated == []        # never evaluated in the old page
    webview._settle(fake._backend.load_future())
    assert asyncio.run(fake.evaluate_js("abc")) == 3


def test_pending_calls_fail_when_the_backend_fails_them(fake):
    fut = fake._backend._future()
    fake._backend._fail_pending(WebViewError("crashed"))
    with pytest.raises(WebViewError, match="crashed"):
        fut.result(0)


# --- bridge ---------------------------------------------------------------------

@pytest.mark.parametrize("name", ["1abc", "a-b", "_private", "", "a b"])
def test_expose_rejects_bad_names(fake, name):
    with pytest.raises(ValueError):
        fake.expose(name, lambda: None)


def test_expose_rebinds_every_name(fake):
    fake.expose("a", lambda: 1)
    fake.expose("b", lambda: 2)
    assert fake._backend.bridges == [["a"], ["a", "b"]]


def _dispatch(view, msg) -> dict:
    return asyncio.run(view._dispatch(json.dumps(msg)))


def test_dispatch_sync_and_async_handlers(fake):
    async def mul(a, b):
        return a * b
    fake.expose("add", lambda a, b: a + b)
    fake.expose("mul", mul)
    assert _dispatch(fake, {"id": 1, "name": "add", "args": [2, 3]}) == {"id": 1, "result": 5}
    assert _dispatch(fake, {"id": 2, "name": "mul", "args": [4, 5]}) == {"id": 2, "result": 20}


def test_dispatch_errors_keep_the_id(fake):
    def boom():
        raise ValueError("nope")
    fake.expose("boom", boom)
    fake.expose("weird", lambda: object())
    assert _dispatch(fake, {"id": 3, "name": "boom"}) == {"id": 3, "error": "ValueError: nope"}
    assert _dispatch(fake, {"id": 4, "name": "missing"}) == {"id": 4, "error": "no such handler: missing"}
    weird = _dispatch(fake, {"id": 5, "name": "weird"})
    assert weird["id"] == 5 and weird["error"].startswith("TypeError")


def test_reply_scripts():
    assert webview._reply_script({"id": 7, "result": {"a": [1]}}) == \
        'window.elysium._resolve(7,{"a": [1]});'
    assert webview._reply_script({"id": 8, "error": 'bad "x"'}) == \
        'window.elysium._reject(8,"bad \\"x\\"");'
    assert webview._reply_script({"id": None, "error": "x"}) is None


def test_bridge_script_is_rerunnable_and_binds_all_names():
    js = webview._bridge_script(["greet", "add"], webview._POST_WEBKIT)
    # The old shim returned early once window.elysium existed, so only the
    # first exposed name ever worked.
    assert "if (window.elysium) return" not in js and "if(window.elysium)return" not in js
    assert "if(!e._pending)" in js
    assert '["greet", "add"]' in js
    assert webview._POST_WEBKIT in js
    assert "_reject" in js


# --- frames / paint -----------------------------------------------------------------

def test_snapshot_rgba_fits_the_view_size(fake):
    rgba = fake.snapshot_rgba()
    assert len(rgba) == 2 * 2 * 4
    assert rgba[:4] == bytes([255, 0, 0, 255])
    assert fake.latest_frame().seq == 1


def test_paint_draws_latest_frame_and_requests_the_next(fake):
    class DL:
        def __init__(self):
            self.calls = []

        def draw_image_bytes(self, *args):
            self.calls.append(args)

    dl = DL()
    assert fake.paint(dl, 1, 2) is False        # no frame yet; one is requested
    assert dl.calls == []
    assert fake.paint(dl, 1, 2) is True
    assert fake.paint(dl, 1, 2, 30, 40) is True
    rgba, w, h, *dest = dl.calls[-1]
    assert (len(rgba), w, h) == (64, 4, 4)      # native pixels…
    assert dest == [1, 2, 30, 40]               # …into the logical rect
    assert fake._backend.snapshots == 3
    assert fake.latest_frame().seq == 3


def test_fit_resamples_premultiplied():
    frame = Frame(bytes([0, 0, 255, 255]) * 64, 8, 8, 2.0, 1)
    out = webview._fit(frame, 4, 4)
    assert len(out) == 64 and out[:4] == bytes([0, 0, 255, 255])
    assert webview._fit(frame, 8, 8) is frame.rgba


def test_composite_over_background():
    clear, opaque = bytes([0, 0, 0, 0]), bytes([10, 20, 30, 255])
    half = bytes([64, 0, 0, 128])
    assert webview._composite(clear + opaque, (0, 255, 0, 255)) == bytes([0, 255, 0, 255]) + opaque
    assert webview._composite(clear, (0, 255, 0, 0)) == clear
    r, g, b, a = webview._composite(half, (0, 0, 255, 255))
    assert (r, g, a) == (64, 0, 255) and 125 <= b <= 128


# --- macOS runtime ------------------------------------------------------------------

darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="Objective-C runtime")


@darwin_only
def test_block_literal_layout():
    import ctypes
    from elysium.webview import _objc

    block = _objc.Block(_objc.BLOCK_ID_ID, lambda a, b: None)
    lit = block._literal
    stack = ctypes.addressof(ctypes.c_void_p.in_dll(_objc.libsystem, "_NSConcreteStackBlock"))
    assert lit.isa == stack                                     # the class, not its contents
    assert lit.flags & (1 << 25) and lit.flags & (1 << 30)       # copy/dispose + signature
    desc = lit.descriptor.contents
    assert desc.copy_helper and desc.dispose_helper
    assert desc.signature == b"v24@?0@8@16"
    block.release()


@darwin_only
def test_block_survives_copy_until_the_last_release():
    import ctypes
    from ctypes import c_void_p
    from elysium.webview import _objc

    lib = _objc.libsystem
    lib._Block_copy.restype = c_void_p
    lib._Block_copy.argtypes = [c_void_p]
    lib._Block_release.restype = None
    lib._Block_release.argtypes = [c_void_p]

    calls = []
    before = _objc.Block.live_count()
    block = _objc.Block(_objc.BLOCK_ID_ID, lambda a, b: calls.append((a, b)))
    heap = lib._Block_copy(block.ptr)          # what WebKit does with a completion handler
    block.release()                             # the method call returned
    assert _objc.Block.live_count() == before + 1

    invoke = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p)(
        _objc._BlockLiteral.from_address(heap).invoke)
    invoke(heap, 11, 22)                        # fires later, through the heap copy
    assert calls == [(11, 22)]

    lib._Block_release(heap)                    # WebKit drops it
    assert _objc.Block.live_count() == before


@darwin_only
def test_on_main_runs_on_the_main_thread_when_pumped():
    import threading
    from elysium.webview import _objc

    fut = _objc.on_main(lambda: (_objc.is_main_thread(), threading.current_thread().name))
    assert _objc.wait(fut, 5.0) == (True, threading.main_thread().name)


@darwin_only
def test_wait_times_out():
    from elysium.webview import _objc

    with pytest.raises(TimeoutError):
        _objc.wait(concurrent.futures.Future(), 0.05)
