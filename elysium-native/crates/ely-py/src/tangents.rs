use pyo3::{exceptions::PyValueError, prelude::*};

extern "C" {
    fn ely_corner_tangents(
        count: i32,
        offsets: *const i32,
        positions: *const f32,
        normals: *const f32,
        uvs: *const f32,
        out: *mut f32,
    ) -> i32;
}

/// Generate independent tangent/sign values for triangle and quad corners.
#[pyfunction]
pub fn mesh_corner_tangents(
    py: Python<'_>,
    counts: Vec<usize>,
    positions: Vec<[f32; 3]>,
    normals: Vec<[f32; 3]>,
    uvs: Vec<[f32; 2]>,
) -> PyResult<Vec<[f32; 4]>> {
    let bad = || {
        PyValueError::new_err(
            "Tangents require finite triangle/quad corner data (at most 2,000,000 corners)",
        )
    };
    if counts.len() > 666_666 || counts.iter().any(|&n| n != 3 && n != 4) {
        return Err(bad());
    }
    let corners: usize = counts.iter().sum();
    if corners > 2_000_000
        || positions.len() != corners
        || normals.len() != corners
        || uvs.len() != corners
        || positions
            .iter()
            .flatten()
            .chain(normals.iter().flatten())
            .chain(uvs.iter().flatten())
            .any(|v| !v.is_finite())
        || normals
            .iter()
            .any(|n| n.iter().map(|v| v * v).sum::<f32>() < 1e-20)
    {
        return Err(bad());
    }
    if corners == 0 {
        return Ok(Vec::new());
    }
    let mut offsets = vec![0i32];
    for &n in &counts {
        offsets.push(offsets.last().unwrap() + n as i32);
    }
    let mut out = vec![[0f32; 4]; corners];
    // Validated lengths and offsets bound every callback; arrays remain owned
    // and stationary until the synchronous, thread-safe C routine returns.
    let success = py.allow_threads(|| unsafe {
        ely_corner_tangents(
            counts.len() as i32,
            offsets.as_ptr(),
            positions.as_ptr().cast(),
            normals.as_ptr().cast(),
            uvs.as_ptr().cast(),
            out.as_mut_ptr().cast(),
        )
    });
    if success == 0 || out.iter().flatten().any(|v| !v.is_finite()) {
        return Err(bad());
    }
    Ok(out)
}
