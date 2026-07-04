//! Native NSMenu (macOS) installation, with a trampoline class that funnels
//! all menu item clicks into a single crossbeam queue Python can poll.
//!
//! On non-macOS platforms the functions are no-ops; the Designer falls back
//! to its in-window menu bar.

use crossbeam_channel::{unbounded, Receiver, Sender};
use pyo3::prelude::*;
use std::sync::OnceLock;

static MENU_CHAN: OnceLock<(Sender<i64>, Receiver<i64>)> = OnceLock::new();

fn chan() -> &'static (Sender<i64>, Receiver<i64>) {
    MENU_CHAN.get_or_init(unbounded)
}

#[cfg(target_os = "macos")] // only the macOS menu trampoline pushes actions
pub(crate) fn push_action(tag: i64) {
    let _ = chan().0.send(tag);
}

#[pyfunction]
pub fn poll_menu_action() -> Option<i64> {
    chan().1.try_recv().ok()
}

#[pyfunction]
#[pyo3(signature = (spec, app_name="Elysium Designer"))]
pub fn set_application_menu(
    spec: Vec<(String, Vec<(String, i64)>)>,
    app_name: &str,
) -> PyResult<()> {
    #[cfg(target_os = "macos")]
    {
        // AppKit's main menu + activation-policy APIs are main-thread-only, but
        // the Designer drives menu installs from a background frame thread
        // (the render/frame callback is not the macOS main thread). Calling
        // `setMainMenu:` off-main aborts the process with
        // "setting the main menu on a non-main thread". Hop to the main
        // dispatch queue. Fire-and-forget: the caller doesn't depend on
        // completion, and async avoids any deadlock with the main run loop.
        cocoa::install_native_menu_on_main(spec, app_name);
        Ok(())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (spec, app_name);
        Ok(())
    }
}

#[cfg(target_os = "macos")]
mod cocoa {
    use super::push_action;
    use objc2::declare::ClassBuilder;
    use objc2::msg_send;
    use objc2::runtime::{AnyClass, AnyObject, Bool, Sel};
    use objc2::{class, sel};
    use std::ffi::CString;
    use std::os::raw::c_void;
    use std::sync::OnceLock;

    static TRAMP_CLASS: OnceLock<&'static AnyClass> = OnceLock::new();
    static TRAMP_INSTANCE: OnceLock<usize> = OnceLock::new(); // *mut AnyObject as usize

    // --- main-thread dispatch (libdispatch, part of libSystem) -------------
    // The AppKit main-menu work below must run on the main thread. The caller
    // is on a background frame thread, so we enqueue the whole install onto
    // the main dispatch queue, which the winit event loop pumps.
    extern "C" {
        static _dispatch_main_q: c_void;
        fn dispatch_async_f(
            queue: *const c_void,
            context: *mut c_void,
            work: extern "C" fn(*mut c_void),
        );
    }

    extern "C" fn main_thread_trampoline(ctx: *mut c_void) {
        // SAFETY: `ctx` is exactly the pointer produced by `Box::into_raw`
        // in `run_on_main`, run at most once.
        let f = unsafe { Box::from_raw(ctx as *mut Box<dyn FnOnce() + Send>) };
        f();
    }

