//! Skia-rendered overlay layer.
//!
//! Phase 0 strategy: Skia paints into its own raster surface; we copy the
//! pixels out and upload to a wgpu texture once per frame. The zero-copy
//! Skia↔wgpu shared-texture handoff (Metal IOSurface / D3D shared handle /
//! Vulkan dma-buf) lands in Phase 0.2's interop modules.

use parking_lot::RwLock;
use skia_safe::{
    gradient_shader, paint::Style, BlurStyle, Color, Color4f, ImageInfo, MaskFilter, Paint, Point,
    RRect, Rect, RuntimeEffect, SamplingOptions, Surface, TileMode,
};
use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

/// Compiled SkSL effects keyed by source string. Compilation is the
/// expensive part; once cached, applying the effect is sub-millisecond.
#[derive(Default)]
pub struct EffectCache {
    inner: RwLock<HashMap<String, RuntimeEffect>>,
}

impl EffectCache {
    pub fn get_or_compile(&self, src: &str) -> Option<RuntimeEffect> {
        {
            let g = self.inner.read();
            if let Some(eff) = g.get(src) {
                return Some(eff.clone());
            }
        }
        let eff = RuntimeEffect::make_for_shader(src, None).ok()?;
        self.inner.write().insert(src.to_string(), eff.clone());
        Some(eff)
    }
}

use crate::texture_cache::TextureCache;

// ---------------------------------------------------------------------------
// Stateless text-shaping primitives (no GPU surface required).
//
// These power caret placement, selection rectangles, and click-to-position
// in editable text fields. They operate on Unicode *codepoint* indices
// (matching Python `str` indexing — `len(s)` and `s[i]`), NOT byte or
// UTF-16 offsets, so the Python text-editing layer can use them directly.
//
// Single-line, measurement-based: exact for the common case (text fields,
// each line of a multi-line area). Multi-line wrapping is done in Python on
// top of `measure_text_run`, so the native surface area stays minimal.
// ---------------------------------------------------------------------------

/// Vertical font metrics at `size`: `(ascent, descent, line_height)`, all
/// positive pixels. `ascent` is the distance from baseline up to the top of
/// glyphs; `descent` from baseline down; `line_height` is the recommended
/// line advance (ascent + descent + leading).
pub fn font_vmetrics(size: f32) -> (f32, f32, f32) {
    let font = default_font(size);
    let (spacing, m) = font.metrics();
    (-m.ascent, m.descent, spacing)
}

/// Total advance width of `text` at `size`, plus `(ascent, descent)`.
/// Stateless equivalent of `SkiaLayer::measure_text` that needs no surface.
pub fn measure_text_run(text: &str, size: f32) -> (f32, f32, f32) {
    let font = default_font(size);
    let (advance, _bounds) = font.measure_str(text, None);
    let m = font.metrics().1;
    (advance, -m.ascent, m.descent)
}

/// X-offset (pixels from the run's left edge) of the caret positioned
/// *before* the codepoint at `char_index`. `char_index` is clamped to
/// `[0, char_count]`; an index of `char_count` returns the run's full width
/// (caret at end). Measures the substring up to the boundary, so the result
/// is exact for proportional fonts.
pub fn text_caret_x(text: &str, size: f32, char_index: usize) -> f32 {
    if char_index == 0 {
        return 0.0;
    }
    let font = default_font(size);
    // Take the prefix of `char_index` codepoints.
    let prefix: String = text.chars().take(char_index).collect();
    let (advance, _) = font.measure_str(&prefix, None);
    advance
}

/// Codepoint index nearest the x coordinate `px` (pixels from the run's left
/// edge) — the inverse of `text_caret_x`, used for click-to-place-caret and
/// drag-selection. Walks codepoints accumulating advances and returns the
/// boundary whose midpoint the cursor has passed (standard text hit-test),
/// so clicking the left half of a glyph lands the caret before it and the
/// right half lands it after. Result is in `[0, char_count]`.
pub fn text_hit_index(text: &str, size: f32, px: f32) -> usize {
    if px <= 0.0 {
        return 0;
    }
    let font = default_font(size);
    let mut acc = 0.0f32;
    let mut idx = 0usize;
    let mut prev = String::new();
    for (i, ch) in text.chars().enumerate() {
        prev.push(ch);
        let (w_to_here, _) = font.measure_str(&prev, None);
        let glyph_w = w_to_here - acc;
        let mid = acc + glyph_w * 0.5;
        if px < mid {
            return i;
        }
        acc = w_to_here;
        idx = i + 1;
    }
    idx
}

// App-set UI font. A typeface registered from a bundled file (`register_ui_
// font_from_file`) wins; otherwise a preferred family name (`set_ui_font_
// family`) is matched against installed fonts; otherwise a modern system
// UI-font stack, then the platform default.
static UI_TYPEFACE: std::sync::OnceLock<RwLock<Option<skia_safe::Typeface>>> =
    std::sync::OnceLock::new();
