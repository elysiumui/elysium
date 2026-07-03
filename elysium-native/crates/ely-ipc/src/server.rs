//! Phase 2.3 hot-reload IPC transport — synchronous UDS server on a
//! background OS thread. Each incoming connection runs on its own
//! per-client thread; messages are length-prefixed JSON.
//!
//! This is the minimum viable transport from spec §3.4 + deep-dive §3.
//! tokio + async was deliberately not used: the IPC traffic is
//! request/response (skin-changed → ack) at file-save frequency, not
//! a hot stream, and skipping tokio keeps the dependency surface tight.

use crate::messages::{Ack, Message};
use parking_lot::Mutex;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::JoinHandle;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum IpcError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("json: {0}")]
    Json(#[from] serde_json::Error),
    #[error("frame too large: {0} > 16 MiB")]
    FrameTooLarge(u32),
    #[error("auth failed")]
    AuthFailed,
}

/// Handler invoked for every received message. Returns the ack to send
/// back. Runs on the connection's worker thread.
pub type Handler = Arc<dyn Fn(Message) -> Ack + Send + Sync + 'static>;

/// A running IPC server. Drop it (or call `stop()`) to shut down.
pub struct IpcServer {
    socket_path: PathBuf,
    stop_flag: Arc<AtomicBool>,
    listener_thread: Mutex<Option<JoinHandle<()>>>,
}

impl IpcServer {
    /// Start a UDS server at `socket_path`. The file is created with
    /// mode 0600 and removed when the server stops.
    pub fn start(socket_path: PathBuf, handler: Handler) -> Result<Self, IpcError> {
        // Best-effort cleanup of a stale socket from a previous run.
        let _ = std::fs::remove_file(&socket_path);
        if let Some(parent) = socket_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let listener = UnixListener::bind(&socket_path)?;
        listener.set_nonblocking(true)?;
        // Restrict access to the current user.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&socket_path)?.permissions();
            perms.set_mode(0o600);
            std::fs::set_permissions(&socket_path, perms)?;
        }

        let stop_flag = Arc::new(AtomicBool::new(false));
        let stop_clone = stop_flag.clone();
        let handler_clone = handler.clone();

        let jh = std::thread::Builder::new()
            .name("elysium-ipc-accept".into())
            .spawn(move || {
                while !stop_clone.load(Ordering::Acquire) {
                    match listener.accept() {
                        Ok((stream, _addr)) => {
                            let h = handler_clone.clone();
                            std::thread::Builder::new()
                                .name("elysium-ipc-conn".into())
                                .spawn(move || {
                                    if let Err(e) = handle_connection(stream, h) {
                                        tracing::warn!(?e, "ipc connection closed with error");
                                    }
                                })
                                .ok();
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(std::time::Duration::from_millis(25));
                        }
                        Err(e) => {
                            tracing::warn!(?e, "ipc accept failed");
                            break;
                        }
                    }
                }
            })
            .expect("spawn ipc accept thread");

        Ok(Self {
            socket_path,
            stop_flag,
            listener_thread: Mutex::new(Some(jh)),
        })
    }

    pub fn stop(&self) {
        self.stop_flag.store(true, Ordering::Release);
        if let Some(jh) = self.listener_thread.lock().take() {
            let _ = jh.join();
        }
        let _ = std::fs::remove_file(&self.socket_path);
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }
}

impl Drop for IpcServer {
    fn drop(&mut self) {
        if !self.stop_flag.load(Ordering::Acquire) {
            self.stop();
        }
    }
}

fn handle_connection(mut stream: UnixStream, handler: Handler) -> Result<(), IpcError> {
    // Accepted streams inherit the listener's nonblocking flag on UNIX;
    // we want blocking I/O on the per-connection thread.
    stream.set_nonblocking(false)?;
    stream.set_read_timeout(Some(std::time::Duration::from_secs(30)))?;
    loop {
        let mut len_buf = [0u8; 4];
        match stream.read_exact(&mut len_buf) {
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(()),
            Err(e) => return Err(e.into()),
        };
        let len = u32::from_be_bytes(len_buf);
        if len > 16 * 1024 * 1024 {
            return Err(IpcError::FrameTooLarge(len));
        }
        let mut body = vec![0u8; len as usize];
        stream.read_exact(&mut body)?;
        let msg: Message = serde_json::from_slice(&body)?;
        let ack = handler(msg);
        let ack_bytes = serde_json::to_vec(&ack)?;
        let ack_len = (ack_bytes.len() as u32).to_be_bytes();
        stream.write_all(&ack_len)?;
        stream.write_all(&ack_bytes)?;
        stream.flush()?;
    }
}

// ---------------------------------------------------------------------------
// Client.
// ---------------------------------------------------------------------------

pub struct IpcClient {
    stream: UnixStream,
}

impl IpcClient {
    pub fn connect(socket_path: impl AsRef<Path>) -> Result<Self, IpcError> {
        let stream = UnixStream::connect(socket_path)?;
        stream.set_read_timeout(Some(std::time::Duration::from_secs(10)))?;
        Ok(Self { stream })
    }

    pub fn send(&mut self, msg: &Message) -> Result<Ack, IpcError> {
        let body = serde_json::to_vec(msg)?;
        let len = (body.len() as u32).to_be_bytes();
        self.stream.write_all(&len)?;
        self.stream.write_all(&body)?;
        self.stream.flush()?;

        let mut len_buf = [0u8; 4];
        self.stream.read_exact(&mut len_buf)?;
        let ack_len = u32::from_be_bytes(len_buf);
        if ack_len > 16 * 1024 * 1024 {
            return Err(IpcError::FrameTooLarge(ack_len));
        }
        let mut body = vec![0u8; ack_len as usize];
        self.stream.read_exact(&mut body)?;
        Ok(serde_json::from_slice(&body)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::messages::Message;

    #[test]
    fn ping_pong_round_trip() {
        let sock = std::env::temp_dir().join(format!("ely-ipc-test-{}.sock", std::process::id()));
        let handler: Handler = Arc::new(|msg| match msg {
            Message::Hello { client, .. } => Ack {
                ok: true,
                message: Some(format!("hello {client}")),
                reload_ms: None,
                warnings: vec![],
            },
            _ => Ack {
                ok: true,
                message: None,
                reload_ms: None,
                warnings: vec![],
            },
        });
        let server = IpcServer::start(sock.clone(), handler).unwrap();

        // Give the listener a moment to bind.
        std::thread::sleep(std::time::Duration::from_millis(50));

        let mut client = IpcClient::connect(&sock).unwrap();
        let ack = client
            .send(&Message::Hello {
                client: "test".into(),
                token: "t".into(),
                protocol_version: 1,
            })
            .unwrap();
        assert!(ack.ok);
        assert_eq!(ack.message.as_deref(), Some("hello test"));

        server.stop();
    }

    #[test]
    fn server_cleans_up_socket_on_drop() {
        let sock = std::env::temp_dir().join(format!("ely-ipc-drop-{}.sock", std::process::id()));
        {
            let handler: Handler = Arc::new(|_| Ack {
                ok: true,
                message: None,
                reload_ms: None,
                warnings: vec![],
            });
            let _server = IpcServer::start(sock.clone(), handler).unwrap();
            assert!(sock.exists());
        }
        // Give the listener time to clean up.
        std::thread::sleep(std::time::Duration::from_millis(100));
        assert!(!sock.exists(), "socket file should be removed on drop");
    }
}
