//! Dedicated render thread.
//!
//! Spec §3.2: "Render thread consumes a lock-free triple-buffered display
//! list, performs Skia/wgpu draw calls. Never touches Python objects directly."
//!
//! The main thread spawns this with `spawn_render_thread`, passing the
//! SurfaceRenderer (Send) and the triple buffer + control channel.
//! Resize and Stop messages come in through the control channel; the
//! thread exits cleanly on Stop.

use crate::skia_layer::SkiaLayer;
use crate::surface::SurfaceRenderer;
use crossbeam_channel::Receiver;
use ely_core::{AnimRegistry, Color, DisplayList, TripleBuffer};
use std::sync::Arc;
use std::time::Duration;

#[derive(Debug, Clone)]
pub enum RenderControl {
    Resize { width: u32, height: u32 },
    Stop,
}

pub fn spawn_render_thread(
    mut renderer: SurfaceRenderer,
    triple_buffer: Arc<TripleBuffer<DisplayList>>,
    control_rx: Receiver<RenderControl>,
    clear_color: Color,
    anim: Option<Arc<AnimRegistry>>,
) -> std::thread::JoinHandle<()> {
    std::thread::Builder::new()
        .name("elysium-render".into())
        .spawn(move || render_loop(&mut renderer, triple_buffer, control_rx, clear_color, anim))
        .expect("spawn render thread")
}

fn render_loop(
    renderer: &mut SurfaceRenderer,
    triple_buffer: Arc<TripleBuffer<DisplayList>>,
    control_rx: Receiver<RenderControl>,
    clear_color: Color,
    anim: Option<Arc<AnimRegistry>>,
) {
    let (mut w, mut h) = renderer.size();
    let mut skia = SkiaLayer::new(w, h);
    let (mut upload_tex, mut bind_group) = create_upload(renderer, w, h);
    let mut cached: DisplayList = DisplayList::default();

    loop {
        // Drain control messages without blocking.
        while let Ok(msg) = control_rx.try_recv() {
            match msg {
                RenderControl::Stop => return,
                RenderControl::Resize { width, height } => {
                    let nw = width.max(1);
                    let nh = height.max(1);
                    renderer.resize(nw, nh);
                    if (nw, nh) != (w, h) {
                        w = nw;
                        h = nh;
                        skia = SkiaLayer::new(w, h);
                        let (t, bg) = create_upload(renderer, w, h);
                        upload_tex = t;
                        bind_group = bg;
                    }
                }
            }
        }

        // Pull latest published display list (lock-free).
        if let Some(g) = triple_buffer.try_acquire() {
            g.with(|new_list| cached = new_list.clone());
        }

        // Paint into Skia, copy out to host-side BGRA buffer.
        // Auto-clear the SkiaLayer to fully transparent before the
        // user's DL runs so callers don't have to remember a leading
        // `clear`, and so composing DisplayLists never "wipes" the
        // parent canvas — the skin compiler emits a scoped FillPath
        // for the scene background instead.
        skia.clear([0.0, 0.0, 0.0, 0.0]);
        // Apply the device pixel ratio so Python's logical-pixel
        // coordinates fill the entire physical surface on retina /
        // HiDPI displays.
        let scale = renderer.scale_factor as f32;
        if (scale - 1.0).abs() > 1e-4 {
            skia.save_with_transform(0.0, 0.0, scale, scale, 0.0);
        }
        skia.execute_with_anim(&cached, anim.as_deref());
        if (scale - 1.0).abs() > 1e-4 {
            skia.restore();
        }
        if !skia.snapshot_bgra() {
            // Skia surface size drifted from texture size — re-sync and skip frame.
            let (sw, sh) = skia.size();
            if (sw, sh) != (w, h) {
                skia = SkiaLayer::new(w, h);
            }
            continue;
        }

        // Upload to wgpu texture. queue.write_texture is thread-safe.
        renderer.queue.write_texture(
            wgpu::ImageCopyTexture {
                texture: &upload_tex,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            &skia.pixels,
            wgpu::ImageDataLayout {
                offset: 0,
                bytes_per_row: Some(skia.row_bytes()),
                rows_per_image: Some(h),
            },
            wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
        );

        // Composite + present. `present_with_bind_group` blocks at vsync.
        match renderer.present_with_bind_group(clear_color, Some(&bind_group)) {
            Ok(()) => {}
            Err(crate::surface::SurfaceError::Present(_)) => {
                // Swapchain may be lost (window minimized / hidden); reconfigure
                // and try again next iteration.
                renderer.resize(w, h);
                std::thread::sleep(Duration::from_millis(16));
            }
            Err(e) => {
                tracing::error!(?e, "render thread present failed");
                return;
            }
        }
    }
}

fn create_upload(
    renderer: &SurfaceRenderer,
    width: u32,
    height: u32,
) -> (wgpu::Texture, wgpu::BindGroup) {
    let texture = renderer.device.create_texture(&wgpu::TextureDescriptor {
        label: Some("skia-layer"),
        size: wgpu::Extent3d { width, height, depth_or_array_layers: 1 },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Bgra8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let bind_group = renderer.device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("skia-blit-bg"),
        layout: &renderer.blit.bind_group_layout,
        entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: wgpu::BindingResource::TextureView(&view) },
            wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::Sampler(&renderer.blit.sampler) },
        ],
    });
    (texture, bind_group)
}