static UI_FAMILY: std::sync::OnceLock<RwLock<String>> = std::sync::OnceLock::new();

fn ui_typeface_slot() -> &'static RwLock<Option<skia_safe::Typeface>> {
    UI_TYPEFACE.get_or_init(|| RwLock::new(None))
}
fn ui_family_slot() -> &'static RwLock<String> {
    UI_FAMILY.get_or_init(|| RwLock::new(String::new()))
}

/// Set the preferred UI font family by name (matched against installed fonts).
/// Empty string clears the preference.
pub fn set_ui_font_family(name: &str) {
    *ui_family_slot().write() = name.to_string();
}

/// Register a UI font from a TTF/OTF file so it is used regardless of what is
/// installed on the machine. Returns true on success.
pub fn register_ui_font_from_file(path: &str) -> bool {
    let Ok(bytes) = std::fs::read(path) else {
        return false;
    };
    match skia_safe::FontMgr::new().new_from_data(&bytes, None) {
        Some(tf) => {
            *ui_typeface_slot().write() = Some(tf);
            true
        }
        None => false,
    }
}

/// Skia-safe 0.78 doesn't expose `Typeface::default()` directly; this helper
/// builds the UI Font, honouring an app-set font (see above) then falling back
/// to a modern system stack and finally the platform default.
fn default_font(size: f32) -> skia_safe::Font {
    // 1) A bundled/registered typeface wins.
    if let Some(tf) = ui_typeface_slot().read().clone() {
        return skia_safe::Font::new(tf, size);
    }
    let mgr = skia_safe::FontMgr::new();
    // 2) An app-set family name, if installed.
    {
        let fam = ui_family_slot().read();
        if !fam.is_empty() {
            if let Some(tf) = mgr.match_family_style(fam.as_str(), skia_safe::FontStyle::normal()) {
                return skia_safe::Font::new(tf, size);
            }
        }
    }
    // 3) No app preference → the original platform-default chain, so apps that
    //    don't opt into a UI font (and the checked-in golden snapshots) render
    //    exactly as before. The modern font is opt-in via the theme/set_ui_font.
    let typeface = mgr
        .legacy_make_typeface(None, skia_safe::FontStyle::normal())
        .or_else(|| mgr.match_family_style("Helvetica", skia_safe::FontStyle::normal()))
        .or_else(|| mgr.match_family_style("Arial", skia_safe::FontStyle::normal()));
    if let Some(tf) = typeface {
        skia_safe::Font::new(tf, size)
    } else {
        // Last resort: pull whatever the platform serves as a fallback.
        let tf = mgr
            .match_family_style("", skia_safe::FontStyle::normal())
            .expect("no usable typeface available");
        skia_safe::Font::new(tf, size)
    }
}

pub struct SkiaLayer {
    surface: Surface,
    /// Host-side staging buffer; `read_pixels()` writes here each frame
    /// before wgpu uploads it.
    pub pixels: Vec<u8>,
    width: u32,
    height: u32,
    row_bytes: usize,
    /// Decoded-image cache (decode once, draw many).
    textures: Arc<TextureCache>,
    /// SkSL RuntimeEffect cache (compile once, apply many).
    effects: Arc<EffectCache>,
}

impl SkiaLayer {
    pub fn new(width: u32, height: u32) -> Self {
        Self::with_cache(width, height, Arc::new(TextureCache::new()))
    }

    /// Variant that lets the caller share a texture cache across
    /// multiple SkiaLayers (e.g., main render thread + offscreen
    /// thumbnailer / snapshot writer).
    // The caches are Arc-wrapped for cheap sharing within the render thread;
    // SkiaLayer is single-threaded (!Send) so Send+Sync isn't required.
    #[allow(clippy::arc_with_non_send_sync)]
    pub fn with_cache(width: u32, height: u32, textures: Arc<TextureCache>) -> Self {
        let surface = skia_safe::surfaces::raster_n32_premul((width as i32, height as i32))
            .expect("SkSurface raster_n32_premul failed");
        let row_bytes = (width as usize) * 4;
        let pixels = vec![0u8; row_bytes * height as usize];
        Self {
            surface,
            pixels,
            width,
            height,
            row_bytes,
            textures,
            effects: Arc::new(EffectCache::default()),
        }
    }

    pub fn texture_cache(&self) -> Arc<TextureCache> {
        self.textures.clone()
    }
    pub fn effect_cache(&self) -> Arc<EffectCache> {
        self.effects.clone()
    }

    /// Apply a compiled SkSL effect over a rounded-rect region.
    /// `uniforms` is little-endian f32 bytes laid out in the order the
    /// shader declares them.
    pub fn apply_skia_effect(
        &mut self,
        src: &str,
        dst: (f32, f32, f32, f32),
        corner_radius: f32,
        uniforms: &[u8],
    ) -> bool {
        let Some(effect) = self.effects.get_or_compile(src) else {
            return false;
        };
        let data = skia_safe::Data::new_copy(uniforms);
        let Some(shader) = effect.make_shader(data, &[], None) else {
            return false;
        };
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_shader(shader);
        let rect = Rect::from_xywh(dst.0, dst.1, dst.2, dst.3);
        let rrect = RRect::new_rect_xy(rect, corner_radius, corner_radius);
        self.surface.canvas().draw_rrect(rrect, &paint);
        true
    }

