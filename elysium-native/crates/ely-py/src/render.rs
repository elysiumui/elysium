use std::cell::Cell;

use pyo3::prelude::*;

use crate::errors::CanvasExpired;

/// Direct-paint escape hatch (`elysium.Component.paint(canvas, bounds)`).
/// The pointer is only valid for the duration of a single paint() call;
/// any reference held past that scope raises `CanvasExpired` rather than
/// crashing the process.
#[pyclass(name = "Canvas", unsendable)]
pub struct PyCanvas {
    live: Cell<bool>,
}

#[allow(dead_code)] // constructed by the deferred live-canvas path
impl PyCanvas {
    pub(crate) fn new() -> Self {
        Self {
            live: Cell::new(true),
        }
    }
    pub(crate) fn invalidate(&self) {
        self.live.set(false);
    }
    fn check(&self) -> PyResult<()> {
        if !self.live.get() {
            return Err(CanvasExpired::new_err(
                "Canvas used outside paint() scope. Don't store canvas references.",
            ));
        }
        Ok(())
    }
}

#[pymethods]
impl PyCanvas {
    fn clear(&self, _color: &str) -> PyResult<()> {
        self.check()
    }
    fn stroke_path(&self, _path: &PyPath, _color: &str, _width: f32) -> PyResult<()> {
        self.check()
    }
    fn fill_path(&self, _path: &PyPath, _color: &str) -> PyResult<()> {
        self.check()
    }
}

#[pyclass(name = "Path", unsendable)]
pub struct PyPath {
    pub(crate) source: String,
}

#[pymethods]
impl PyPath {
    #[new]
    fn new() -> Self {
        Self {
            source: String::new(),
        }
    }

    #[staticmethod]
    fn from_svg(d: &str) -> Self {
        Self {
            source: d.to_string(),
        }
    }

    fn move_to(&mut self, x: f32, y: f32) {
        self.source.push_str(&format!("M {x} {y} "));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.source.push_str(&format!("L {x} {y} "));
    }
    fn close(&mut self) {
        self.source.push_str("Z ");
    }

    #[getter]
    fn source(&self) -> &str {
        &self.source
    }
}
