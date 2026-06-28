use std::sync::Arc;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use ely_platform::window::{
    ely_core_hook_stub::{Hook, HookKind},
    WindowHandle,
};

#[pyclass(name = "HookProxy", unsendable)]
pub struct PyHookProxy {
    window: Arc<WindowHandle>,
    hook: Hook,
}

impl PyHookProxy {
    pub(crate) fn new(window: Arc<WindowHandle>, hook: Hook) -> Self {
        Self { window, hook }
    }
}

#[pymethods]
impl PyHookProxy {
    #[getter]
    fn name(&self) -> &str {
        &self.hook.name
    }
    #[getter]
    fn kind(&self) -> String {
        format!("{:?}", self.hook.kind)
    }

    #[setter]
    fn set_text(&self, value: &str) -> PyResult<()> {
        match self.hook.kind {
            HookKind::Text => {
                self.window.scene_mut().set_text(self.hook.node_id, value);
                Ok(())
            }
            ref other => Err(PyValueError::new_err(format!(
                "Hook '{}' is a {other:?}, not a text hook",
                self.hook.name
            ))),
        }
    }

    #[setter]
    fn set_value(&self, value: f64) -> PyResult<()> {
        match self.hook.kind {
            HookKind::Value { min, max } => {
                if value < min || value > max {
                    return Err(PyValueError::new_err(format!(
                        "Value {value} out of range [{min}, {max}] for hook '{}'",
                        self.hook.name
                    )));
                }
                self.window.scene_mut().set_value(self.hook.node_id, value);
                Ok(())
            }
            ref other => Err(PyValueError::new_err(format!(
                "Hook '{}' is a {other:?}, not a value hook",
                self.hook.name
            ))),
        }
    }

    #[setter]
    fn set_state(&self, state: &str) -> PyResult<()> {
        match &self.hook.kind {
            HookKind::State { states } => {
                if !states.iter().any(|s| s == state) {
                    return Err(PyValueError::new_err(format!(
                        "State '{state}' not declared. Valid: {states:?}"
                    )));
                }
                self.window
                    .scene_mut()
                    .transition_state(self.hook.node_id, state);
                Ok(())
            }
            other => Err(PyValueError::new_err(format!(
                "Hook '{}' is a {other:?}, not a state hook",
                self.hook.name
            ))),
        }
    }
}
