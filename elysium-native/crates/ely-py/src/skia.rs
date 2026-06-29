//! Python-facing offscreen Skia paint API.
//!
//! Used for headless / CI verification of the renderer without opening a
//! window. `SkiaLayer` itself lives in `ely-render`.

use pyo3::prelude::*;
use pyo3::types::PyBytes;

use ely_render::SkiaLayer;

#[pyclass(name = "SkiaLayer", unsendable)]
pub struct PySkiaLayer {
    inner: SkiaLayer,
}

#[pymethods]
impl PySkiaLayer {
    #[new]
    fn new(width: u32, height: u32) -> Self {
        Self {
            inner: SkiaLayer::new(width, height),
        }
    }

    fn clear(&mut self, r: f32, g: f32, b: f32, a: f32) {
        self.inner.clear([r, g, b, a]);
    }

    #[pyo3(signature = (x, y, w, h, corner_radius, start_color, end_color, shadow_blur=20.0, shadow_offset=(0.0, 12.0), shadow_color=(0, 0, 0, 127)))]
    fn draw_gradient_card(
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
        self.inner.draw_gradient_card(
            (x, y, w, h),
            corner_radius,
            [
                (
                    0.0,
                    [start_color.0, start_color.1, start_color.2, start_color.3],
                ),
                (1.0, [end_color.0, end_color.1, end_color.2, end_color.3]),
            ],
            shadow_blur,
            shadow_offset,
            [
                shadow_color.0,
                shadow_color.1,
                shadow_color.2,
                shadow_color.3,
            ],
        );
    }

    fn draw_filled_circle(&mut self, cx: f32, cy: f32, r: f32, color: (u8, u8, u8, u8)) {
        self.inner
            .draw_filled_circle(cx, cy, r, [color.0, color.1, color.2, color.3]);
    }

    #[pyo3(signature = (x, y, w, h, corner_radius, blur_sigma, tint, border=None))]
    fn draw_frosted_panel(
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
        self.inner.draw_frosted_panel(
            (x, y, w, h),
            corner_radius,
            blur_sigma,
            [tint.0, tint.1, tint.2, tint.3],
            border.map(|b| [b.0, b.1, b.2, b.3]),
        );
    }

    fn encode_png<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = self
            .inner
            .encode_png()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("PNG encode failed"))?;
        Ok(PyBytes::new(py, &bytes))
    }

    /// Execute a DisplayList against this layer — exactly what the live
    /// render thread does each frame, but offscreen and inspectable.
    fn execute(&mut self, dl: &crate::display_list::PyDisplayList) {
        self.inner.execute(&dl.inner);
    }

    fn fill_path(&mut self, svg_d: &str, color: (u8, u8, u8, u8)) {
        self.inner
            .fill_path_solid(svg_d, [color.0, color.1, color.2, color.3]);
    }

    fn fill_path_linear_gradient(
        &mut self,
        svg_d: &str,
        p1: (f32, f32),
        p2: (f32, f32),
        start_color: (u8, u8, u8, u8),
        end_color: (u8, u8, u8, u8),
    ) {
        self.inner.fill_path_linear_gradient(
            svg_d,
            p1,
            p2,
            [start_color.0, start_color.1, start_color.2, start_color.3],
            [end_color.0, end_color.1, end_color.2, end_color.3],
        );
    }

    fn fill_path_radial_gradient(
        &mut self,
        svg_d: &str,
        center: (f32, f32),
        radius: f32,
        start_color: (u8, u8, u8, u8),
        end_color: (u8, u8, u8, u8),
    ) {
        self.inner.fill_path_radial_gradient(
            svg_d,
            center,
            radius,
            [start_color.0, start_color.1, start_color.2, start_color.3],
            [end_color.0, end_color.1, end_color.2, end_color.3],
        );
    }

    fn stroke_path(&mut self, svg_d: &str, color: (u8, u8, u8, u8), width: f32) {
        self.inner
            .stroke_path(svg_d, [color.0, color.1, color.2, color.3], width);
    }

    /// Decode the file at `path` (PNG / JPEG / etc.) and draw it into the
    /// destination rect. Returns False if the file can't be read or
    /// decoded. First call decodes; subsequent calls hit the cache.
    fn draw_image(&mut self, path: &str, x: f32, y: f32, w: f32, h: f32) -> bool {
        self.inner.draw_image_file(path, (x, y, w, h))
    }

    /// Decode `path` into the texture cache without drawing — call this
    /// at app start for hot textures so the first paint doesn't stall.
    fn preload_image(&mut self, path: &str) -> bool {
        self.inner.preload_image(path)
    }

    /// Cache instrumentation (for tests + perf dashboards). `decodes`
    /// counts cold loads from disk; `hits` counts in-memory reuses.
    #[getter]
    fn cache_decodes(&self) -> u64 {
        self.inner.texture_cache().decode_count()
    }
    #[getter]
    fn cache_hits(&self) -> u64 {
        self.inner.texture_cache().hit_count()
    }

    /// Draw a text string. `y` is the baseline.
    fn draw_text(&mut self, text: &str, x: f32, y: f32, size: f32, color: (u8, u8, u8, u8)) {
        self.inner
            .draw_text(text, x, y, size, [color.0, color.1, color.2, color.3]);
    }

    /// Measure a text run: (width, ascent, descent).
    fn measure_text(&self, text: &str, size: f32) -> (f32, f32, f32) {
        self.inner.measure_text(text, size)
    }

    /// Wrapped multi-line paragraph via Skia textlayout. Returns the
    /// resulting block height in pixels. `align`: 0=left, 1=right,
    /// 2=center, 3=justify.
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
    ) -> f32 {
        self.inner.draw_paragraph(
            text,
            x,
            y,
            max_width,
            size,
            [color.0, color.1, color.2, color.3],
            align,
            font_family,
            weight,
            &variation_axes,
            rtl,
            tabular,
        )
    }

    fn measure_paragraph(&self, text: &str, max_width: f32, size: f32) -> f32 {
        self.inner.measure_paragraph(text, max_width, size)
    }

    /// Apply a custom SkSL shader to a rounded-rect region. `uniforms`
    /// is the raw little-endian f32 byte buffer in the order the shader
    /// declares them. The shader is compiled once and cached.
    fn apply_skia_effect(
        &mut self,
        sksl_src: &str,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        corner_radius: f32,
        uniforms: &[u8],
    ) -> bool {
        self.inner
            .apply_skia_effect(sksl_src, (x, y, w, h), corner_radius, uniforms)
    }

    #[pyo3(signature = (tx, ty, sx=1.0, sy=1.0, rotation=0.0))]
    fn save_with_transform(&mut self, tx: f32, ty: f32, sx: f32, sy: f32, rotation: f32) {
        self.inner.save_with_transform(tx, ty, sx, sy, rotation);
    }

    fn restore(&mut self) {
        self.inner.restore();
    }

    /// Save canvas state and intersect the clip with a rectangle. Pair with
    /// `restore()`. Mirrors the DisplayList `push_clip` so offscreen renders
    /// (golden snapshots) match the live render thread.
    fn push_clip(&mut self, x: f32, y: f32, w: f32, h: f32) {
        self.inner.save();
        self.inner.clip_rect(x, y, w, h);
    }

    #[getter]
    fn size(&self) -> (u32, u32) {
        self.inner.size()
    }
}
