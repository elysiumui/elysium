//! Dirty-region tracking for the render thread.
//!
//! The render loop publishes a fresh [`DisplayList`] each frame, but most
//! frames change only a small part of the UI (a blinking caret, a hovered
//! button, one edited cell). Re-rasterising and re-uploading the whole
//! surface every frame wastes CPU + GPU bandwidth.
//!
//! [`diff_damage`] compares the previous and current display lists and
//! returns the smallest logical-pixel rectangle that must be repainted —
//! or [`Damage::Full`] when it can't safely localise the change (a `Clear`,
//! a backdrop-blur panel, a transform/animation, or a command whose bounds
//! we don't compute). The render thread then clips its raster + texture
//! upload to that rectangle. Output is pixel-identical to a full redraw;
//! see the tests.

use ely_core::display_list::{DisplayList, DrawCommand as C};
use skia_safe::Rect;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Damage {
    /// Nothing changed — the frame can be skipped entirely.
    None,
    /// Repaint just this logical-pixel rectangle `(x, y, w, h)`.
    Rect(f32, f32, f32, f32),
    /// Could not localise — repaint the whole surface.
    Full,
}

fn r4(b: &[f32; 4]) -> Rect {
    Rect::from_xywh(b[0], b[1], b[2], b[3])
}

fn union(acc: Option<Rect>, r: Rect) -> Option<Rect> {
    Some(match acc {
        None => r,
        Some(mut a) => {
            a.join(r);
            a
        }
    })
}

/// Logical-pixel bounds a single command paints into. `None` means the
/// command is unbounded / context-dependent and forces a full repaint.
fn cmd_bounds(cmd: &C) -> Option<Rect> {
    match cmd {
        // Whole-surface or context-dependent → cannot localise.
        C::Clear { .. } => None,
        C::FrostedPanel { .. } => None, // backdrop blur samples neighbours
        C::PushTransform { .. } | C::PopTransform => None,
        C::PushClip { .. } | C::PopClip => None, // changes clip for following cmds
        C::DrawImageFileTransformed { .. } => None, // per-instance rotation

        C::SkslEffect { dst, .. } => Some(r4(dst)),
        C::GradientCard {
            bounds,
            shadow_blur,
            shadow_offset,
            ..
        } => {
            // Expand for the drop shadow (blur radius + offset, both signs).
            let base = r4(bounds);
            let b = *shadow_blur + 1.0;
            let ox = shadow_offset[0];
            let oy = shadow_offset[1];
            let mut r = base;
            r.left -= b - ox.min(0.0);
            r.top -= b - oy.min(0.0);
            r.right += b + ox.max(0.0);
            r.bottom += b + oy.max(0.0);
            Some(r)
        }
        C::FilledCircle { cx, cy, r, .. } => {
            Some(Rect::from_xywh(cx - r, cy - r, r * 2.0, r * 2.0))
        }
        C::FillPath { d, .. }
        | C::FillPathLinearGradient { d, .. }
        | C::FillPathRadialGradient { d, .. } => path_bounds(d),
        C::StrokePath { d, width, .. } => path_bounds(d).map(|r| inflate(r, width / 2.0 + 1.0)),
        C::DrawImageFile { dst, .. }
        | C::DrawImageBytes { dst, .. }
        | C::DrawImageFileRegion { dst, .. } => Some(r4(dst)),
        C::DrawText {
            text, x, y, size, ..
        } => {
            let (adv, asc, desc) = crate::skia_layer::measure_text_run(text, *size);
            // `y` is the baseline; the glyph box spans ascent..descent.
            Some(Rect::from_xywh(*x, *y - asc, adv.max(1.0), asc + desc))
        }
        // Wrapped paragraphs need a full layout (font family / axes) to
        // bound precisely; treat as unbounded for v1 (conservative, correct).
        C::DrawParagraph { .. } => None,
    }
}

fn inflate(r: Rect, by: f32) -> Rect {
    Rect::new(r.left - by, r.top - by, r.right + by, r.bottom + by)
}

