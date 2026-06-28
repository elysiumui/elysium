//! macOS Metal interop: zero-copy texture sharing between Skia and wgpu.
//!
//! Strategy: allocate an `IOSurface` (BGRA8) once. Skia paints into its
//! CPU-mapped base address via `wrap_pixels`. wgpu wraps the same
//! IOSurface as a Metal `MTLTexture` via the wgpu_hal Metal backend —
//! no per-frame upload, no copy. The render thread issues a lightweight
//! memory barrier (`IOSurfaceUnlock`) after Skia paints so Metal sees
//! the latest pixels.

// FFI interop module (gated to macOS by the `pub mod metal` declaration).
// Some IOSurface accessors are declared for completeness but unused; the
// `unsafe fn` wrappers are inherently unsafe FFI with documented contracts.
#![allow(dead_code, clippy::missing_safety_doc)]

use std::ffi::c_void;
use std::os::raw::c_int;

#[repr(C)]
#[derive(Copy, Clone)]
struct CGSize {
    width: f64,
    height: f64,
}

#[link(name = "IOSurface", kind = "framework")]
extern "C" {
    fn IOSurfaceCreate(properties: *mut c_void) -> *mut c_void;
    fn IOSurfaceLock(surface: *mut c_void, options: u32, seed: *mut u32) -> c_int;
    fn IOSurfaceUnlock(surface: *mut c_void, options: u32, seed: *mut u32) -> c_int;
    fn IOSurfaceGetBaseAddress(surface: *mut c_void) -> *mut c_void;
    fn IOSurfaceGetBytesPerRow(surface: *mut c_void) -> usize;
    fn IOSurfaceGetWidth(surface: *mut c_void) -> usize;
    fn IOSurfaceGetHeight(surface: *mut c_void) -> usize;
    fn CFRelease(cf: *mut c_void);
    fn CFRetain(cf: *mut c_void) -> *mut c_void;
}

/// An IOSurface allocated for BGRA8 (4 bytes/pixel), suitable for
/// painting via Skia raster and sampling via Metal.
pub struct SharedSurface {
    handle: *mut c_void,
    width: u32,
    height: u32,
}

unsafe impl Send for SharedSurface {}
unsafe impl Sync for SharedSurface {}

impl SharedSurface {
    /// Allocate via IOSurfaceCreate with a CFDictionary of properties
    /// describing width / height / pixel format / bytes-per-element.
    /// Returns None if the allocation fails (rare; typically a
    /// device-resource pressure issue).
    pub fn new(width: u32, height: u32) -> Option<Self> {
        let handle = unsafe { create_iosurface(width, height)? };
        Some(Self {
            handle,
            width,
            height,
        })
    }

    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }

    /// Borrow the CPU-mapped pixel buffer. The returned slice is valid
    /// until `unlock` is called. BGRA8 layout, row-stride is
    /// `IOSurfaceGetBytesPerRow`.
    pub unsafe fn lock_mut(&self) -> (*mut u8, usize) {
        let mut seed: u32 = 0;
        let _ = IOSurfaceLock(self.handle, 0, &mut seed);
        let base = IOSurfaceGetBaseAddress(self.handle) as *mut u8;
        let stride = IOSurfaceGetBytesPerRow(self.handle);
        (base, stride)
    }

    pub unsafe fn unlock(&self) {
        let mut seed: u32 = 0;
        let _ = IOSurfaceUnlock(self.handle, 0, &mut seed);
    }

    /// Raw IOSurface handle, suitable to pass to
    /// `MTLDevice newTextureWithDescriptor:iosurface:plane:`.
    pub fn raw(&self) -> *mut c_void {
        self.handle
    }
}

impl Drop for SharedSurface {
    fn drop(&mut self) {
        unsafe {
            CFRelease(self.handle);
        }
    }
}

impl Clone for SharedSurface {
    fn clone(&self) -> Self {
        unsafe {
            CFRetain(self.handle);
        }
        Self {
            handle: self.handle,
            width: self.width,
            height: self.height,
        }
    }
}

