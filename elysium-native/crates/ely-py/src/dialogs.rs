//! Native file-picker dialog. Returns `None` on cancel or when no native
//! implementation is available on the current platform.

use pyo3::prelude::*;

#[pyfunction]
#[pyo3(signature = (title=None, initial_dir=None, filter_label=None, filter_patterns=None, save=false))]
pub fn open_file_dialog(
    title: Option<String>,
    initial_dir: Option<String>,
    filter_label: Option<String>,
    filter_patterns: Option<Vec<String>>,
    save: bool,
) -> PyResult<Option<String>> {
    #[cfg(target_os = "macos")]
    {
        return Ok(unsafe { macos::run_dialog(
            title.as_deref(), initial_dir.as_deref(),
            filter_label.as_deref(), filter_patterns.as_deref(), save,
        )});
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (title, initial_dir, filter_label, filter_patterns, save);
        Ok(None)
    }
}

#[cfg(target_os = "macos")]
mod macos {
    use objc2::msg_send;
    use objc2::runtime::AnyObject;
    use objc2::class;
    use std::ffi::CString;

    unsafe fn ns_string(s: &str) -> *mut AnyObject {
        let c = CString::new(s).unwrap();
        msg_send![class!(NSString), stringWithUTF8String: c.as_ptr()]
    }

    unsafe fn read_utf8(s: *mut AnyObject) -> Option<String> {
        if s.is_null() { return None; }
        let cstr: *const i8 = msg_send![s, UTF8String];
        if cstr.is_null() { return None; }
        Some(std::ffi::CStr::from_ptr(cstr).to_string_lossy().into_owned())
    }

    pub(super) unsafe fn run_dialog(
        title: Option<&str>,
        initial_dir: Option<&str>,
        filter_label: Option<&str>,
        filter_patterns: Option<&[String]>,
        save: bool,
    ) -> Option<String> {
        let cls = if save { class!(NSSavePanel) } else { class!(NSOpenPanel) };
        let panel: *mut AnyObject = msg_send![cls, savePanel];   // class method on both
        if !save {
            let _: () = msg_send![panel, setCanChooseFiles: true];
            let _: () = msg_send![panel, setCanChooseDirectories: false];
            let _: () = msg_send![panel, setAllowsMultipleSelection: false];
        }
        if let Some(t) = title {
            let _: () = msg_send![panel, setTitle: ns_string(t)];
        }
        if let Some(dir) = initial_dir {
            let url_cls = class!(NSURL);
            let dir_ns = ns_string(dir);
            let url: *mut AnyObject = msg_send![url_cls, fileURLWithPath: dir_ns isDirectory: true];
            let _: () = msg_send![panel, setDirectoryURL: url];
        }
        if let Some(pats) = filter_patterns {
            // Best-effort: derive extensions from glob patterns like "*.svg".
            let cls_set = class!(NSMutableArray);
            let arr: *mut AnyObject = msg_send![cls_set, array];
            for p in pats {
                if let Some(ext) = p.rsplit('.').next() {
                    let ext = ext.trim_start_matches('*').trim_start_matches('.');
                    if !ext.is_empty() {
                        let s = ns_string(ext);
                        let _: () = msg_send![arr, addObject: s];
                    }
                }
            }
            let _: () = msg_send![panel, setAllowedFileTypes: arr];
        }
        let _ = filter_label;   // unused — Cocoa's filter UI is implicit
        let response: i64 = msg_send![panel, runModal];
        if response != 1 {
            return None;
        }
        let url: *mut AnyObject = msg_send![panel, URL];
        let path: *mut AnyObject = msg_send![url, path];
        read_utf8(path)
    }
}


#[pyfunction]
pub fn path_bounds(d: &str) -> PyResult<(f32, f32, f32, f32)> {
    let p = skia_safe::utils::parse_path::from_svg(d)
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("invalid SVG path"))?;
    let b = p.compute_tight_bounds();
    Ok((b.left, b.top, b.width(), b.height()))
}
