use pyo3::prelude::*;

mod app;
mod compute;
mod dialogs;
mod display_list;
mod errors;
mod ipc;
mod menu;
mod path_ops;
mod render;
mod runtime;
mod scene;
mod skia;
mod skin;
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
    m.add_function(wrap_pyfunction!(dialogs::open_file_dialog, m)?)?;
    m.add_function(wrap_pyfunction!(dialogs::path_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(wgsl::validate_wgsl, m)?)?;
    m.add_function(wrap_pyfunction!(compute::render_pbr_compute, m)?)?;

    errors::register_exceptions(py, m)?;

    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
