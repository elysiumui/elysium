use crate::window::{CursorKind, ResizeDirection, WindowConfig, WindowHandle, WindowRequest};
use crossbeam_channel::Sender;
use ely_core::{Color, DisplayList, DrawCommand};
use ely_render::{spawn_render_thread, RenderControl, SurfaceRenderer, SurfaceTarget};
use parking_lot::Mutex;
use raw_window_handle::{
    DisplayHandle, HandleError, HasDisplayHandle, HasWindowHandle, WindowHandle as RawWindowHandle,
};
use std::sync::atomic::Ordering;
use std::sync::Arc;
use thiserror::Error;
use winit::application::ApplicationHandler;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::window::{Window as WinitWindow, WindowId};

#[derive(Debug, Clone, Default)]
pub struct Config {
    pub title: String,
    pub identifier: String,
    pub icon: Option<String>,
    pub theme: String,
    pub log_level: String,
    pub enable_hot_reload: bool,
}

#[derive(Debug, Error)]
pub enum AppError {
    #[error("winit error: {0}")]
    Winit(String),
    #[error("window creation failed: {0}")]
    Window(String),
    #[error("renderer init failed: {0}")]
    Renderer(String),
}

/// Adapter so a winit `Arc<Window>` satisfies the `SurfaceTarget` trait
/// without ely-render depending on winit.
struct WinitTarget {
    window: Arc<WinitWindow>,
}

impl HasWindowHandle for WinitTarget {
    fn window_handle(&self) -> Result<RawWindowHandle<'_>, HandleError> {
        self.window.window_handle()
    }
}
impl HasDisplayHandle for WinitTarget {
    fn display_handle(&self) -> Result<DisplayHandle<'_>, HandleError> {
        self.window.display_handle()
    }
}
impl SurfaceTarget for WinitTarget {
    fn surface_size(&self) -> (u32, u32) {
        let s = self.window.inner_size();
        (s.width, s.height)
    }
    fn scale_factor(&self) -> f64 {
        self.window.scale_factor()
    }
}

struct PendingWindow {
    cfg: WindowConfig,
    handle: WindowHandle,
}

struct LiveWindow {
    winit_window: Arc<WinitWindow>,
    handle: WindowHandle,
    /// Control channel to the dedicated render thread.
    render_tx: Sender<RenderControl>,
    render_thread: Option<std::thread::JoinHandle<()>>,
    /// Per-window accessibility bridge — translates the framework's
    /// A11yTree into accesskit_macos/accesskit_unix/accesskit_windows
    /// updates. Attached lazily on first publish so windows that don't
    /// care about a11y don't pay the adapter cost.
    a11y_bridge: Option<crate::a11y_bridge::A11yBridge>,
}

/// Sendable, lock-free state shared between the event-loop thread and any
/// thread that may call `quit()` (worker pools, IPC server, signal handlers).
#[derive(Clone)]
pub struct AppHandle {
    pending: Arc<Mutex<Vec<PendingWindow>>>,
    quit_flag: Arc<std::sync::atomic::AtomicBool>,
}

impl AppHandle {
    pub fn quit(&self) {
        self.quit_flag
            .store(true, std::sync::atomic::Ordering::Release);
    }
}

pub struct AppLoop {
    config: Config,
    handle: AppHandle,
}

impl AppLoop {
    pub fn new(config: Config) -> Result<Self, AppError> {
        Ok(Self {
            config,
            handle: AppHandle {
                pending: Arc::new(Mutex::new(Vec::new())),
                quit_flag: Arc::new(std::sync::atomic::AtomicBool::new(false)),
            },
        })
    }

    pub fn config(&self) -> &Config {
        &self.config
    }
    pub fn handle(&self) -> AppHandle {
        self.handle.clone()
    }

    pub fn create_window(&mut self, cfg: WindowConfig) -> Result<WindowHandle, AppError> {
        let handle = WindowHandle::stub(cfg.clone());
        self.handle.pending.lock().push(PendingWindow {
            cfg,
            handle: handle.clone(),
        });
        Ok(handle)
    }

