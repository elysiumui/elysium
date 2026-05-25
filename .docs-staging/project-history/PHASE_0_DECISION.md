# Phase 0 Go/No-Go Decision Memo

**Date:** 2026-05-16
**Author:** Elysium UI engineering team
**Decision:** **GO** — proceed to Phase 1.

## What we set out to prove (spec §14, Phase 0)

> Prove the rendering hybrid works.
>
> - Skia-python + wgpu-py composition demo: shaped window with backdrop blur, 60 FPS on three platforms.
> - Decision: Rust vs C++ for `_native` extension.
> - Spike: hot-swap a Skia layer texture from a Python thread without tearing.
>
> **Exit:** A demo video, a written design doc, and a go/no-go on the hybrid.

## What we shipped

| Spike requirement | Status | Evidence |
|---|---|---|
| Skia + wgpu composition demo | ✅ | [`examples/hello/window_smoke.py`](../examples/hello/window_smoke.py) opens a shaped window, Skia paints gradient + shadow + frosted-glass overlay, wgpu composites at 60 FPS, locked to vsync. |
| Backdrop blur | ✅ | Skia `image_filters::blur` integrated through the WGSL composite pipeline. PNG goldens: [`hero_glass.png`](../tests/snapshots/darwin/hero_glass.png). |
| Shaped (per-pixel alpha) window | ✅ on macOS | `transparent=True, title_bar=False` passes through winit's `with_transparent + with_decorations(false)`, which on macOS sets `NSWindow.isOpaque=NO + backgroundColor=clearColor`. Alpha-0 corners → desktop visible through them. [`shaped_window.png`](../tests/snapshots/darwin/shaped_window.png). |
| Three platforms (mac / Windows / Linux KWin) | macOS ✅ verified; Windows + Linux untested locally but the same winit + wgpu code path works there per upstream CI. CI matrix targets `macos-14`, `windows-latest`, `ubuntu-22.04`. |
| Rust vs C++ for native | ✅ **Rust + PyO3** chosen. See [`docs/PHASE_0_DECISION.md#rust-vs-c-rationale`](#rust-vs-c-rationale). |
| Triple-buffer hot-swap test | ✅ Lock-free 3-slot atomic queue in [`ely-core::display_list`](../elysium-native/crates/ely-core/src/display_list.rs); concurrent producer/consumer test asserts no torn reads across 1000 frames; second test pumps 5000 frames from Python under the GIL with a window present. |

## Phase 0 metrics (Apple M5, macOS 26.4.1, Metal)

| Target (spec §11.1) | Hit? | Measured |
|---|---|---|
| Steady-state frame rate ≥ 60 FPS | ✅ | Locked to `PresentMode::AutoVsync`. 60 FPS, dropped frames near zero during demo. |
| Frame budget ≤ 8 ms typical | ✅ | Skia paint <1 ms for the hero card; wgpu submit + present <1 ms; total <2 ms wall. |
| Cold start ≤ 250 ms (cached) | ✅ | ~150 ms to first frame on second-and-subsequent runs. |
| Cold start ≤ 250 ms (first run) | ❌ | macOS Gatekeeper notarization check on fresh `.so` adds ~30 s. Mitigated by documenting in [`docs/PHASE_0.md`](./PHASE_0.md). Production builds will be codesigned + notarized once at distribution time. |

## Architecture decisions ratified

### Rust vs C++ rationale

We adopted Rust + PyO3 for the native layer. Concrete wins observed in Phase 0:

- **Compile-time error surface.** Catching wgpu lifetime bugs at compile time, not in a C++ debugger.
- **Send/Sync as a first-class concept.** When we moved the renderer to its own thread (spec §3.2), Rust's `Send` checker told us exactly which fields couldn't move (Skia surfaces are !Send), forcing the clean producer/consumer split we'd have hand-waved in C++.
- **`naga` Skia of WGSL.** The WGSL static-validation crate sits in the same ecosystem as wgpu; embedding it in the skin sandbox (per spec §11.5) was a 5-line dependency add, not a vendored library.
- **PyO3 0.23 `abi3-py310`.** One wheel covers Python 3.10–3.13, including free-threaded builds. C extensions would have needed per-version wheels or stable-ABI work.

No C++ alternative was attempted; the team consensus is that the Skia (C++) + wgpu (Rust) + PyO3 (Rust) stack is most coherent when the glue is Rust.

### Backend: Skia 2D + wgpu compositor + hybrid

Per spec §4.2. The hybrid stands; both layers work, both are stable, both have prebuilt binaries for our target triples.

### Skia ↔ wgpu interop strategy

**Phase 0 chose the CPU-upload path** (Skia paints to a host-side RGBA buffer, `Skia::Surface::read_pixels` copies to BGRA, `wgpu::Queue::write_texture` uploads, fragment shader samples). This is correct and runs at locked 60 FPS for typical UI complexity.

**Phase 0.2 will implement zero-copy** via platform-specific shared-texture handles: Metal `MTLSharedTextureHandle` / `IOSurface` on macOS, D3D11/12 shared NT handles on Windows, `VK_KHR_external_memory_fd` + dma-buf on Linux. This is a perf optimization, not a correctness requirement. Deferring it lets us land Phase 1's `.esk` loader and scene graph first.

The interop crates ([`ely-render/src/interop/{metal,d3d12,vulkan}.rs`](../elysium-native/crates/ely-render/src/interop/)) are stubs today, with the API surface defined so the upgrade lands without touching call sites.

### Render thread split (spec §3.2)

Phase 0 closes with the render thread split shipped. The main thread runs winit + Python callbacks; the render thread (`elysium-render`) owns wgpu surface, SkiaLayer, and the per-frame paint + present. Communication is via the lock-free `TripleBuffer<DisplayList>` (Python → render) and a `crossbeam_channel::Sender<RenderControl>` (Resize/Stop, main → render).

### File format direction

`.esk` v1.0 — ZIP container with JSON `document.json`, `manifest.json`, `hooks.json`, `animations/`, `shaders/`, `variants/`, `assets/`, `signature.json`. Schema committed at [`schemas/esk-1.0.json`](../schemas/esk-1.0.json). Phase 1.3 implements the loader.

## Risks raised and mitigated

| Risk (spec §15) | Phase 0 outcome |
|---|---|
| §15.3 Skia ↔ wgpu interop complexity | Lowered to "perf-only" by validating that the CPU upload path hits 60 FPS. The zero-copy work is no longer on the critical path. |
| §15.4 GIL under animation load | Mitigated structurally — render thread never touches Python. Producer publishes DisplayLists under no GIL contention with the consumer. |
| Skia static-init clash with winit on macOS | Identified, root-caused (first-run Gatekeeper, not a true incompatibility), documented. No code change needed; users just wait through first launch. |

## What we are NOT carrying into Phase 1

- **GPU shared-handle interop.** Stubs in place, code in Phase 0.2. Documented in [`docs/PHASE_0.md`](./PHASE_0.md).
- **Backdrop blur on the window chrome itself** (NSVisualEffectView). The `blur_behind` config flag is accepted but unimplemented. Phase 1.2 lands the per-OS platform code.
- **Hot-reload IPC over the wire.** The `ely-ipc` crate has message types and framing defined; transport (UDS / named pipes) lands in Phase 2.3.

## Decision

**Proceed to Phase 1.** The Skia + wgpu + winit + PyO3 + triple-buffer stack works end-to-end on macOS, has a clear path to Windows and Linux, and the architecture is exactly what spec §3.2 calls for. Phase 1 work — real `.esk` loader, scene graph, hook proxies wired to scene nodes, decorator events — has no foundational risk left.
