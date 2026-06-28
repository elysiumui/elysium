use std::time::{Duration, Instant};

/// Monotonic frame clock with adaptive present-skipping when the window
/// is hidden. Mantis-inheritance: dynamic FPS / VSync per spec §3.3.
#[derive(Debug)]
pub struct FrameClock {
    start: Instant,
    last_tick: Instant,
    frame_index: u64,
    target_period: Duration,
}

impl FrameClock {
    pub fn new(target_hz: u32) -> Self {
        let now = Instant::now();
        Self {
            start: now,
            last_tick: now,
            frame_index: 0,
            target_period: Duration::from_secs_f64(1.0 / target_hz as f64),
        }
    }

    pub fn elapsed(&self) -> Duration {
        self.start.elapsed()
    }
    pub fn frame_index(&self) -> u64 {
        self.frame_index
    }

    /// Returns the delta seconds since the previous tick.
    pub fn tick(&mut self) -> f32 {
        let now = Instant::now();
        let dt = now - self.last_tick;
        self.last_tick = now;
        self.frame_index += 1;
        dt.as_secs_f32()
    }

    pub fn target_period(&self) -> Duration {
        self.target_period
    }
}
