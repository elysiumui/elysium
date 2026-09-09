use ely_core::{geometry::Path as ElyPath, DisplayList, TripleBuffer};
use parking_lot::{Condvar, Mutex, RwLock};
use std::sync::atomic::{AtomicI32, AtomicU64, Ordering};
use std::sync::Arc;

/// A connected display, in **logical** pixels (physical ÷ scale factor), which
/// is the unit all Elysium layout maths uses.
#[derive(Debug, Clone, PartialEq)]
pub struct MonitorInfo {
    pub name: String,
    /// Top-left of the display in the virtual desktop, logical px.
    pub x: i32,
    pub y: i32,
    /// Full display size, logical px.
    pub width: u32,
    pub height: u32,
    /// Usable area (display minus the reserve for system chrome — see
    /// [`CHROME_RESERVE`]), logical px.
    pub work_x: i32,
    pub work_y: i32,
    pub work_width: u32,
    pub work_height: u32,
    pub scale_factor: f64,
    pub is_primary: bool,
}

/// Fraction of a display considered usable for a new window.
///
/// winit 0.30 exposes no work-area API — `MonitorHandle` gives `size()`,
/// `position()` and `scale_factor()`, but nothing that accounts for the macOS
/// menu bar and Dock, the Windows taskbar, or Linux panels. Rather than pull
/// in per-platform system calls, we reserve a conservative slice so a
/// default-sized window is always fully visible and reachable.
///
/// Apps that need the exact work area can read [`MonitorInfo`] from Python and
/// size themselves.
pub const CHROME_RESERVE: f64 = 0.90;

impl MonitorInfo {
    /// Build from a raw display rect. `position`/`size` are physical pixels,
    /// as winit reports them.
    pub fn from_physical(
        name: String,
        position: (i32, i32),
        size: (u32, u32),
        scale_factor: f64,
        is_primary: bool,
    ) -> Self {
        let scale = if scale_factor.is_finite() && scale_factor > 0.0 {
            scale_factor
        } else {
            1.0
        };
        let x = (position.0 as f64 / scale).round() as i32;
        let y = (position.1 as f64 / scale).round() as i32;
        let width = ((size.0 as f64 / scale).round() as u32).max(1);
        let height = ((size.1 as f64 / scale).round() as u32).max(1);
        let work_width = ((width as f64 * CHROME_RESERVE).round() as u32).max(1);
        let work_height = ((height as f64 * CHROME_RESERVE).round() as u32).max(1);
        Self {
            name,
            x,
            y,
            width,
            height,
            // Centre the usable area within the display, so the reserve is
            // split between top and bottom rather than assuming which edge
            // the taskbar/dock is on.
            work_x: x + ((width - work_width) / 2) as i32,
            work_y: y + ((height - work_height) / 2) as i32,
            work_width,
            work_height,
            scale_factor: scale,
            is_primary,
        }
    }

    /// Clamp a requested logical size to this display's usable area, and
    /// return the top-left that centres it there.
    ///
    /// This is what stops a window opening bigger than the screen: a hardcoded
    /// 1200x800 does not fit a 1366x768 laptop, nor a 1920x1080 panel at 150%
    /// scaling (1280x720 logical), and an oversized window on a borderless
    /// setup has no title bar to drag it back by.
    pub fn fit(&self, requested: (u32, u32)) -> ((u32, u32), (i32, i32)) {
        let w = requested.0.clamp(1, self.work_width);
        let h = requested.1.clamp(1, self.work_height);
        let x = self.work_x + ((self.work_width - w) / 2) as i32;
        let y = self.work_y + ((self.work_height - h) / 2) as i32;
        ((w, h), (x, y))
    }
}

#[derive(Debug, Clone)]
pub struct WindowConfig {
    pub skin_path: Option<String>,
    pub variant: Option<String>,
    pub shaped: bool,
    pub transparent: bool,
    pub title_bar: bool,
    pub resizable: bool,
    pub blur_behind: bool,
    pub always_on_top: bool,
    pub min_size: Option<(u32, u32)>,
    /// Preferred size in logical pixels. Treated as a *request*: unless
    /// `fit_to_display` is off it is clamped to what the target display can
    /// actually show, so the window never opens larger than the screen.
    pub initial_size: (u32, u32),
    /// Clamp `initial_size` to the display's usable area and centre the
    /// window on it (default). Turn off only when you deliberately want a
    /// window larger than the screen, e.g. for offscreen capture.
    pub fit_to_display: bool,
    /// Process-unique id of the owner window, if this is an owned/child
    /// window. Drives modal + owned-window semantics in the Python
    /// `WindowManager`; the platform layer only records it.
    pub owner_id: Option<u64>,
    /// When true, this window is application-modal with respect to its
    /// owner — the `WindowManager` sets the owner's `input_blocked` flag
    /// while this window is live.
    pub modal: bool,
}

impl Default for WindowConfig {
    fn default() -> Self {
        Self {
            skin_path: None,
            variant: None,
            shaped: false,
            transparent: true,
            title_bar: false,
            resizable: true,
            blur_behind: false,
            always_on_top: false,
            min_size: None,
            initial_size: (1200, 800),
            fit_to_display: true,
            owner_id: None,
            modal: false,
        }
    }
}

#[derive(Debug, Default)]
pub struct Scene {
    /// Phase 1.4 replaces this stub with the real retained scene graph.
    pub dirty: bool,
}

