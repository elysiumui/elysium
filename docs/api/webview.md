# `elysium.webview`

Embedded native browser engine, rendered off-screen and composited like
any other Elysium element.

## Classes and functions

| Name | Purpose |
|---|---|
| `WebView` | The browser surface |
| `Frame` | One rendered page image (`rgba`, `width`, `height`, `scale`, `seq`) |
| `WebViewError` | Base error: engine failure, closed view, crashed page process |
| `WebViewJSError` | The evaluated JavaScript threw |
| `WebViewTimeout` | The engine did not answer in time (also a `TimeoutError`) |
| `pump(seconds)` | Let the engine work on the main thread (macOS scripts without an App) |

## WebView surface

```python
wv = WebView(width=800, height=600, user_agent=None, background=(255, 255, 255, 255))
wv.available                                       # False → no engine, every call is a no-op

async def tour(dl, x, y, w, h):
    wv.load_url("https://example.com")
    wv.load_html("<h1>Hello</h1>", base_url="https://app.local/")
    wv.reload(); wv.back(); wv.forward()
    await wv.wait_loaded(timeout=10.0)                 # raises WebViewError if the load failed

    await wv.evaluate_js("document.title")             # JSON-compatible value
    wv.expose("greet", lambda name: f"hi, {name}")     # window.elysium.greet(...) → Promise

    wv.paint(dl, x, y, w, h)                           # latest frame, never blocks
    wv.latest_frame()                                  # Frame | None
    wv.request_snapshot()                              # start rendering the next frame
    rgba = wv.snapshot_rgba(timeout=2.0)               # render now: width*height*4 bytes

    wv.resize(1024, 768)
    wv.close()                                         # or: with WebView(...) as wv:
```

## Backends

| OS | Backend |
|---|---|
| macOS | WKWebView (ctypes, off-screen window) |
| Windows | none yet (`available` is False) |
| Linux | WebKitGTK 6.0 via PyGObject (own GTK thread) |
| Headless | No-op stub |

## Return values

`evaluate_js` maps JavaScript values the way `JSON.stringify` +
`json.loads` would: integral numbers become `int`, `null` and
`undefined` become `None`, and objects and arrays become dicts and lists.

## Bridge

Python callables exposed via `wv.expose(name, fn)` become
`window.elysium.<name>(...)` on the JS side, returning a Promise. Sync
handlers run on a worker thread and coroutines on Elysium's background
event loop. An exception rejects the Promise.

## Auto-rendered details

::: elysium.webview

## See also

- [WebView](../guides/webview.md)
