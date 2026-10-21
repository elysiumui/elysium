"""Live WebView scenarios, one per process (see ``test_webview_live.py``).

    python tests/_webview_probe.py <scenario>

Prints one JSON object on the last stdout line. A scenario that cannot
run here (no engine) prints ``{"skip": "<reason>"}``. Each scenario runs
in its own process so a crash in native code fails one test instead of
the whole session, and so the macOS application object (one per process)
never leaks between scenarios.
"""
from __future__ import annotations

import asyncio
import faulthandler
import json
import sys
import threading
import time

faulthandler.enable()

from elysium.webview import WebView, WebViewError, WebViewJSError, pump  # noqa: E402

W, H = 320, 240

SPLIT_PAGE = """<html><body style="margin:0;background:#ff0000">
<div style="position:absolute;left:0;top:120px;width:320px;height:120px;background:#0000ff"></div>
</body></html>"""

WEBGL_PAGE = """<html><body style="margin:0;background:#ff0000">
<canvas id=c width=320 height=240 style="position:absolute;left:0;top:0"></canvas>
<script>
window.__frames = 0;
const gl = document.getElementById('c').getContext('webgl', {preserveDrawingBuffer: false});
window.__gl = !!gl;
function frame() {
  window.__frames++;
  if (gl) { gl.clearColor(0, 0, 1, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>"""

BARE_PAGE = "<html><body style='margin:0'></body></html>"


def pixel(rgba: bytes, x: int, y: int, width: int = W) -> list[int]:
    i = (y * width + x) * 4
    return list(rgba[i:i + 4])


def run(coro):
    return asyncio.run(coro)


def make(**kw) -> WebView:
    wv = WebView(width=W, height=H, **kw)
    if not wv.available:
        print(json.dumps({"skip": "no web engine on this machine"}))
        sys.exit(0)
    return wv


# --- scenarios -----------------------------------------------------------------

def repro() -> dict:
    """The snippet from the bug report: evaluate right after load_html (it segfaulted)."""
    wv = make()
    wv.load_html("<html><body><script>window.__p=42</script></body></html>", "https://probe.local/")
    return {"value": run(wv.evaluate_js("String(window.__p)"))}


def types() -> dict:
    wv = make()
    wv.load_html(BARE_PAGE, "https://probe.local/")
    exprs = ["1+1", "1.5", "'s'", "true", "false", "null", "undefined",
             "({a:[1,'x',null], b:{c:2.5}})", "[]", "-0", "0/0", "1/0"]

    async def go():
        await wv.wait_loaded()
        out = {e: await wv.evaluate_js(e) for e in exprs}
        try:
            await wv.evaluate_js("throw new Error('boom')")
            out["throw"] = "no error"
        except WebViewJSError as e:
            out["throw"] = ["WebViewJSError", str(e)]
        return out
    return run(go())


def many() -> dict:
    wv = make()
    wv.load_html(BARE_PAGE, "https://probe.local/")

    async def go():
        return [await wv.evaluate_js(f"{i}*2") for i in range(50)]
    values = run(go())
    out = {"ok": values == [i * 2 for i in range(50)]}
    if sys.platform == "darwin":
        from elysium.webview import _objc
        pump(0.2)
        out["live_blocks"] = _objc.Block.live_count()
    return out


def snapshot() -> dict:
    wv = make()
    wv.load_html(SPLIT_PAGE, "https://probe.local/")
    rgba = wv.snapshot_rgba(timeout=10)
    frame = wv.latest_frame()
    out = {
        "len": len(rgba),
        "top": pixel(rgba, 160, 40),
        "bottom": pixel(rgba, 160, 200),
        "frame": [frame.width, frame.height, frame.scale, frame.seq],
    }
    wv.close()

    # Background shows through a page without one; alpha 0 stays transparent.
    for name, bg in (("green_bg", (0, 255, 0, 255)), ("clear_bg", (0, 0, 0, 0))):
        v = make(background=bg)
        v.load_html(BARE_PAGE, "https://probe.local/")
        out[name] = pixel(v.snapshot_rgba(timeout=10), 160, 120)
        v.close()
    return out


def webgl() -> dict:
    wv = make()
    wv.load_html(WEBGL_PAGE, "https://probe.local/")
    run(wv.wait_loaded())
    if not run(wv.evaluate_js("window.__gl")):
        return {"skip": "no WebGL context on this machine"}
    f0 = run(wv.evaluate_js("window.__frames"))
    pump(0.5)
    f1 = run(wv.evaluate_js("window.__frames"))
    rgba = wv.snapshot_rgba(timeout=10)
    return {"center": pixel(rgba, 160, 120), "frames_advanced": f1 - f0}


BRIDGE_PAGE = """<html><body><script>
window.__r = {};
async function go() {
  window.__r.add = await window.elysium.add(2, 3);
  window.__r.mul = await window.elysium.mul(4, 5);
  try { await window.elysium.fail(); window.__r.fail = 'resolved'; }
  catch (e) { window.__r.fail = String(e.message); }
  window.__r.done = true;
}
window.addEventListener('load', go);
</script></body></html>"""