    fn run_on_main<F: FnOnce() + Send + 'static>(f: F) {
        // Double-box so the fat `dyn` pointer fits in one thin `*mut c_void`.
        let boxed: Box<Box<dyn FnOnce() + Send>> = Box::new(Box::new(f));
        let ctx = Box::into_raw(boxed) as *mut c_void;
        unsafe {
            dispatch_async_f(
                core::ptr::addr_of!(_dispatch_main_q) as *const c_void,
                ctx,
                main_thread_trampoline,
            );
        }
    }

    /// Install the native menu on the macOS main thread (see the call site in
    /// `set_application_menu`).
    pub(super) fn install_native_menu_on_main(
        spec: Vec<(String, Vec<(String, i64)>)>,
        app_name: &str,
    ) {
        let app_name = app_name.to_string();
        run_on_main(move || unsafe { install_native_menu(spec, &app_name) });
    }

    extern "C" fn fired(_this: *mut AnyObject, _cmd: Sel, sender: *mut AnyObject) {
        unsafe {
            let tag: i64 = msg_send![sender, tag];
            push_action(tag);
        }
    }

    fn ensure_class() -> &'static AnyClass {
        TRAMP_CLASS.get_or_init(|| unsafe {
            if let Some(c) = AnyClass::get("ElysiumMenuTramp") {
                return c;
            }
            let ns = class!(NSObject);
            let mut b =
                ClassBuilder::new("ElysiumMenuTramp", ns).expect("declare ElysiumMenuTramp");
            b.add_method(
                sel!(menuItemFired:),
                fired as extern "C" fn(*mut AnyObject, Sel, *mut AnyObject),
            );
            b.register()
        })
    }

    unsafe fn ns_string(s: &str) -> *mut AnyObject {
        let cls = class!(NSString);
        let c = CString::new(s).unwrap();
        let bytes: *mut AnyObject = msg_send![cls, stringWithUTF8String: c.as_ptr()];
        bytes
    }

    unsafe fn make_menu(title: &str) -> *mut AnyObject {
        let cls = class!(NSMenu);
        let m: *mut AnyObject = msg_send![cls, alloc];
        let title_ns = ns_string(title);
        let m: *mut AnyObject = msg_send![m, initWithTitle: title_ns];
        m
    }

    unsafe fn make_item(title: &str, tag: i64, target: *mut AnyObject) -> *mut AnyObject {
        let cls = class!(NSMenuItem);
        let item: *mut AnyObject = msg_send![cls, alloc];
        let t = ns_string(title);
        let empty = ns_string("");
        let sel = sel!(menuItemFired:);
        let item: *mut AnyObject =
            msg_send![item, initWithTitle: t action: sel keyEquivalent: empty];
        let _: () = msg_send![item, setTarget: target];
        let _: () = msg_send![item, setTag: tag];
        item
    }

    unsafe fn make_separator() -> *mut AnyObject {
        let cls = class!(NSMenuItem);
        let item: *mut AnyObject = msg_send![cls, separatorItem];
        item
    }

    pub(super) unsafe fn install_native_menu(
        spec: Vec<(String, Vec<(String, i64)>)>,
        app_name: &str,
    ) {
        let _ = ensure_class();
        // Build (or reuse) trampoline instance.
        let target_ptr = *TRAMP_INSTANCE.get_or_init(|| {
            let cls = ensure_class();
            let o: *mut AnyObject = msg_send![cls, alloc];
            let o: *mut AnyObject = msg_send![o, init];
            o as usize
        });
        let target = target_ptr as *mut AnyObject;

        let app: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];

        // CRITICAL: Python-spawned processes default to a transient activation
        // policy. Without this, the window renders but the OS won't deliver
        // normal mouse / keyboard events to it. NSApplicationActivationPolicyRegular = 0.
        let _: Bool = msg_send![app, setActivationPolicy: 0i64];

        // Root menu.
        let root = make_menu("");

        // Standard application menu (so quit / about work).
        let app_top = make_item("", 0, target);
        let app_menu = make_menu(app_name);
        // About …
        let about_title = format!("About {app_name}");
        let about_item = make_item(&about_title, 0, target);
        let about_sel = sel!(orderFrontStandardAboutPanel:);
        let _: () = msg_send![about_item, setAction: about_sel];
        let _: () = msg_send![about_item, setTarget: app];
        let _: () = msg_send![app_menu, addItem: about_item];
        let _: () = msg_send![app_menu, addItem: make_separator()];
        // Hide / Hide Others / Show All
        let hide_item: *mut AnyObject = msg_send![class!(NSMenuItem), alloc];
        let hide_title = ns_string(&format!("Hide {app_name}"));
        let hide_key = ns_string("h");
        let hide_sel = sel!(hide:);
        let hide_item: *mut AnyObject = msg_send![hide_item,
            initWithTitle: hide_title action: hide_sel keyEquivalent: hide_key];
        let _: () = msg_send![hide_item, setTarget: app];
        let _: () = msg_send![app_menu, addItem: hide_item];
        // Quit
        let quit_item: *mut AnyObject = msg_send![class!(NSMenuItem), alloc];
        let quit_title = ns_string(&format!("Quit {app_name}"));
        let quit_key = ns_string("q");
        let quit_sel = sel!(terminate:);
        let quit_item: *mut AnyObject = msg_send![quit_item,
            initWithTitle: quit_title action: quit_sel keyEquivalent: quit_key];
        let _: () = msg_send![quit_item, setTarget: app];
        let _: () = msg_send![app_menu, addItem: make_separator()];
        let _: () = msg_send![app_menu, addItem: quit_item];
        let _: () = msg_send![app_top, setSubmenu: app_menu];
        let _: () = msg_send![root, addItem: app_top];

        // User-defined top-level menus.
        for (top_title, items) in spec {
            let top_item = make_item(&top_title, 0, target);
            let sub = make_menu(&top_title);
            for (label, tag) in items {
                if label == "---" {
                    let _: () = msg_send![sub, addItem: make_separator()];
                } else {
                    let it = make_item(&label, tag, target);
                    let _: () = msg_send![sub, addItem: it];
                }
            }
            let _: () = msg_send![top_item, setSubmenu: sub];
            let _: () = msg_send![root, addItem: top_item];
        }

        let _: () = msg_send![app, setMainMenu: root];
        let _: () = msg_send![app, activateIgnoringOtherApps: true];
    }
}
