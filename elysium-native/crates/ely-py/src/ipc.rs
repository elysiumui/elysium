//! Python-facing IPC: starts a UDS server on a background thread,
//! dispatches messages to the matching `Window` (via callback) or to
//! Python handlers registered through `IpcServer.on_message`.

use ely_ipc::{Ack, Handler, IpcServer as RustServer, Message};
use parking_lot::Mutex;
use pyo3::prelude::*;
use pyo3::types::PyDict;
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

    #[getter] fn socket_path(&self) -> String { self.socket_path.display().to_string() }

    fn start(&self) -> PyResult<()> {
        let handlers = self.handlers.clone();
        let handler: Handler = Arc::new(move |msg: Message| -> Ack {
            let kind = match &msg {
                Message::Hello { .. }              => "hello",
                Message::SkinChanged { .. }        => "skin_changed",
                Message::NodePatch { .. }          => "node_patch",
                Message::HookRenamed { .. }        => "hook_renamed",
                Message::PythonModuleReloaded { .. } => "python_module_reloaded",
                Message::SubscribeScene            => "subscribe_scene",
                Message::Disconnect                => "disconnect",
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
            Ack { ok, message: None, reload_ms: None, warnings }
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
        format!("IpcServer(socket='{}', running={running})", self.socket_path.display())
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
        Ok(Self { inner: Mutex::new(client) })
    }

    fn send_skin_changed(&self, py: Python<'_>, path: &str, sha256: &str) -> PyResult<bool> {
        let msg = Message::SkinChanged {
            path: path.to_string(),
            sha256: sha256.to_string(),
        };
        // Drop the GIL during the blocking I/O so the server's
        // connection thread can acquire it to invoke Python callbacks.
        // Without this we deadlock until the read timeout fires.
        let ack = py.allow_threads(|| self.inner.lock().send(&msg))
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(ack.ok)
    }

    fn send_hello(&self, py: Python<'_>, client: &str, token: &str) -> PyResult<bool> {
        let msg = Message::Hello {
            client: client.to_string(),
            token: token.to_string(),
            protocol_version: 1,
        };
        let ack = py.allow_threads(|| self.inner.lock().send(&msg))
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(ack.ok)
    }
}

// Required to receive the message payload's `PyDict` form in Python.
#[allow(dead_code)]
fn _types(_: &Bound<'_, PyDict>) {}
