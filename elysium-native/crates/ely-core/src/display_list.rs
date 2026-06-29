//! Lock-free triple-buffered display list.
//!
//! Producer (Python main thread) writes into slot N; consumer (render thread)
//! atomically swaps to slot M to read the most recent fully-written frame.
//! Adapted from the standard SPSC triple-buffer pattern (Acquire/Release on
//! a single atomic state word).
//!
//! State word encoding (8 bits, only low 4 used):
//!   bits 0-1: index of the latest "ready" slot (most recently published)
//!   bit  2  : "new" flag — set by producer on publish, cleared by consumer on acquire
//!   bits 3-4: producer's current write slot
//!
//! The consumer slot is implicit: whichever slot the consumer is currently
//! holding. The producer never picks the consumer's slot; the consumer never
//! picks the producer's slot. The remaining slot is the rotating "back" slot.

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU8, Ordering};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DisplayList {
    /// Opaque draw commands. Layered crates fill this in.
    pub commands: Vec<DrawCommand>,
    pub frame_index: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum DrawCommand {
    Clear {
        color: [f32; 4],
    },
    GradientCard {
        bounds: [f32; 4],
        corner_radius: f32,
        start_color: [u8; 4],
        end_color: [u8; 4],
        shadow_blur: f32,
        shadow_offset: [f32; 2],
        shadow_color: [u8; 4],
    },
    FrostedPanel {
        bounds: [f32; 4],
        corner_radius: f32,
        blur_sigma: f32,
        tint: [u8; 4],
        border: Option<[u8; 4]>,
    },
    FilledCircle {
        cx: f32,
        cy: f32,
        r: f32,
        color: [u8; 4],
    },
    PushTransform {
        tx: f32,
        ty: f32,
        sx: f32,
        sy: f32,
        rotation: f32,
        /// Render-thread animation slot. When `Some(id)`, the live tween
        /// for that slot is composed on top of the static values before
        /// the matrix is applied. See `ely_core::AnimRegistry`.
        anim_slot: Option<u32>,
    },
    PopTransform,

    /// Intersect the canvas clip with a rectangle (in the current
    /// transform space) until the matching `PopClip`. Saves canvas state so
    /// `PopClip` restores both the clip and any nested transforms. Used by
    /// `ScrollView` to keep scrolled content inside its viewport.
    PushClip {
        x: f32,
        y: f32,
        w: f32,
        h: f32,
    },
    PopClip,

    // Generic SVG-path commands. Used by the butterfly demo and any
    // future custom paint built up from Python.
    FillPath {
        d: String,
        color: [u8; 4],
    },
    FillPathLinearGradient {
        d: String,
        p1: [f32; 2],
        p2: [f32; 2],
        start_color: [u8; 4],
        end_color: [u8; 4],
    },
    FillPathRadialGradient {
        d: String,
        center: [f32; 2],
        radius: f32,
        start_color: [u8; 4],
        end_color: [u8; 4],
    },
    StrokePath {
        d: String,
        color: [u8; 4],
        width: f32,
    },

    /// Draw a raster image (PNG / JPEG / etc) from disk into a destination
    /// rect. The render thread decodes once and caches by path.
    DrawImageFile {
        path: String,
        dst: [f32; 4],
    },
    /// Draw a raw RGBA8 buffer (premultiplied alpha) at a destination
    /// rect. Used by WebView / Mesh3D / dynamic textures that produce
    /// pixels each frame and don't have a stable on-disk filename.
    DrawImageBytes {
        rgba: Vec<u8>,
        width: u32,
        height: u32,
        dst: [f32; 4],
    },
    /// Draw a cached image with a per-instance affine transform: rotate
    /// and scale around `anchor`, then translate. Drives per-wing flap
    /// animation in the butterfly demo.
    DrawImageFileTransformed {
        path: String,
        dst: [f32; 4],
        anchor: [f32; 2],
        translate: [f32; 2],
        scale: [f32; 2],
        rotation_rad: f32,
    },
    /// Draw a sub-rectangle of a cached image (texture-atlas style).
    DrawImageFileRegion {
        path: String,
        src: [f32; 4],
        dst: [f32; 4],
    },
    /// Draw a string of text at (x, y) — `y` is the baseline. Phase 2's
    /// component library uses this for labels, captions, button text.
    DrawText {
        text: String,
        x: f32,
        y: f32,
        size: f32,
        color: [u8; 4],
    },
    /// Wrapped multi-line paragraph via Skia textlayout. `align`: 0=left,
    /// 1=right, 2=center, 3=justify.
    DrawParagraph {
        text: String,
        x: f32,
        y: f32,
        max_width: f32,
        size: f32,
        color: [u8; 4],
        align: i32,
        /// Font family — empty string means default. Used to opt into a
        /// specific variable font installed on the system (e.g. "Inter",
        /// "Roboto Flex").
        font_family: String,
        /// Weight in CSS units: 100..1000. 400 = regular, 700 = bold.
        /// For variable fonts this maps onto the `wght` axis.
        weight: i32,
        /// Optional variation axes as `(tag, value)` pairs (e.g.
        /// `[("wdth", 110.0), ("ital", 0.0), ("slnt", -8.0)]`).
        variation_axes: Vec<(String, f32)>,
        /// Base paragraph direction. `true` lays the paragraph out
        /// right-to-left (Arabic / Hebrew); Skia still shapes + reorders
        /// bidi runs internally either way. Defaults to `false` (LTR).
        #[serde(default)]
        rtl: bool,
        /// Tabular (lining, equal-width) numerals via the OpenType `tnum`+`lnum`
        /// features, so monetary / metric columns align to the digit.
        #[serde(default)]
        tabular: bool,
    },
    /// Custom SkSL shader pass over a rounded rectangle. The Skia layer
    /// compiles + caches the SkSL once per unique `src` and binds the
    /// `uniforms` (raw little-endian f32 bytes) before painting. Use
    /// for per-component glow / refraction / noise effects.
    SkslEffect {
        src: String,
        dst: [f32; 4],
        corner_radius: f32,
        uniforms: Vec<u8>,
    },
}

pub struct TripleBuffer<T> {
    slots: [Mutex<T>; 3],
    /// See module docs for encoding.
    state: AtomicU8,
}

const READY_MASK: u8 = 0b0000_0011;
const NEW_FLAG: u8 = 0b0000_0100;
const PRODUCER_MASK: u8 = 0b0001_1000;
const PRODUCER_SHIFT: u8 = 3;

impl<T: Default> Default for TripleBuffer<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T: Default> TripleBuffer<T> {
    pub fn new() -> Self {
        Self {
            slots: [
                Mutex::new(T::default()),
                Mutex::new(T::default()),
                Mutex::new(T::default()),
            ],
            // Producer starts at slot 0, ready=1 (stale), no-new.
            state: AtomicU8::new((0 << PRODUCER_SHIFT) | 1),
        }
    }
}

impl<T> TripleBuffer<T> {
    /// Returns a guard around the producer's current write slot. The producer
    /// fills it, then calls `publish()` to make it visible to the consumer.
    pub fn producer_slot(&self) -> ProducerGuard<'_, T> {
        let s = self.state.load(Ordering::Acquire);
        let idx = ((s & PRODUCER_MASK) >> PRODUCER_SHIFT) as usize;
        ProducerGuard { buffer: self, idx }
    }

    /// Atomically publish the producer's current slot and rotate the
    /// producer onto the previously-back slot.
    pub fn publish(&self) {
        loop {
            let s = self.state.load(Ordering::Acquire);
            let producer = (s & PRODUCER_MASK) >> PRODUCER_SHIFT;
            let ready = s & READY_MASK;
            // The remaining (non-producer, non-ready) slot becomes the new producer slot.
            let back = 3 - producer - ready;
            let next = (back << PRODUCER_SHIFT) | NEW_FLAG | producer;
            if self
                .state
                .compare_exchange(s, next, Ordering::AcqRel, Ordering::Acquire)
                .is_ok()
            {
                return;
            }
        }
    }

    /// Acquire the most recently published slot for reading. Returns
    /// `Some` only when fresh data is available since the last `acquire`.
    pub fn try_acquire(&self) -> Option<ConsumerGuard<'_, T>> {
        loop {
            let s = self.state.load(Ordering::Acquire);
            if s & NEW_FLAG == 0 {
                return None;
            }
            let next = s & !NEW_FLAG;
            if self
                .state
                .compare_exchange(s, next, Ordering::AcqRel, Ordering::Acquire)
                .is_ok()
            {
                let idx = (s & READY_MASK) as usize;
                return Some(ConsumerGuard { buffer: self, idx });
            }
        }
    }
}

