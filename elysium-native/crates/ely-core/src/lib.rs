//! ely-core: pure-Rust geometry, display list, color, time primitives.
//!
//! No Python, no GPU, no OS deps. Every other crate in the workspace
//! depends on this one.

pub mod anim;
pub mod color;
pub mod display_list;
pub mod geometry;
pub mod time;

pub use anim::{AnimRegistry, Easing, TransformValue};
pub use color::{Color, ColorSpace};
pub use display_list::{DisplayList, DrawCommand, TripleBuffer};
pub use geometry::{Path, Point, Rect, Transform};
pub use time::FrameClock;