impl Scene {
    pub fn set_text(&mut self, _node_id: NodeId, _text: &str) {
        self.dirty = true;
    }
    pub fn get_text(&self, _node_id: NodeId) -> String {
        String::new()
    }
    pub fn set_value(&mut self, _node_id: NodeId, _v: f64) {
        self.dirty = true;
    }
    pub fn transition_state(&mut self, _node_id: NodeId, _state: &str) {
        self.dirty = true;
    }
}

pub type NodeId = u32;
pub type SubscriptionId = u64;

#[derive(Debug, Clone)]
pub enum Event {
    Click { x: f32, y: f32 },
    Hover { entered: bool },
    Custom(String),
}

/// Public handle threaded through PyO3. `Arc` semantics — cheaply cloneable.
#[derive(Clone)]
pub struct WindowHandle {
    inner: Arc<WindowInner>,
}

struct WindowInner {
    config: WindowConfig,
    scene: RwLock<Scene>,
    hooks: Arc<RwLock<ely_core_hook_stub::HookRegistry>>,
    next_sub: AtomicU64,
    closed: std::sync::atomic::AtomicBool,
    /// `true` once anything was published into the triple buffer. The
    /// event loop's `make_live_window` checks this before seeding the
    /// default-hero-card "phase 0" placeholder so a `load_skin` (or
    /// other Python publish) that races ahead of window creation isn't
    /// silently overwritten.
    has_published: std::sync::atomic::AtomicBool,
    /// Triple-buffered display list. Producer (Python user code) writes
    /// via `publish_display_list`; consumer (render path) reads via
    /// `acquire_display_list`. Lock-free between producer and consumer.
    display_list: Arc<TripleBuffer<DisplayList>>,
    /// Last known mouse state, polled by Python animation loops.
    /// `(x, y)` are window-local logical pixels; `(-1, -1)` means
    /// the cursor is outside the window.
    mouse: Arc<MouseState>,
    keyboard: Arc<KeyboardState>,
    /// Requests to the main thread from Python (e.g. set_outer_position).
    /// Drained by the AppHandler each iteration.
    pub window_requests: Arc<Mutex<Vec<WindowRequest>>>,
    /// Optional hit-test path. When set, clicks outside the path
    /// pass through to whatever's underneath the window. The event
    /// loop toggles NSWindow.ignoresMouseEvents on cursor moves.
    pub hit_test_path: Arc<RwLock<Option<ElyPath>>>,
    /// Cached cursor-inside-path state; lets us only toggle
    /// ignoresMouseEvents on the transition edge.
    pub cursor_inside_path: Arc<std::sync::atomic::AtomicBool>,
    /// Files dropped onto the window since the last poll. Each entry is
    /// `(absolute path, cursor x, cursor y)` in window-local logical px.
    pub file_drops: Arc<Mutex<std::collections::VecDeque<(String, f64, f64)>>>,
    /// `true` while one or more files are being dragged over the window
    /// (after `HoveredFile`, before `Dropped` / `Cancelled`).
    pub file_hover: std::sync::atomic::AtomicBool,
    /// Latest window-local *logical* surface dimensions (NOT physical
    /// pixels). The event loop updates these on every `Resized` event;
    /// Python reads them via `Window.surface_size` so layout math
    /// reacts to OS resize / fullscreen / window-zoom.
    pub surface_w: std::sync::atomic::AtomicU32,
    pub surface_h: std::sync::atomic::AtomicU32,
    /// Latest outer screen position in logical pixels — updated on
    /// every `WindowEvent::Moved`. Python reads via `outer_position`
    /// to persist the window's location across launches.
    pub outer_x: AtomicI32,
    pub outer_y: AtomicI32,
    /// Live display scale factor, ×1000 so it fits an atomic. Updated on
    /// creation and on every `ScaleFactorChanged` — dragging the window to a
    /// display with different scaling changes this. Python reads it via
    /// `Window.scale_factor`.
    pub scale_milli: std::sync::atomic::AtomicU32,
    /// The display this window currently sits on, as of the last time the
    /// event loop looked. Guarded rather than atomic because it's a struct.
    pub monitor: RwLock<Option<MonitorInfo>>,
    /// Accumulated trackpad pinch-gesture delta since the last poll, as
    /// a fixed-point integer (×1000) to fit in an atomic. Python polls
    /// `poll_pinch_delta()` once per frame to read+reset the accumulator
    /// and apply the value to whatever zoom logic owns it.
    pub pinch_delta_milli: AtomicI32,
    /// Monotonic count of input events delivered to this window. Python reads
    /// it before running a frame and hands it back to `wait_for_input`, so an
    /// event that lands *during* the frame can't be missed.
    pub input_seq: AtomicU64,
    /// Signalled whenever `input_seq` advances. Lets the frame loop block
    /// until there is something to react to instead of polling on a timer —
    /// see `wait_for_input`.
    pub wake_lock: Mutex<()>,
    pub wake_cv: Condvar,
    /// Process-unique window id, assigned at creation. Stable for the life
    /// of the handle; used by the Python `WindowManager` to express
    /// owner/child + modal relationships without depending on the OS
    /// `WindowId` (which doesn't exist until the window is materialised).
    pub id: u64,
    /// When true, the event loop drops mouse-button / key / scroll input to
    /// this window (paint still flows). Set by the `WindowManager` to make
    /// a window's owner inert while a modal child is live.
    pub input_blocked: std::sync::atomic::AtomicBool,
    /// Lifecycle / power events seen since the last poll (e.g. "suspended",
    /// "resumed"). Python drains via `poll_lifecycle_event()`.
    pub lifecycle: Mutex<std::collections::VecDeque<String>>,
    pub a11y: Arc<crate::a11y::A11yState>,
    pub anim: Arc<ely_core::AnimRegistry>,
}

