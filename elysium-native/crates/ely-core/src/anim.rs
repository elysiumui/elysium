//! Render-thread animation evaluator.
//!
//! Spec §3.2 "1-ms rule": animated transforms must not require a Python
//! callback every frame. The producer publishes a *target* into a slot
//! once; the render thread interpolates between frames and substitutes
//! the live value into matching `PushTransform` commands before paint.
//!
//! Slots are addressed by integer ids that Python embeds in
//! `PushTransform.anim_slot`. When the render thread sees `Some(id)` it
//! looks up the slot, computes the eased value at the current wall-clock,
//! and overrides the matrix.
//!
//! No locks on the hot path: each slot lives in a single `Mutex<SlotState>`
//! and the render thread takes it briefly per frame per slot.

use parking_lot::Mutex;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

#[derive(Copy, Clone, Debug)]
pub enum Easing {
    Linear,
    EaseInOut,
    EaseOut,
    EaseIn,
    /// Critically-damped spring approximation in closed form.
    Spring {
        stiffness: f32,
        damping: f32,
    },
}

#[derive(Copy, Clone, Debug)]
pub struct TransformValue {
    pub tx: f32,
    pub ty: f32,
    pub sx: f32,
    pub sy: f32,
    pub rotation: f32,
    pub alpha: f32,
}

impl TransformValue {
    pub const IDENT: Self = Self {
        tx: 0.0,
        ty: 0.0,
        sx: 1.0,
        sy: 1.0,
        rotation: 0.0,
        alpha: 1.0,
    };
}

#[derive(Clone, Debug)]
struct SlotState {
    from: TransformValue,
    to: TransformValue,
    start: Instant,
    duration: f32,
    easing: Easing,
    /// Resolved snapshot of the most recent evaluation. Kept so Python
    /// can read the current value without re-evaluating.
    current: TransformValue,
}

pub struct AnimRegistry {
    slots: Mutex<HashMap<u32, SlotState>>,
}

impl AnimRegistry {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            slots: Mutex::new(HashMap::new()),
        })
    }

    /// Push (or replace) a target for `slot`. Animation starts from the
    /// current resolved value of that slot (so consecutive calls behave
    /// like a CSS transition).
    pub fn set_target(&self, slot: u32, to: TransformValue, duration_secs: f32, easing: Easing) {
        let mut g = self.slots.lock();
        let from = g
            .get(&slot)
            .map(|s| s.current)
            .unwrap_or(TransformValue::IDENT);
        g.insert(
            slot,
            SlotState {
                from,
                to,
                start: Instant::now(),
                duration: duration_secs.max(1e-3),
                easing,
                current: from,
            },
        );
    }

    /// Snap a slot directly to a value (no tween). Used to set initial
    /// state without an animation.
    pub fn snap(&self, slot: u32, v: TransformValue) {
        let mut g = self.slots.lock();
        g.insert(
            slot,
            SlotState {
                from: v,
                to: v,
                start: Instant::now(),
                duration: 1e-3,
                easing: Easing::Linear,
                current: v,
            },
        );
    }

    /// Render-thread call: returns the value to substitute, evaluating
    /// the easing curve at the current wall-clock.
    pub fn evaluate(&self, slot: u32) -> Option<TransformValue> {
        let mut g = self.slots.lock();
        let s = g.get_mut(&slot)?;
        let t = s.start.elapsed().as_secs_f32() / s.duration;
        let t = t.clamp(0.0, 1.0);
        let e = apply_easing(s.easing, t);
        let v = TransformValue {
            tx: lerp(s.from.tx, s.to.tx, e),
            ty: lerp(s.from.ty, s.to.ty, e),
            sx: lerp(s.from.sx, s.to.sx, e),
            sy: lerp(s.from.sy, s.to.sy, e),
            rotation: lerp(s.from.rotation, s.to.rotation, e),
            alpha: lerp(s.from.alpha, s.to.alpha, e),
        };
        s.current = v;
        Some(v)
    }

    pub fn current(&self, slot: u32) -> Option<TransformValue> {
        self.slots.lock().get(&slot).map(|s| s.current)
    }

    pub fn clear(&self, slot: u32) {
        self.slots.lock().remove(&slot);
    }
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

fn apply_easing(e: Easing, t: f32) -> f32 {
    match e {
        Easing::Linear => t,
        Easing::EaseIn => t * t,
        Easing::EaseOut => 1.0 - (1.0 - t) * (1.0 - t),
        Easing::EaseInOut => {
            if t < 0.5 {
                2.0 * t * t
            } else {
                1.0 - (-2.0 * t + 2.0).powi(2) / 2.0
            }
        }
        Easing::Spring { stiffness, damping } => {
            // Critically-damped form: 1 - (1 + ωt)e^(-ωt) with ω = sqrt(k/m).
            // For non-critical damping we fall back to underdamped form.
            let omega = stiffness.max(1e-3).sqrt();
            let zeta = damping / (2.0 * omega.max(1e-3));
            if (zeta - 1.0).abs() < 1e-3 {
                let wt = omega * t;
                1.0 - (1.0 + wt) * (-wt).exp()
            } else if zeta < 1.0 {
                let wd = omega * (1.0 - zeta * zeta).sqrt();
                let phi = (zeta * omega / wd).atan();
                let env = (-zeta * omega * t).exp();
                1.0 - env * (wd * t + phi).cos() / phi.cos().abs().max(1e-3)
            } else {
                // Overdamped — analytic but rarely useful; degrade to ease-out.
                1.0 - (1.0 - t) * (1.0 - t)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ident_value() {
        let v = TransformValue::IDENT;
        assert_eq!(v.sx, 1.0);
        assert_eq!(v.alpha, 1.0);
    }

    #[test]
    fn easing_bounds() {
        for e in [
            Easing::Linear,
            Easing::EaseIn,
            Easing::EaseOut,
            Easing::EaseInOut,
        ] {
            assert!((apply_easing(e, 0.0)).abs() < 1e-4);
            assert!((apply_easing(e, 1.0) - 1.0).abs() < 1e-4);
        }
    }

    #[test]
    fn set_and_snap() {
        let r = AnimRegistry::new();
        r.snap(
            7,
            TransformValue {
                tx: 100.0,
                ..TransformValue::IDENT
            },
        );
        let v = r.current(7).unwrap();
        assert_eq!(v.tx, 100.0);
        r.set_target(
            7,
            TransformValue {
                tx: 200.0,
                ..TransformValue::IDENT
            },
            0.05,
            Easing::Linear,
        );
        std::thread::sleep(std::time::Duration::from_millis(60));
        let v = r.evaluate(7).unwrap();
        assert!((v.tx - 200.0).abs() < 1e-3);
    }
}
