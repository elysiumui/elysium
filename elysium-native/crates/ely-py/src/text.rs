//! Stateless text-shaping primitives exposed to Python for caret placement,
//! selection geometry, and click-to-position in editable text widgets.
//!
//! All indices are Unicode *codepoint* indices, matching Python `str`
//! semantics (`len(s)`, `s[i]`), so the Python text-editing layer
//! (`elysium.text.edit`) can pass `str` slices and caret positions directly
//! with no byte/UTF-16 conversion. These functions need no GPU surface —
//! they measure against the platform default font only, so they're cheap
//! enough to call per-frame for a focused field.

use pyo3::prelude::*;

/// Vertical font metrics at `size`: `(ascent, descent, line_height)` in
/// positive pixels. Use `ascent` to place the caret top above the baseline
/// and `descent` below; `line_height` is the per-line advance for multi-line
/// layout.
#[pyfunction]
pub fn font_vmetrics(size: f32) -> (f32, f32, f32) {
    ely_render::font_vmetrics(size)
}

/// Advance width of `text` at `size`, plus `(ascent, descent)`. Surface-free
/// equivalent of `SkiaLayer.measure_text`.
#[pyfunction]
pub fn measure_text_run(text: &str, size: f32) -> (f32, f32, f32) {
    ely_render::measure_text_run(text, size)
}

/// X-offset (px from the run's left edge) of the caret positioned *before*
/// codepoint `char_index`. `char_index` is clamped to `[0, len(text)]`;
/// `len(text)` yields the caret-at-end position.
#[pyfunction]
pub fn text_caret_x(text: &str, size: f32, char_index: usize) -> f32 {
    ely_render::text_caret_x(text, size, char_index)
}

/// Codepoint index nearest x-coordinate `px` (px from the run's left edge) —
/// the inverse of `text_caret_x`, for click/drag caret placement. Returns a
/// value in `[0, len(text)]`.
#[pyfunction]
pub fn text_hit_index(text: &str, size: f32, px: f32) -> usize {
    ely_render::text_hit_index(text, size, px)
}

/// Set the app-wide UI font family by name (matched against installed fonts).
/// Empty string clears the preference. Affects all `draw_text` rendering +
/// the shaping primitives above, so caret geometry stays consistent.
#[pyfunction]
pub fn set_ui_font(family: &str) {
    ely_render::set_ui_font_family(family);
}

/// Register a UI font from a TTF/OTF file so it is used regardless of what is
/// installed on the machine. Returns True on success.
#[pyfunction]
pub fn register_ui_font(path: &str) -> bool {
    ely_render::register_ui_font_from_file(path)
}