fn path_bounds(svg_d: &str) -> Option<Rect> {
    let path = skia_safe::utils::parse_path::from_svg(svg_d)?;
    let b = path.compute_tight_bounds();
    // Anti-aliasing can touch one extra pixel on each edge.
    Some(inflate(b, 1.0))
}

/// Diff two display lists into the rectangle that must be repainted.
///
/// Strategy: skip the common prefix + suffix of identical commands; the
/// differing middle (in *both* lists — removed regions must be cleared,
/// added regions painted) defines the damage. Any unbounded command in the
/// middle escalates to [`Damage::Full`].
pub fn diff_damage(prev: &DisplayList, new: &DisplayList) -> Damage {
    let pc = &prev.commands;
    let nc = &new.commands;

    // First-ever frame (or recovery): nothing retained → full repaint.
    if pc.is_empty() {
        return if nc.is_empty() {
            Damage::None
        } else {
            Damage::Full
        };
    }

    // Common prefix.
    let mut lo = 0usize;
    let max_lo = pc.len().min(nc.len());
    while lo < max_lo && pc[lo] == nc[lo] {
        lo += 1;
    }
    if lo == pc.len() && lo == nc.len() {
        return Damage::None; // identical lists
    }

    // Common suffix (not overlapping the prefix).
    let mut hp = pc.len();
    let mut hn = nc.len();
    while hp > lo && hn > lo && pc[hp - 1] == nc[hn - 1] {
        hp -= 1;
        hn -= 1;
    }

    // Union the bounds of every differing command in both lists.
    let mut acc: Option<Rect> = None;
    for cmd in &pc[lo..hp] {
        match cmd_bounds(cmd) {
            None => return Damage::Full,
            Some(r) => acc = union(acc, r),
        }
    }
    for cmd in &nc[lo..hn] {
        match cmd_bounds(cmd) {
            None => return Damage::Full,
            Some(r) => acc = union(acc, r),
        }
    }
    match acc {
        None => Damage::None,
        Some(r) => Damage::Rect(r.left, r.top, r.width(), r.height()),
    }
}

