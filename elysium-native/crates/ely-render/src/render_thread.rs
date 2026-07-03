//! Dedicated render thread.
//!
//! Spec §3.2: "Render thread consumes a lock-free triple-buffered display
//! list, performs Skia/wgpu draw calls. Never touches Python objects directly."
//!
//! The main thread spawns this with `spawn_render_thread`, passing the
//! SurfaceRenderer (Send) and the triple buffer + control channel.
//! Resize and Stop messages come in through the control channel; the
//! thread exits cleanly on Stop.

use crate::damage::Damage;
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

/// Physical-pixel damage rect + its logical clip:
/// `(px, py, pw, ph, clip_x, clip_y, clip_w, clip_h)`.
type PhysDamage = (u32, u32, u32, u32, f32, f32, f32, f32);

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
    // The display list whose pixels currently live in the retained Skia
    // surface — diffed against each new list to compute damage.
    let mut prev: DisplayList = DisplayList::default();
    // Dirty-rect compositing: partial repaint + skip-when-clean. Set
    // `ELYSIUM_DIRTY_RECT=0` to force a full redraw every frame (A/B + safety).
    let dirty_enabled = std::env::var("ELYSIUM_DIRTY_RECT")
        .map(|v| v != "0")
        .unwrap_or(true);
    let mut region_buf: Vec<u8> = Vec::new();

    loop {
        // Drain control messages without blocking.
        let mut resized = false;
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
                        resized = true;
                    }
                }
            }
        }
        // A resize discards the retained surface — next frame must be full.
        if resized {
            prev = DisplayList::default();
        }

        // Pull latest published display list (lock-free).
        let got_new = if let Some(g) = triple_buffer.try_acquire() {
            g.with(|new_list| cached = new_list.clone());
            true
        } else {
            false
        };

        let anim_active = crate::damage::has_live_anim(&cached);

        // Decide what to repaint this frame.
        let damage = if !dirty_enabled {
            Damage::Full
        } else if got_new {
            if anim_active {
                Damage::Full
            } else {
                crate::damage::diff_damage(&prev, &cached)
            }
        } else if anim_active {
            Damage::Full // a tween is mid-flight; keep repainting
        } else {
            Damage::None // nothing new, nothing animating → idle
        };
        if got_new {
            prev = cached.clone();
        }

        // Idle: leave the last presented frame on screen, sleep briefly so
        // we don't busy-spin (present's vsync block no longer paces us).
        if matches!(damage, Damage::None) {
            std::thread::sleep(Duration::from_millis(6));
            continue;
        }

        let scale = renderer.scale_factor as f32;
        let scaled = (scale - 1.0).abs() > 1e-4;

        // Resolve the damage to a physical-pixel sub-rect, or fall back to
        // a full repaint when it's unbounded or covers most of the surface.
        // Tuple = (px, py, pw, ph, clip_x, clip_y, clip_w, clip_h).
        let phys: Option<PhysDamage> = match damage {
            Damage::Full | Damage::None => None,
            Damage::Rect(lx, ly, lw, lh) => {
                let pad = 1.0_f32;
                let x0 = (((lx - pad) * scale).floor()).max(0.0);
                let y0 = (((ly - pad) * scale).floor()).max(0.0);
                let x1 = (((lx + lw + pad) * scale).ceil()).min(w as f32);
                let y1 = (((ly + lh + pad) * scale).ceil()).min(h as f32);
                let pw = (x1 - x0).max(0.0) as u32;
                let ph = (y1 - y0).max(0.0) as u32;
                // Not worth a partial when the region is most of the surface.
                if pw == 0 || ph == 0 || (pw as u64 * ph as u64) * 5 >= (w as u64 * h as u64) * 3 {
                    None
                } else {
                    Some((
                        x0 as u32,
                        y0 as u32,
                        pw,
                        ph,
                        lx - pad,
                        ly - pad,
                        lw + 2.0 * pad,
                        lh + 2.0 * pad,
                    ))
                }
            }
        };

        let upload_full;
        if let Some((px, py, pw, ph, clx, cly, clw, clh)) = phys {
            // --- Partial repaint: clip → clear-within-clip → replay all. ---
            skia.save_with_transform(0.0, 0.0, scale, scale, 0.0);
            skia.clip_rect(clx, cly, clw, clh);
            skia.clear([0.0, 0.0, 0.0, 0.0]);
            skia.execute_with_anim(&cached, anim.as_deref());
            skia.restore();

            region_buf.resize((pw as usize) * (ph as usize) * 4, 0);
            if !skia.snapshot_region_bgra(px, py, pw, ph, &mut region_buf) {
                let (sw, sh) = skia.size();
                if (sw, sh) != (w, h) {
                    skia = SkiaLayer::new(w, h);
                }
                prev = DisplayList::default();
                continue;
            }
            renderer.queue.write_texture(
                wgpu::ImageCopyTexture {
                    texture: &upload_tex,
                    mip_level: 0,
                    origin: wgpu::Origin3d { x: px, y: py, z: 0 },
                    aspect: wgpu::TextureAspect::All,
                },
                &region_buf,
                wgpu::ImageDataLayout {
                    offset: 0,
                    bytes_per_row: Some(pw * 4),
                    rows_per_image: Some(ph),
                },
                wgpu::Extent3d {
                    width: pw,
                    height: ph,
                    depth_or_array_layers: 1,
                },
            );
            upload_full = false;
        } else {
            upload_full = true;
        }

        if upload_full {
            // --- Full repaint (legacy path; pixel reference for partials). ---
            skia.clear([0.0, 0.0, 0.0, 0.0]);
            if scaled {
                skia.save_with_transform(0.0, 0.0, scale, scale, 0.0);
            }
            skia.execute_with_anim(&cached, anim.as_deref());
            if scaled {
                skia.restore();
            }
            if !skia.snapshot_bgra() {
                let (sw, sh) = skia.size();
                if (sw, sh) != (w, h) {
                    skia = SkiaLayer::new(w, h);
                }
                prev = DisplayList::default();
                continue;
            }
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
        }

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
        size: wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Bgra8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let bind_group = renderer
        .device
        .create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("skia-blit-bg"),
            layout: &renderer.blit.bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&renderer.blit.sampler),
                },
            ],
        });
    (texture, bind_group)
}
