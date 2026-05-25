//! naga-based static validation of WGSL bundled inside a skin. Reject
//! anything that fails to parse or that uses disallowed features (compute
//! shaders, storage buffers, etc.) before submitting to the GPU.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ShaderError {
    #[error("wgsl parse failed: {0}")]
    Parse(String),
    #[error("disallowed feature: {0}")]
    Disallowed(String),
}

pub fn validate_wgsl(src: &str) -> Result<(), ShaderError> {
    naga::front::wgsl::parse_str(src).map_err(|e| ShaderError::Parse(e.to_string()))?;
    // Phase 1.3 adds the disallowed-feature scan once the policy is settled.
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_trivial_shader() {
        let src = "@vertex fn vs() -> @builtin(position) vec4<f32> { return vec4<f32>(0.0); }";
        assert!(validate_wgsl(src).is_ok());
    }
    #[test]
    fn rejects_garbage() {
        assert!(validate_wgsl("not a shader").is_err());
    }
}
