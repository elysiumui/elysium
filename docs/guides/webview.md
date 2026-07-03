# WebView

Embed a native browser engine inside a skin layer: composited like any other Elysium element, with rounding, blur, and animation applied uniformly.

```python
from elysium.webview import WebView

wv = WebView(width=800, height=600)
wv.load_url("https://example.com")

# Surface a Python callable on the JS side as window.elysium.<name>.
wv.expose("greet", lambda name: f"hi, {name}")

# From inside the page:
#   const reply = await window.elysium.greet("kenley");

# Per-frame snapshot for compositing.
rgba = wv.snapshot_rgba()
```

## Backends
- **macOS**: `WKWebView` (system framework, no extra install).
- **Windows**: WebView2 via [pywebview](https://pywebview.flowrl.com/) (`pip install pywebview`). Requires the Evergreen WebView2 runtime; ships with Windows 11, auto-installed on Windows 10 via Edge Updater.
- **Linux**: WebKitGTK 6.0 via PyGObject (`sudo apt-get install gir1.2-webkit-6.0 python3-gi`).
- **Headless**: a no-op fallback so tests can construct a `WebView` on platforms without an installed backend.

## Bridge protocol
The bridge uses `webkit.messageHandlers.elysium.postMessage(JSON.stringify({id, name, args}))` on macOS and Linux, and pywebview's `window.pywebview.api.*` on Windows, with a shim that rewrites both into `window.elysium.<name>(...)` so application code stays portable.

Round-tripped Python return values land via `window.elysium._resolve(id, value)`.

## Composition
`snapshot_rgba()` returns premultiplied RGBA the same size as the view; pass it through `DisplayList::draw_image_bytes` and it inherits the parent layer's transform: rounded corners, frosted-glass blur, anim-slot tweens, all of it.

## When to use WebView

A WebView is a hatch into the OS's browser engine. Use when:

- Embedding a third-party widget (Stripe Elements, a video player,
  a documentation page).
- Rendering a chart from a JS lib (D3, ECharts) that has no Python
  equivalent.
- Hosting OAuth flows whose providers require a real browser.

Avoid for general UI: the framework's components and the brush
+ skin system are dramatically faster than a WebView for rendering
native chrome.

## Latency

`snapshot_rgba()` takes ~3-8 ms on a baseline GPU. For real-time
compositing, target ~30 Hz updates rather than 60 Hz unless you
need every frame.

For interactive WebViews (Stripe forms, etc.), the WebView's own
event loop handles input; you do not need to drive snapshot
updates rapidly.

## Security

The bridge exposes only Python callables you explicitly pass to
`wv.expose(...)`. No filesystem, no shell. If you bind a callable
that reads sensitive state, sanitize its inputs the same as any
network surface: the WebView is the network from the framework's
point of view.

## See also

- [API: elysium.webview](../api/webview.md)
- [Recipes](../recipes/index.md): search for "webview" patterns.
