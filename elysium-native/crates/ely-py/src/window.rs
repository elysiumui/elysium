use std::sync::Arc;

use parking_lot::RwLock;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::display_list::PyDisplayList;
use crate::errors::{HookNotFound, SkinError as PySkinError};
use crate::scene::PyHookProxy;
use ely_platform::window::{
    ely_core_hook_stub::{Hook as PHook, HookKind as PHookKind, HookRegistry},
    CursorKind, WindowConfig, WindowHandle,
};
use ely_skin::{compile as compile_skin, load as load_skin_from_path, HookKind as SkinHookKind};

pub fn config_from_kwargs(
    py: Python<'_>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<WindowConfig> {
    let _ = py;
    let mut cfg = WindowConfig::default();
    if let Some(kw) = kwargs {
        if let Some(v) = kw.get_item("skin")? {
            cfg.skin_path = Some(v.extract()?);
        }
        if let Some(v) = kw.get_item("variant")? {
            cfg.variant = Some(v.extract()?);
        }
        if let Some(v) = kw.get_item("shaped")? {
            cfg.shaped = v.extract()?;
        }
        if let Some(v) = kw.get_item("transparent")? {
            cfg.transparent = v.extract()?;
        }
        if let Some(v) = kw.get_item("title_bar")? {
            cfg.title_bar = v.extract()?;
        }
        if let Some(v) = kw.get_item("resizable")? {
            cfg.resizable = v.extract()?;
        }
        if let Some(v) = kw.get_item("blur_behind")? {
            cfg.blur_behind = v.extract()?;
        }
        if let Some(v) = kw.get_item("always_on_top")? {
            cfg.always_on_top = v.extract()?;
        }
        if let Some(v) = kw.get_item("min_size")? {
            cfg.min_size = Some(v.extract()?);
        }
        if let Some(v) = kw.get_item("initial_size")? {
            cfg.initial_size = v.extract()?;
        }
        if let Some(v) = kw.get_item("owner_id")? {
            cfg.owner_id = Some(v.extract()?);
        }
        if let Some(v) = kw.get_item("modal")? {
            cfg.modal = v.extract()?;
        }
    }
    Ok(cfg)
}

// `Window` is logically bound to the OS main thread, but its internals
// (WindowHandle clones, Arc<MouseState>) are Send+Sync. We drop the
// `unsendable` marker so Python animation/IPC threads can poll cursor
// state + publish display lists across thread boundaries.
#[pyclass(name = "Window")]
pub struct PyWindow {
    handle: Arc<WindowHandle>,
    hooks: Arc<RwLock<HookRegistry>>,
}

impl PyWindow {
    pub(crate) fn wrap(handle: WindowHandle) -> Self {
        let hooks = handle.hook_registry();
        Self {
            handle: Arc::new(handle),
            hooks,
        }
    }
}

#[pymethods]
impl PyWindow {
    fn __getitem__(&self, key: &str) -> PyResult<PyHookProxy> {
        let hook = self
            .hooks
            .read()
            .get(key)
            .ok_or_else(|| HookNotFound::new_err(format!("hook '{key}' not found")))?
            .clone();
        Ok(PyHookProxy::new(self.handle.clone(), hook))
    }

    fn close(&self) {
        self.handle.close();
    }

    /// (x, y) in window-local logical pixels, or `None` if the cursor is
    /// outside the window. Read each animation frame from Python.
    #[getter]
    fn cursor_position(&self) -> Option<(i32, i32)> {
        use std::sync::atomic::Ordering;
        let m = self.handle.mouse();
        if !m.inside.load(Ordering::Acquire) {
            return None;
        }
        let x = m.x.load(Ordering::Acquire);
        let y = m.y.load(Ordering::Acquire);
        if x < 0 || y < 0 {
            return None;
        }
        Some((x, y))
    }

    #[getter]
    fn cursor_inside(&self) -> bool {
        self.handle
            .mouse()
            .inside
            .load(std::sync::atomic::Ordering::Acquire)
    }

    #[getter]
    fn mouse_pressed(&self) -> bool {
        self.handle
            .mouse()
            .pressed_left
            .load(std::sync::atomic::Ordering::Acquire)
    }