    pub fn size(&self) -> (u32, u32) {
        (self.width, self.height)
    }
    pub fn row_bytes(&self) -> u32 {
        self.row_bytes as u32
    }

    pub fn clear(&mut self, color: [f32; 4]) {
        let c = Color4f::new(color[0], color[1], color[2], color[3]);
        self.surface.canvas().clear(c);
    }

    /// Save canvas state (clip + transform). Pair with `restore`.
    pub fn save(&mut self) {
        self.surface.canvas().save();
    }

    /// Intersect the canvas clip with a rectangle (current coordinate
    /// space). Pair with `save_with_transform` / `restore`. Used by the
    /// dirty-rect render path so `clear` + replayed draws only touch the
    /// damaged region; `SkCanvas::clear` honours the active clip.
    pub fn clip_rect(&mut self, x: f32, y: f32, w: f32, h: f32) {
        let r = Rect::from_xywh(x, y, w, h);
        self.surface.canvas().clip_rect(r, None, false);
    }

    /// Read a physical-pixel sub-rectangle of the surface into `dst` as
    /// tightly-packed BGRA8 (row stride = `w*4`). Returns false if the
    /// region is out of range or the read fails. Used to upload only the
    /// damaged region to the GPU.
    pub fn snapshot_region_bgra(&mut self, x: u32, y: u32, w: u32, h: u32, dst: &mut [u8]) -> bool {
        if w == 0
            || h == 0
            || x + w > self.width
            || y + h > self.height
            || dst.len() < (w as usize) * (h as usize) * 4
        {
            return false;
        }
        let info = ImageInfo::new(
            (w as i32, h as i32),
            skia_safe::ColorType::BGRA8888,
            skia_safe::AlphaType::Premul,
            None,
        );
        self.surface
            .read_pixels(&info, dst, (w as usize) * 4, (x as i32, y as i32))
    }

    pub fn draw_gradient_card(
        &mut self,
        bounds: (f32, f32, f32, f32),
        corner_radius: f32,
        gradient: [(f32, [u8; 4]); 2],
        shadow_blur: f32,
        shadow_offset: (f32, f32),
        shadow_color: [u8; 4],
    ) {
        let canvas = self.surface.canvas();
        let (x, y, w, h) = bounds;
        let rect = Rect::from_xywh(x, y, w, h);
        let rrect = RRect::new_rect_xy(rect, corner_radius, corner_radius);

        let mut shadow_paint = Paint::default();
        shadow_paint.set_anti_alias(true);
        shadow_paint.set_color(Color::from_argb(
            shadow_color[3],
            shadow_color[0],
            shadow_color[1],
            shadow_color[2],
        ));
        shadow_paint.set_mask_filter(MaskFilter::blur(
            BlurStyle::Normal,
            shadow_blur * 0.5,
            false,
        ));
        let shadow_rect = RRect::new_rect_xy(
            Rect::from_xywh(x + shadow_offset.0, y + shadow_offset.1, w, h),
            corner_radius,
            corner_radius,
        );
        canvas.draw_rrect(shadow_rect, &shadow_paint);

        let colors = [
            Color::from_argb(
                gradient[0].1[3],
                gradient[0].1[0],
                gradient[0].1[1],
                gradient[0].1[2],
            ),
            Color::from_argb(
                gradient[1].1[3],
                gradient[1].1[0],
                gradient[1].1[1],
                gradient[1].1[2],
            ),
        ];
        let stops = [gradient[0].0, gradient[1].0];
        let p1 = Point::new(x, y);
        let p2 = Point::new(x + w, y + h);
        let shader = gradient_shader::linear(
            (p1, p2),
            gradient_shader::GradientShaderColors::Colors(&colors),
            Some(&stops[..]),
            TileMode::Clamp,
            None,
            None,
        );
        let mut fill = Paint::default();
        fill.set_anti_alias(true);
        fill.set_style(Style::Fill);
        fill.set_shader(shader);
        canvas.draw_rrect(rrect, &fill);
    }

    pub fn draw_filled_circle(&mut self, cx: f32, cy: f32, r: f32, color: [u8; 4]) {
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_color(Color::from_argb(color[3], color[0], color[1], color[2]));
        self.surface.canvas().draw_circle((cx, cy), r, &paint);
    }

    /// Solid-color fill of an SVG path. Used by the butterfly demo and
    /// any caller building custom geometry from Python.
    pub fn fill_path_solid(&mut self, svg_d: &str, color: [u8; 4]) {
        let Some(path) = skia_safe::utils::parse_path::from_svg(svg_d) else {
            return;
        };
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_color(Color::from_argb(color[3], color[0], color[1], color[2]));
        self.surface.canvas().draw_path(&path, &paint);
    }

