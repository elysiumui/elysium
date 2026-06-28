//! wgpu surface initialization + per-frame present, with a Skia-layer
//! sampling pass on top of the clear.
//!
//! Phase 0 split: `SurfaceRenderer` holds the wgpu side only (Send). The
//! Skia side lives in `crate::render_thread::run_render_thread`, which
//! is spawned by `ely-platform` on its own OS thread and consumes
//! display lists from a `TripleBuffer<DisplayList>`.

use ely_core::Color;
use raw_window_handle::{HasDisplayHandle, HasWindowHandle};
use std::sync::Arc;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SurfaceError {
    #[error("no compatible wgpu adapter")]
    NoAdapter,
    #[error("device request failed: {0}")]
    Device(String),
    #[error("present failed: {0}")]
    Present(String),
    #[error("create_surface: {0}")]
    CreateSurface(String),
}

pub trait SurfaceTarget: HasWindowHandle + HasDisplayHandle + Send + Sync + 'static {
    fn surface_size(&self) -> (u32, u32);
    /// Device pixel ratio. Default 1.0; macOS retina = 2.0.
    fn scale_factor(&self) -> f64 {
        1.0
    }
}

pub struct BlitPipeline {
    pub pipeline: wgpu::RenderPipeline,
    pub bind_group_layout: wgpu::BindGroupLayout,
    pub sampler: wgpu::Sampler,
}

/// Send-able wgpu state. The render thread takes ownership and pumps
/// the swapchain from there.
pub struct SurfaceRenderer {
    pub _instance: wgpu::Instance,
    pub surface: wgpu::Surface<'static>,
    pub device: Arc<wgpu::Device>,
    pub queue: Arc<wgpu::Queue>,
    pub config: wgpu::SurfaceConfiguration,
    /// Held purely for liveness — the surface borrows the window's
    /// raw_window_handle inside its CAMetalLayer / D3D / wl_surface.
    pub _target: Arc<dyn SurfaceTarget>,
    pub blit: BlitPipeline,
    /// Device pixel ratio. Python publishes display lists in logical
    /// pixels; the render thread auto-scales by this factor so the
    /// painted output covers the full physical surface.
    pub scale_factor: f64,
}

impl SurfaceRenderer {
    /// Zero-copy interop: try to allocate a platform-shared backing
    /// surface that Skia and wgpu can both refer to without copying.
    ///
    /// Returns `Some(width, height)` if the allocation succeeded. The
    /// caller can then paint Skia into the shared address (via
    /// `interop::*::skia_surface_for`) and bind the wgpu texture
    /// directly. Returns `None` when the platform / driver does not
    /// support the shared-handle path; the caller should fall back to
    /// `queue.write_texture` upload.
    ///
    /// Currently active on macOS (IOSurface). The Windows + Linux
    /// helpers compile but return `None` until their CI rigs land.
    #[allow(unused_variables)]
    pub fn allocate_shared(&self, width: u32, height: u32) -> Option<(u32, u32)> {
        #[cfg(target_os = "macos")]
        {
            if let Some(_surf) = crate::interop::metal::SharedSurface::new(width, height) {
                return Some((width, height));
            }
        }
        #[cfg(target_os = "windows")]
        {
            if let Some(_surf) = crate::interop::d3d12::SharedSurface::new(width, height) {
                return Some((width, height));
            }
        }
        #[cfg(target_os = "linux")]
        {
            if let Some(_surf) = crate::interop::vulkan::SharedSurface::new(width, height) {
                return Some((width, height));
            }
        }
        None
    }

