//! Python bindings for the headless wgpu compute PBR renderer.
//!
//! The fast path. Mirrors the API surface of the Python reference
//! implementation in `elysium.render.pbr.render_mesh` but pushes the
//! ray-triangle / BVH / shading work onto the GPU.

use ely_render::compute_pbr::{ComputePbr, GpuMaterial, Uniforms};
use parking_lot::Mutex;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::sync::OnceLock;

static ENGINE: OnceLock<Mutex<Option<ComputePbr>>> = OnceLock::new();

fn engine() -> PyResult<&'static Mutex<Option<ComputePbr>>> {
    Ok(ENGINE.get_or_init(|| Mutex::new(ComputePbr::new())))
}

/// Render a PBR mesh with the wgpu compute path.
///
/// All array arguments are flat `list[float]` / `list[int]` to keep the
/// PyO3 surface dependency-free. Vertex / normal arrays use xyz+pad (4
/// floats per element). Faces use `(v0, v1, v2, mat_idx)` per triangle
/// (4 u32s). Materials use the GpuMaterial layout (16 floats each).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn render_pbr_compute<'py>(
    py: Python<'py>,
    w: u32,
    h: u32,
    uniforms: Vec<f32>, // 32 floats + 2 u32 + 2 f32 packed (see below)
    size_packed: (u32, u32),
    fov_scale: f32,
    aspect: f32,
    verts: Vec<f32>,    // multiple of 4
    faces: Vec<u32>,    // multiple of 4
    normals: Vec<f32>,  // multiple of 4
    bvh_min: Vec<f32>,  // multiple of 4
    bvh_max: Vec<f32>,  // multiple of 4
    bvh_meta: Vec<i32>, // multiple of 4
    tri_order: Vec<u32>,
    materials: Vec<f32>, // multiple of 16
) -> PyResult<Bound<'py, PyBytes>> {
    if uniforms.len() != 32 {
        return Err(PyRuntimeError::new_err(format!(
            "uniforms must be 32 floats, got {}",
            uniforms.len()
        )));
    }
    let u = uniforms;
    let uni = Uniforms {
        cam_pos: [u[0], u[1], u[2], u[3]],
        cam_look: [u[4], u[5], u[6], u[7]],
        cam_right: [u[8], u[9], u[10], u[11]],
        cam_up: [u[12], u[13], u[14], u[15]],
        sun_dir: [u[16], u[17], u[18], u[19]],
        sun_color: [u[20], u[21], u[22], u[23]],
        fill_dir: [u[24], u[25], u[26], u[27]],
        fill_color: [u[28], u[29], u[30], u[31]],
        size: [size_packed.0, size_packed.1],
        fov_scale,
        aspect,
    };

    let verts4: Vec<[f32; 4]> = verts
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let faces4: Vec<[u32; 4]> = faces
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let normals4: Vec<[f32; 4]> = normals
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let bmin4: Vec<[f32; 4]> = bvh_min
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let bmax4: Vec<[f32; 4]> = bvh_max
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let bmeta4: Vec<[i32; 4]> = bvh_meta
        .chunks_exact(4)
        .map(|c| [c[0], c[1], c[2], c[3]])
        .collect();
    let mats: Vec<GpuMaterial> = materials
        .chunks_exact(16)
        .map(|c| GpuMaterial {
            base_color: [c[0], c[1], c[2], c[3]],
            params: [c[4], c[5], c[6], c[7]],
            emissive: [c[8], c[9], c[10], c[11]],
            cc: [c[12], c[13], c[14], c[15]],
        })
        .collect();

    // Engine creation might fail on adapters without compute support.
    let guard = engine()?.lock();
    let eng = guard
        .as_ref()
        .ok_or_else(|| PyRuntimeError::new_err("wgpu compute device unavailable"))?;
    let pixels = py.allow_threads(|| {
        eng.render(
            w, h, uni, &verts4, &faces4, &normals4, &bmin4, &bmax4, &bmeta4, &tri_order, &mats,
        )
    });
    Ok(PyBytes::new(py, &pixels))
}