/// Monotonic source of process-unique window ids.
static NEXT_WINDOW_ID: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Default)]
pub struct MouseState {
    pub x: AtomicI32,
    pub y: AtomicI32,
    pub inside: std::sync::atomic::AtomicBool,
    pub pressed_left: std::sync::atomic::AtomicBool,
    pub pressed_right: std::sync::atomic::AtomicBool,
    /// Monotonic counter incremented on every left-button press transition;
    /// Python compares against a cached value to detect new clicks.
    pub press_count: AtomicU64,
    /// Window-local origin of the most recent left-button press.
    pub left_press_x: AtomicI32,
    pub left_press_y: AtomicI32,
    /// Same counter, for right-button presses. Lets Python distinguish
    /// "open context menu" from "use this swatch".
    pub right_press_count: AtomicU64,
    /// Accumulated mouse-wheel / trackpad scroll delta since the last poll,
    /// in logical pixels ×1000 (fixed-point to fit an atomic). Line-delta
    /// wheel events are normalised to pixels via `WHEEL_LINE_PX`. Python
    /// drains via `poll_scroll_delta()` once per frame.
    pub scroll_x_milli: AtomicI32,
    pub scroll_y_milli: AtomicI32,
    /// Set whenever a precise (pixel-delta / trackpad) scroll event
    /// contributed since the last poll — lets the scroll system pick
    /// momentum behaviour. Cleared on drain.
    pub scroll_precise: std::sync::atomic::AtomicBool,
}

impl MouseState {
    pub fn record_left_press(&self) {
        self.left_press_x
            .store(self.x.load(Ordering::Acquire), Ordering::Release);
        self.left_press_y
            .store(self.y.load(Ordering::Acquire), Ordering::Release);
        self.press_count.fetch_add(1, Ordering::AcqRel);
    }
}

/// One wheel "line" is treated as this many logical pixels when an OS
/// reports `MouseScrollDelta::LineDelta` (mouse wheels) rather than precise
/// pixel deltas (trackpads). Matches the common platform convention.
pub const WHEEL_LINE_PX: f32 = 40.0;

#[derive(Debug, Clone)]
pub struct KeyEvent {
    /// Stable identifier (e.g. "KeyV", "Escape", "Digit5", "ArrowLeft").
    pub code: String,
    /// True on key-down, false on key-up.
    pub pressed: bool,
    /// Modifier bitmask: 1=Shift, 2=Ctrl, 4=Alt, 8=Meta (Cmd / Win key).
    pub modifiers: u8,
    /// Typed character produced by the key, if any (e.g. "v", "V", "5").
    pub text: String,
}

#[derive(Debug, Default)]
pub struct KeyboardState {
    pub events: Mutex<std::collections::VecDeque<KeyEvent>>,
    pub held: Mutex<std::collections::HashSet<String>>,
    pub modifiers: std::sync::atomic::AtomicU8,
    /// Active IME composition (pre-edit) string. Updated on
    /// `WindowEvent::Ime(Ime::Preedit)`; cleared on commit / disable.
    /// Read by Python via `PyWindow.preedit()` to render candidate text.
    pub preedit: Mutex<String>,
}

/// OS-level mouse cursor icon. Maps 1:1 to a subset of
/// `winit::window::CursorIcon` covering the variants the designer
/// actually drives (resize affordances, hand, text, crosshair, move).
/// Kept Copy so it can ride inside `WindowRequest`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CursorKind {
    Default,
    Pointer,
    Text,
    Crosshair,
    Move,
    Grab,
    Grabbing,
    NotAllowed,
    /// Horizontal double-arrow (↔). For W / E mid-edge resize handles.
    EwResize,
    /// Vertical double-arrow (↕). For N / S mid-edge resize handles.
    NsResize,
    /// Diagonal double-arrow (↘↖). For NW / SE corner resize handles.
    NwseResize,
    /// Diagonal double-arrow (↙↗). For NE / SW corner resize handles.
    NeswResize,
    /// Magnifying-glass + "+" — for the Zoom tool's zoom-in mode.
    ZoomIn,
    /// Magnifying-glass + "−" — for the Zoom tool's Alt-held zoom-out.
    ZoomOut,
}

