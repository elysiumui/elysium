//! Frosted-glass / backdrop-blur effect pass.
//!
//! Pipeline (per deep-dive §2):
//!   1. Two-pass separable Gaussian blur on the backdrop texture
//!      (horizontal then vertical) with `radius` configurable per-layer.
//!   2. Optional tint mix in linear sRGB.
//!   3. Optional noise overlay for the "frosted" granular feel.
//!
//! All passes share a single bind-group layout; uniforms are a 32-byte
//! struct (radius, tint_rgba, noise_intensity, _padding).

pub const SHADER_SRC: &str = include_str!("../shaders/frosted_glass.wgsl");

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct FrostedGlassUniforms {
    pub radius: f32,
    pub tint: [f32; 4],
    pub noise_intensity: f32,
    pub _pad: [f32; 2],
}

impl Default for FrostedGlassUniforms {
    fn default() -> Self {
        Self {
            radius: 16.0,
            tint: [1.0, 1.0, 1.0, 0.1],
            noise_intensity: 0.03,
            _pad: [0.0; 2],
        }
    }
}
