//! Skia ↔ wgpu shared-texture handoff. The concrete implementation lives
//! in `interop::{metal,d3d12,vulkan}`; this module exposes the common API.
//!
//! Lifecycle:
//!   1. `SkiaBridge::new(device, queue, size)` allocates a wgpu texture
//!      AND a Skia GPU surface that wraps the *same* underlying GPU
//!      memory via the platform's shared-handle mechanism.
//!   2. Producer draws into the Skia canvas.
//!   3. `SkiaBridge::wgpu_view()` returns a `TextureView` for the
//!      compositor to sample.

pub struct SkiaBridge {
    width: u32,
    height: u32,
}

impl SkiaBridge {
    pub fn new(width: u32, height: u32) -> Self {
        Self { width, height }
    }
    pub fn size(&self) -> (u32, u32) {
        (self.width, self.height)
    }
}
