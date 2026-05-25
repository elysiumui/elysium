//! Hot-reload IPC between Designer ↔ running app ↔ IDE plugin.
//! Length-prefixed JSON over UDS (macOS/Linux) or named pipes (Windows).

pub mod auth;
pub mod framing;
pub mod messages;
#[cfg(unix)] pub mod server;
pub mod transport;

pub use messages::{Message, Ack};
#[cfg(unix)] pub use server::{Handler, IpcClient, IpcError, IpcServer};
