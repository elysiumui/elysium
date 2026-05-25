//! 4-byte big-endian length prefix + JSON body. Phase 2.3 wires into
//! tokio_util::codec; this module exposes only the on-wire constants.

pub const MAX_FRAME: u32 = 16 * 1024 * 1024;