    /// Linear-gradient fill of an SVG path, with two stops.
    pub fn fill_path_linear_gradient(
        &mut self,
        svg_d: &str,
        p1: (f32, f32),
        p2: (f32, f32),
        start_color: [u8; 4],
        end_color: [u8; 4],
    ) {
        let Some(path) = skia_safe::utils::parse_path::from_svg(svg_d) else {
            return;
        };
        let colors = [
            Color::from_argb(
                start_color[3],
                start_color[0],
                start_color[1],
                start_color[2],
            ),
            Color::from_argb(end_color[3], end_color[0], end_color[1], end_color[2]),
        ];
        let shader = gradient_shader::linear(
            (Point::new(p1.0, p1.1), Point::new(p2.0, p2.1)),
            gradient_shader::GradientShaderColors::Colors(&colors),
            None,
            TileMode::Clamp,
            None,
            None,
        );
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_style(Style::Fill);
        paint.set_shader(shader);
        self.surface.canvas().draw_path(&path, &paint);
    }

    /// Radial-gradient fill of an SVG path (useful for iridescent body
    /// segments and centred wing highlights).
    pub fn fill_path_radial_gradient(
        &mut self,
        svg_d: &str,
        center: (f32, f32),
        radius: f32,
        start_color: [u8; 4],
        end_color: [u8; 4],
    ) {
        let Some(path) = skia_safe::utils::parse_path::from_svg(svg_d) else {
            return;
        };
        let colors = [
            Color::from_argb(
                start_color[3],
                start_color[0],
                start_color[1],
                start_color[2],
            ),
            Color::from_argb(end_color[3], end_color[0], end_color[1], end_color[2]),
        ];
        let shader = gradient_shader::radial(
            Point::new(center.0, center.1),
            radius,
            gradient_shader::GradientShaderColors::Colors(&colors),
            None,
            TileMode::Clamp,
            None,
            None,
        );
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_style(Style::Fill);
        paint.set_shader(shader);
        self.surface.canvas().draw_path(&path, &paint);
    }

    /// Stroke an SVG path (used for wing veins).
    pub fn stroke_path(&mut self, svg_d: &str, color: [u8; 4], width: f32) {
        let Some(path) = skia_safe::utils::parse_path::from_svg(svg_d) else {
            return;
        };
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_color(Color::from_argb(color[3], color[0], color[1], color[2]));
        paint.set_style(Style::Stroke);
        paint.set_stroke_width(width);
        paint.set_stroke_cap(skia_safe::paint::Cap::Round);
        paint.set_stroke_join(skia_safe::paint::Join::Round);
        self.surface.canvas().draw_path(&path, &paint);
    }

    /// Push a save state with a [tx, ty, sx, sy, rotation_radians] affine
    /// transform. Pop via `restore`. Lets the butterfly demo mirror the
    /// right wing as `scale_x(-1)` of the left.
    pub fn save_with_transform(&mut self, tx: f32, ty: f32, sx: f32, sy: f32, rotation_rad: f32) {
        let canvas = self.surface.canvas();
        canvas.save();
        canvas.translate((tx, ty));
        if rotation_rad != 0.0 {
            canvas.rotate(rotation_rad.to_degrees(), None);
        }
        canvas.scale((sx, sy));
    }

    pub fn restore(&mut self) {
        self.surface.canvas().restore();
    }

    /// Load a raster image from disk (cached after first decode) and
    /// draw it into the destination rect.
    pub fn draw_image_file(&mut self, path: &str, dst: (f32, f32, f32, f32)) -> bool {
        let Some(image) = self.textures.get_or_load(Path::new(path)) else {
            return false;
        };
        let canvas = self.surface.canvas();
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        // skia-safe 0.78's `draw_image_rect[_with_sampling_options]`
        // partially renders when scaling up a small source into a
        // larger dst at the surface level — fills only the source's
        // intrinsic-height worth of dst rows. Route through an
        // explicit translate+scale canvas transform + draw_image at
        // origin, which goes through Skia's stable matrix path.
        let sx = dst.2 / image.width() as f32;
        let sy = dst.3 / image.height() as f32;
        canvas.save();
        let mut m = skia_safe::Matrix::new_identity();
        m.set_translate((dst.0, dst.1));
        m.pre_scale((sx, sy), None);
        canvas.concat(&m);
        canvas.draw_image(&*image, (0.0, 0.0), Some(&paint));
        canvas.restore();
        true
    }

