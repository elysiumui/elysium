//! Mouse / keyboard / pen / touch dispatch and path-aware hit testing.
//! Phase 1.2 implements; Phase 0 just declares the kinds.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum HitTestMode {
    Path,
    BBox,
    Circle(f32),
    None,
    Alpha(f32),
}