#[derive(Debug, Clone)]
pub enum WindowRequest {
    /// Cross-platform native title update, applied on the event-loop thread.
    SetTitle { title: String },
    SetOuterPosition {
        x: i32,
        y: i32,
    },
    /// macOS-only — attach (or remove) an `NSVisualEffectView` backdrop.
    /// Material is the raw `NSVisualEffectMaterial` constant; 12 = HUD,
    /// 21 = under-window background, 3 = title-bar.
    SetBlurBehind {
        enabled: bool,
        material: i64,
    },
    /// macOS-only — toggle `NSWindow.ignoresMouseEvents`. Used by the
    /// render loop to make transparent corners click through to the
    /// desktop without subclassing NSWindow.
    SetIgnoresMouse {
        ignores: bool,
    },
    /// macOS-only — toggle `NSWindow.hasShadow`.
    SetHasShadow {
        has_shadow: bool,
    },
    /// macOS-only — set `NSWindow.level`. 3 = floating, 5 = modal panel.
    SetWindowLevel {
        level: i64,
    },
    /// Cross-platform — change the OS mouse cursor icon. Python drives
    /// this from on_frame based on hover state (e.g. corner handle →
    /// nwse-resize). Coalescing happens naturally because the main
    /// thread sees only the latest request per frame.
    SetCursor {
        kind: CursorKind,
    },
    /// Cross-platform — toggle the OS minimised state. Hooked up to
    /// the custom borderless title strip in apps that paint their
    /// own traffic-light buttons (the OS handles the minimise
    /// animation when title_bar=True).
    SetMinimized {
        minimized: bool,
    },
    /// Cross-platform — toggle the OS maximised state.
    SetMaximized {
        maximized: bool,
    },
    /// Cross-platform — toggle borderless fullscreen. The "green
    /// maximise" traffic light on a custom title bar typically wants
    /// fullscreen rather than zoom; `Some(Fullscreen::Borderless)`
    /// stretches the window over the active monitor.
    SetFullscreen {
        fullscreen: bool,
    },
    /// Cross-platform — start an OS-driven interactive resize from
    /// one of the eight directional edges. Used by the Designer's
    /// borderless-window edge-resize band: on press inside the band
    /// the Designer fires this; the OS takes over until the user
    /// releases the mouse. Mirrors winit's
    /// `Window::drag_resize_window(ResizeDirection)`.
    DragResize {
        direction: ResizeDirection,
    },
    /// Cross-platform — enable/disable OS input-method composition.
    /// Required for CJK / dead-key text input. Mirrors
    /// `Window::set_ime_allowed(bool)`.
    SetImeAllowed {
        allowed: bool,
    },
    /// Cross-platform — position the IME candidate popup next to the
    /// focused caret (logical px in window coords). Mirrors
    /// `Window::set_ime_cursor_area(position, size)`.
    SetImeCursorArea {
        x: f32,
        y: f32,
        w: f32,
        h: f32,
    },
}

/// Edge/corner the user wants to resize from.  Maps 1:1 to
/// `winit::window::ResizeDirection` so the event loop's handler
/// can pattern-match without translation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResizeDirection {
    East,
    North,
    NorthEast,
    NorthWest,
    South,
    SouthEast,
    SouthWest,
    West,
}

impl WindowHandle {
    pub fn request_blur_behind(&self, enabled: bool, material: i64) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetBlurBehind { enabled, material });
    }
    pub fn request_set_ignores_mouse(&self, ignores: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetIgnoresMouse { ignores });
    }
    pub fn request_set_has_shadow(&self, has_shadow: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetHasShadow { has_shadow });
    }
    pub fn request_set_window_level(&self, level: i64) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetWindowLevel { level });
    }
    pub fn request_set_minimized(&self, minimized: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetMinimized { minimized });
    }
    pub fn request_drag_resize(&self, direction: ResizeDirection) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::DragResize { direction });
    }
    pub fn request_set_ime_allowed(&self, allowed: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetImeAllowed { allowed });
    }
    pub fn request_set_ime_cursor_area(&self, x: f32, y: f32, w: f32, h: f32) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetImeCursorArea { x, y, w, h });
    }
    pub fn request_set_maximized(&self, maximized: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetMaximized { maximized });
    }
    pub fn request_set_fullscreen(&self, fullscreen: bool) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetFullscreen { fullscreen });
    }
    /// Queue an OS cursor-icon swap. Applied by the winit main thread on
    /// its next iteration via `WinitWindow::set_cursor`.
    pub fn request_set_cursor(&self, kind: CursorKind) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetCursor { kind });
    }
}

impl WindowHandle {
    pub fn stub(config: WindowConfig) -> Self {
        let mouse = MouseState::default();
        mouse.x.store(-1, Ordering::Relaxed);
        mouse.y.store(-1, Ordering::Relaxed);
        let init_w = config.initial_size.0;
        let init_h = config.initial_size.1;
        Self {
            inner: Arc::new(WindowInner {
                config,
                scene: RwLock::new(Scene::default()),
                hooks: Arc::new(RwLock::new(ely_core_hook_stub::HookRegistry::default())),
                next_sub: AtomicU64::new(1),
                closed: std::sync::atomic::AtomicBool::new(false),
                has_published: std::sync::atomic::AtomicBool::new(false),
                display_list: Arc::new(TripleBuffer::<DisplayList>::new()),
                mouse: Arc::new(mouse),
                keyboard: Arc::new(KeyboardState::default()),
                window_requests: Arc::new(Mutex::new(Vec::new())),
                hit_test_path: Arc::new(RwLock::new(None)),
                cursor_inside_path: Arc::new(std::sync::atomic::AtomicBool::new(true)),
                file_drops: Arc::new(Mutex::new(std::collections::VecDeque::new())),
                file_hover: std::sync::atomic::AtomicBool::new(false),
                surface_w: std::sync::atomic::AtomicU32::new(init_w),
                surface_h: std::sync::atomic::AtomicU32::new(init_h),
                outer_x: AtomicI32::new(0),
                outer_y: AtomicI32::new(0),
                scale_milli: std::sync::atomic::AtomicU32::new(1000),
                monitor: RwLock::new(None),
                pinch_delta_milli: AtomicI32::new(0),
                input_seq: AtomicU64::new(0),
                wake_lock: Mutex::new(()),
                wake_cv: Condvar::new(),
                id: NEXT_WINDOW_ID.fetch_add(1, Ordering::AcqRel),
                input_blocked: std::sync::atomic::AtomicBool::new(false),
                lifecycle: Mutex::new(std::collections::VecDeque::new()),
                a11y: crate::a11y::A11yState::new(),
                anim: ely_core::AnimRegistry::new(),
            }),
        }
    }