    /// Draw a raw RGBA8 (premultiplied) byte buffer at a destination
    /// rect. Skips the texture cache — used by WebView snapshots and
    /// dynamically generated textures whose contents change every frame.
    pub fn draw_image_bytes(
        &mut self,
        rgba: &[u8],
        w: u32,
        h: u32,
        dst: (f32, f32, f32, f32),
    ) -> bool {
        if rgba.len() < (w as usize) * (h as usize) * 4 {
            return false;
        }
        let info = skia_safe::ImageInfo::new(
            (w as i32, h as i32),
            skia_safe::ColorType::RGBA8888,
            skia_safe::AlphaType::Premul,
            None,
        );
        let data = skia_safe::Data::new_copy(rgba);
        let row_bytes = (w as usize) * 4;
        let Some(image) = skia_safe::images::raster_from_data(&info, data, row_bytes) else {
            return false;
        };
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        let dst_rect = Rect::from_xywh(dst.0, dst.1, dst.2, dst.3);
        let sampling = SamplingOptions::from(skia_safe::CubicResampler::mitchell());
        self.surface
            .canvas()
            .draw_image_rect_with_sampling_options(&image, None, dst_rect, sampling, &paint);
        true
    }

    /// Draw a cached image with an arbitrary affine transform built up
    /// from the canvas save/translate/rotate/scale stack. Used by the
    /// animated-butterfly demo to flap each wing independently.
    pub fn draw_image_file_transformed(
        &mut self,
        path: &str,
        dst: (f32, f32, f32, f32),
        anchor: (f32, f32),
        translate: (f32, f32),
        scale: (f32, f32),
        rotation_rad: f32,
    ) -> bool {
        let Some(image) = self.textures.get_or_load(Path::new(path)) else {
            return false;
        };
        let canvas = self.surface.canvas();
        canvas.save();
        canvas.translate((translate.0, translate.1));
        // Anchor-relative rotate + scale.
        canvas.translate((anchor.0, anchor.1));
        if rotation_rad != 0.0 {
            canvas.rotate(rotation_rad.to_degrees(), None);
        }
        canvas.scale((scale.0, scale.1));
        canvas.translate((-anchor.0, -anchor.1));

        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        let dst_rect = Rect::from_xywh(dst.0, dst.1, dst.2, dst.3);
        let sampling = SamplingOptions::from(skia_safe::CubicResampler::mitchell());
        canvas.draw_image_rect_with_sampling_options(&*image, None, dst_rect, sampling, &paint);
        canvas.restore();
        true
    }

    /// Draw only a sub-rectangle of a cached image into the destination
    /// rect. Lets a single butterfly atlas image contribute the left
    /// wing, the right wing, and the body as three independently
    /// animated sub-images.
    pub fn draw_image_file_region(
        &mut self,
        path: &str,
        src: (f32, f32, f32, f32),
        dst: (f32, f32, f32, f32),
    ) -> bool {
        let Some(image) = self.textures.get_or_load(Path::new(path)) else {
            return false;
        };
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        let src_rect = Rect::from_xywh(src.0, src.1, src.2, src.3);
        let dst_rect = Rect::from_xywh(dst.0, dst.1, dst.2, dst.3);
        let sampling = SamplingOptions::from(skia_safe::CubicResampler::mitchell());
        self.surface.canvas().draw_image_rect_with_sampling_options(
            &*image,
            Some((&src_rect, skia_safe::canvas::SrcRectConstraint::Strict)),
            dst_rect,
            sampling,
            &paint,
        );
        true
    }

    /// Preload an image asynchronously: decode happens NOW (synchronously)
    /// but the call returns `true` once cached so subsequent draws are
    /// pure GPU work. Call this at app startup for hot textures.
    pub fn preload_image(&self, path: &str) -> bool {
        self.textures.get_or_load(Path::new(path)).is_some()
    }

    /// Draw a string of text. `x, y` is the baseline left of the first
    /// glyph (Skia convention). `size` is in canvas pixels.
    pub fn draw_text(&mut self, text: &str, x: f32, y: f32, size: f32, color: [u8; 4]) {
        let font = default_font(size);
        let mut paint = Paint::default();
        paint.set_anti_alias(true);
        paint.set_color(Color::from_argb(color[3], color[0], color[1], color[2]));
        self.surface.canvas().draw_str(text, (x, y), &font, &paint);
    }

    /// Measure a text run; returns (width, ascent, descent).
    pub fn measure_text(&self, text: &str, size: f32) -> (f32, f32, f32) {
        let font = default_font(size);
        let (advance, _bounds) = font.measure_str(text, None);
        let metrics = font.metrics();
        // Skia returns negative ascent (going up); flip sign for the
        // caller-friendly form.
        (advance, -metrics.1.ascent, metrics.1.descent)
    }