/// Build a CFDictionary holding the IOSurface creation properties, then
/// call IOSurfaceCreate. We use raw CoreFoundation bindings so we don't
/// need a `core-foundation` crate dep.
unsafe fn create_iosurface(width: u32, height: u32) -> Option<*mut c_void> {
    use std::ffi::CString;

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFDictionaryCreateMutable(
            allocator: *mut c_void,
            capacity: isize,
            key_cbs: *const c_void,
            val_cbs: *const c_void,
        ) -> *mut c_void;
        fn CFDictionaryAddValue(dict: *mut c_void, key: *const c_void, value: *const c_void);
        fn CFStringCreateWithCString(
            allocator: *mut c_void,
            cstr: *const i8,
            encoding: u32,
        ) -> *mut c_void;
        fn CFNumberCreate(allocator: *mut c_void, type_: i64, ptr: *const c_void) -> *mut c_void;
    }
    const KCFSTRING_ENCODING_UTF8: u32 = 0x08000100;
    const KCFNUMBER_INT32: i64 = 3;

    let mk_str = |s: &str| -> *mut c_void {
        let c = CString::new(s).unwrap();
        CFStringCreateWithCString(std::ptr::null_mut(), c.as_ptr(), KCFSTRING_ENCODING_UTF8)
    };
    let mk_num = |n: i32| -> *mut c_void {
        let n: i64 = n as i64;
        let n_ptr = &n as *const _ as *const c_void;
        CFNumberCreate(std::ptr::null_mut(), KCFNUMBER_INT32, n_ptr)
    };

    let dict =
        CFDictionaryCreateMutable(std::ptr::null_mut(), 0, std::ptr::null(), std::ptr::null());
    if dict.is_null() {
        return None;
    }

    // BGRA8 → 0x42475241  ('BGRA')
    let bgra: u32 = u32::from_be_bytes([b'B', b'G', b'R', b'A']);
    CFDictionaryAddValue(
        dict,
        mk_str("IOSurfaceWidth") as *const _,
        mk_num(width as i32) as *const _,
    );
    CFDictionaryAddValue(
        dict,
        mk_str("IOSurfaceHeight") as *const _,
        mk_num(height as i32) as *const _,
    );
    CFDictionaryAddValue(
        dict,
        mk_str("IOSurfaceBytesPerElement") as *const _,
        mk_num(4) as *const _,
    );
    CFDictionaryAddValue(
        dict,
        mk_str("IOSurfacePixelFormat") as *const _,
        mk_num(bgra as i32) as *const _,
    );

    let surface = IOSurfaceCreate(dict);
    CFRelease(dict);
    if surface.is_null() {
        None
    } else {
        Some(surface)
    }
}

/// Wrap the IOSurface as a Skia raster surface that paints into the
/// IOSurface's CPU-mapped memory directly. The caller MUST keep the
/// `SharedSurface` alive for as long as it uses the returned surface,
/// and must call `surface.unlock()` after each paint frame so the GPU
/// sees the latest writes.
pub unsafe fn skia_surface_for(shared: &SharedSurface) -> Option<skia_safe::Surface> {
    let (base, stride) = shared.lock_mut();
    if base.is_null() {
        return None;
    }
    let info = skia_safe::ImageInfo::new(
        (shared.width as i32, shared.height as i32),
        skia_safe::ColorType::BGRA8888,
        skia_safe::AlphaType::Premul,
        None,
    );
    let len = stride * shared.height as usize;
    let slice = std::slice::from_raw_parts_mut(base, len);
    let surf = skia_safe::surfaces::wrap_pixels(&info, slice, Some(stride), None)?;
    // skia-safe returns `Borrows<'_, Surface>`; we need to coerce. Pull
    // out the inner Surface via the Borrows API.
    use std::ops::Deref;
    let inner: &skia_safe::Surface = surf.deref();
    Some(inner.clone())
}

/// Sentinel — the actual wgpu::Texture wrapping requires going through
/// wgpu_hal::metal::Device::texture_from_raw with a metal::Texture built
/// from the IOSurface. The wiring lives in `crate::surface` once the
/// SurfaceRenderer gains an `attach_shared_surface` method; this module
/// owns the IOSurface lifecycle alone.
pub fn is_supported() -> bool {
    true
}
