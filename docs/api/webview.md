# `elysium.webview`

Embedded native browser engine, composited like any other Elysium
element.

## Classes

| Class | Purpose |
|---|---|
| `WebView` | The browser surface |

## WebView surface

```python
wv = WebView(width=800, height=600)
wv.load_url("https://example.com")
wv.load_html("<h1>Hello</h1>")
wv.expose("greet", lambda name: f"hi, {name}")    # callable as window.elysium.greet
wv.evaluate("document.title")                      # returns a future
rgba = wv.snapshot_rgba()                          # for composition
```

## Backends

| OS | Backend |
|---|---|
| macOS | WKWebView |
| Windows | WebView2 via pywebview |
| Linux | WebKitGTK 6.0 via PyGObject |
| Headless | No-op stub for tests |

## Bridge

Python-side callables exposed via `wv.expose(name, fn)` become
`window.elysium.<name>(...)` on the JS side, returning a Promise.

## Auto-rendered details

::: elysium.webview

## See also

- [WebView](../guides/webview.md)