    /// Draw wrapped multi-line text using Skia's textlayout::Paragraph.
    /// `max_width` controls the line-wrap width; `align`: 0=left, 1=right,
    /// 2=center, 3=justify. Returns the resulting block height in pixels.
    #[allow(clippy::too_many_arguments)] // mirrors the rich Skia paragraph API
    pub fn draw_paragraph(
        &mut self,
        text: &str,
        x: f32,
        y: f32,
        max_width: f32,
        size: f32,
        color: [u8; 4],
        align: i32,
        font_family: &str,
        weight: i32,
        variation_axes: &[(String, f32)],
        rtl: bool,
        tabular: bool,
    ) -> f32 {
        use skia_safe::font_arguments::variation_position::Coordinate;
        use skia_safe::textlayout::{
            FontCollection, ParagraphBuilder, ParagraphStyle, TextAlign, TextDirection, TextStyle,
        };
        use skia_safe::{font_style::Weight, FontArguments};
        let mut font_collection = FontCollection::new();
        font_collection.set_default_font_manager(skia_safe::FontMgr::new(), None);

        let mut ps = ParagraphStyle::new();
        ps.set_text_direction(if rtl {
            TextDirection::RTL
        } else {
            TextDirection::LTR
        });
        ps.set_text_align(match align {
            1 => TextAlign::Right,
            2 => TextAlign::Center,
            3 => TextAlign::Justify,
            _ => TextAlign::Left,
        });

        let mut ts = TextStyle::new();
        ts.set_font_size(size);
        ts.set_color(Color::from_argb(color[3], color[0], color[1], color[2]));
        if !font_family.is_empty() {
            ts.set_font_families(&[font_family]);
        }
        if weight > 0 {
            let mut fs = ts.font_style();
            fs = skia_safe::FontStyle::new(Weight::from(weight), fs.width(), fs.slant());
            ts.set_font_style(fs);
        }
        // Variable-font axis coordinates (wght / wdth / slnt / ital / opsz …).
        if !variation_axes.is_empty() {
            let coords: Vec<Coordinate> = variation_axes
                .iter()
                .map(|(tag, val)| {
                    let bytes = tag.as_bytes();
                    let mut t = [0u8; 4];
                    for (i, b) in bytes.iter().take(4).enumerate() {
                        t[i] = *b;
                    }
                    Coordinate {
                        axis: u32::from_be_bytes(t).into(),
                        value: *val,
                    }
                })
                .collect();
            let args = FontArguments::new().set_variation_design_position(
                skia_safe::font_arguments::VariationPosition {
                    coordinates: &coords,
                },
            );
            ts.set_font_arguments(Some(&args));
        }
        // Tabular + lining numerals so figures align across rows/columns.
        if tabular {
            ts.add_font_feature("tnum", 1);
            ts.add_font_feature("lnum", 1);
        }

        let mut builder = ParagraphBuilder::new(&ps, &font_collection);
        builder.push_style(&ts);
        builder.add_text(text);
        builder.pop();
        let mut paragraph = builder.build();
        paragraph.layout(max_width);
        paragraph.paint(self.surface.canvas(), Point::new(x, y));
        paragraph.height()
    }

    /// Measure paragraph height for a given width without drawing.
    pub fn measure_paragraph(&self, text: &str, max_width: f32, size: f32) -> f32 {
        use skia_safe::textlayout::{FontCollection, ParagraphBuilder, ParagraphStyle, TextStyle};
        let mut font_collection = FontCollection::new();
        font_collection.set_default_font_manager(skia_safe::FontMgr::new(), None);
        let ps = ParagraphStyle::new();
        let mut ts = TextStyle::new();
        ts.set_font_size(size);
        let mut builder = ParagraphBuilder::new(&ps, &font_collection);
        builder.push_style(&ts);
        builder.add_text(text);
        builder.pop();
        let mut paragraph = builder.build();
        paragraph.layout(max_width);
        paragraph.height()
    }

    /// Frosted-glass card: backdrop-blur the area under the rounded rect,
    /// tint with the given color, then draw a thin 1px stroke for the
    /// glass edge. Matches the spec's `frosted_glass(radius, tint)` effect.
    pub fn draw_frosted_panel(
        &mut self,
        bounds: (f32, f32, f32, f32),
        corner_radius: f32,
        blur_sigma: f32,
        tint: [u8; 4],
        border: Option<[u8; 4]>,
    ) {
        use skia_safe::{image_filters, ClipOp, SamplingOptions};

        let canvas = self.surface.canvas();
        let (x, y, w, h) = bounds;
        let rect = Rect::from_xywh(x, y, w, h);
        let rrect = RRect::new_rect_xy(rect, corner_radius, corner_radius);

        canvas.save();
        canvas.clip_rrect(rrect, Some(ClipOp::Intersect), Some(true));

        // Blur the existing backdrop into a snapshot, then re-draw it
        // inside the clip — that's the glass.
        let blur = image_filters::blur((blur_sigma, blur_sigma), None, None, None);
        let mut blur_paint = Paint::default();
        blur_paint.set_image_filter(blur);
        canvas.save_layer(&skia_safe::canvas::SaveLayerRec::default().paint(&blur_paint));
        canvas.restore();

        // Tint mix.
        let mut tint_paint = Paint::default();
        tint_paint.set_anti_alias(true);
        tint_paint.set_color(Color::from_argb(tint[3], tint[0], tint[1], tint[2]));
        canvas.draw_rect(rect, &tint_paint);

        canvas.restore();

        if let Some(b) = border {
            let mut stroke = Paint::default();
            stroke.set_anti_alias(true);
            stroke.set_color(Color::from_argb(b[3], b[0], b[1], b[2]));
            stroke.set_style(Style::Stroke);
            stroke.set_stroke_width(1.0);
            canvas.draw_rrect(rrect, &stroke);
        }
        // suppress unused-import warning when sampling is unused
        let _ = SamplingOptions::default();
    }

