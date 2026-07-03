//! Cross-platform windowing & input via winit, with shaped/transparent
//! window extensions per OS. Phase 0.3 fills in the platform/* modules.

pub mod a11y;
pub mod a11y_bridge;
pub mod event_loop;
pub mod input;
pub mod window;

mod platform {
    #[cfg(target_os = "linux")]
    pub mod linux;
    #[cfg(target_os = "macos")]
    pub mod macos;
    #[cfg(target_os = "windows")]
    pub mod windows;
}

pub use event_loop::{AppLoop, Config};
pub use window::{WindowConfig, WindowHandle};
