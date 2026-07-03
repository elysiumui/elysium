// PyO3 binding methods intentionally mirror the rich, multi-parameter
// drawing / window APIs they wrap (gradient cards, paragraphs, transforms),
// so several exceed clippy's 7-arg suggestion. That's by design at the FFI
// boundary; keeping them flat keeps the Python call sites readable.
#![allow(clippy::too_many_arguments)]

use pyo3::prelude::*;

mod app;
mod compute;
mod dialogs;
mod display_list;
mod errors;
mod ipc;
mod menu;
mod native_os;
mod path_ops;
mod render;
mod runtime;
mod scene;
mod skia;
mod skin;
mod text;
mod wgsl;
mod window;

#[pymodule]
fn _native(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    runtime::init_tracing();

    m.add_class::<app::PyApp>()?;
    m.add_class::<window::PyWindow>()?;
    m.add_class::<scene::PyHookProxy>()?;
    m.add_class::<render::PyCanvas>()?;
    m.add_class::<render::PyPath>()?;
    m.add_class::<ipc::PyIpcServer>()?;
    m.add_class::<ipc::PyIpcClient>()?;
    m.add_class::<skia::PySkiaLayer>()?;
    m.add_class::<display_list::PyDisplayList>()?;
    m.add_class::<skin::PySkin>()?;
    m.add_function(wrap_pyfunction!(skin::load_skin, m)?)?;
    m.add_function(wrap_pyfunction!(path_ops::path_op, m)?)?;
    m.add_function(wrap_pyfunction!(menu::poll_menu_action, m)?)?;
    m.add_function(wrap_pyfunction!(menu::set_application_menu, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::single_instance, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::notify, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::tray_create, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::tray_poll, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::hotkey_register, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::hotkey_poll, m)?)?;
    m.add_function(wrap_pyfunction!(native_os::capabilities, m)?)?;
    m.add_function(wrap_pyfunction!(dialogs::open_file_dialog, m)?)?;
    m.add_function(wrap_pyfunction!(dialogs::save_file_dialog, m)?)?;
    m.add_function(wrap_pyfunction!(dialogs::pick_folder, m)?)?;
    m.add_function(wrap_pyfunction!(dialogs::path_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(text::font_vmetrics, m)?)?;
    m.add_function(wrap_pyfunction!(text::measure_text_run, m)?)?;
    m.add_function(wrap_pyfunction!(text::text_caret_x, m)?)?;
    m.add_function(wrap_pyfunction!(text::text_hit_index, m)?)?;
    m.add_function(wrap_pyfunction!(text::set_ui_font, m)?)?;
    m.add_function(wrap_pyfunction!(text::register_ui_font, m)?)?;
    m.add_function(wrap_pyfunction!(wgsl::validate_wgsl, m)?)?;
    m.add_function(wrap_pyfunction!(compute::render_pbr_compute, m)?)?;

    errors::register_exceptions(py, m)?;

    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