    /// Snapshot the Skia surface into `self.pixels` in BGRA8 layout (which
    /// is what wgpu's surface format expects on Metal / D3D / most Vulkan).
    /// Returns true on success.
    pub fn snapshot_bgra(&mut self) -> bool {
        let info = ImageInfo::new(
            (self.width as i32, self.height as i32),
            skia_safe::ColorType::BGRA8888,
            skia_safe::AlphaType::Premul,
            None,
        );
        self.surface
            .read_pixels(&info, &mut self.pixels, self.row_bytes, (0, 0))
    }

    /// Walk a `DisplayList` and dispatch each command to the appropriate
    /// painting method. Used by the live render path to consume work
    /// published from Python via the triple-buffered command queue.
    pub fn execute(&mut self, list: &ely_core::DisplayList) {
        self.execute_with_anim(list, None);
    }

    /// Same as `execute`, but substitutes live tween values from `anim`
    /// into any `PushTransform` whose `anim_slot` is set. Called by the
    /// render thread; Python code uses the simpler `execute`.
    pub fn execute_with_anim(
        &mut self,
        list: &ely_core::DisplayList,
        anim: Option<&ely_core::AnimRegistry>,
    ) {
        use ely_core::display_list::DrawCommand as C;
        for cmd in &list.commands {
            match cmd {
                C::Clear { color } => self.clear(*color),
                C::GradientCard {
                    bounds,
                    corner_radius,
                    start_color,
                    end_color,
                    shadow_blur,
                    shadow_offset,
                    shadow_color,
                } => {
                    self.draw_gradient_card(
                        (bounds[0], bounds[1], bounds[2], bounds[3]),
                        *corner_radius,
                        [(0.0, *start_color), (1.0, *end_color)],
                        *shadow_blur,
                        (shadow_offset[0], shadow_offset[1]),
                        *shadow_color,
                    );
                }
                C::FrostedPanel {
                    bounds,
                    corner_radius,
                    blur_sigma,
                    tint,
                    border,
                } => {
                    self.draw_frosted_panel(
                        (bounds[0], bounds[1], bounds[2], bounds[3]),
                        *corner_radius,
                        *blur_sigma,
                        *tint,
                        *border,
                    );
                }
                C::FilledCircle { cx, cy, r, color } => {
                    self.draw_filled_circle(*cx, *cy, *r, *color);
                }
                C::PushTransform {
                    tx,
                    ty,
                    sx,
                    sy,
                    rotation,
                    anim_slot,
                } => {
                    let (mut atx, mut aty, mut asx, mut asy, mut arot, mut alpha) =
                        (*tx, *ty, *sx, *sy, *rotation, 1.0_f32);
                    if let (Some(id), Some(reg)) = (anim_slot, anim) {
                        if let Some(v) = reg.evaluate(*id) {
                            atx += v.tx;
                            aty += v.ty;
                            asx *= v.sx;
                            asy *= v.sy;
                            arot += v.rotation;
                            alpha = v.alpha;
                        }
                    }
                    self.save_with_transform(atx, aty, asx, asy, arot);
                    let _ = alpha; // alpha-blend hook reserved for paint sites
                }
                C::PopTransform => self.restore(),
                C::PushClip { x, y, w, h } => {
                    // Save canvas state, then intersect the clip. The
                    // matching PopClip restores (also unwinding any nested
                    // transforms), so ScrollView content stays in its rect.
                    self.surface.canvas().save();
                    self.clip_rect(*x, *y, *w, *h);
                }
                C::PopClip => self.restore(),
                C::FillPath { d, color } => self.fill_path_solid(d, *color),
                C::FillPathLinearGradient {
                    d,
                    p1,
                    p2,
                    start_color,
                    end_color,
                } => self.fill_path_linear_gradient(
                    d,
                    (p1[0], p1[1]),
                    (p2[0], p2[1]),
                    *start_color,
                    *end_color,
                ),
                C::FillPathRadialGradient {
                    d,
                    center,
                    radius,
                    start_color,
                    end_color,
                } => self.fill_path_radial_gradient(
                    d,
                    (center[0], center[1]),
                    *radius,
                    *start_color,
                    *end_color,
                ),
                C::StrokePath { d, color, width } => self.stroke_path(d, *color, *width),
                C::DrawImageFile { path, dst } => {
                    self.draw_image_file(path, (dst[0], dst[1], dst[2], dst[3]));
                }
                C::DrawImageBytes {
                    rgba,
                    width,
                    height,
                    dst,
                } => {
                    self.draw_image_bytes(rgba, *width, *height, (dst[0], dst[1], dst[2], dst[3]));
                }
                C::DrawImageFileTransformed {
                    path,
                    dst,
                    anchor,
                    translate,
                    scale,
                    rotation_rad,
                } => {
                    self.draw_image_file_transformed(
                        path,
                        (dst[0], dst[1], dst[2], dst[3]),
                        (anchor[0], anchor[1]),
                        (translate[0], translate[1]),
                        (scale[0], scale[1]),
                        *rotation_rad,
                    );
                }
                C::DrawImageFileRegion { path, src, dst } => {
                    self.draw_image_file_region(
                        path,
                        (src[0], src[1], src[2], src[3]),
                        (dst[0], dst[1], dst[2], dst[3]),
                    );
                }
                C::DrawText {
                    text,
                    x,
                    y,
                    size,
                    color,
                } => {
                    self.draw_text(text, *x, *y, *size, *color);
                }
                C::DrawParagraph {
                    text,
                    x,
                    y,
                    max_width,
                    size,
                    color,
                    align,
                    font_family,
                    weight,
                    variation_axes,
                    rtl,
                    tabular,
                } => {
                    self.draw_paragraph(
                        text,
                        *x,
                        *y,
                        *max_width,
                        *size,
                        *color,
                        *align,
                        font_family,
                        *weight,
                        variation_axes,
                        *rtl,
                        *tabular,
                    );
                }
                C::SkslEffect {
                    src,
                    dst,
                    corner_radius,
                    uniforms,
                } => {
                    self.apply_skia_effect(
                        src,
                        (dst[0], dst[1], dst[2], dst[3]),
                        *corner_radius,
                        uniforms,
                    );
                }
            }
        }
    }

