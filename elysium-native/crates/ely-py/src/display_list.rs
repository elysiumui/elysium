//! Python-facing display-list builder. Constructs an `ely_core::DisplayList`
//! that the user pushes through `Window.publish_display_list(...)`.

use ely_core::{DisplayList, DrawCommand};
use pyo3::prelude::*;

#[pyclass(name = "DisplayList", module = "elysium")]
pub struct PyDisplayList {
    pub(crate) inner: DisplayList,
}

#[pymethods]
impl PyDisplayList {
    #[new]
    fn new() -> Self {
        Self {
            inner: DisplayList::default(),
        }
    }

    fn clear(&mut self, r: f32, g: f32, b: f32, a: f32) {
        self.inner.commands.push(DrawCommand::Clear {
            color: [r, g, b, a],
        });
    }

    #[pyo3(signature = (x, y, w, h, corner_radius, start_color, end_color,
                        shadow_blur=20.0, shadow_offset=(0.0, 12.0), shadow_color=(0,0,0,127)))]
    fn gradient_card(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        corner_radius: f32,
        start_color: (u8, u8, u8, u8),
        end_color: (u8, u8, u8, u8),
        shadow_blur: f32,
        shadow_offset: (f32, f32),
        shadow_color: (u8, u8, u8, u8),
    ) {
        self.inner.commands.push(DrawCommand::GradientCard {
            bounds: [x, y, w, h],
            corner_radius,
            start_color: [start_color.0, start_color.1, start_color.2, start_color.3],
            end_color: [end_color.0, end_color.1, end_color.2, end_color.3],
            shadow_blur,
            shadow_offset: [shadow_offset.0, shadow_offset.1],
            shadow_color: [
                shadow_color.0,
                shadow_color.1,
                shadow_color.2,
                shadow_color.3,
            ],
        });
    }

    #[pyo3(signature = (x, y, w, h, corner_radius, blur_sigma, tint, border=None))]
    fn frosted_panel(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        corner_radius: f32,
        blur_sigma: f32,
        tint: (u8, u8, u8, u8),
        border: Option<(u8, u8, u8, u8)>,
    ) {
        self.inner.commands.push(DrawCommand::FrostedPanel {
            bounds: [x, y, w, h],
            corner_radius,
            blur_sigma,
            tint: [tint.0, tint.1, tint.2, tint.3],
            border: border.map(|b| [b.0, b.1, b.2, b.3]),
        });
    }

    fn filled_circle(&mut self, cx: f32, cy: f32, r: f32, color: (u8, u8, u8, u8)) {
        self.inner.commands.push(DrawCommand::FilledCircle {
            cx,
            cy,
            r,
            color: [color.0, color.1, color.2, color.3],
        });
    }

    fn fill_path(&mut self, d: &str, color: (u8, u8, u8, u8)) {
        self.inner.commands.push(DrawCommand::FillPath {
            d: d.to_string(),
            color: [color.0, color.1, color.2, color.3],
        });
    }

    fn fill_path_linear_gradient(
        &mut self,
        d: &str,
        p1: (f32, f32),
        p2: (f32, f32),
        start_color: (u8, u8, u8, u8),
        end_color: (u8, u8, u8, u8),
    ) {
        self.inner
            .commands
            .push(DrawCommand::FillPathLinearGradient {
                d: d.to_string(),
                p1: [p1.0, p1.1],
                p2: [p2.0, p2.1],
                start_color: [start_color.0, start_color.1, start_color.2, start_color.3],
                end_color: [end_color.0, end_color.1, end_color.2, end_color.3],
            });
    }

    fn fill_path_radial_gradient(
        &mut self,
        d: &str,
        center: (f32, f32),
        radius: f32,
        start_color: (u8, u8, u8, u8),
        end_color: (u8, u8, u8, u8),
    ) {
        self.inner
            .commands
            .push(DrawCommand::FillPathRadialGradient {
                d: d.to_string(),
                center: [center.0, center.1],
                radius,
                start_color: [start_color.0, start_color.1, start_color.2, start_color.3],
                end_color: [end_color.0, end_color.1, end_color.2, end_color.3],
            });
    }

    fn stroke_path(&mut self, d: &str, color: (u8, u8, u8, u8), width: f32) {
        self.inner.commands.push(DrawCommand::StrokePath {
            d: d.to_string(),
            color: [color.0, color.1, color.2, color.3],
            width,
        });
    }

    /// Decode `path` (PNG / JPEG / WebP / etc.) and draw it into the
    /// destination rect when this DisplayList renders. The render
    /// thread caches the decoded image by path — first frame pays the
    /// decode cost, every subsequent frame is a single GPU sample.
    fn draw_image_file(&mut self, path: &str, x: f32, y: f32, w: f32, h: f32) {
        self.inner.commands.push(DrawCommand::DrawImageFile {
            path: path.to_string(),
            dst: [x, y, w, h],
        });
    }

    /// Draw raw RGBA8 (premultiplied) bytes at a destination rect.
    /// Bytes are copied into the command — caller can reuse / mutate
    /// the source buffer after the call. Used by WebView snapshots and
    /// any in-memory pixel producer.
    fn draw_image_bytes(
        &mut self,
        rgba: &[u8],
        width: u32,
        height: u32,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
    ) {
        self.inner.commands.push(DrawCommand::DrawImageBytes {
            rgba: rgba.to_vec(),
            width,
            height,
            dst: [x, y, w, h],
        });
    }

    /// Draw a cached image with an affine transform: rotate + scale
    /// around `anchor` (in the destination rect's frame), then translate.
    /// This is the primitive for per-wing flap animation.
    #[pyo3(signature = (
        path, x, y, w, h,
        anchor_x=0.5, anchor_y=0.5,
        translate_x=0.0, translate_y=0.0,
        scale_x=1.0, scale_y=1.0,
        rotation_rad=0.0,
    ))]
    fn draw_image_file_transformed(
        &mut self,
        path: &str,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        anchor_x: f32,
        anchor_y: f32,
        translate_x: f32,
        translate_y: f32,
        scale_x: f32,
        scale_y: f32,
        rotation_rad: f32,
    ) {
        // anchor expressed as a fraction of the dst rect.
        let anchor = [x + anchor_x * w, y + anchor_y * h];
        self.inner
            .commands
            .push(DrawCommand::DrawImageFileTransformed {
                path: path.to_string(),
                dst: [x, y, w, h],
                anchor,
                translate: [translate_x, translate_y],
                scale: [scale_x, scale_y],
                rotation_rad,
            });
    }

    /// Draw a sub-rectangle of a cached image (texture-atlas style).
    fn draw_image_file_region(
        &mut self,
        path: &str,
        sx: f32,
        sy: f32,
        sw: f32,
        sh: f32,
        dx: f32,
        dy: f32,
        dw: f32,
        dh: f32,
    ) {
        self.inner.commands.push(DrawCommand::DrawImageFileRegion {
            path: path.to_string(),
            src: [sx, sy, sw, sh],
            dst: [dx, dy, dw, dh],
        });
    }

    /// Draw text. `y` is the baseline.
    fn draw_text(&mut self, text: &str, x: f32, y: f32, size: f32, color: (u8, u8, u8, u8)) {
        self.inner.commands.push(DrawCommand::DrawText {
            text: text.to_string(),
            x,
            y,
            size,
            color: [color.0, color.1, color.2, color.3],
        });
    }

    /// Wrapped paragraph. `align`: 0=left, 1=right, 2=center, 3=justify.
    #[pyo3(signature = (text, x, y, max_width, size, color, align=0,
                        font_family="", weight=0, variation_axes=Vec::new(), rtl=false,
                        tabular=false))]
    fn draw_paragraph(
        &mut self,
        text: &str,
        x: f32,
        y: f32,
        max_width: f32,
        size: f32,
        color: (u8, u8, u8, u8),
        align: i32,
        font_family: &str,
        weight: i32,
        variation_axes: Vec<(String, f32)>,
        rtl: bool,
        tabular: bool,
    ) {
        self.inner.commands.push(DrawCommand::DrawParagraph {
            text: text.to_string(),
            x,
            y,
            max_width,
            size,
            color: [color.0, color.1, color.2, color.3],
            align,
            font_family: font_family.to_string(),
            weight,
            variation_axes,
            rtl,
            tabular,
        });
    }

    /// Apply a custom SkSL shader to a rounded-rect region.
    fn skia_effect(
        &mut self,
        sksl_src: &str,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        corner_radius: f32,
        uniforms: &[u8],
    ) {
        self.inner.commands.push(DrawCommand::SkslEffect {
            src: sksl_src.to_string(),
            dst: [x, y, w, h],
            corner_radius,
            uniforms: uniforms.to_vec(),
        });
    }

    #[pyo3(signature = (tx, ty, sx=1.0, sy=1.0, rotation=0.0, anim_slot=None))]
    fn push_transform(
        &mut self,
        tx: f32,
        ty: f32,
        sx: f32,
        sy: f32,
        rotation: f32,
        anim_slot: Option<u32>,
    ) {
        self.inner.commands.push(DrawCommand::PushTransform {
            tx,
            ty,
            sx,
            sy,
            rotation,
            anim_slot,
        });
    }

    fn pop_transform(&mut self) {
        self.inner.commands.push(DrawCommand::PopTransform);
    }

    /// Clip subsequent draws to a rectangle (current transform space) until
    /// the matching `pop_clip()`. Used by ScrollView to keep scrolled
    /// content inside its viewport.
    fn push_clip(&mut self, x: f32, y: f32, w: f32, h: f32) {
        self.inner
            .commands
            .push(DrawCommand::PushClip { x, y, w, h });
    }

    fn pop_clip(&mut self) {
        self.inner.commands.push(DrawCommand::PopClip);
    }

    // Aliases so the same drawing code targets either a SkiaLayer (offscreen)
    // or a DisplayList (published to the render thread).
    #[pyo3(signature = (tx, ty, sx=1.0, sy=1.0, rotation=0.0))]
    fn save_with_transform(&mut self, tx: f32, ty: f32, sx: f32, sy: f32, rotation: f32) {
        self.push_transform(tx, ty, sx, sy, rotation, None);
    }
    fn restore(&mut self) {
        self.pop_transform();
    }

    fn clear_color(&mut self, r: f32, g: f32, b: f32, a: f32) {
        self.clear(r, g, b, a);
    }

    #[getter]
    fn len(&self) -> usize {
        self.inner.commands.len()
    }

    fn __len__(&self) -> usize {
        self.inner.commands.len()
    }

    fn __repr__(&self) -> String {
        format!("DisplayList(commands={})", self.inner.commands.len())
    }

    /// Append every command from `other` after this DisplayList's
    /// current commands. Lets compositional UI build a frame by
    /// splicing sub-trees (Designer preview, embedded panels, etc.).
    fn extend(&mut self, other: &PyDisplayList) {
        self.inner.commands.extend_from_slice(&other.inner.commands);
    }

    /// Same as `extend` but returns self for fluent chaining.
    fn extend_(&mut self, other: &PyDisplayList) {
        self.extend(other)
    }
}