    pub fn run(&mut self) -> Result<(), AppError> {
        let event_loop = EventLoop::new().map_err(|e| AppError::Winit(e.to_string()))?;
        event_loop.set_control_flow(ControlFlow::Poll);

        let mut handler = AppHandler {
            title: self.config.title.clone(),
            pending: self.handle.pending.clone(),
            live: Vec::new(),
            quit_flag: self.handle.quit_flag.clone(),
            init_error: None,
        };

        event_loop
            .run_app(&mut handler)
            .map_err(|e| AppError::Winit(e.to_string()))?;
        if let Some(e) = handler.init_error.take() {
            return Err(e);
        }
        Ok(())
    }

    pub fn quit(&self) {
        self.handle.quit();
    }
}

struct AppHandler {
    title: String,
    pending: Arc<Mutex<Vec<PendingWindow>>>,
    live: Vec<LiveWindow>,
    quit_flag: Arc<std::sync::atomic::AtomicBool>,
    init_error: Option<AppError>,
}

impl AppHandler {
    fn create_pending(&mut self, event_loop: &ActiveEventLoop) {
        let pending: Vec<PendingWindow> = std::mem::take(&mut self.pending.lock());
        for PendingWindow { cfg, handle } in pending {
            match self.make_live_window(event_loop, &cfg, handle) {
                Ok(live) => self.live.push(live),
                Err(e) => self.init_error = Some(e),
            }
        }
    }

    fn make_live_window(
        &self,
        event_loop: &ActiveEventLoop,
        cfg: &WindowConfig,
        handle: WindowHandle,
    ) -> Result<LiveWindow, AppError> {
        let mut attrs = WinitWindow::default_attributes()
            .with_title(&self.title)
            .with_transparent(cfg.transparent)
            .with_decorations(cfg.title_bar)
            .with_resizable(cfg.resizable)
            .with_inner_size(winit::dpi::LogicalSize::new(
                cfg.initial_size.0 as f64,
                cfg.initial_size.1 as f64,
            ));
        if let Some((w, h)) = cfg.min_size {
            attrs = attrs.with_min_inner_size(winit::dpi::LogicalSize::new(w as f64, h as f64));
        }

        let win = event_loop
            .create_window(attrs)
            .map_err(|e| AppError::Window(e.to_string()))?;
        // Allow OS input-method composition by default so CJK / dead-key
        // input works as soon as a text widget is focused. winit only
        // emits `WindowEvent::Ime` during an actual composition, so this
        // is free when the user isn't composing. The Python input router
        // may toggle it per focus via `set_ime_allowed`.
        win.set_ime_allowed(true);
        let win = Arc::new(win);

        let target = Arc::new(WinitTarget {
            window: win.clone(),
        });
        let renderer =
            SurfaceRenderer::new(target).map_err(|e| AppError::Renderer(e.to_string()))?;

        let clear = if cfg.transparent {
            Color::TRANSPARENT
        } else {
            Color::rgba(0.055, 0.043, 0.102, 1.0) // surface dark "#0E0B1A"
        };

        // Seed the triple buffer with the Phase 0 hero card so the render
        // thread has something to draw on its very first iteration —
        // BUT only if Python hasn't already published its own content.
        // `load_skin()` and friends can race ahead of the deferred
        // window-creation step here; without this guard the seed
        // silently overwrites the user's actual DisplayList and they
        // see the placeholder instead of their skin.
        if !handle.has_published() {
            let (sw, sh) = renderer.size();
            handle.publish_display_list(default_hero_card(sw, sh));
        }

        // Hand the renderer off to a dedicated thread. From here on the
        // main thread only does winit events; Skia paint + wgpu present
        // run on `elysium-render`.
        let (render_tx, render_rx) = crossbeam_channel::unbounded::<RenderControl>();
        let render_thread = spawn_render_thread(
            renderer,
            handle.display_list(),
            render_rx,
            clear,
            Some(handle.anim().clone()),
        );

        Ok(LiveWindow {
            winit_window: win,
            handle,
            render_tx,
            render_thread: Some(render_thread),
            a11y_bridge: None,
        })
    }
}

