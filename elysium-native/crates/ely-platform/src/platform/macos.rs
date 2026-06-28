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

use objc2::msg_send;
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