def bridge() -> dict:
    wv = make()

    async def mul(a, b):
        await asyncio.sleep(0.01)
        return a * b

    def fail():
        raise ValueError("nope")

    wv.expose("add", lambda a, b: a + b)
    wv.expose("mul", mul)
    wv.expose("fail", fail)
    wv.load_html(BRIDGE_PAGE, "https://probe.local/")

    async def poll(expr, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            v = await wv.evaluate_js(expr)
            if v:
                return v
            await asyncio.sleep(0.05)
        return None

    async def go():
        await wv.wait_loaded()
        await poll("window.__r.done")
        result = await wv.evaluate_js("window.__r")
        # A name exposed after the page loaded is callable in that page.
        wv.expose("late", lambda: "late-ok")
        await asyncio.sleep(0.2)
        await wv.evaluate_js("window.elysium.late().then(v => window.__late = v)")
        result["late"] = await poll("window.__late")
        return result
    return run(go())


def worker() -> dict:
    """App-mode shape: the main thread only turns the run loop while a
    worker thread drives the WebView."""
    wv = make()
    out: dict = {}

    def drive():
        try:
            wv.load_html(SPLIT_PAGE, "https://probe.local/")
            out["eval"] = asyncio.run(wv.evaluate_js("document.body.style.background"))
            rgba = wv.snapshot_rgba(timeout=10)
            out["top"] = pixel(rgba, 160, 40)
        except Exception as e:  # noqa: BLE001
            out["error"] = repr(e)

    t = threading.Thread(target=drive)
    t.start()
    while t.is_alive():
        pump(0.05)
    return out


def paint() -> dict:
    wv = make()
    wv.load_html(SPLIT_PAGE, "https://probe.local/")
    run(wv.wait_loaded())

    class DL:
        calls = []

        def draw_image_bytes(self, *args):
            self.calls.append(args)

    dl = DL()
    first = wv.paint(dl, 10, 20)
    deadline = time.monotonic() + 10
    while wv.latest_frame() is None and time.monotonic() < deadline:
        pump(0.05)
    second = wv.paint(dl, 10, 20, 160, 120)
    rgba, fw, fh, x, y, w, h = dl.calls[-1] if dl.calls else (b"", 0, 0, 0, 0, 0, 0)
    return {"first": first, "second": second,
            "args": [len(rgba) == fw * fh * 4, x, y, w, h]}


def lifecycle() -> dict:
    wv = make()
    out = {}
    import socket
    with socket.socket() as sock:               # a port that just stopped listening
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    wv.load_url(f"http://127.0.0.1:{port}/")
    try:
        run(wv.wait_loaded(timeout=15))
        out["bad_load"] = "loaded"
    except WebViewError as e:
        out["bad_load"] = type(e).__name__
    wv.load_html(BARE_PAGE, "https://probe.local/")
    run(wv.wait_loaded())
    out["good_load"] = "ok"
    wv.resize(200, 100)
    out["resized"] = len(wv.snapshot_rgba(timeout=10)) == 200 * 100 * 4
    wv.close()
    wv.close()                                  # idempotent
    try:
        run(wv.evaluate_js("1"))
        out["after_close"] = "no error"
    except WebViewError as e:
        out["after_close"] = type(e).__name__
    return out


def app() -> dict:
    """A real elysium.App: the WebView is created before App.run() and
    driven from a worker thread while the app's own loop pumps."""
    import elysium as ely
    application = ely.App(title="webview-probe", identifier="dev.elysium.webview-probe")
    application.window(transparent=False, title_bar=True, initial_size=(200, 120))
    wv = make()
    out: dict = {}

    def drive():
        try:
            wv.load_html(SPLIT_PAGE, "https://probe.local/")
            out["eval"] = asyncio.run(wv.evaluate_js("1+1"))
            out["top"] = pixel(wv.snapshot_rgba(timeout=10), 160, 40)
        except Exception as e:  # noqa: BLE001
            out["error"] = repr(e)
        finally:
            application.quit()

    threading.Thread(target=drive, daemon=True).start()
    application.run()
    return out


def app_guard() -> dict:
    """A script that already pumped the WebView from the main thread can
    no longer start an App: a clear ElysiumError instead of a winit panic."""
    import elysium as ely
    wv = make()
    wv.load_html(BARE_PAGE, "https://probe.local/")
    run(wv.wait_loaded())
    application = ely.App(title="webview-probe", identifier="dev.elysium.webview-probe")
    application.window(transparent=False, title_bar=True, initial_size=(200, 120))
    try:
        application.run()
        return {"raised": None}
    except ely.ElysiumError as e:
        return {"raised": type(e).__name__, "mentions_run": "App.run()" in str(e)}


SCENARIOS = {f.__name__: f for f in
             (repro, types, many, snapshot, webgl, bridge, worker, paint, lifecycle, app, app_guard)}

if __name__ == "__main__":
    result = SCENARIOS[sys.argv[1]]()
    print(json.dumps(result), flush=True)
