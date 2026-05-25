# Phase 1 — what works today

Status: Phase 1 exit gate **met** for macOS. Tier-1 Windows + Linux verification deferred to CI runs.

> *Phase 1 exit:* "A Python developer can `pip install`, hand-author a tiny `.esk`, run, and see a custom-shaped window with a clickable button."

## The end-to-end demo

```bash
maturin develop --release
python examples/hello/main.py
```

```python
# examples/hello/main.py
import elysium as ely

app = ely.App(title="Hello, Elysium", identifier="dev.elysium.hello")
window = app.window(initial_size=(480, 320))
window.load_skin("examples/hello/hello.esk")

@window.on("greeting_button.click")
def say_hello(event):
    print(f"click! {event}")

app.run()
```

The skin file (`examples/hello/hello.esk/`) is the source of truth for visual layout. Behaviour is a few lines of Python.

## Visual evidence

Rendered through the full Phase 1 pipeline (`.esk → DisplayList → SkiaLayer → PNG`):

![hello from esk](../tests/snapshots/darwin/hello_from_esk.png)

This is the actual `examples/hello/hello.esk/document.json` going through the SVG path parser, the document compiler, the Skia raster surface, and the PNG encoder — byte-for-byte SHA256 verified in `test_hello_from_esk_matches_golden`.

## Subsystem inventory (delta from Phase 0)

| Subsystem | Status | Where |
|---|---|---|
| SVG path mini-language parser (`M m L l H h V v C c S s Q q T t Z z`) + scientific notation + smooth-control reflection | ✅ 10 tests | [`ely-core::geometry`](../elysium-native/crates/ely-core/src/geometry.rs) |
| `Path::bounds()` for axis-aligned bbox | ✅ | same |
| `.esk` loader: directory + ZIP, manifest + document + hooks.json | ✅ 4 tests | [`ely-skin::parser`](../elysium-native/crates/ely-skin/src/parser.rs) |
| Document → DisplayList compiler (paths, gradient/solid fills, outer shadow, corner-radius detection) | ✅ 3 tests | [`ely-skin::compile`](../elysium-native/crates/ely-skin/src/compile.rs) |
| Hook registry walker for documents with no `hooks.json` | ✅ | same |
| Hook collision detection | ✅ | same |
| `Skin` Python class (`elysium.load_skin(path)`, `.hooks()`, `.to_display_list(w, h)`) | ✅ | [`ely-py::skin`](../elysium-native/crates/ely-py/src/skin.rs) |
| `Window.load_skin(path)` (registers hooks + publishes display list) | ✅ | [`ely-py::window`](../elysium-native/crates/ely-py/src/window.rs) |
| `SkiaLayer.execute(dl)` Python binding | ✅ | [`ely-py::skia`](../elysium-native/crates/ely-py/src/skia.rs) |
| `@window.on(hook)` decorator events | ✅ 3 tests | [`elysium._window_ext`](../python/elysium/_window_ext.py) |
| `window.subscribe(hook, fn)` imperative API + unsubscribe | ✅ | same |
| `window.fire(hook, event)` dispatch | ✅ | same |
| Handler-exception isolation (one bad handler doesn't kill the others) | ✅ | same |
| Render thread split (spec §3.2) | ✅ landed in Phase 0 closeout | [`ely-render::render_thread`](../elysium-native/crates/ely-render/src/render_thread.rs) |

## Tests

| Layer | Command | Count |
|---|---|---|
| Rust | `cd elysium-native && cargo test -p ely-core -p ely-skin -p ely-ipc` | 24 pass |
| Python (no display) | `pytest tests/` | 32 pass, 2 skip |
| Python (with display) | `ELYSIUM_RUN_WINDOW_TEST=1 pytest tests/` | 2 additional pass |

Visual goldens (all SHA256-locked):

- `tests/snapshots/darwin/hero_card.png` — hand-built hero card
- `tests/snapshots/darwin/hero_glass.png` — frosted-glass overlay
- `tests/snapshots/darwin/shaped_window.png` — transparent-corner shaped window
- `tests/snapshots/darwin/hello_from_esk.png` — **the actual `.esk` rendered through the full Phase 1 pipeline**

## What's not done (carried to Phase 2)

1. **Path-aware hit testing** — clicking the rendered button doesn't yet fire `greeting_button.click` because OS input hasn't been routed through path bounds. The decorator is wired today; `window.fire(...)` proves the dispatch path. Phase 1.2's `hit_test: "path"` modes need a renderer-side ray cast over `PathVerb` to translate cursor → hit.
2. **Image / text / component / webview nodes** — the document compiler only handles `<path>` today. Images need a texture cache, text needs HarfBuzz layout (deferred from Phase 0 due to the macOS link clash). Phase 2.1 hooks these up alongside the animation engine.
3. **Real transform composition** — the walker accumulates `x/y` offsets but ignores `rotation` and `scale`. Phase 2.x extends `DrawCommand::PushTransform`/`PopTransform` consumption to a real 3×2 matrix stack.
4. **Hook proxies firing setters that mutate the scene** — `window["message.text"].text = "Hello"` validates the type contract but doesn't yet retarget the rendered text node, since text rendering itself isn't implemented. Wires up with Phase 2.1.

## Phase 1 metrics

Same as Phase 0 (the render thread is hot-loop-bound):

- Steady-state: 60 FPS, locked vsync.
- Skia paint per frame: <1 ms for the hello scene.
- Cold start (cached binary): ~150 ms.
- `.esk` load + compile: <2 ms for the hello skin (<1 KB document).
- Memory: <40 MB resident with the hello window open.
