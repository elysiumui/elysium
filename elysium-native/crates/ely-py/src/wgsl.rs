//! Parse-only WGSL validation exposed to Python.
//!
//! Trusted-source validator — unlike the skin sandbox, this does not
//! reject compute shaders or storage buffers. It's the path the internal
//! renderer + Designer use to gate WGSL before handing it to wgpu.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
pub fn validate_wgsl(src: &str) -> PyResult<()> {
    naga::front::wgsl::parse_str(src)
        .map(|_| ())
        .map_err(|e| PyValueError::new_err(format!("wgsl parse failed: {e}")))
}
