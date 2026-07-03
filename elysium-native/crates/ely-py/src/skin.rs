//! Python-facing `.esk` loader. `elysium.load_skin(path)` returns a `Skin`
//! that exposes the parsed manifest, hooks, and a `to_display_list(w, h)`
//! method that compiles the document for the renderer.

use crate::display_list::PyDisplayList;
use ely_skin::{compile, load, Skin};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyclass(name = "Skin", module = "elysium")]
pub struct PySkin {
    inner: Skin,
}

#[pymethods]
impl PySkin {
    #[getter]
    fn id(&self) -> &str {
        &self.inner.manifest.id
    }
    #[getter]
    fn name(&self) -> &str {
        &self.inner.manifest.name
    }
    #[getter]
    fn version(&self) -> &str {
        &self.inner.manifest.version
    }
    #[getter]
    fn schema_version(&self) -> &str {
        &self.inner.manifest.schema_version
    }
    /// "application" or "component". Application skins own a window;
    /// component skins are designed to be composed into another skin's
    /// DisplayList. The Designer uses this to suppress App-Window
    /// chrome for component skins; runtime hosts can use it to reject
    /// misuse (e.g. trying to load a component as a top-level window).
    #[getter]
    fn kind(&self) -> &'static str {
        match self.inner.manifest.kind {
            ely_skin::SkinKind::Application => "application",
            ely_skin::SkinKind::Component => "component",
        }
    }

    /// `hooks` returns a {hook_name: {type, ...}} dict for introspection.
    fn hooks<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new(py);
        for (name, hook) in self.inner.hooks.iter() {
            let entry = PyDict::new(py);
            let kind_label = match &hook.kind {
                ely_skin::HookKind::Event { .. } => "event",
                ely_skin::HookKind::Text => "text",
                ely_skin::HookKind::Image => "image",
                ely_skin::HookKind::Value { .. } => "value",
                ely_skin::HookKind::State { .. } => "state",
                ely_skin::HookKind::Slot => "slot",
                ely_skin::HookKind::Style => "style",
            };
            entry.set_item("type", kind_label)?;
            if let ely_skin::HookKind::Event { events } = &hook.kind {
                entry.set_item("events", events.clone())?;
            }
            if let ely_skin::HookKind::State { states } = &hook.kind {
                entry.set_item("states", states.clone())?;
            }
            dict.set_item(name, entry)?;
        }
        Ok(dict)
    }

    /// Compile the skin's document tree to a DisplayList at the given size.
    fn to_display_list(&self, surface_w: u32, surface_h: u32) -> PyDisplayList {
        PyDisplayList {
            inner: compile(&self.inner.document, surface_w, surface_h),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "Skin(id='{}', name='{}', version='{}', hooks={})",
            self.inner.manifest.id,
            self.inner.manifest.name,
            self.inner.manifest.version,
            self.inner.hooks.len(),
        )
    }
}

#[pyfunction]
pub fn load_skin(path: &str) -> PyResult<PySkin> {
    let skin = load(path).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(PySkin { inner: skin })
}