    #[getter]
    fn press_count(&self) -> u64 {
        self.handle
            .mouse()
            .press_count
            .load(std::sync::atomic::Ordering::Acquire)
    }

    #[getter]
    fn mouse_right_pressed(&self) -> bool {
        self.handle
            .mouse()
            .pressed_right
            .load(std::sync::atomic::Ordering::Acquire)
    }

    #[getter]
    fn right_press_count(&self) -> u64 {
        self.handle
            .mouse()
            .right_press_count
            .load(std::sync::atomic::Ordering::Acquire)
    }

    /// Pop the oldest pending file-drop event. Returns `(path, x, y)` in
    /// window-local logical pixels, or `None` when the queue is empty.
    /// Latest logical-pixel surface size of the OS window. Updates as
    /// the user resizes / fullscreens. Read this every frame so layout
    /// math reacts to window changes.
    #[getter]
    fn surface_size(&self) -> (u32, u32) {
        self.handle.surface_size()
    }

    /// Latest outer (top-left) screen position in logical pixels.
    /// Pair with `set_outer_position(x, y)` to persist + restore the
    /// window's location across launches.
    #[getter]
    fn outer_position(&self) -> (i32, i32) {
        self.handle.outer_position()
    }

    fn poll_file_drop(&self) -> Option<(String, f64, f64)> {
        self.handle.pop_file_drop()
    }

    /// Drain (read + reset) the accumulated trackpad pinch-gesture delta
    /// since the last poll. Positive = pinch out / zoom in, negative =
    /// pinch in / zoom out. Returns 0.0 if no pinch occurred. Call once
    /// per frame from on_frame.
    fn poll_pinch_delta(&self) -> f32 {
        self.handle.drain_pinch_delta()
    }

    /// Drain (read + reset) the accumulated mouse-wheel / trackpad scroll
    /// delta since the last poll. Returns `(dx, dy, precise)` in logical
    /// pixels — `precise` is True for trackpad pixel deltas (momentum
    /// candidates), False for normalised mouse-wheel line deltas. Call once
    /// per frame; route the delta to the hovered scrollable.
    fn poll_scroll_delta(&self) -> (f32, f32, bool) {
        self.handle.drain_scroll()
    }

    /// Pop the next pending lifecycle / power event ("suspended",
    /// "resumed", "memory_warning"), or None. Lets apps pause animation /
    /// flush state when the OS suspends the process.
    fn poll_lifecycle_event(&self) -> Option<String> {
        self.handle.poll_lifecycle()
    }

    /// Process-unique window id. Stable for the window's life; used to
    /// express owner/child + modal relationships in the WindowManager.
    #[getter]
    fn id(&self) -> u64 {
        self.handle.id()
    }

    /// Suppress (or restore) OS input dispatch to this window — mouse
    /// buttons, keys, and scroll are dropped while blocked; paint still
    /// flows. The WindowManager sets this on a modal dialog's owner.
    fn set_input_blocked(&self, blocked: bool) {
        self.handle.set_input_blocked(blocked);
    }

    /// Whether input to this window is currently suppressed.
    #[getter]
    fn input_blocked(&self) -> bool {
        self.handle.is_input_blocked()
    }

    /// True while the user is dragging a file over the window (after
    /// HoveredFile but before Drop / Cancel). Use this to paint a drop
    /// target overlay each frame.
    #[getter]
    fn file_hovering(&self) -> bool {
        self.handle.is_file_hovering()
    }

