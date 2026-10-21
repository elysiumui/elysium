# WebView

Embed the platform's browser engine as an image in a skin layer, composited like any other Elysium element, with rounding, blur and animation applied uniformly.

```python
import asyncio
from elysium.webview import WebView

wv = WebView(width=800, height=600)
wv.load_url("https://example.com")

# Surface a Python callable on the JS side as window.elysium.<name>.
wv.expose("greet", lambda name: f"hi, {name}")
# From inside the page:
#   const reply = await window.elysium.greet("kenley");

async def main():
    await wv.wait_loaded()
    print(await wv.evaluate_js("document.title"))

asyncio.run(main())
```

A WebView is **display and scripting only**: the page renders off-screen and is drawn as an image, and mouse and keyboard input are not forwarded to it. Drive the page from Python with `evaluate_js` and `expose`.

## Backends

| OS | Engine | Install |
|---|---|---|
| macOS | `WKWebView` | nothing (system framework) |
| Windows | WebView2 (Edge) | the Evergreen WebView2 Runtime: ships with Windows 11, installed by the Edge updater on Windows 10 |
| Linux | WebKitGTK 6.0 (GTK 4) | `sudo apt-get install gir1.2-webkit-6.0 gir1.2-gtk-4.0 python3-gi` (Ubuntu 24.04+, Debian 13+) |

On Linux, `python3-gi` provides PyGObject for the system interpreter. In a virtualenv, `pip install PyGObject` instead, which builds against `libgirepository-2.0-dev`, `libcairo2-dev` and `pkg-config`. The engine needs a display (X11, Wayland or Xvfb).

Without an engine, a no-op backend stands in so code and tests can still construct a `WebView`. Check `wv.available` before relying on output.

## Scripting

`await wv.evaluate_js(code, timeout=5.0)` returns the completion value of `code` as JSON-compatible Python: strings, `int`/`float`, `bool`, `None` (for both `null` and `undefined`), lists and dicts. A thrown JavaScript error raises `WebViewJSError`, an engine that does not answer in time raises `WebViewTimeout`, and every other failure raises `WebViewError`. If a page is still loading, `evaluate_js` waits for it first, within the same timeout. Promises are not awaited: to get an async result, have the page store it and poll, or call back into Python through the bridge.

`await wv.wait_loaded()` waits for the latest `load_url`/`load_html`/`reload` and raises `WebViewError` if it failed.

## Bridge

`wv.expose(name, fn)` binds `window.elysium.<name>(...)` in the current page and every page loaded later. Each call returns a Promise. Arguments and return values travel as JSON. Sync handlers run on a worker thread and coroutines run on Elysium's background event loop, so a slow handler never blocks the engine. A handler that raises rejects the Promise with `"<ExceptionType>: <message>"`.

Under the hood the page posts `JSON.stringify({id, name, args})` to the `elysium` script-message handler, and the reply settles the Promise through `window.elysium._resolve(id, value)` or `window.elysium._reject(id, message)`.

## Composition

- `wv.paint(dl, x, y, w, h)` draws the latest page image into a display list and requests a fresh one for the next frame. It never blocks; it returns `False` until the first frame exists. Call it from your frame loop.
- `wv.latest_frame()` returns that image as a `Frame` (premultiplied RGBA8 at the engine's native pixel size, which is 2× on Retina displays) without blocking.
- `wv.snapshot_rgba(timeout=2.0)` renders *now* and returns exactly `width*height*4` bytes, top row first. Use it for one-off captures and tests.

`background` (default opaque white) shows wherever the page itself is transparent. Pass an alpha of 0 for a transparent webview.

## Threading

Every method can be called from any thread.

**macOS.** The engine lives on the main thread.
- **Inside a running `elysium.App`**, the app already turns the main thread, and frame callbacks run on worker threads, so nothing special is needed.
- **In a plain script**, the blocking calls (`snapshot_rgba`, and awaiting `evaluate_js`/`wait_loaded` on the main thread) turn the main thread themselves. A script whose main thread is busy elsewhere calls `elysium.webview.pump(seconds)` to let the engine catch up.
- **Ordering.** Call `App.run()` before blocking on a WebView from the main thread. Once a script has done that, the process can no longer start an App, and `App.run()` raises `ElysiumError`. Constructing a `WebView` before `App.run()` is fine.

**Windows.** WebView2 runs on its own COM apartment thread (`elysium-webview2`) with its own message loop, so nothing needs pumping. Pages render in a tool window parked off-screen that never takes focus. Chromium's occlusion and background throttling are switched off through `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`, which the backend appends to and does not replace. Browser data lives under `%LOCALAPPDATA%\Elysium\WebView2\<executable name>`. Before WebView2 runtime 1.0.2210, `ExecuteScriptWithResult` is missing, so a thrown error comes back as `None` instead of raising.

**Linux.** WebKitGTK runs on its own GTK thread (`elysium-webkitgtk`) with its own GLib main loop, so neither the app nor a script has to pump anything, and `pump()` just sleeps. The page is hosted in an undecorated, fully transparent window that takes no input: invisible on X11 and Xvfb, though a Wayland compositor may still list it.

Call `wv.close()`, or use `with WebView(...) as wv:`, to destroy the engine view. Views still open at interpreter exit are closed automatically.

## When to use WebView

A WebView is a hatch into the OS's browser engine. Use it to:

- Render a chart or scene from a JS library (D3, ECharts, three.js) that has no Python equivalent.
- Show a documentation page or other read-only web content.

Avoid it for general UI: the framework's components and the brush and skin system are much faster than a WebView for native chrome. Interactive pages (forms, OAuth flows) need input forwarding, which the WebView does not do yet.

## Security

The bridge exposes only the Python callables you explicitly pass to `wv.expose(...)`: no filesystem, no shell. Messages from sub-frames are ignored. If you bind a callable that reads sensitive state, sanitize its inputs as you would for any network surface, because from the framework's point of view the WebView *is* the network.

## See also

- [API: elysium.webview](../api/webview.md)
