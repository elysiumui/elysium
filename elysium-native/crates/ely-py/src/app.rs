use std::sync::Arc;

use parking_lot::Mutex;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::window::PyWindow;
use ely_platform::event_loop::{AppHandle, AppLoop, Config};

/// Bound to the OS main thread in practice (winit + NSApplication need it),
/// but we don't mark `unsendable` because the inner state is Send+Sync and
/// we need `app.quit()` to be callable from worker threads / IPC threads.
#[pyclass(name = "App")]
pub struct PyApp {
    inner: Arc<Mutex<AppLoop>>,
    /// Cached lock-free handle so `quit()` from a worker thread doesn't
    /// race the event-loop thread holding the inner mutex during `run()`.
    handle: AppHandle,
    identifier: String,
}

#[pymethods]
impl PyApp {
    #[new]
    #[pyo3(signature = (
        title,
        identifier,
        icon = None,
        theme = "dark",
        log_level = "info",
        enable_hot_reload = false,
    ))]
    fn new(
        title: &str,
        identifier: &str,
        icon: Option<&str>,
        theme: &str,
        log_level: &str,
        enable_hot_reload: bool,
    ) -> PyResult<Self> {
        // On macOS, Python-spawned processes default to a transient
        // activation policy. Without `setActivationPolicy: Regular`, the
        // window renders but the OS won't deliver normal mouse / key
        // events. Must run *before* any window is created.
        #[cfg(target_os = "macos")]
        unsafe {
            use objc2::runtime::{AnyObject, Bool};
            use objc2::{class, msg_send};
            let app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
            let _: Bool = msg_send![app, setActivationPolicy: 0i64]; // .regular
            let _: () = msg_send![app, activateIgnoringOtherApps: true];
        }

        let inner = AppLoop::new(Config {
            title: title.into(),
            identifier: identifier.into(),
            icon: icon.map(Into::into),
            theme: theme.into(),
            log_level: log_level.into(),
            enable_hot_reload,
        })
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let handle = inner.handle();
        Ok(Self {
            inner: Arc::new(Mutex::new(inner)),
            handle,
            identifier: identifier.into(),
        })
    }

    #[pyo3(signature = (**kwargs))]
    fn window(&self, py: Python<'_>, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<PyWindow> {
        let cfg = crate::window::config_from_kwargs(py, kwargs)?;
        let handle = self
            .inner
            .lock()
            .create_window(cfg)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(PyWindow::wrap(handle))
    }

    fn run(&self, py: Python<'_>) -> PyResult<()> {
        let inner = self.inner.clone();
        py.allow_threads(|| inner.lock().run())
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }

    fn quit(&self) {
        // Lock-free; safe to call from any thread, including while
        // another thread holds the inner mutex inside `run()`.
        self.handle.quit();
    }

    #[getter]
    fn identifier(&self) -> &str {
        &self.identifier
    }
}
