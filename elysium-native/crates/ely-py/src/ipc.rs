//! Python-facing IPC.
//!
//! On Unix the real implementation runs over a Unix domain socket
//! (see `ely_ipc::IpcServer`). On Windows the underlying transport
//! isn't ported yet (UDS exists in Win10+ but `ely_ipc` was authored
//! Unix-only), so we expose stub classes that raise
//! `NotImplementedError` at construction time. The Python module
//! still exports `IpcServer` and `IpcClient` so consumers don't need
//! to platform-fork their `from elysium._native import _native as _n`
//! lines; they just have to handle the runtime error.

use pyo3::prelude::*;
use pyo3::types::PyDict;

#[cfg(unix)]
mod unix_impl {
    use super::*;
    use ely_ipc::{Ack, Handler, IpcServer as RustServer, Message};
    use parking_lot::Mutex;
    use std::path::PathBuf;
    use std::sync::Arc;

    #[pyclass(name = "IpcServer", module = "elysium")]
    pub struct PyIpcServer {
        socket_path: PathBuf,
        server: Mutex<Option<RustServer>>,
        /// Handlers per-message-kind (e.g., "skin_changed").
        handlers: Arc<Mutex<Vec<(String, PyObject)>>>,
    }

    #[pymethods]
    impl PyIpcServer {
        #[new]
        fn new(socket_path: &str) -> Self {
            Self {
                socket_path: PathBuf::from(socket_path),
                server: Mutex::new(None),
                handlers: Arc::new(Mutex::new(Vec::new())),
            }
        }

        #[getter]
        fn socket_path(&self) -> String {
            self.socket_path.display().to_string()
        }

        fn start(&self) -> PyResult<()> {
            let handlers = self.handlers.clone();
            let handler: Handler = Arc::new(move |msg: Message| -> Ack {
                let kind = match &msg {
                    Message::Hello { .. } => "hello",
                    Message::SkinChanged { .. } => "skin_changed",
                    Message::NodePatch { .. } => "node_patch",
                    Message::HookRenamed { .. } => "hook_renamed",
                    Message::PythonModuleReloaded { .. } => "python_module_reloaded",
                    Message::SubscribeScene => "subscribe_scene",
                    Message::Disconnect => "disconnect",
                };
                // Invoke Python handlers under the GIL. Errors are caught
                // and surfaced as a non-ok Ack.
                let mut warnings: Vec<String> = Vec::new();
                let mut ok = true;
                Python::with_gil(|py| {
                    let snapshot: Vec<PyObject> = handlers
                        .lock()
                        .iter()
                        .filter(|(k, _)| k == kind)
                        .map(|(_, fn_obj)| fn_obj.clone_ref(py))
                        .collect();
                    let payload = match serde_json::to_string(&msg) {
                        Ok(s) => s,
                        Err(e) => {
                            warnings.push(format!("serialize: {e}"));
                            return;
                        }
                    };
                    for fn_obj in snapshot {
                        if let Err(e) = fn_obj.call1(py, (payload.as_str(),)) {
                            ok = false;
                            warnings.push(format!("handler raised: {e}"));
                        }
                    }
                });
                Ack {
                    ok,
                    message: None,
                    reload_ms: None,
                    warnings,
                }
            });
            let server = RustServer::start(self.socket_path.clone(), handler)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            *self.server.lock() = Some(server);
            Ok(())
        }

        fn stop(&self) -> PyResult<()> {
            if let Some(server) = self.server.lock().take() {
                server.stop();
            }
            Ok(())
        }

        /// Register a Python callback for a message kind. The callback
        /// receives the JSON-encoded message body. Multiple handlers per
        /// kind are supported.
        fn on_message(&self, kind: &str, callback: PyObject) {
            self.handlers.lock().push((kind.to_string(), callback));
        }

        fn __repr__(&self) -> String {
            let running = self.server.lock().is_some();
            format!(
                "IpcServer(socket='{}', running={running})",
                self.socket_path.display()
            )
        }
    }

    #[pyclass(name = "IpcClient", module = "elysium")]
    pub struct PyIpcClient {
        inner: Mutex<ely_ipc::IpcClient>,
    }

    #[pymethods]
    impl PyIpcClient {
        #[new]
        fn new(socket_path: &str) -> PyResult<Self> {
            let client = ely_ipc::IpcClient::connect(socket_path)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            Ok(Self {
                inner: Mutex::new(client),
            })
        }

        fn send_skin_changed(&self, py: Python<'_>, path: &str, sha256: &str) -> PyResult<bool> {
            let msg = Message::SkinChanged {
                path: path.to_string(),
                sha256: sha256.to_string(),
            };
            // Drop the GIL during the blocking I/O so the server's
            // connection thread can acquire it to invoke Python callbacks.
            // Without this we deadlock until the read timeout fires.
            let ack = py
                .allow_threads(|| self.inner.lock().send(&msg))
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            Ok(ack.ok)
        }

        fn send_hello(&self, py: Python<'_>, client: &str, token: &str) -> PyResult<bool> {
            let msg = Message::Hello {
                client: client.to_string(),
                token: token.to_string(),
                protocol_version: 1,
            };
            let ack = py
                .allow_threads(|| self.inner.lock().send(&msg))
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            Ok(ack.ok)
        }
    }
}

#[cfg(not(unix))]
mod stub_impl {
    use super::*;

    fn unsupported() -> PyErr {
        pyo3::exceptions::PyNotImplementedError::new_err(
            "elysium IPC is currently Unix-only — the Windows transport \
             (named-pipes / AF_UNIX in Win10+) hasn't been wired into \
             ely_ipc yet. Hot-reload over IPC is a no-op on Windows; \
             the Designer + examples still work, just without live IPC.",
        )
    }

    #[pyclass(name = "IpcServer", module = "elysium")]
    pub struct PyIpcServer;

    #[pymethods]
    impl PyIpcServer {
        #[new]
        fn new(_socket_path: &str) -> PyResult<Self> {
            Err(unsupported())
        }
        #[getter]
        fn socket_path(&self) -> String {
            String::new()
        }
        fn start(&self) -> PyResult<()> {
            Err(unsupported())
        }
        fn stop(&self) -> PyResult<()> {
            Err(unsupported())
        }
        fn on_message(&self, _kind: &str, _callback: PyObject) {}
        fn __repr__(&self) -> String {
            "IpcServer(stub: Windows unsupported)".into()
        }
    }

    #[pyclass(name = "IpcClient", module = "elysium")]
    pub struct PyIpcClient;

    #[pymethods]
    impl PyIpcClient {
        #[new]
        fn new(_socket_path: &str) -> PyResult<Self> {
            Err(unsupported())
        }
        fn send_skin_changed(&self, _py: Python<'_>, _path: &str, _sha256: &str) -> PyResult<bool> {
            Err(unsupported())
        }
        fn send_hello(&self, _py: Python<'_>, _client: &str, _token: &str) -> PyResult<bool> {
            Err(unsupported())
        }
    }
}

#[cfg(not(unix))]
pub use stub_impl::{PyIpcClient, PyIpcServer};
#[cfg(unix)]
pub use unix_impl::{PyIpcClient, PyIpcServer};

// Required to receive the message payload's `PyDict` form in Python.
#[allow(dead_code)]
fn _types(_: &Bound<'_, PyDict>) {}