/// Extract the macOS NSView pointer from a winit window via raw_window_handle.
#[cfg(target_os = "macos")]
fn ns_view_ptr(win: &WinitWindow) -> Option<*mut std::ffi::c_void> {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    let handle = win.window_handle().ok()?;
    match handle.as_raw() {
        RawWindowHandle::AppKit(h) => Some(h.ns_view.as_ptr()),
        _ => None,
    }
}

#[cfg(target_os = "windows")]
fn hwnd_for(win: &WinitWindow) -> Option<isize> {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    let handle = win.window_handle().ok()?;
    match handle.as_raw() {
        RawWindowHandle::Win32(h) => Some(h.hwnd.get()),
        _ => None,
    }
}

/// Dispatch a `WindowRequest` to the live winit window. Cross-platform:
/// position changes apply everywhere; the macOS Cocoa branches no-op on
/// other OSes via `#[cfg]`.
fn apply_window_request(win: &WinitWindow, req: WindowRequest) {
    match req {
        WindowRequest::SetOuterPosition { x, y } => {
            // x, y are LOGICAL coords — that's what `WindowEvent::Moved`
            // records via `record_outer_position` after dividing by the
            // scale factor. Using PhysicalPosition here on a HiDPI
            // display would halve (or worse) the requested position.
            win.set_outer_position(winit::dpi::LogicalPosition::new(x, y));
        }
        #[cfg(target_os = "macos")]
        WindowRequest::SetBlurBehind { enabled, material } => {
            use crate::platform::macos::{enable_blur_behind, Material};
            let mat = match material {
                3 => Material::TitleBar,
                4 | 12 => Material::HudWindow,
                15 => Material::FullScreenUI,
                21 => Material::UnderWindowBg,
                7 => Material::Sidebar,
                10 => Material::HeaderView,
                11 => Material::Menu,
                _ => Material::HudWindow,
            };
            if let Some(ns_view) = ns_view_ptr(win) {
                unsafe {
                    enable_blur_behind(ns_view, enabled, mat);
                }
            }
        }
        #[cfg(target_os = "macos")]
        WindowRequest::SetIgnoresMouse { ignores } => {
            if let Some(ns_view) = ns_view_ptr(win) {
                unsafe {
                    crate::platform::macos::set_window_ignores_mouse(ns_view, ignores);
                }
            }
        }
        #[cfg(target_os = "macos")]
        WindowRequest::SetHasShadow { has_shadow } => {
            if let Some(ns_view) = ns_view_ptr(win) {
                unsafe {
                    crate::platform::macos::set_window_has_shadow(ns_view, has_shadow);
                }
            }
        }
        #[cfg(target_os = "macos")]
        WindowRequest::SetWindowLevel { level } => {
            if let Some(ns_view) = ns_view_ptr(win) {
                unsafe {
                    crate::platform::macos::set_window_level(ns_view, level);
                }
            }
        }
        // Non-macOS catch-alls so the build is clean on other platforms.
        #[cfg(not(target_os = "macos"))]
        WindowRequest::SetBlurBehind { .. }
        | WindowRequest::SetIgnoresMouse { .. }
        | WindowRequest::SetHasShadow { .. }
        | WindowRequest::SetWindowLevel { .. } => {
            tracing::debug!("window request ignored on non-macOS");
        }
        // Cross-platform — change the mouse cursor icon. winit handles
        // the OS-specific lookup (NSCursor on macOS, IDC_* on Windows,
        // X11/Wayland cursor themes on Linux) for us.
        WindowRequest::SetCursor { kind } => {
            use winit::window::CursorIcon;
            let icon = match kind {
                CursorKind::Default => CursorIcon::Default,
                CursorKind::Pointer => CursorIcon::Pointer,
                CursorKind::Text => CursorIcon::Text,
                CursorKind::Crosshair => CursorIcon::Crosshair,
                CursorKind::Move => CursorIcon::Move,
                CursorKind::Grab => CursorIcon::Grab,
                CursorKind::Grabbing => CursorIcon::Grabbing,
                CursorKind::NotAllowed => CursorIcon::NotAllowed,
                CursorKind::EwResize => CursorIcon::EwResize,
                CursorKind::NsResize => CursorIcon::NsResize,
                CursorKind::NwseResize => CursorIcon::NwseResize,
                CursorKind::NeswResize => CursorIcon::NeswResize,
                CursorKind::ZoomIn => CursorIcon::ZoomIn,
                CursorKind::ZoomOut => CursorIcon::ZoomOut,
            };
            win.set_cursor(icon);
        }
        // Cross-platform — toggle the OS minimised state. winit
        // exposes set_minimized(bool); the OS handles the
        // animation.
        WindowRequest::SetMinimized { minimized } => {
            win.set_minimized(minimized);
        }
        // Cross-platform — toggle the OS maximised state. winit
        // exposes set_maximized(bool).
        WindowRequest::SetMaximized { maximized } => {
            win.set_maximized(maximized);
        }
        // Cross-platform — toggle borderless fullscreen. We use
        // `Fullscreen::Borderless(None)` so winit picks the active
        // monitor automatically.
        WindowRequest::SetFullscreen { fullscreen } => {
            use winit::window::Fullscreen;
            win.set_fullscreen(if fullscreen {
                Some(Fullscreen::Borderless(None))
            } else {
                None
            });
        }
        // Cross-platform — start an OS-driven interactive resize from
        // a specific edge / corner. winit forwards this to the
        // compositor (NSResizeMode on macOS, WM_SYSCOMMAND on Win32,
        // _NET_WM_MOVERESIZE on X11). The OS owns the drag until
        // mouse release; we don't need a release event here.
        WindowRequest::DragResize { direction } => {
            use winit::window::ResizeDirection as WD;
            let dir = match direction {
                ResizeDirection::East => WD::East,
                ResizeDirection::North => WD::North,
                ResizeDirection::NorthEast => WD::NorthEast,
                ResizeDirection::NorthWest => WD::NorthWest,
                ResizeDirection::South => WD::South,
                ResizeDirection::SouthEast => WD::SouthEast,
                ResizeDirection::SouthWest => WD::SouthWest,
                ResizeDirection::West => WD::West,
            };
            // Best-effort: some platforms may refuse mid-event (e.g.
            // when there's no active mouse button); swallow the error
            // and let the user try again.
            let _ = win.drag_resize_window(dir);
        }
        // Cross-platform — enable/disable OS input-method composition.
        WindowRequest::SetImeAllowed { allowed } => {
            win.set_ime_allowed(allowed);
        }
        // Cross-platform — position the IME candidate popup at the caret.
        WindowRequest::SetImeCursorArea { x, y, w, h } => {
            use winit::dpi::LogicalPosition;
            use winit::dpi::LogicalSize;
            win.set_ime_cursor_area(
                winit::dpi::Position::Logical(LogicalPosition::new(x as f64, y as f64)),
                winit::dpi::Size::Logical(LogicalSize::new(w as f64, h as f64)),
            );
        }
    }
}

