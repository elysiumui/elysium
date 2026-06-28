//! Headless wgpu compute path for the PBR mesh renderer.
//!
//! Owns its own `wgpu::Instance` + `Device` + `Queue` (independent of the
//! present surface) and dispatches the WGSL shader at
//! `shaders/pbr_compute.wgsl` over a flat triangle mesh + median-split BVH.
//! Returns an RGBA8 buffer the caller can hand to whatever downstream
//! consumer wants it (Skia atlas, PNG encoder, etc.).
//!
//! This is the offscreen first half of the wgpu compute port. A future
//! pass will fuse it with the present pipeline so we render directly into
//! a swapchain texture instead of reading back to system memory.

use bytemuck::{Pod, Zeroable};
use std::sync::Arc;

#[repr(C)]
#[derive(Copy, Clone, Debug, Pod, Zeroable)]
pub struct Uniforms {
    pub cam_pos: [f32; 4],
    pub cam_look: [f32; 4],
    pub cam_right: [f32; 4],
    pub cam_up: [f32; 4],
    pub sun_dir: [f32; 4],
    pub sun_color: [f32; 4],
    pub fill_dir: [f32; 4],
    pub fill_color: [f32; 4],
    pub size: [u32; 2],
    pub fov_scale: f32,
    pub aspect: f32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug, Pod, Zeroable)]
pub struct GpuMaterial {
    pub base_color: [f32; 4],
    pub params: [f32; 4], // (metallic, roughness, specular, clearcoat)
    pub emissive: [f32; 4],
    pub cc: [f32; 4],
}

pub struct ComputePbr {
    device: Arc<wgpu::Device>,
    queue: Arc<wgpu::Queue>,
    pipeline: wgpu::ComputePipeline,
    layout: wgpu::BindGroupLayout,
}

const SHADER_SRC: &str = include_str!("shaders/pbr_compute.wgsl");

