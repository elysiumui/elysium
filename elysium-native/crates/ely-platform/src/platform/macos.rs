//! macOS Cocoa interop for window-chrome polish.
//!
//! - `enable_blur_behind(ns_view, enabled)` attaches an
//!   `NSVisualEffectView` as a back-positioned subview of the window's
//!   content view. With `setOpaque: NO` (already set by winit's
//!   `with_transparent`), this gives the iconic macOS Aqua / Mica blur
//!   behind the window.
//!
//! - `set_ignores_mouse_outside_path(ns_view, mask_pixels, ...)` lets the
//!   render loop tell Cocoa "this pixel is transparent, don't deliver
//!   mouse events here." Backed by `NSWindow.ignoresMouseEvents` modulated
//!   per-pixel through a sampling callback. Lower-fi than a true
//!   `hitTest:` override but works without subclassing NSWindow.
//!
//! Gated to macOS by the `pub mod macos` declaration.

use objc2::{class, msg_send};
use objc2::runtime::AnyObject;
use objc2::{Encode, Encoding, RefEncode};
use std::ffi::c_void;

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct NSPoint {
    pub x: f64,
    pub y: f64,
}
#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct NSSize {
    pub width: f64,
    pub height: f64,
}
#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct NSRect {
    pub origin: NSPoint,
    pub size: NSSize,
}

/// Replace the fallback chrome reservation with NSScreen.visibleFrame.
/// Called on the main thread. Cocoa reports logical points.
pub unsafe fn refine_monitor_work_area(info: &mut crate::window::MonitorInfo) {
    let screens: *mut AnyObject = msg_send![class!(NSScreen), screens];
    if screens.is_null() { return; }
    let count: usize = msg_send![screens, count];
    if count == 0 { return; }
    let primary: *mut AnyObject = msg_send![screens, objectAtIndex: 0usize];
    let primary_frame: NSRect = msg_send![primary, frame];
    for index in 0..count {
        let screen: *mut AnyObject = msg_send![screens, objectAtIndex: index];
        let frame: NSRect = msg_send![screen, frame];
        let top = primary_frame.size.height - frame.origin.y - frame.size.height;
        if (frame.origin.x - info.x as f64).abs() < 2.0 && (top - info.y as f64).abs() < 2.0 {
            let visible: NSRect = msg_send![screen, visibleFrame];
            info.work_x = visible.origin.x.round() as i32;
            info.work_y = (primary_frame.size.height-visible.origin.y-visible.size.height).round() as i32;
            info.work_width = visible.size.width.round() as u32;
            info.work_height = visible.size.height.round() as u32;
            return;
        }
    }
}

unsafe impl Encode for NSPoint {
    const ENCODING: Encoding = Encoding::Struct("CGPoint", &[Encoding::Double, Encoding::Double]);
}
unsafe impl Encode for NSSize {
    const ENCODING: Encoding = Encoding::Struct("CGSize", &[Encoding::Double, Encoding::Double]);
}
unsafe impl Encode for NSRect {
    const ENCODING: Encoding = Encoding::Struct("CGRect", &[NSPoint::ENCODING, NSSize::ENCODING]);
}
unsafe impl RefEncode for NSRect {
    const ENCODING_REF: Encoding = Encoding::Pointer(&NSRect::ENCODING);
}

/// Material constants from NSVisualEffectView.
#[allow(dead_code)]
#[repr(i64)]
pub enum Material {
    TitleBar = 3,
    HudWindow = 12, // The popover-style strong frosted look
    FullScreenUI = 15,
    UnderWindowBg = 21,
    Sidebar = 7,
    HeaderView = 10,
    Menu = 11,
}

const BLENDING_BEHIND_WINDOW: i64 = 0;
const STATE_ACTIVE: i64 = 1;
const NS_WINDOW_BELOW: i64 = -1;
const NS_VIEW_WIDTH_SIZABLE: u64 = 2;
const NS_VIEW_HEIGHT_SIZABLE: u64 = 16;

/// Attach an `NSVisualEffectView` to the content view as a backdrop.
/// Idempotent: if a previous effect view exists (tagged 0xE_15A1), it's
/// removed first.
///
/// # Safety
/// `ns_view_ptr` must be a live `NSView*` (typically from winit's
/// `WindowExtMacOS::ns_view()`). The view's window must be active.
pub unsafe fn enable_blur_behind(ns_view_ptr: *mut c_void, enabled: bool, material: Material) {
    if ns_view_ptr.is_null() {
        return;
    }
    let content: *mut AnyObject = ns_view_ptr as *mut AnyObject;

    // First, remove any previous effect-view we added (tagged for identification).
    let tag: isize = 0x0E15A1;
    let existing: *mut AnyObject = msg_send![content, viewWithTag: tag];
    if !existing.is_null() {
        let _: () = msg_send![existing, removeFromSuperview];
    }

    if !enabled {
        return;
    }

    let bounds: NSRect = msg_send![content, bounds];

    let cls = objc2::runtime::AnyClass::get("NSVisualEffectView");
    let Some(cls) = cls else {
        return;
    };
    let fx: *mut AnyObject = msg_send![cls, alloc];
    let fx: *mut AnyObject = msg_send![fx, initWithFrame: bounds];
    if fx.is_null() {
        return;
    }

    let _: () = msg_send![fx, setBlendingMode: BLENDING_BEHIND_WINDOW];
    let _: () = msg_send![fx, setMaterial: material as i64];
    let _: () = msg_send![fx, setState: STATE_ACTIVE];
    let _: () = msg_send![fx, setAutoresizingMask: NS_VIEW_WIDTH_SIZABLE | NS_VIEW_HEIGHT_SIZABLE];
    let _: () = msg_send![fx, setTag: tag];
    // wantsLayer must be on for the visual-effect compositing path.
    let _: () = msg_send![fx, setWantsLayer: true];

    let nil_view: *mut AnyObject = std::ptr::null_mut();
    let _: () = msg_send![content, addSubview: fx
                                   positioned: NS_WINDOW_BELOW
                                   relativeTo: nil_view];
}