/// Build the spec's hero-card display list at the given size. Used as the
/// initial content for any window the caller hasn't published into yet.
fn default_hero_card(w: u32, h: u32) -> DisplayList {
    let w = w as f32;
    let h = h as f32;
    let pad = w.min(h) * 0.08;
    let card_w = w - 2.0 * pad;
    let card_h = h - 2.0 * pad;
    let cx = w / 2.0;
    let cy = h - pad - card_h * 0.18;
    DisplayList {
        frame_index: 0,
        commands: vec![
            DrawCommand::Clear {
                color: [0.0, 0.0, 0.0, 0.0],
            },
            DrawCommand::GradientCard {
                bounds: [pad, pad, card_w, card_h],
                corner_radius: 24.0,
                start_color: [0x5B, 0x3F, 0xF5, 0xFF],
                end_color: [0xFF, 0x5C, 0x8A, 0xFF],
                shadow_blur: 40.0,
                shadow_offset: [0.0, 12.0],
                shadow_color: [0, 0, 0, 0x7F],
            },
            DrawCommand::FilledCircle {
                cx,
                cy,
                r: card_w.min(card_h) * 0.05,
                color: [0xFA, 0xF7, 0xFF, 0xFF],
            },
        ],
    }
}

impl ApplicationHandler for AppHandler {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        // `resumed` fires both on first launch and on a real OS resume
        // (e.g. app foregrounded after suspend). Only surface a lifecycle
        // event for the latter — when windows already exist.
        if !self.live.is_empty() {
            for lw in &self.live {
                lw.handle.push_lifecycle("resumed");
            }
        }
        self.create_pending(event_loop);
        if self.init_error.is_some() {
            event_loop.exit();
        }
    }

    fn suspended(&mut self, _event_loop: &ActiveEventLoop) {
        for lw in &self.live {
            lw.handle.push_lifecycle("suspended");
        }
    }

    fn memory_warning(&mut self, _event_loop: &ActiveEventLoop) {
        for lw in &self.live {
            lw.handle.push_lifecycle("memory_warning");
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        window_id: WindowId,
        event: WindowEvent,
    ) {
        let idx = self
            .live
            .iter()
            .position(|w| w.winit_window.id() == window_id);
        let Some(idx) = idx else {
            return;
        };

        match event {
            WindowEvent::CloseRequested => {
                let mut lw = self.live.swap_remove(idx);
                lw.handle.close();
                let _ = lw.render_tx.send(RenderControl::Stop);
                if let Some(jh) = lw.render_thread.take() {
                    let _ = jh.join();
                }
                if self.live.is_empty() {
                    event_loop.exit();
                }
            }
            WindowEvent::Resized(size) => {
                let lw = &self.live[idx];
                // Convert physical → logical pixels so Python layout
                // math (which always uses logical units) sees the right
                // numbers across DPI.
                let scale = lw.winit_window.scale_factor();
                let lw_w = (size.width as f64 / scale).round() as u32;
                let lw_h = (size.height as f64 / scale).round() as u32;
                lw.handle.set_surface_size(lw_w, lw_h);
                let _ = lw.render_tx.send(RenderControl::Resize {
                    width: size.width,
                    height: size.height,
                });
            }
            WindowEvent::PinchGesture { delta, .. } => {
                // Trackpad pinch — macOS reports a per-event ratio change.
                // Accumulate into the window handle; Python drains it
                // once per frame and applies it to canvas zoom.
                let lw = &self.live[idx];
                if lw.handle.is_input_blocked() {
                    return;
                }
                lw.handle.accumulate_pinch_delta(delta as f32);
            }
            WindowEvent::MouseWheel { delta, .. } => {
                // Discrete wheel (mouse) or precise pixel deltas (trackpad).
                // Normalise line deltas to logical pixels; accumulate for
                // Python to drain via `poll_scroll_delta()` once per frame.
                let lw = &self.live[idx];
                if lw.handle.is_input_blocked() {
                    return;
                }
                use crate::window::WHEEL_LINE_PX;
                match delta {
                    winit::event::MouseScrollDelta::LineDelta(x, y) => {
                        lw.handle
                            .accumulate_scroll(x * WHEEL_LINE_PX, y * WHEEL_LINE_PX, false);
                    }
                    winit::event::MouseScrollDelta::PixelDelta(p) => {
                        let scale = lw.winit_window.scale_factor();
                        lw.handle.accumulate_scroll(
                            (p.x / scale) as f32,
                            (p.y / scale) as f32,
                            true,
                        );
                    }
                }
            }
            WindowEvent::Moved(pos) => {
                // Record the current outer position so Python can
                // persist it. winit Moved gives physical pixels.
                let lw = &self.live[idx];
                let scale = lw.winit_window.scale_factor();
                let lx = (pos.x as f64 / scale).round() as i32;
                let ly = (pos.y as f64 / scale).round() as i32;
                lw.handle.record_outer_position(lx, ly);
            }
            WindowEvent::CursorMoved { position, .. } => {
                let lw = &self.live[idx];
                let scale = lw.winit_window.scale_factor();
                let x = (position.x / scale) as i32;
                let y = (position.y / scale) as i32;
                lw.handle.mouse().x.store(x, Ordering::Release);
                lw.handle.mouse().y.store(y, Ordering::Release);
                lw.handle.mouse().inside.store(true, Ordering::Release);

                // Path-aware hit testing: if a hit-test path is set, the
                // OS window passes clicks through whenever the cursor is
                // outside it. We track edge transitions and post a
                // SetIgnoresMouse request to the same drain queue that
                // applies set_outer_position.
                let path_arc = lw.handle.hit_test_path();
                let guard = path_arc.read();
                if let Some(p) = guard.as_ref() {
                    use ely_core::geometry::Point as ElyPoint;
                    let inside = p.contains(ElyPoint::new(x as f32, y as f32));
                    let was = lw
                        .handle
                        .cursor_inside_path()
                        .swap(inside, Ordering::AcqRel);
                    if inside != was {
                        // Inside → don't ignore; outside → ignore (pass-through).
                        lw.handle.request_set_ignores_mouse(!inside);
                    }
                }
            }
            WindowEvent::CursorEntered { .. } => {
                self.live[idx]
                    .handle
                    .mouse()
                    .inside
                    .store(true, Ordering::Release);
            }
            WindowEvent::DroppedFile(path) => {
                let lw = &self.live[idx];
                let x = lw.handle.mouse().x.load(Ordering::Acquire) as f64;
                let y = lw.handle.mouse().y.load(Ordering::Acquire) as f64;
                lw.handle
                    .push_file_drop(path.to_string_lossy().into_owned(), x, y);
                lw.handle.set_file_hover(false);
            }
            WindowEvent::HoveredFile(_) => {
                self.live[idx].handle.set_file_hover(true);
            }
            WindowEvent::HoveredFileCancelled => {
                self.live[idx].handle.set_file_hover(false);
            }
            WindowEvent::CursorLeft { .. } => {
                let lw = &self.live[idx];
                lw.handle.mouse().inside.store(false, Ordering::Release);
                lw.handle.mouse().x.store(-1, Ordering::Release);
                lw.handle.mouse().y.store(-1, Ordering::Release);
            }
            WindowEvent::MouseInput { state, button, .. } => {
                let lw = &self.live[idx];
                if lw.handle.is_input_blocked() {
                    return;
                }
                let pressed = state == winit::event::ElementState::Pressed;
                match button {
                    winit::event::MouseButton::Left => {
                        let was = lw
                            .handle
                            .mouse()
                            .pressed_left
                            .swap(pressed, Ordering::AcqRel);
                        if pressed && !was {
                            lw.handle.mouse().press_count.fetch_add(1, Ordering::AcqRel);
                        }
                    }
                    winit::event::MouseButton::Right => {
                        let was = lw
                            .handle
                            .mouse()
                            .pressed_right
                            .swap(pressed, Ordering::AcqRel);
                        if pressed && !was {
                            lw.handle
                                .mouse()
                                .right_press_count
                                .fetch_add(1, Ordering::AcqRel);
                        }
                    }
                    _ => {}
                }
            }
            WindowEvent::RedrawRequested => {
                // No-op: the render thread runs its own present loop.
            }
            WindowEvent::ModifiersChanged(mods) => {
                let lw = &self.live[idx];
                let m = mods.state();
                let mut bits: u8 = 0;
                if m.shift_key() {
                    bits |= 1;
                }
                if m.control_key() {
                    bits |= 2;
                }
                if m.alt_key() {
                    bits |= 4;
                }
                if m.super_key() {
                    bits |= 8;
                }
                lw.handle
                    .keyboard()
                    .modifiers
                    .store(bits, Ordering::Release);
            }
            WindowEvent::KeyboardInput { event, .. } => {
                let lw = &self.live[idx];
                if lw.handle.is_input_blocked() {
                    return;
                }
                let code = format!("{:?}", event.physical_key)
                    .replace("Code(", "")
                    .replace(')', "");
                let pressed = event.state == winit::event::ElementState::Pressed;
                let text = event.text.as_deref().unwrap_or("").to_string();
                let mods = lw.handle.keyboard().modifiers.load(Ordering::Acquire);
                {
                    let mut held = lw.handle.keyboard().held.lock();
                    if pressed {
                        held.insert(code.clone());
                    } else {
                        held.remove(&code);
                    }
                }
                let ev = crate::window::KeyEvent {
                    code,
                    pressed,
                    modifiers: mods,
                    text,
                };
                let mut q = lw.handle.keyboard().events.lock();
                if q.len() >= 256 {
                    q.pop_front();
                }
                q.push_back(ev);
            }
            // Input-method (IME) composition. Preedit text is the in-flight
            // candidate string (rendered with an underline by the text
            // widget); Commit is the finished string, delivered into the
            // normal key-event queue as an "ImeCommit" entry so the text
            // layer treats it like typed input. Required for CJK / accent
            // composition.
            WindowEvent::Ime(ime) => {
                use winit::event::Ime;
                let lw = &self.live[idx];
                match ime {
                    Ime::Preedit(text, _cursor) => {
                        *lw.handle.keyboard().preedit.lock() = text;
                    }
                    Ime::Commit(text) => {
                        lw.handle.keyboard().preedit.lock().clear();
                        let mods = lw.handle.keyboard().modifiers.load(Ordering::Acquire);
                        let ev = crate::window::KeyEvent {
                            code: "ImeCommit".to_string(),
                            pressed: true,
                            modifiers: mods,
                            text,
                        };
                        let mut q = lw.handle.keyboard().events.lock();
                        if q.len() >= 256 {
                            q.pop_front();
                        }
                        q.push_back(ev);
                    }
                    Ime::Enabled | Ime::Disabled => {
                        lw.handle.keyboard().preedit.lock().clear();
                    }
                }
            }
            _ => {}
        }

        // Drain any window requests that Python posted (e.g. set_position).
        // Guard: a CloseRequested branch above may have swap_removed this idx.
        if let Some(lw) = self.live.get(idx) {
            for req in lw.handle.drain_window_requests() {
                apply_window_request(&lw.winit_window, req);
            }
        }

        if self.quit_flag.load(std::sync::atomic::Ordering::Acquire) {
            event_loop.exit();
        }
    }

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if self.quit_flag.load(std::sync::atomic::Ordering::Acquire) {
            // Signal each render thread to stop and join it before we exit
            // the OS loop, so wgpu surface teardown happens in a known order.
            for lw in self.live.drain(..) {
                let _ = lw.render_tx.send(RenderControl::Stop);
                if let Some(jh) = lw.render_thread {
                    let _ = jh.join();
                }
            }
            event_loop.exit();
        }
        // Drain Python-posted window requests every iteration so
        // set_outer_position / set_blur_behind / etc. fire within a
        // frame of being requested.
        for lw in &mut self.live {
            for req in lw.handle.drain_window_requests() {
                apply_window_request(&lw.winit_window, req);
            }
            // First-time accessibility attach: as soon as we know the
            // window's native handle, hook the accesskit adapter to it.
            // The bridge then publishes the (already-shared) A11yState
            // to NSAccessibility / UIA / AT-SPI2 on every refresh.
            if lw.a11y_bridge.is_none() {
                let mut bridge = crate::a11y_bridge::A11yBridge::new(lw.handle.a11y().clone());
                #[cfg(target_os = "macos")]
                if let Some(view) = ns_view_ptr(&lw.winit_window) {
                    bridge.attach_macos(view);
                }
                #[cfg(target_os = "windows")]
                if let Some(hwnd) = hwnd_for(&lw.winit_window) {
                    bridge.attach_windows(hwnd);
                }
                #[cfg(target_os = "linux")]
                {
                    bridge.attach_linux();
                }
                lw.a11y_bridge = Some(bridge);
            } else if let Some(b) = lw.a11y_bridge.as_mut() {
                // Cheap: refresh forwards the latest tree to the adapter
                // only when its `tree_dirty` flag is set; we tick that
                // bit inside `A11yState::publish`.
                if lw
                    .handle
                    .a11y()
                    .tree_dirty
                    .swap(false, std::sync::atomic::Ordering::AcqRel)
                {
                    b.refresh();
                }
            }
        }
        // No request_redraw needed; the render thread paints on its own clock.
    }

    fn new_events(&mut self, event_loop: &ActiveEventLoop, _cause: winit::event::StartCause) {
        // Re-assert Poll every iteration. winit 0.30 on macOS occasionally
        // reverts control flow internally; explicit reassertion keeps the
        // loop ticking so quit_flag gets observed within a frame.
        event_loop.set_control_flow(ControlFlow::Poll);
    }
}