    /// Read + reset the trackpad pinch accumulator in one shot. Returns the
    /// total pinch delta (a unit-less ratio: positive = pinch out / zoom in,
    /// negative = pinch in / zoom out) since the last call.
    pub fn drain_pinch_delta(&self) -> f32 {
        let raw = self.inner.pinch_delta_milli.swap(0, Ordering::AcqRel);
        raw as f32 / 1000.0
    }

    /// Internal — accumulate a pinch-gesture delta seen on the event loop.
    pub fn accumulate_pinch_delta(&self, delta: f32) {
        let inc = (delta * 1000.0).round() as i32;
        self.inner
            .pinch_delta_milli
            .fetch_add(inc, Ordering::AcqRel);
    }

    /// Read + reset the scroll accumulator in one shot. Returns
    /// `(dx, dy, precise)` in logical pixels since the last call; `precise`
    /// is true when a trackpad / pixel-delta event contributed.
    pub fn drain_scroll(&self) -> (f32, f32, bool) {
        let dx = self.inner.mouse.scroll_x_milli.swap(0, Ordering::AcqRel) as f32 / 1000.0;
        let dy = self.inner.mouse.scroll_y_milli.swap(0, Ordering::AcqRel) as f32 / 1000.0;
        let precise = self
            .inner
            .mouse
            .scroll_precise
            .swap(false, Ordering::AcqRel);
        (dx, dy, precise)
    }

    /// Internal — accumulate a scroll delta (logical pixels) seen on the
    /// event loop. `precise` distinguishes trackpad pixel deltas from
    /// normalised mouse-wheel line deltas.
    pub fn accumulate_scroll(&self, dx: f32, dy: f32, precise: bool) {
        self.inner
            .mouse
            .scroll_x_milli
            .fetch_add((dx * 1000.0).round() as i32, Ordering::AcqRel);
        self.inner
            .mouse
            .scroll_y_milli
            .fetch_add((dy * 1000.0).round() as i32, Ordering::AcqRel);
        if precise {
            self.inner
                .mouse
                .scroll_precise
                .store(true, Ordering::Release);
        }
    }

    /// Process-unique window id (stable for the handle's life).
    pub fn id(&self) -> u64 {
        self.inner.id
    }

    /// Whether input dispatch to this window is currently suppressed (modal
    /// owner). Checked by the event loop before applying button/key/scroll.
    pub fn is_input_blocked(&self) -> bool {
        self.inner.input_blocked.load(Ordering::Acquire)
    }
    /// Set/clear the input-suppression flag (driven by the `WindowManager`).
    pub fn set_input_blocked(&self, blocked: bool) {
        self.inner.input_blocked.store(blocked, Ordering::Release);
    }

    /// Internal — record a lifecycle/power event for Python to drain.
    pub fn push_lifecycle(&self, kind: &str) {
        self.inner.lifecycle.lock().push_back(kind.to_string());
    }
    /// Pop the oldest pending lifecycle event, if any.
    pub fn poll_lifecycle(&self) -> Option<String> {
        self.inner.lifecycle.lock().pop_front()
    }

    /// Latest logical surface size (set by the event loop on Resized).
    pub fn surface_size(&self) -> (u32, u32) {
        (
            self.inner.surface_w.load(Ordering::Acquire),
            self.inner.surface_h.load(Ordering::Acquire),
        )
    }
    pub fn set_surface_size(&self, w: u32, h: u32) {
        self.inner.surface_w.store(w, Ordering::Release);
        self.inner.surface_h.store(h, Ordering::Release);
    }
    /// Monotonic input-event counter. Read it *before* running a frame and
    /// pass the value to [`wait_for_input`](Self::wait_for_input).
    pub fn input_seq(&self) -> u64 {
        self.inner.input_seq.load(Ordering::Acquire)
    }

    /// Internal — called by the event loop for anything the app would want to
    /// react to (pointer, keyboard, scroll, IME, focus, resize, file drop).
    pub fn notify_input(&self) {
        self.inner.input_seq.fetch_add(1, Ordering::AcqRel);
        // Hold the lock across the notify so a waiter that has just checked
        // the sequence but not yet parked cannot miss the wakeup.
        let _g = self.inner.wake_lock.lock();
        self.inner.wake_cv.notify_all();
    }