/// True when the list contains a live animation transform — those tween
/// every frame even without a new list, so the render thread must keep
/// repainting while one is present.
pub fn has_live_anim(list: &DisplayList) -> bool {
    list.commands.iter().any(|c| {
        matches!(
            c,
            C::PushTransform {
                anim_slot: Some(_),
                ..
            }
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use ely_core::display_list::DrawCommand as C;

    fn dl(cmds: Vec<C>) -> DisplayList {
        DisplayList {
            commands: cmds,
            frame_index: 0,
        }
    }

    fn circle(cx: f32, cy: f32, r: f32) -> C {
        C::FilledCircle {
            cx,
            cy,
            r,
            color: [255, 0, 0, 255],
        }
    }

    #[test]
    fn identical_lists_have_no_damage() {
        let a = dl(vec![circle(10.0, 10.0, 5.0), circle(50.0, 50.0, 5.0)]);
        let b = a.clone();
        assert_eq!(diff_damage(&a, &b), Damage::None);
    }

    #[test]
    fn first_frame_is_full() {
        let empty = dl(vec![]);
        let b = dl(vec![circle(10.0, 10.0, 5.0)]);
        assert_eq!(diff_damage(&empty, &b), Damage::Full);
    }

    #[test]
    fn single_changed_command_localises() {
        let a = dl(vec![circle(10.0, 10.0, 5.0), circle(50.0, 50.0, 5.0)]);
        // Second circle moves; first is unchanged (common prefix).
        let b = dl(vec![circle(10.0, 10.0, 5.0), circle(60.0, 50.0, 5.0)]);
        match diff_damage(&a, &b) {
            Damage::Rect(x, y, w, h) => {
                // Union of old (45..55) and new (55..65) circle x-extents.
                assert!(x <= 45.0 && x + w >= 65.0, "x={x} w={w}");
                assert!(y <= 45.0 && y + h >= 55.0, "y={y} h={h}");
            }
            other => panic!("expected Rect, got {other:?}"),
        }
    }

    #[test]
    fn clear_escalates_to_full() {
        let a = dl(vec![circle(10.0, 10.0, 5.0)]);
        let b = dl(vec![C::Clear { color: [0.0; 4] }, circle(10.0, 10.0, 5.0)]);
        assert_eq!(diff_damage(&a, &b), Damage::Full);
    }

    #[test]
    fn transform_escalates_to_full() {
        let a = dl(vec![circle(10.0, 10.0, 5.0)]);
        let b = dl(vec![
            C::PushTransform {
                tx: 1.0,
                ty: 0.0,
                sx: 1.0,
                sy: 1.0,
                rotation: 0.0,
                anim_slot: None,
            },
            circle(10.0, 10.0, 5.0),
            C::PopTransform,
        ]);
        assert_eq!(diff_damage(&a, &b), Damage::Full);
    }

    #[test]
    fn text_change_localises_to_text_box() {
        let a = dl(vec![C::DrawText {
            text: "a".into(),
            x: 100.0,
            y: 100.0,
            size: 14.0,
            color: [0; 4],
        }]);
        let b = dl(vec![C::DrawText {
            text: "ab".into(),
            x: 100.0,
            y: 100.0,
            size: 14.0,
            color: [0; 4],
        }]);
        match diff_damage(&a, &b) {
            Damage::Rect(x, _y, w, _h) => {
                assert!((99.0..=101.0).contains(&x), "x={x}");
                assert!(w > 0.0, "w={w}");
            }
            other => panic!("expected Rect, got {other:?}"),
        }
    }

    #[test]
    fn has_live_anim_detects_anim_slot() {
        let a = dl(vec![C::PushTransform {
            tx: 0.0,
            ty: 0.0,
            sx: 1.0,
            sy: 1.0,
            rotation: 0.0,
            anim_slot: Some(3),
        }]);
        assert!(has_live_anim(&a));
        let b = dl(vec![circle(0.0, 0.0, 1.0)]);
        assert!(!has_live_anim(&b));
    }

    /// The invariant the whole feature rests on: a partial repaint of the
    /// damage rect (clip → clear → replay) produces a surface byte-identical
    /// to a full redraw of the new list. Emulates the render thread's
    /// partial path with a `SkiaLayer` (scale = 1, no wgpu needed).
    #[test]
    fn partial_repaint_is_pixel_identical_to_full() {
        use crate::skia_layer::SkiaLayer;
        const W: u32 = 200;
        const H: u32 = 120;

        let scene_a = dl(vec![
            circle(40.0, 40.0, 12.0),
            C::DrawText {
                text: "Name: a".into(),
                x: 20.0,
                y: 90.0,
                size: 16.0,
                color: [20, 20, 20, 255],
            },
        ]);
        // Only the text changes (caret/typing) — common prefix is the circle.
        let scene_b = dl(vec![
            circle(40.0, 40.0, 12.0),
            C::DrawText {
                text: "Name: ab".into(),
                x: 20.0,
                y: 90.0,
                size: 16.0,
                color: [20, 20, 20, 255],
            },
        ]);

        // Reference: full redraw of B.
        let mut reference = SkiaLayer::new(W, H);
        reference.clear([0.0, 0.0, 0.0, 0.0]);
        reference.execute(&scene_b);
        assert!(reference.snapshot_bgra());
        let ref_px = reference.pixels.clone();

        // Partial: establish A, then repaint only the damage of A→B.
        let mut partial = SkiaLayer::new(W, H);
        partial.clear([0.0, 0.0, 0.0, 0.0]);
        partial.execute(&scene_a);

        let dmg = diff_damage(&scene_a, &scene_b);
        let Damage::Rect(x, y, w, h) = dmg else {
            panic!("expected a localised Rect, got {dmg:?}");
        };
        let pad = 1.0;
        partial.save_with_transform(0.0, 0.0, 1.0, 1.0, 0.0);
        partial.clip_rect(x - pad, y - pad, w + 2.0 * pad, h + 2.0 * pad);
        partial.clear([0.0, 0.0, 0.0, 0.0]);
        partial.execute(&scene_b);
        partial.restore();
        assert!(partial.snapshot_bgra());

        assert_eq!(
            partial.pixels, ref_px,
            "partial repaint must be byte-identical to a full redraw"
        );
    }
}