    /// Snapshot the Skia surface as a PNG-encoded byte vector. Useful for
    /// headless visual-regression tests.
    pub fn encode_png(&mut self) -> Option<Vec<u8>> {
        let image = self.surface.image_snapshot();
        let data = image.encode(None, skia_safe::EncodedImageFormat::PNG, None)?;
        Some(data.as_bytes().to_vec())
    }
}

#[cfg(test)]
mod text_shaping_tests {
    use super::{font_vmetrics, measure_text_run, text_caret_x, text_hit_index};

    const SZ: f32 = 16.0;

    #[test]
    fn caret_x_monotonic_and_bounded() {
        let s = "hello world";
        let n = s.chars().count();
        // caret(0) is 0; caret advances monotonically; caret(n) == run width.
        assert_eq!(text_caret_x(s, SZ, 0), 0.0);
        let mut prev = 0.0;
        for i in 1..=n {
            let x = text_caret_x(s, SZ, i);
            assert!(
                x >= prev,
                "caret x must be non-decreasing at {i}: {x} < {prev}"
            );
            prev = x;
        }
        let (width, _, _) = measure_text_run(s, SZ);
        assert!((text_caret_x(s, SZ, n) - width).abs() < 0.5);
        // Over-long index clamps to the end rather than panicking.
        assert!((text_caret_x(s, SZ, n + 50) - width).abs() < 0.5);
    }

    #[test]
    fn hit_index_round_trips_caret() {
        let s = "Editable";
        let n = s.chars().count();
        // Clicking just past each caret position should resolve back to that
        // index (midpoint hit-test: sample a hair past the boundary).
        for i in 0..=n {
            let x = text_caret_x(s, SZ, i);
            let probe = if i == n { x } else { x + 0.5 };
            let hit = text_hit_index(s, SZ, probe);
            assert!(
                (hit as i64 - i as i64).abs() <= 1,
                "hit_index({probe}) = {hit}, expected ~{i}"
            );
        }
        // Negative / left-of-start clamps to 0; far-right clamps to end.
        assert_eq!(text_hit_index(s, SZ, -100.0), 0);
        assert_eq!(text_hit_index(s, SZ, 100_000.0), n);
    }

    #[test]
    fn empty_string_is_safe() {
        assert_eq!(text_caret_x("", SZ, 0), 0.0);
        assert_eq!(text_hit_index("", SZ, 25.0), 0);
        let (w, asc, desc) = measure_text_run("", SZ);
        assert_eq!(w, 0.0);
        assert!(asc >= 0.0 && desc >= 0.0);
    }

    #[test]
    fn vmetrics_positive() {
        let (asc, desc, lh) = font_vmetrics(SZ);
        assert!(asc > 0.0 && desc > 0.0 && lh > 0.0);
        assert!(
            lh >= asc + desc - 1.0,
            "line height should cover ascent+descent"
        );
    }

    #[test]
    fn cjk_codepoints_count_correctly() {
        // CJK is BMP; codepoint indexing must match Python str indexing.
        let s = "日本語ABC"; // 6 codepoints
        assert_eq!(s.chars().count(), 6);
        let (width, _, _) = measure_text_run(s, SZ);
        assert!((text_caret_x(s, SZ, 6) - width).abs() < 0.5);
        // Caret before "A" (index 3) sits left of the run end.
        assert!(text_caret_x(s, SZ, 3) < width);
    }
}