impl ComputePbr {
    /// Spin up an independent wgpu device that supports storage buffers
    /// and storage textures. Returns `None` on adapters that don't expose
    /// the required features.
    pub fn new() -> Option<Self> {
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::PRIMARY,
            flags: wgpu::InstanceFlags::default(),
            dx12_shader_compiler: wgpu::Dx12Compiler::default(),
            gles_minor_version: wgpu::Gles3MinorVersion::default(),
        });
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            force_fallback_adapter: false,
            compatible_surface: None,
        }))?;
        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor {
                label: Some("elysium-compute-pbr-device"),
                required_features: wgpu::Features::empty(),
                required_limits: wgpu::Limits::default(),
                memory_hints: wgpu::MemoryHints::default(),
            },
            None,
        ))
        .ok()?;
        let device = Arc::new(device);
        let queue = Arc::new(queue);

        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pbr_compute.wgsl"),
            source: wgpu::ShaderSource::Wgsl(SHADER_SRC.into()),
        });

        let layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("pbr_compute_bgl"),
            entries: &[
                // 0 uniforms
                bgl_entry(
                    0,
                    wgpu::BindingType::Buffer {
                        ty: wgpu::BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                ),
                // 1..8 storage buffers (read-only)
                bgl_entry(1, sb_read()),
                bgl_entry(2, sb_read()),
                bgl_entry(3, sb_read()),
                bgl_entry(4, sb_read()),
                bgl_entry(5, sb_read()),
                bgl_entry(6, sb_read()),
                bgl_entry(7, sb_read()),
                bgl_entry(8, sb_read()),
                // 9 storage texture (write-only rgba8unorm)
                wgpu::BindGroupLayoutEntry {
                    binding: 9,
                    visibility: wgpu::ShaderStages::COMPUTE,
                    ty: wgpu::BindingType::StorageTexture {
                        access: wgpu::StorageTextureAccess::WriteOnly,
                        format: wgpu::TextureFormat::Rgba8Unorm,
                        view_dimension: wgpu::TextureViewDimension::D2,
                    },
                    count: None,
                },
            ],
        });
        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("pbr_compute_pl"),
            bind_group_layouts: &[&layout],
            push_constant_ranges: &[],
        });
        let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
            label: Some("pbr_compute_pipeline"),
            layout: Some(&pipeline_layout),
            module: &shader,
            entry_point: "cs_render",
            compilation_options: Default::default(),
            cache: None,
        });

        Some(Self {
            device,
            queue,
            pipeline,
            layout,
        })
    }

    /// Dispatch the compute shader over `(w, h)` and return an RGBA8 buffer.
    ///
    /// `verts` is xyz-padded vec4s, `faces` is (v0, v1, v2, mat_idx) per
    /// triangle, `normals` is the face normal as xyz-padded vec4s, the
    /// `bvh_*` slices come from the same builder used by the Python
    /// reference path tracer.
    #[allow(clippy::too_many_arguments)]
    pub fn render(
        &self,
        w: u32,
        h: u32,
        uniforms: Uniforms,
        verts_xyz4: &[[f32; 4]],
        faces_v3i1: &[[u32; 4]],
        normals_xyz4: &[[f32; 4]],
        bvh_min: &[[f32; 4]],
        bvh_max: &[[f32; 4]],
        bvh_meta: &[[i32; 4]],
        tri_order: &[u32],
        materials: &[GpuMaterial],
    ) -> Vec<u8> {
        let device = &self.device;
        let queue = &self.queue;

        use wgpu::util::DeviceExt as _;
        let mk = |bytes: &[u8], label: &str, usage: wgpu::BufferUsages| -> wgpu::Buffer {
            device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some(label),
                contents: bytes,
                usage,
            })
        };
        let uni_buf = mk(
            bytemuck::cast_slice(&[uniforms]),
            "uniforms",
            wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        );
        let verts_buf = mk(bytemuck::cast_slice(verts_xyz4), "verts", storage_usage());
        let faces_buf = mk(bytemuck::cast_slice(faces_v3i1), "faces", storage_usage());
        let normals_buf = mk(
            bytemuck::cast_slice(normals_xyz4),
            "normals",
            storage_usage(),
        );
        let bmin_buf = mk(bytemuck::cast_slice(bvh_min), "bvh_min", storage_usage());
        let bmax_buf = mk(bytemuck::cast_slice(bvh_max), "bvh_max", storage_usage());
        let bmeta_buf = mk(bytemuck::cast_slice(bvh_meta), "bvh_meta", storage_usage());
        let tri_buf = mk(
            bytemuck::cast_slice(tri_order),
            "tri_order",
            storage_usage(),
        );
        let mat_buf = mk(
            bytemuck::cast_slice(materials),
            "materials",
            storage_usage(),
        );

        let tex = device.create_texture(&wgpu::TextureDescriptor {
            label: Some("pbr_compute_out"),
            size: wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Rgba8Unorm,
            usage: wgpu::TextureUsages::STORAGE_BINDING | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let view = tex.create_view(&wgpu::TextureViewDescriptor::default());

        let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("pbr_compute_bg"),
            layout: &self.layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: uni_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: verts_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 2,
                    resource: faces_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 3,
                    resource: normals_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 4,
                    resource: bmin_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 5,
                    resource: bmax_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 6,
                    resource: bmeta_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 7,
                    resource: tri_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 8,
                    resource: mat_buf.as_entire_binding(),
                },
                wgpu::BindGroupEntry {
                    binding: 9,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
            ],
        });

        // Readback buffer — wgpu requires bytes-per-row aligned to 256.
        let bpp = 4u32;
        let unpadded = w * bpp;
        let align = wgpu::COPY_BYTES_PER_ROW_ALIGNMENT;
        let padded = unpadded.div_ceil(align) * align;
        let readback = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("pbr_readback"),
            size: (padded * h) as u64,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let mut enc = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("pbr_compute_enc"),
        });
        {
            let mut cp = enc.begin_compute_pass(&wgpu::ComputePassDescriptor {
                label: Some("pbr_compute_pass"),
                timestamp_writes: None,
            });
            cp.set_pipeline(&self.pipeline);
            cp.set_bind_group(0, &bind_group, &[]);
            let gx = w.div_ceil(8);
            let gy = h.div_ceil(8);
            cp.dispatch_workgroups(gx, gy, 1);
        }
        enc.copy_texture_to_buffer(
            wgpu::ImageCopyTexture {
                texture: &tex,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::ImageCopyBuffer {
                buffer: &readback,
                layout: wgpu::ImageDataLayout {
                    offset: 0,
                    bytes_per_row: Some(padded),
                    rows_per_image: Some(h),
                },
            },
            wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
        );
        queue.submit(std::iter::once(enc.finish()));

        let slice = readback.slice(..);
        let (tx, rx) = std::sync::mpsc::channel();
        slice.map_async(wgpu::MapMode::Read, move |r| {
            let _ = tx.send(r);
        });
        device.poll(wgpu::Maintain::Wait);
        let _ = rx.recv();
        let data = slice.get_mapped_range();

        // De-pad rows.
        let mut out = vec![0u8; (unpadded * h) as usize];
        for row in 0..h {
            let src = (row * padded) as usize;
            let dst = (row * unpadded) as usize;
            out[dst..dst + unpadded as usize].copy_from_slice(&data[src..src + unpadded as usize]);
        }
        drop(data);
        readback.unmap();
        out
    }
}

fn bgl_entry(binding: u32, ty: wgpu::BindingType) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry {
        binding,
        visibility: wgpu::ShaderStages::COMPUTE,
        ty,
        count: None,
    }
}

fn sb_read() -> wgpu::BindingType {
    wgpu::BindingType::Buffer {
        ty: wgpu::BufferBindingType::Storage { read_only: true },
        has_dynamic_offset: false,
        min_binding_size: None,
    }
}

fn storage_usage() -> wgpu::BufferUsages {
    wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST
}