    /// Publish the accessible tree for the current frame. `nodes` is a
    /// flat list of dicts each carrying `id`, `role`, optionally
    /// `label`, `description`, `shortcut`, `bounds` (4-tuple) and
    /// `children` (list of child ids). The platform bridge maps this to
    /// NSAccessibility / AT-SPI2 / UIA the next time the OS asks.
    fn publish_a11y_tree(
        &self,
        root_id: u64,
        nodes: Vec<pyo3::Bound<'_, pyo3::types::PyDict>>,
    ) -> PyResult<()> {
        let mut by_id: std::collections::HashMap<u64, ely_platform::a11y::A11yNode> =
            Default::default();
        let mut parents: std::collections::HashMap<u64, Vec<u64>> = Default::default();
        for d in nodes {
            let id: u64 = d.get_item("id")?.unwrap().extract()?;
            let role: String = d.get_item("role")?.unwrap().extract()?;
            let label = d
                .get_item("label")
                .ok()
                .flatten()
                .and_then(|v| v.extract::<String>().ok());
            let desc = d
                .get_item("description")
                .ok()
                .flatten()
                .and_then(|v| v.extract::<String>().ok());
            let sc = d
                .get_item("shortcut")
                .ok()
                .flatten()
                .and_then(|v| v.extract::<String>().ok());
            let bounds: (f32, f32, f32, f32) = d
                .get_item("bounds")?
                .map(|v| v.extract().unwrap_or((0.0, 0.0, 0.0, 0.0)))
                .unwrap_or((0.0, 0.0, 0.0, 0.0));
            let kids: Vec<u64> = d
                .get_item("children")?
                .map(|v| v.extract().unwrap_or_default())
                .unwrap_or_default();
            parents.insert(id, kids);
            by_id.insert(
                id,
                ely_platform::a11y::A11yNode {
                    id,
                    role,
                    label,
                    description: desc,
                    shortcut: sc,
                    bounds,
                    children: Vec::new(),
                },
            );
        }
        fn build(
            id: u64,
            by_id: &std::collections::HashMap<u64, ely_platform::a11y::A11yNode>,
            parents: &std::collections::HashMap<u64, Vec<u64>>,
        ) -> ely_platform::a11y::A11yNode {
            let mut node = by_id
                .get(&id)
                .cloned()
                .unwrap_or(ely_platform::a11y::A11yNode {
                    id,
                    role: "group".into(),
                    label: None,
                    description: None,
                    shortcut: None,
                    bounds: (0.0, 0.0, 0.0, 0.0),
                    children: Vec::new(),
                });
            if let Some(kids) = parents.get(&id) {
                node.children = kids.iter().map(|k| build(*k, by_id, parents)).collect();
            }
            node
        }
        let tree = ely_platform::a11y::A11yTree {
            root: Some(build(root_id, &by_id, &parents)),
        };
        self.handle.a11y().publish(tree);
        Ok(())
    }

    /// Tell the OS-level a11y bridge which node id is currently focused.
    #[pyo3(signature = (id=None))]
    fn set_a11y_focus(&self, id: Option<u64>) {
        self.handle.a11y().set_focus(id);
    }

    /// Hit-test the accessible tree at a window-local point. Returns the
    /// matched node's id, or None.
    fn a11y_hit(&self, x: f32, y: f32) -> Option<u64> {
        self.handle.a11y().hit(x, y).map(|n| n.id)
    }

    /// Pop the oldest pending assistive-tech action: a screen reader
    /// asking us to "click this button", "focus this", etc. Returns
    /// `(node_id, action_name)` or None when the queue is empty.
    /// Drain this once per frame and dispatch to your hook handlers.
    fn poll_a11y_action(&self) -> Option<(u64, String)> {
        self.handle.a11y().pop_action()
    }