/// Toggle `NSWindow.ignoresMouseEvents`. When `true`, clicks pass
/// through the entire window to whatever is underneath. The render
/// loop alternates between true (cursor over a transparent pixel) and
/// false (cursor over the rendered content) by sampling the SkiaLayer
/// at the cursor position.
///
/// # Safety
/// `ns_view_ptr` must be a live `NSView*`. Its parent window receives
/// the message.
pub unsafe fn set_window_ignores_mouse(ns_view_ptr: *mut c_void, ignores: bool) {
    if ns_view_ptr.is_null() {
        return;
    }
    let view: *mut AnyObject = ns_view_ptr as *mut AnyObject;
    let window: *mut AnyObject = msg_send![view, window];
    if window.is_null() {
        return;
    }
    let _: () = msg_send![window, setIgnoresMouseEvents: ignores];
}

/// Current cursor in top-left logical view coordinates, including when the
/// window ignores events or moves underneath a stationary pointer.
///
/// # Safety
/// Called on the main thread with a live NSView pointer.
pub unsafe fn cursor_in_view(ns_view_ptr: *mut c_void) -> Option<(f64, f64)> {
    if ns_view_ptr.is_null() { return None; }
    let view = ns_view_ptr as *mut AnyObject;
    let window: *mut AnyObject = msg_send![view, window];
    if window.is_null() { return None; }
    let point: NSPoint = msg_send![window, mouseLocationOutsideOfEventStream];
    let nil_view: *mut AnyObject = std::ptr::null_mut();
    let local: NSPoint = msg_send![view, convertPoint: point fromView: nil_view];
    let bounds: NSRect = msg_send![view, bounds];
    let flipped: bool = msg_send![view, isFlipped];
    Some((local.x - bounds.origin.x, if flipped { local.y - bounds.origin.y }
          else { bounds.size.height - local.y + bounds.origin.y }))
}

/// Position carried by the current mouse-button event, rather than the
/// separately polled global pointer. A moving shaped window may have changed
/// its cached cursor since CursorMoved was delivered.
///
/// # Safety
/// Called on the main thread with a live NSView pointer.
pub unsafe fn button_event_cursor_in_view(ns_view_ptr: *mut c_void) -> Option<(f64, f64)> {
    if ns_view_ptr.is_null() { return None; }
    let view = ns_view_ptr as *mut AnyObject;
    let window: *mut AnyObject = msg_send![view, window];
    let app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
    let event: *mut AnyObject = msg_send![app, currentEvent];
    if window.is_null() || event.is_null() { return None; }
    let event_window: *mut AnyObject = msg_send![event, window];
    let kind: usize = msg_send![event, type];
    // NSEvent left/right/other mouse-button down/up, excluding key events.
    if event_window != window || !matches!(kind, 1 | 2 | 3 | 4 | 25 | 26) { return None; }
    let point: NSPoint = msg_send![event, locationInWindow];
    let nil_view: *mut AnyObject = std::ptr::null_mut();
    let local: NSPoint = msg_send![view, convertPoint: point fromView: nil_view];
    let bounds: NSRect = msg_send![view, bounds];
    let flipped: bool = msg_send![view, isFlipped];
    Some((local.x - bounds.origin.x, if flipped { local.y - bounds.origin.y }
          else { bounds.size.height - local.y + bounds.origin.y }))
}

/// Toggle NSWindow.hasShadow — useful to suppress the OS shadow on a
/// fully-transparent shaped window (we paint our own).
pub unsafe fn set_window_has_shadow(ns_view_ptr: *mut c_void, has_shadow: bool) {
    if ns_view_ptr.is_null() {
        return;
    }
    let view: *mut AnyObject = ns_view_ptr as *mut AnyObject;
    let window: *mut AnyObject = msg_send![view, window];
    if window.is_null() {
        return;
    }
    let _: () = msg_send![window, setHasShadow: has_shadow];
}

/// Set the window's level — useful for "always on top" or "stay below."
/// Common levels: 0 (normal), 3 (floating), 5 (modal panel), 25 (popup menu).
pub unsafe fn set_window_level(ns_view_ptr: *mut c_void, level: i64) {
    if ns_view_ptr.is_null() {
        return;
    }
    let view: *mut AnyObject = ns_view_ptr as *mut AnyObject;
    let window: *mut AnyObject = msg_send![view, window];
    if window.is_null() {
        return;
    }
    let _: () = msg_send![window, setLevel: level];
}