pub struct ProducerGuard<'a, T> {
    buffer: &'a TripleBuffer<T>,
    idx: usize,
}
pub struct ConsumerGuard<'a, T> {
    buffer: &'a TripleBuffer<T>,
    idx: usize,
}

impl<'a, T> ProducerGuard<'a, T> {
    pub fn with_mut<R>(&self, f: impl FnOnce(&mut T) -> R) -> R {
        f(&mut self.buffer.slots[self.idx].lock())
    }
}
impl<'a, T> ConsumerGuard<'a, T> {
    pub fn with<R>(&self, f: impl FnOnce(&T) -> R) -> R {
        f(&self.buffer.slots[self.idx].lock())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn publish_visible_to_consumer() {
        let buf = TripleBuffer::<DisplayList>::new();
        buf.producer_slot().with_mut(|dl| dl.frame_index = 42);
        buf.publish();
        let got = buf.try_acquire().expect("must have new frame");
        got.with(|dl| assert_eq!(dl.frame_index, 42));
        assert!(buf.try_acquire().is_none(), "no more new frames");
    }

    #[test]
    fn concurrent_producer_consumer_no_tear() {
        let buf = Arc::new(TripleBuffer::<DisplayList>::new());
        let producer = {
            let buf = buf.clone();
            thread::spawn(move || {
                for i in 0..1000u64 {
                    buf.producer_slot().with_mut(|dl| {
                        dl.frame_index = i;
                        dl.commands.clear();
                        for _ in 0..i as usize % 8 {
                            dl.commands.push(DrawCommand::Clear { color: [0.0; 4] });
                        }
                    });
                    buf.publish();
                }
            })
        };
        let consumer = {
            let buf = buf.clone();
            thread::spawn(move || {
                let mut last = 0u64;
                let start = std::time::Instant::now();
                while start.elapsed() < Duration::from_millis(200) {
                    if let Some(g) = buf.try_acquire() {
                        g.with(|dl| {
                            assert!(dl.frame_index >= last, "monotonic order");
                            // Consistency check: commands.len() must match the
                            // producer's invariant (frame_index % 8).
                            assert_eq!(dl.commands.len(), (dl.frame_index % 8) as usize);
                            last = dl.frame_index;
                        });
                    }
                }
            })
        };
        producer.join().unwrap();
        consumer.join().unwrap();
    }
}
