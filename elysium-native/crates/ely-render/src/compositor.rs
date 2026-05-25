//! wgpu compositor: samples Skia-rendered layers, applies effect passes
//! (frosted glass, shadows, grain), presents to swapchain.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum CompositorError {
    #[error("wgpu adapter unavailable")]
    NoAdapter,
    #[error("surface configuration failed: {0}")]
    Surface(String),
}

pub struct Compositor {
    // Phase 0.2 will hold wgpu::Instance, Device, Queue, SurfaceConfiguration,
    // bind groups for effect uniforms, and a present pipeline.
    _placeholder: (),
}

impl Compositor {
    pub fn headless() -> Result<Self, CompositorError> {
        Ok(Self { _placeholder: () })
    }
}
