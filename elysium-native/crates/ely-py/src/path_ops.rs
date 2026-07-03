//! Skia path-op binding. Parses two SVG path strings, runs a boolean op,
//! and returns the result as an SVG path string.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
pub fn path_op(d_a: &str, d_b: &str, op: &str) -> PyResult<String> {
    let a = skia_safe::utils::parse_path::from_svg(d_a)
        .ok_or_else(|| PyValueError::new_err("invalid SVG path A"))?;
    let b = skia_safe::utils::parse_path::from_svg(d_b)
        .ok_or_else(|| PyValueError::new_err("invalid SVG path B"))?;
    let path_op = match op {
        "union" => skia_safe::PathOp::Union,
        "intersect" => skia_safe::PathOp::Intersect,
        "subtract" => skia_safe::PathOp::Difference,
        "exclude" => skia_safe::PathOp::XOR,
        _ => return Err(PyValueError::new_err(format!("unknown op: {op}"))),
    };
    let result = a
        .op(&b, path_op)
        .ok_or_else(|| PyValueError::new_err("path op failed"))?;
    Ok(result.to_svg())
}