    /// Push a target tween into render-thread animation `slot`. Easing
    /// is one of `"linear" | "ease_in" | "ease_out" | "ease_in_out" |
    /// "spring"`. For `"spring"` you can pass `(stiffness, damping)`
    /// in the tuple form `(target, duration, "spring", stiffness, damping)`.
    /// The render thread interpolates without re-entering Python.
    #[pyo3(signature = (slot, tx, ty, sx=1.0, sy=1.0, rotation=0.0, alpha=1.0,
                        duration=0.3, easing="ease_out", spring_k=180.0, spring_d=26.0))]
    fn anim_set_target(
        &self,
        slot: u32,
        tx: f32,
        ty: f32,
        sx: f32,
        sy: f32,
        rotation: f32,
        alpha: f32,
        duration: f32,
        easing: &str,
        spring_k: f32,
        spring_d: f32,
    ) {
        use ely_core::{Easing, TransformValue};
        let e = match easing {
            "linear" => Easing::Linear,
            "ease_in" => Easing::EaseIn,
            "ease_in_out" => Easing::EaseInOut,
            "spring" => Easing::Spring {
                stiffness: spring_k,
                damping: spring_d,
            },
            _ => Easing::EaseOut,
        };
        // Reduce-motion: collapse the tween to a near-instant snap.
        // Honors $ELYSIUM_REDUCE_MOTION (set by elysium.accessibility's
        // poller when the OS reports the user's pref).
        let scaled = if std::env::var("ELYSIUM_REDUCE_MOTION").as_deref() == Ok("1") {
            duration * 0.05
        } else {
            duration
        };
        self.handle.anim().set_target(
            slot,
            TransformValue {
                tx,
                ty,
                sx,
                sy,
                rotation,
                alpha,
            },
            scaled,
            e,
        );
    }

    /// Hard-snap a slot to a value with no tween.
    #[pyo3(signature = (slot, tx, ty, sx=1.0, sy=1.0, rotation=0.0, alpha=1.0))]
    fn anim_snap(&self, slot: u32, tx: f32, ty: f32, sx: f32, sy: f32, rotation: f32, alpha: f32) {
        self.handle.anim().snap(
            slot,
            ely_core::TransformValue {
                tx,
                ty,
                sx,
                sy,
                rotation,
                alpha,
            },
        );
    }

    /// Read the current (render-thread-resolved) tween value for `slot`.
    fn anim_current(&self, slot: u32) -> Option<(f32, f32, f32, f32, f32, f32)> {
        self.handle
            .anim()
            .current(slot)
            .map(|v| (v.tx, v.ty, v.sx, v.sy, v.rotation, v.alpha))
    }

    fn anim_clear(&self, slot: u32) {
        self.handle.anim().clear(slot);
    }

    /// Pop the oldest pending key event. Returns `(code, pressed, modifiers, text)`
    /// or `None` if the queue is empty. `modifiers` is a bitmask:
    /// 1=Shift, 2=Ctrl, 4=Alt, 8=Meta (Cmd / Win key).
    fn poll_key_event(&self) -> Option<(String, bool, u8, String)> {
        let mut q = self.handle.keyboard().events.lock();
        q.pop_front()
            .map(|e| (e.code, e.pressed, e.modifiers, e.text))
    }

    /// Snapshot of currently-held key codes.
    fn keys_held(&self) -> Vec<String> {
        self.handle.keyboard().held.lock().iter().cloned().collect()
    }

    #[getter]
    fn modifiers(&self) -> u8 {
        self.handle
            .keyboard()
            .modifiers
            .load(std::sync::atomic::Ordering::Acquire)
    }

    /// Current IME composition (pre-edit) string, or "" when no
    /// composition is active. The text-input layer reads this each frame
    /// to render the underlined candidate text while a CJK / accent
    /// composition is in progress. Committed text arrives separately as a
    /// `poll_key_event` entry whose `code == "ImeCommit"` and whose
    /// `text` is the finished string.
    fn preedit(&self) -> String {
        self.handle.keyboard().preedit.lock().clone()
    }

    /// Enable or disable OS input-method composition for this window.
    /// Must be on for CJK / dead-key input to work. Off by default so
    /// pure-hotkey apps don't get composition popups; the input router
    /// turns it on when an editable widget gains focus.
    fn set_ime_allowed(&self, allowed: bool) {
        self.handle.request_set_ime_allowed(allowed);
    }

    /// Tell the OS where the focused text caret is (logical px, window
    /// coords) so the candidate-selection popup appears next to it
    /// rather than at the window origin. Call when the caret moves.
    fn set_ime_cursor_area(&self, x: f32, y: f32, w: f32, h: f32) {
        self.handle.request_set_ime_cursor_area(x, y, w, h);
    }

    /// Put `text` on the system clipboard. Cross-platform via `arboard`.
    /// Safe to call from any thread.
    fn set_clipboard_text(&self, text: &str) -> PyResult<()> {
        let mut cb = arboard::Clipboard::new().map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("clipboard open failed: {e}"))
        })?;
        cb.set_text(text.to_string()).map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("clipboard write failed: {e}"))
        })?;
        Ok(())
    }

    /// Read text from the system clipboard. Returns "" when the clipboard
    /// is empty or holds non-text content. Cross-platform via `arboard`.
    fn get_clipboard_text(&self) -> PyResult<String> {
        match arboard::Clipboard::new() {
            Ok(mut cb) => Ok(cb.get_text().unwrap_or_default()),
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                "clipboard open failed: {e}"
            ))),
        }
    }

    /// Move the window's top-left corner to (x, y) on screen in
    /// physical pixels. Non-blocking; the main thread applies the
    /// request on its next iteration.
    fn set_outer_position(&self, x: i32, y: i32) {
        self.handle.request_set_position(x, y);
    }

    /// Toggle the OS minimised state. Drives the OS's native
    /// minimise animation (Dock-bounce on macOS, taskbar-flash on
    /// Windows). Custom borderless windows that paint their own
    /// traffic-light buttons call this from the minimise click.
    fn set_minimized(&self, minimized: bool) {
        self.handle.request_set_minimized(minimized);
    }

    /// Begin an OS-driven interactive resize from a specific edge
    /// or corner. `direction` is one of
    /// `"e" | "n" | "ne" | "nw" | "s" | "se" | "sw" | "w"`.
    /// Used by the Designer's borderless-window edge-resize band:
    /// on press inside the band, dispatch this and the OS takes
    /// over until the user releases the mouse. Backed by winit's
    /// `Window::drag_resize_window` (winit 0.30+).
    fn drag_resize_window(&self, direction: &str) -> PyResult<()> {
        use ely_platform::window::ResizeDirection as RD;
        let dir = match direction.to_ascii_lowercase().as_str() {
            "e" | "east" => RD::East,
            "n" | "north" => RD::North,
            "ne" | "northeast" => RD::NorthEast,
            "nw" | "northwest" => RD::NorthWest,
            "s" | "south" => RD::South,
            "se" | "southeast" => RD::SouthEast,
            "sw" | "southwest" => RD::SouthWest,
            "w" | "west" => RD::West,
            other => {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "drag_resize_window: unknown direction {:?}; \
                         expected one of e/n/ne/nw/s/se/sw/w",
                    other
                )))
            }
        };
        self.handle.request_drag_resize(dir);
        Ok(())
    }

    /// Toggle the OS maximised state. Custom borderless windows
    /// that paint their own traffic-light buttons call this from
    /// the maximise click.
    fn set_maximized(&self, maximized: bool) {
        self.handle.request_set_maximized(maximized);
    }

    /// Toggle borderless fullscreen. Stretches the window over the
    /// active monitor; pass False to restore to windowed. Custom
    /// title bars that paint a "green maximise" traffic light wire
    /// this from the green button.
    fn set_fullscreen(&self, fullscreen: bool) {
        self.handle.request_set_fullscreen(fullscreen);
    }

    /// macOS: attach (or detach) an `NSVisualEffectView` backdrop.
    /// `material`: 3=titlebar, 12=HUD, 21=under-window, 7=sidebar,
    /// 10=header, 11=menu. Defaults to 12 (HUD).
    #[pyo3(signature = (enabled, material=12))]
    fn set_blur_behind(&self, enabled: bool, material: i64) {
        self.handle.request_blur_behind(enabled, material);
    }

    /// macOS: when `True`, the whole window lets clicks pass through to
    /// whatever is underneath. The animation loop typically toggles
    /// this based on whether the cursor is over an opaque pixel.
    fn set_ignores_mouse(&self, ignores: bool) {
        self.handle.request_set_ignores_mouse(ignores);
    }

    /// macOS: toggle the standard OS-drawn drop shadow.
    fn set_has_shadow(&self, has_shadow: bool) {
        self.handle.request_set_has_shadow(has_shadow);
    }

    /// macOS: set window stacking level. 3=floating (always on top of
    /// regular windows), 5=modal panel, 25=popup menu. Default 0.
    fn set_window_level(&self, level: i64) {
        self.handle.request_set_window_level(level);
    }

    /// Swap the OS-level mouse cursor icon. `kind` is a CSS-style name:
    /// `"default" | "pointer" | "text" | "crosshair" | "move" |
    /// "grab" | "grabbing" | "not-allowed" | "ew-resize" | "ns-resize" |
    /// "nwse-resize" | "nesw-resize"`. Unknown names fall back to
    /// `"default"`. Non-blocking; the main thread applies the request
    /// on its next iteration via `winit::window::Window::set_cursor`.
    fn set_cursor(&self, kind: &str) {
        let k = match kind {
            "default" => CursorKind::Default,
            "pointer" | "hand" => CursorKind::Pointer,
            "text" => CursorKind::Text,
            "crosshair" => CursorKind::Crosshair,
            "move" => CursorKind::Move,
            "grab" => CursorKind::Grab,
            "grabbing" => CursorKind::Grabbing,
            "not-allowed" | "no-drop" => CursorKind::NotAllowed,
            "ew-resize" => CursorKind::EwResize,
            "ns-resize" => CursorKind::NsResize,
            "nwse-resize" => CursorKind::NwseResize,
            "nesw-resize" => CursorKind::NeswResize,
            "zoom-in" => CursorKind::ZoomIn,
            "zoom-out" => CursorKind::ZoomOut,
            // Convenience aliases — fall back to the closest standard
            // cursor on Maya-style names that don't have a 1:1 winit
            // equivalent.
            "closedhand" => CursorKind::Grabbing,
            "openhand" => CursorKind::Grab,
            "crosshair-soft" => CursorKind::Crosshair,
            "pivot-cross" => CursorKind::Crosshair,
            _ => CursorKind::Default,
        };
        self.handle.request_set_cursor(k);
    }

    /// Set an SVG-path that defines the window's interactive region.
    /// Cursor positions outside the path will pass clicks through to
    /// the desktop (the OS window's `ignoresMouseEvents` is toggled on
    /// the transition edge). Pass `None` to disable.
    #[pyo3(signature = (svg_d=None))]
    fn set_hit_test_path(&self, svg_d: Option<&str>) {
        self.handle.set_hit_test_path(svg_d);
    }

    /// Publish a fresh display list. Safe to call from any thread; the
    /// triple-buffered queue is lock-free between Python (producer) and
    /// the render loop (consumer).
    fn publish_display_list(&self, dl: &PyDisplayList) {
        self.handle.publish_display_list(dl.inner.clone());
    }

    /// Load a `.esk` skin from disk, register its hooks, compile its
    /// document to a DisplayList, and publish it. The scene becomes
    /// immediately visible on the next render frame.
    #[pyo3(signature = (path, surface_size=None))]
    fn load_skin(&self, path: &str, surface_size: Option<(u32, u32)>) -> PyResult<()> {
        let skin = load_skin_from_path(path).map_err(|e| PySkinError::new_err(e.to_string()))?;

        // Register hooks into the window's flat registry. We blow away
        // any previously-loaded hooks first so reloads don't accumulate.
        {
            let mut reg = self.hooks.write();
            reg.clear();
            for (name, h) in skin.hooks.iter() {
                let kind = match &h.kind {
                    SkinHookKind::Event { events } => PHookKind::Event {
                        events: events.clone(),
                    },
                    SkinHookKind::Text => PHookKind::Text,
                    SkinHookKind::Image => PHookKind::Image,
                    SkinHookKind::Value { range } => {
                        let (min, max) = range.map(|r| (r[0], r[1])).unwrap_or((0.0, 1.0));
                        PHookKind::Value { min, max }
                    }
                    SkinHookKind::State { states } => PHookKind::State {
                        states: states.clone(),
                    },
                    SkinHookKind::Slot => PHookKind::Slot,
                    SkinHookKind::Style => PHookKind::Style,
                };
                reg.insert(PHook {
                    name: name.clone(),
                    node_id: 0,
                    kind,
                });
            }
        }

        // Compile and publish at requested size (or the initial window size).
        let (sw, sh) = surface_size.unwrap_or(self.handle.config().initial_size);
        let dl = compile_skin(&skin.document, sw, sh);
        self.handle.publish_display_list(dl);
        Ok(())
    }
}
