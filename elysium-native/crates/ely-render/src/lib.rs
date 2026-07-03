//! Skia (path/text) + wgpu (compositor / effects / present) hybrid pipeline.
//!
//! **Phase 0 status:** wgpu surface + clear-to-color works end-to-end on
//! macOS/Windows/Linux. Skia is not yet wired through — the Skia↔wgpu
//! shared-texture handoff (`interop/*`) is the planned Phase 0.2 work and
//! lands in a follow-up.

pub mod compositor;
pub mod compute_pbr;
pub mod damage;
pub mod effects;
pub mod render_thread;
pub mod skia_bridge;
pub mod skia_layer;
pub mod surface;
pub mod texture_cache;

pub mod interop {
    #[cfg(target_os = "windows")]
    pub mod d3d12;
    #[cfg(target_os = "macos")]
    pub mod metal;
    #[cfg(target_os = "linux")]
    pub mod vulkan;
}

pub use compositor::Compositor;
pub use render_thread::{spawn_render_thread, RenderControl};
pub use skia_bridge::SkiaBridge;
pub use skia_layer::SkiaLayer;
pub use skia_layer::{font_vmetrics, measure_text_run, text_caret_x, text_hit_index};
pub use skia_layer::{register_ui_font_from_file, set_ui_font_family};
pub use surface::{SurfaceRenderer, SurfaceTarget};
pub use texture_cache::TextureCache;
