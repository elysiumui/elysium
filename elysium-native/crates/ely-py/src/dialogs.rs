//! Native OS file dialogs (open / save / folder), backed by the `rfd`
//! crate so all three desktop platforms get the real system picker —
//! Cocoa `NSOpenPanel`/`NSSavePanel` on macOS, the Win32 common dialog on
//! Windows, and the XDG desktop portal / GTK chooser on Linux.
//!
//! Replaces the previous macOS-only `objc2` implementation. These are the
//! synchronous `rfd` calls: they block until the user picks or cancels and
//! must be invoked on the process's main thread (the OS dialog drives the
//! main run loop). The Python `elysium.dialogs` layer is responsible for
//! ensuring it calls these from the UI thread (and may fall back to a
//! subprocess picker for off-main-thread callers such as the Designer's
//! animation thread).

use pyo3::prelude::*;

/// Build an extension list (`"svg"`, `"png"`) from glob patterns (`"*.svg"`).
fn exts_from_patterns(patterns: &[String]) -> Vec<String> {
    patterns
        .iter()
        .filter_map(|p| {
            let e = p.rsplit('.').next().unwrap_or("");
            let e = e.trim_start_matches('*').trim_start_matches('.');
            if e.is_empty() || e == "*" {
                None
            } else {
                Some(e.to_string())
            }
        })
        .collect()
}

fn base_dialog(
    title: Option<&str>,
    initial_dir: Option<&str>,
    filter_label: Option<&str>,
    filter_patterns: Option<&[String]>,
) -> rfd::FileDialog {
    let mut d = rfd::FileDialog::new();
    if let Some(t) = title {
        d = d.set_title(t);
    }
    if let Some(dir) = initial_dir {
        d = d.set_directory(dir);
    }
    if let Some(pats) = filter_patterns {
        let exts = exts_from_patterns(pats);
        if !exts.is_empty() {
            let refs: Vec<&str> = exts.iter().map(String::as_str).collect();
            d = d.add_filter(filter_label.unwrap_or("Files"), &refs);
        }
    }
    d
}

/// Open a file. Returns the chosen absolute path, or `None` on cancel.
/// `filter_patterns` are globs like `["*.svg", "*.png"]`. `save=true` routes
/// to the save panel (kept for backward-compat with the previous combined
/// entry point; prefer `save_file_dialog`).
#[pyfunction]
#[pyo3(signature = (title=None, initial_dir=None, filter_label=None, filter_patterns=None, save=false))]
pub fn open_file_dialog(
    title: Option<String>,
    initial_dir: Option<String>,
    filter_label: Option<String>,
    filter_patterns: Option<Vec<String>>,
    save: bool,
) -> PyResult<Option<String>> {
    let d = base_dialog(
        title.as_deref(),
        initial_dir.as_deref(),
        filter_label.as_deref(),
        filter_patterns.as_deref(),
    );
    let picked = if save { d.save_file() } else { d.pick_file() };
    Ok(picked.map(|p| p.to_string_lossy().into_owned()))
}

/// Save-file dialog. Returns the chosen path (may not yet exist) or `None`.
#[pyfunction]
#[pyo3(signature = (title=None, initial_dir=None, default_name=None, filter_label=None, filter_patterns=None))]
pub fn save_file_dialog(
    title: Option<String>,
    initial_dir: Option<String>,
    default_name: Option<String>,
    filter_label: Option<String>,
    filter_patterns: Option<Vec<String>>,
) -> PyResult<Option<String>> {
    let mut d = base_dialog(
        title.as_deref(),
        initial_dir.as_deref(),
        filter_label.as_deref(),
        filter_patterns.as_deref(),
    );
    if let Some(name) = default_name {
        d = d.set_file_name(name);
    }
    Ok(d.save_file().map(|p| p.to_string_lossy().into_owned()))
}

/// Folder-picker dialog. Returns the chosen directory or `None`.
#[pyfunction]
#[pyo3(signature = (title=None, initial_dir=None))]
pub fn pick_folder(title: Option<String>, initial_dir: Option<String>) -> PyResult<Option<String>> {
    let d = base_dialog(title.as_deref(), initial_dir.as_deref(), None, None);
    Ok(d.pick_folder().map(|p| p.to_string_lossy().into_owned()))
}

/// Tight bounds `(x, y, w, h)` of an SVG path string. Unrelated to file
/// dialogs but historically lived here; kept for existing callers.
#[pyfunction]
pub fn path_bounds(d: &str) -> PyResult<(f32, f32, f32, f32)> {
    let p = skia_safe::utils::parse_path::from_svg(d)
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("invalid SVG path"))?;
    let b = p.compute_tight_bounds();
    Ok((b.left, b.top, b.width(), b.height()))
}