    pub fn new(target: Arc<dyn SurfaceTarget>) -> Result<Self, SurfaceError> {
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::PRIMARY,
            flags: wgpu::InstanceFlags::default(),
            dx12_shader_compiler: wgpu::Dx12Compiler::default(),
            gles_minor_version: wgpu::Gles3MinorVersion::default(),
        });

        let surface: wgpu::Surface<'static> = unsafe {
            let target_ref: &dyn SurfaceTarget = &*target;
            let raw_window = target_ref
                .window_handle()
                .map_err(|e| SurfaceError::CreateSurface(e.to_string()))?
                .as_raw();
            let raw_display = target_ref
                .display_handle()
                .map_err(|e| SurfaceError::CreateSurface(e.to_string()))?
                .as_raw();
            instance
                .create_surface_unsafe(wgpu::SurfaceTargetUnsafe::RawHandle {
                    raw_display_handle: raw_display,
                    raw_window_handle: raw_window,
                })
                .map_err(|e| SurfaceError::CreateSurface(e.to_string()))?
        };

        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            force_fallback_adapter: false,
            compatible_surface: Some(&surface),
        }))
        .ok_or(SurfaceError::NoAdapter)?;

        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor {
                label: Some("elysium-device"),
                required_features: wgpu::Features::empty(),
                required_limits:
                    wgpu::Limits::downlevel_webgl2_defaults().using_resolution(adapter.limits()),
                memory_hints: wgpu::MemoryHints::default(),
            },
            None,
        ))
        .map_err(|e| SurfaceError::Device(e.to_string()))?;

        let (w, h) = target.surface_size();
        let caps = surface.get_capabilities(&adapter);
        let format = caps
            .formats
            .iter()
            .copied()
            .find(|f| f.is_srgb())
            .unwrap_or_else(|| caps.formats[0]);

        let alpha_mode = if caps
            .alpha_modes
            .contains(&wgpu::CompositeAlphaMode::PreMultiplied)
        {
            wgpu::CompositeAlphaMode::PreMultiplied
        } else if caps
            .alpha_modes
            .contains(&wgpu::CompositeAlphaMode::PostMultiplied)
        {
            wgpu::CompositeAlphaMode::PostMultiplied
        } else {
            caps.alpha_modes[0]
        };

        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,
            width: w.max(1),
            height: h.max(1),
            present_mode: wgpu::PresentMode::AutoVsync,
            alpha_mode,
            view_formats: vec![],
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);

        let blit = build_blit_pipeline(&device, format);

        let scale_factor = target.scale_factor();
        Ok(Self {
            _instance: instance,
            surface,
            device: Arc::new(device),
            queue: Arc::new(queue),
            config,
            _target: target,
            blit,
            scale_factor,
        })
    }

    pub fn size(&self) -> (u32, u32) {
        (self.config.width, self.config.height)
    }

    pub fn resize(&mut self, width: u32, height: u32) {
        self.config.width = width.max(1);
        self.config.height = height.max(1);
        self.surface.configure(&self.device, &self.config);
    }

    /// Render one frame: clear, sample the given Skia-pixel texture, present.
    /// The texture must already contain the BGRA8UnormSrgb image to composite.
    pub fn present_with_bind_group(
        &self,
        clear: Color,
        bind_group: Option<&wgpu::BindGroup>,
    ) -> Result<(), SurfaceError> {
        let frame = self
            .surface
            .get_current_texture()
            .map_err(|e| SurfaceError::Present(e.to_string()))?;
        let view = frame
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());

        let mut encoder = self
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("elysium-frame"),
            });
        {
            let mut rp = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("clear+blit"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: clear.r as f64,
                            g: clear.g as f64,
                            b: clear.b as f64,
                            a: clear.a as f64,
                        }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            if let Some(bg) = bind_group {
                rp.set_pipeline(&self.blit.pipeline);
                rp.set_bind_group(0, bg, &[]);
                rp.draw(0..3, 0..1);
            }
        }
        self.queue.submit(Some(encoder.finish()));
        frame.present();
        Ok(())
    }
}

fn build_blit_pipeline(device: &wgpu::Device, target_format: wgpu::TextureFormat) -> BlitPipeline {
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("skia-blit"),
        source: wgpu::ShaderSource::Wgsl(include_str!("shaders/skia_blit.wgsl").into()),
    });

    let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: Some("skia-blit-bgl"),
        entries: &[
            wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Texture {
                    sample_type: wgpu::TextureSampleType::Float { filterable: true },
                    view_dimension: wgpu::TextureViewDimension::D2,
                    multisampled: false,
                },
                count: None,
            },
            wgpu::BindGroupLayoutEntry {
                binding: 1,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                count: None,
            },
        ],
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("skia-blit-pl"),
        bind_group_layouts: &[&bind_group_layout],
        push_constant_ranges: &[],
    });
    let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("skia-blit-rp"),
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: "vs_main",
            buffers: &[],
            compilation_options: Default::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: "fs_main",
            targets: &[Some(wgpu::ColorTargetState {
                format: target_format,
                blend: Some(wgpu::BlendState::PREMULTIPLIED_ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
            compilation_options: Default::default(),
        }),
        primitive: wgpu::PrimitiveState::default(),
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    });
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        label: Some("skia-blit-sampler"),
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        ..Default::default()
    });
    BlitPipeline {
        pipeline,
        bind_group_layout,
        sampler,
    }
}
