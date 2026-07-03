use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;

create_exception!(_native, ElysiumError, PyException);
create_exception!(_native, SkinError, ElysiumError);
create_exception!(_native, HookNotFound, ElysiumError);
create_exception!(_native, ShaderValidationError, ElysiumError);
create_exception!(_native, CanvasExpired, ElysiumError);

pub fn register_exceptions(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("ElysiumError", py.get_type::<ElysiumError>())?;
    m.add("SkinError", py.get_type::<SkinError>())?;
    m.add("HookNotFound", py.get_type::<HookNotFound>())?;
    m.add(
        "ShaderValidationError",
        py.get_type::<ShaderValidationError>(),
    )?;
    m.add("CanvasExpired", py.get_type::<CanvasExpired>())?;
    Ok(())
}
