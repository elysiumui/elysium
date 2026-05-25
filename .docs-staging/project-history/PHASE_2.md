# Phase 2 — what works today

Phase 2 is **substantially complete** for everything that doesn't require building a standalone visual editor application. The Designer GUI app (2.4) remains the one large unfinished item, clearly delineated below.

## What's real, what's tested

| Spec section | Status | Surface |
|---|---|---|
| **2.1 Animation engine** | ✅ real | `elysium.anim` — `Tween`, `Timeline`, `StateMachine`, `Spring`, `SpringValue`, `AnimationClock`, `run_animation_thread`, 11 built-in easings, `cubic_bezier`, `spring()` solver |
| **2.2 Reactive layer** | ✅ real | `elysium.reactive` — `signal`, `computed`, `effect` with fine-grained dependency tracking, dedup on equal writes, dispose-to-unsubscribe |
| **2.3 Hot-reload IPC transport** | ✅ real | `ely_ipc::server::IpcServer` (UDS, length-prefixed JSON, mode 0600 socket, multi-subscriber dispatch); Python `IpcServer`/`IpcClient` with `on_message(kind, fn)` callback registration. GIL is released during blocking I/O so callbacks can run from the server thread. |
| **2.5 Component library** (starter) | ✅ 7/30 | `elysium.components` — `Button`, `IconCloseButton`, `Label`, `Card`, `Toggle`, `Slider`, `Stack`. Each is a `dataclass(Component)` with `paint(dl, state)` + `hit_test(mx, my)`. |
| **Text rendering** | ✅ real | `DrawCommand::DrawText` + `SkiaLayer::draw_text` + `measure_text`; Python `DisplayList.draw_text(text, x, y, size, color)`, `SkiaLayer.draw_text/measure_text`. Default typeface via platform `FontMgr`. |
| **Raster-asset pipeline** | ✅ real | `TextureCache` decodes each path once. `SkiaLayer.draw_image_file / draw_image_file_transformed / draw_image_file_region`. Async decode via `TextureCache::preload_async`. Decode-count + hit-count instrumentation. |
| **2.4 Designer GUI app** | ❌ **not started** | The standalone visual editor is genuinely weeks of work and was always the largest Phase 2.x item. The framework now supports everything it needs (skin load, hook registry, IPC, components), but the Qt-style canvas + tool palette is out of scope for this leg. |
| Async texture decode worker (Rust thread) | ✅ | `TextureCache::preload_async` returns a `JoinHandle`. Render thread can use `try_get` to check readiness each frame. |
| CLI `elysium dev <skin>` file-watcher | ❌ | The IPC server + watcher protocol exist; `notify` integration is one small Python file away. Stub left for the next leg. |

## Tests

| Layer | Command | Result |
|---|---|---|
| Rust | `cd elysium-native && cargo test --workspace` excluding `ely-py` cdylib | 26 pass (ely-core 15, ely-skin 9, ely-ipc 2) |
| Python | `pytest tests/` | **67 pass**, 3 skipped (display-gated) |
| Python with display | `ELYSIUM_RUN_WINDOW_TEST=1 pytest tests/` | +3 pass |

24 new Phase 2 tests cover:
- 7 animation primitives (tween interpolation, easings, ping-pong, tuple values, state machine, spring convergence, clock GC)
- 5 reactive primitives (signal notification, dedup, computed memoization + propagation, dispose, effect isolation)
- 3 raster pipeline (cache decode-once + hit-many counters, preload, transform/region commands)
- 7 components (button paint + hit-test + state-based fill, icon close hit-test, toggle change-callback, slider clamping, stack layout)
- 2 IPC round-trip (hello → ack, multi-subscriber skin-changed dispatch)

## The butterfly demo, rewired

`examples/butterfly/main.py` is now a **framework showcase**, not a hand-rolled animation loop. Every block of work happens through a framework primitive:

```python
# Reactive cells for cursor + drag state.
hover_butterfly = reactive.signal(False)
hover_close     = reactive.signal(False)
window_pos      = reactive.signal((200, 200))
reactive.effect(lambda: win.set_outer_position(*window_pos()))

# One Tween, ping-pong, ease-in-out-sine = the entire flap animation.
clock = anim.AnimationClock()
flap = reactive.signal(1.0)
anim.Tween(0.0, 1.0,
    duration=duration/2.0, easing="ease-in-out-sine", loop="ping_pong",
    on_update=lambda v: flap.set(v)).start(clock)

# Close button is a real component that hit-tests itself.
close_btn = IconCloseButton(x=..., y=..., w=28, h=28,
    on_click=lambda: (state.update(running=False), app.quit()))

# 60 Hz frame loop: poll cursor, update state, build DisplayList, publish.
anim.run_animation_thread(clock, on_frame, target_hz=60.0)
```

What used to be ~50 lines of manual cosine math + close-button geometry is now ~12 lines of `Tween` + `IconCloseButton` declarations. The framework absorbed the boilerplate.

## Photographic rendering

Procedural geometry — Skia paths, gradients, strokes — cannot pixel-replicate a photograph. That isn't a limitation I can engineer around; gradient stops cannot represent the millions of subpixel scales catching light on a real butterfly's wings. **The framework's raster-asset pipeline is the right path for photographic content**, and it's complete:

```bash
python examples/butterfly/main.py --image=/path/to/butterfly.png
```

The framework decodes the image once via `TextureCache`, re-draws it each frame from the cached `skia_safe::Image`, and animates around it (drag, hover-revealed close, flap as a horizontal squash). The wing-flap, hover, and drag interactions are identical whether the texture is procedural or photographic.

For per-wing rotation on a single image asset, an atlas with `left_wing`, `right_wing`, and `body` regions composes through `dl.draw_image_file_region(...)` — three layers, each animated by an independent `Tween` rotating around its inner edge.

## What's deferred to Phase 3

1. **Standalone Designer GUI app (spec §2.4).** Genuinely multi-week. The framework now supports everything it needs.
2. **CLI `elysium dev <skin>` file watcher.** IPC server + protocol exist; one `notify` integration + Python script remain.
3. **Hot-reload Windows + Linux transports.** Today UDS-only (macOS/Linux). Windows named pipes are scaffolded in `ely-ipc/src/transport.rs` but not wired.
4. **Path-aware OS hit-testing** (clicks pass through transparent corners to the desktop).
5. **`blur_behind` window-chrome blur** (NSVisualEffectView / acrylic / KWin blur).
6. **30-component library** (currently 7 of 30).