    /// Block until an input event arrives or `timeout` elapses. Returns true
    /// if input arrived.
    ///
    /// `since` is the value [`input_seq`](Self::input_seq) had before the
    /// caller's last frame. Comparing against it — rather than just parking —
    /// closes the race where an event lands *while* the frame is running:
    /// without it that event would be swallowed and the app would sit idle
    /// holding stale input.
    ///
    /// This exists so the frame loop can idle cheaply without going deaf.
    /// Polling on a timer forces a trade nobody wins: a slow idle tick means
    /// a click waits up to a whole tick to be seen (and a press+release inside
    /// one tick is never seen as a drag at all), while a fast one burns CPU
    /// doing nothing.
    pub fn wait_for_input(&self, timeout: std::time::Duration, since: u64) -> bool {
        if self.inner.input_seq.load(Ordering::Acquire) != since {
            return true; // already fired, during the caller's frame
        }
        let mut guard = self.inner.wake_lock.lock();
        // Re-check under the lock: notify_input takes it too, so this closes
        // the window between the check above and parking below.
        if self.inner.input_seq.load(Ordering::Acquire) != since {
            return true;
        }
        self.inner.wake_cv.wait_for(&mut guard, timeout);
        // Spurious wakeups are allowed, so the sequence is the source of
        // truth rather than the wait's return value.
        self.inner.input_seq.load(Ordering::Acquire) != since
    }

    /// Live display scale factor (1.0 = 100%, 2.0 = Retina/200%).
    ///
    /// Tracks the display the window is actually on, so it changes when the
    /// window is dragged between monitors of different scaling. Compare with
    /// the value the renderer is using to detect a mismatch.
    pub fn scale_factor(&self) -> f64 {
        self.inner.scale_milli.load(Ordering::Acquire) as f64 / 1000.0
    }
    /// Internal — called by the event loop on creation and on
    /// `ScaleFactorChanged`.
    pub fn set_scale_factor(&self, scale: f64) {
        let s = if scale.is_finite() && scale > 0.0 {
            scale
        } else {
            1.0
        };
        self.inner
            .scale_milli
            .store((s * 1000.0).round() as u32, Ordering::Release);
    }
    /// The display this window is currently on, in logical pixels, or `None`
    /// before the first frame (or when the platform reports no monitors —
    /// a headless or remote session).
    pub fn monitor(&self) -> Option<MonitorInfo> {
        self.inner.monitor.read().clone()
    }
    /// Internal — called by the event loop when the window's display changes.
    pub fn set_monitor(&self, info: Option<MonitorInfo>) {
        *self.inner.monitor.write() = info;
    }

    /// Latest outer (top-left) screen position in logical pixels.
    pub fn outer_position(&self) -> (i32, i32) {
        (
            self.inner.outer_x.load(Ordering::Acquire),
            self.inner.outer_y.load(Ordering::Acquire),
        )
    }
    /// Internal — called by the event loop on `Moved`. Don't confuse
    /// with `request_set_position` which asks the OS to move the
    /// window; this just records where it currently *is*.
    pub fn record_outer_position(&self, x: i32, y: i32) {
        self.inner.outer_x.store(x, Ordering::Release);
        self.inner.outer_y.store(y, Ordering::Release);
    }

    pub fn hit_test_path(&self) -> Arc<RwLock<Option<ElyPath>>> {
        self.inner.hit_test_path.clone()
    }

    pub fn set_hit_test_path(&self, svg_d: Option<&str>) {
        let mut g = self.inner.hit_test_path.write();
        *g = svg_d.map(ElyPath::from_svg);
        if svg_d.is_none() {
            self.cursor_inside_path().store(true, Ordering::Release);
            self.request_set_ignores_mouse(false);
        }
    }

    pub fn cursor_inside_path(&self) -> &std::sync::atomic::AtomicBool {
        &self.inner.cursor_inside_path
    }

    pub fn mouse(&self) -> &MouseState {
        &self.inner.mouse
    }
    pub fn keyboard(&self) -> &KeyboardState {
        &self.inner.keyboard
    }
    #[allow(clippy::type_complexity)] // queue of (path, x, y) file drops
    pub fn file_drops(&self) -> &Arc<Mutex<std::collections::VecDeque<(String, f64, f64)>>> {
        &self.inner.file_drops
    }
    pub fn push_file_drop(&self, path: String, x: f64, y: f64) {
        self.inner.file_drops.lock().push_back((path, x, y));
    }
    pub fn pop_file_drop(&self) -> Option<(String, f64, f64)> {
        self.inner.file_drops.lock().pop_front()
    }
    pub fn set_file_hover(&self, hovering: bool) {
        self.inner
            .file_hover
            .store(hovering, std::sync::atomic::Ordering::Release);
    }
    pub fn is_file_hovering(&self) -> bool {
        self.inner
            .file_hover
            .load(std::sync::atomic::Ordering::Acquire)
    }
    pub fn a11y(&self) -> &Arc<crate::a11y::A11yState> {
        &self.inner.a11y
    }
    pub fn anim(&self) -> &Arc<ely_core::AnimRegistry> {
        &self.inner.anim
    }

    pub fn request_set_position(&self, x: i32, y: i32) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetOuterPosition { x, y });
    }

    pub fn request_set_title(&self, title: String) {
        self.inner
            .window_requests
            .lock()
            .push(WindowRequest::SetTitle { title });
    }

    pub fn drain_window_requests(&self) -> Vec<WindowRequest> {
        std::mem::take(&mut *self.inner.window_requests.lock())
    }

    pub fn display_list(&self) -> Arc<TripleBuffer<DisplayList>> {
        self.inner.display_list.clone()
    }

    /// Producer side: publish a fresh display list. Wakes nothing — the
    /// render loop polls each frame via `try_acquire`.
    pub fn publish_display_list(&self, list: DisplayList) {
        self.inner.display_list.producer_slot().with_mut(|slot| {
            *slot = list;
        });
        self.inner.display_list.publish();
        self.inner
            .has_published
            .store(true, std::sync::atomic::Ordering::Release);
    }

    /// True when any caller has published into the triple buffer at
    /// least once. The event loop reads this before seeding its
    /// placeholder so a Python `load_skin()` that ran before the
    /// window was actually created isn't silently overwritten.
    pub fn has_published(&self) -> bool {
        self.inner
            .has_published
            .load(std::sync::atomic::Ordering::Acquire)
    }
    pub fn config(&self) -> &WindowConfig {
        &self.inner.config
    }
    pub fn hook_registry(&self) -> Arc<RwLock<ely_core_hook_stub::HookRegistry>> {
        self.inner.hooks.clone()
    }
    pub fn scene(&self) -> parking_lot::RwLockReadGuard<'_, Scene> {
        self.inner.scene.read()
    }
    pub fn scene_mut(&self) -> parking_lot::RwLockWriteGuard<'_, Scene> {
        self.inner.scene.write()
    }

    pub fn subscribe(
        &self,
        _node_id: NodeId,
        _callback: impl Fn(&Event) + Send + Sync + 'static,
    ) -> SubscriptionId {
        self.inner.next_sub.fetch_add(1, Ordering::Relaxed)
    }
    pub fn unsubscribe(&self, _id: SubscriptionId) {}
    pub fn close(&self) {
        self.inner
            .closed
            .store(true, std::sync::atomic::Ordering::Release);
    }
}

// Lean hook registry held inside the window. Mirrors the on-disk shape
// from ely-skin's HookRegistry but without depending on ely-skin (which
// would invert the dependency direction). The PyO3 binding crate or
// future runtime helper does the translation when loading a `.esk`.
pub mod ely_core_hook_stub {
    use std::collections::HashMap;

    #[derive(Debug, Default)]
    pub struct HookRegistry {
        map: HashMap<String, Hook>,
    }
    impl HookRegistry {
        pub fn insert(&mut self, h: Hook) {
            self.map.insert(h.name.clone(), h);
        }
        pub fn get(&self, key: &str) -> Option<&Hook> {
            self.map.get(key)
        }
        pub fn iter(&self) -> impl Iterator<Item = (&String, &Hook)> {
            self.map.iter()
        }
        pub fn len(&self) -> usize {
            self.map.len()
        }
        pub fn is_empty(&self) -> bool {
            self.map.is_empty()
        }
        pub fn clear(&mut self) {
            self.map.clear();
        }
    }

    #[derive(Debug, Clone)]
    pub struct Hook {
        pub name: String,
        pub node_id: u32,
        pub kind: HookKind,
    }
    impl Hook {
        pub fn id(&self) -> u32 {
            self.node_id
        }
    }

    #[derive(Debug, Clone)]
    pub enum HookKind {
        Event { events: Vec<String> },
        Text,
        Image,
        Value { min: f64, max: f64 },
        State { states: Vec<String> },
        Slot,
        Style,
    }
}

#[cfg(test)]
mod tier2_tests {
    use super::*;

    #[test]
    fn press_origin_survives_motion_and_release_between_frames() {
        let mouse = MouseState::default();
        mouse.x.store(120, Ordering::Release);
        mouse.y.store(160, Ordering::Release);
        mouse.record_left_press();
        mouse.x.store(240, Ordering::Release);
        mouse.y.store(190, Ordering::Release);
        mouse.pressed_left.store(false, Ordering::Release);
        assert_eq!(mouse.press_count.load(Ordering::Acquire), 1);
        assert_eq!(mouse.left_press_x.load(Ordering::Acquire), 120);
        assert_eq!(mouse.left_press_y.load(Ordering::Acquire), 160);
    }

    #[test]
    fn scroll_accumulates_and_drains() {
        let h = WindowHandle::stub(WindowConfig::default());
        h.accumulate_scroll(1.5, -2.0, false);
        h.accumulate_scroll(0.5, -1.0, true);
        let (dx, dy, precise) = h.drain_scroll();
        assert!((dx - 2.0).abs() < 1e-3);
        assert!((dy + 3.0).abs() < 1e-3);
        assert!(precise, "precise flag latches when any pixel-delta arrives");
        // Drained → reset.
        let (dx2, dy2, precise2) = h.drain_scroll();
        assert_eq!((dx2, dy2), (0.0, 0.0));
        assert!(!precise2);
    }

    #[test]
    fn input_block_flag_round_trips() {
        let h = WindowHandle::stub(WindowConfig::default());
        assert!(!h.is_input_blocked());
        h.set_input_blocked(true);
        assert!(h.is_input_blocked());
        h.set_input_blocked(false);
        assert!(!h.is_input_blocked());
    }

    #[test]
    fn window_ids_are_unique() {
        let a = WindowHandle::stub(WindowConfig::default());
        let b = WindowHandle::stub(WindowConfig::default());
        assert_ne!(a.id(), b.id());
    }

    #[test]
    fn lifecycle_events_queue_fifo() {
        let h = WindowHandle::stub(WindowConfig::default());
        assert_eq!(h.poll_lifecycle(), None);
        h.push_lifecycle("suspended");
        h.push_lifecycle("resumed");
        assert_eq!(h.poll_lifecycle().as_deref(), Some("suspended"));
        assert_eq!(h.poll_lifecycle().as_deref(), Some("resumed"));
        assert_eq!(h.poll_lifecycle(), None);
    }

    // --- display fitting (QA report item 14) ------------------------------

    /// Reference displays, as physical pixels + scale, the way winit reports
    /// them. The 1200x800 default does not fit the last three.
    fn displays() -> Vec<(&'static str, (u32, u32), f64)> {
        vec![
            ("1920x1080 @100%", (1920, 1080), 1.0),
            ("2560x1440 @100%", (2560, 1440), 1.0),
            ("MBP 14 Retina", (3024, 1964), 2.0), // 1512x982 logical
            ("1366x768 laptop", (1366, 768), 1.0),
            ("1080p @150%", (1920, 1080), 1.5), // 1280x720 logical
            ("1080p @200%", (1920, 1080), 2.0), // 960x540 logical
        ]
    }

    #[test]
    fn window_never_opens_larger_than_the_display() {
        for (name, size, scale) in displays() {
            let m = MonitorInfo::from_physical(name.into(), (0, 0), size, scale, true);
            let ((w, h), (x, y)) = m.fit((1200, 800));
            assert!(w <= m.work_width && h <= m.work_height, "{name}: {w}x{h}");
            // ...and fully on-screen, which is what makes it recoverable when
            // there is no title bar to drag by.
            assert!(x >= m.x && y >= m.y, "{name}: origin {x},{y}");
            assert!(
                x + w as i32 <= m.x + m.width as i32 && y + h as i32 <= m.y + m.height as i32,
                "{name}: {w}x{h} at {x},{y} overflows {}x{}",
                m.width,
                m.height
            );
        }
    }

    #[test]
    fn a_request_that_already_fits_is_untouched() {
        // No behaviour change on the displays where 1200x800 was always fine.
        let m = MonitorInfo::from_physical("1920x1080".into(), (0, 0), (1920, 1080), 1.0, true);
        assert_eq!(m.fit((1200, 800)).0, (1200, 800));
    }

    #[test]
    fn oversized_requests_are_clamped_on_small_displays() {
        // 1366x768 -> work area 1229x691, so the height must come down.
        let m = MonitorInfo::from_physical("1366x768".into(), (0, 0), (1366, 768), 1.0, true);
        let ((w, h), _) = m.fit((1200, 800));
        assert_eq!(w, 1200);
        assert!(h < 800 && h == m.work_height, "got {h}");
    }

    #[test]
    fn logical_size_accounts_for_scale_factor() {
        // A 1080p panel at 150% is 1280x720 to layout, not 1920x1080 — this
        // is the case a physical-pixel comparison silently gets wrong.
        let m = MonitorInfo::from_physical("150%".into(), (0, 0), (1920, 1080), 1.5, true);
        assert_eq!((m.width, m.height), (1280, 720));
        assert!(m.fit((1200, 800)).0 .1 <= 720);
    }

    #[test]
    fn window_is_centred_on_a_secondary_display() {
        // Position is respected, so a window on the right-hand monitor of a
        // dual setup lands there rather than at the virtual-desktop origin.
        let m = MonitorInfo::from_physical("right".into(), (1920, 0), (1920, 1080), 1.0, false);
        let ((w, _h), (x, _y)) = m.fit((800, 600));
        assert_eq!(w, 800);
        assert!(
            x >= 1920,
            "expected placement on the second display, got x={x}"
        );
    }

    #[test]
    fn degenerate_scale_factor_falls_back_to_one() {
        for bad in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            let m = MonitorInfo::from_physical("odd".into(), (0, 0), (1920, 1080), bad, true);
            assert_eq!(m.scale_factor, 1.0);
            assert_eq!((m.width, m.height), (1920, 1080));
        }
    }

    #[test]
    fn zero_sized_request_still_yields_a_usable_window() {
        let m = MonitorInfo::from_physical("d".into(), (0, 0), (1920, 1080), 1.0, true);
        assert_eq!(m.fit((0, 0)).0, (1, 1));
    }

    #[test]
    fn scale_factor_round_trips_through_the_handle() {
        let h = WindowHandle::stub(WindowConfig::default());
        assert_eq!(h.scale_factor(), 1.0);
        h.set_scale_factor(2.0);
        assert_eq!(h.scale_factor(), 2.0);
        h.set_scale_factor(f64::NAN); // never poison the divisor
        assert_eq!(h.scale_factor(), 1.0);
    }
}

#[cfg(test)]
mod title_request_tests {
    use super::*;

    #[test]
    fn title_updates_are_owned_and_queued_for_the_event_thread() {
        let handle = WindowHandle::stub(WindowConfig::default());
        let title = String::from("Elysium Designer — 日本語.esk");
        handle.request_set_title(title.clone());
        drop(title);
        let requests = handle.drain_window_requests();
        assert!(matches!(&requests[..], [WindowRequest::SetTitle { title }] if title == "Elysium Designer — 日本語.esk"));
        assert!(handle.drain_window_requests().is_empty());
    }
}
