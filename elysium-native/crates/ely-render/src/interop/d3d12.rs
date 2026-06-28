//! Windows D3D11 shared NT handles for zero-copy Skia↔wgpu interop.
//!
//! Strategy:
//!   1. Create a D3D11 device with `D3D11CreateDevice`.
//!   2. Allocate a B8G8R8A8_UNORM `ID3D11Texture2D` with the
//!      `D3D11_RESOURCE_MISC_SHARED_NTHANDLE | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX`
//!      misc flags so the resource is sharable across processes.
//!   3. `QueryInterface` it for `IDXGIResource1` and call
//!      `CreateSharedHandle` to get an NT `HANDLE`.
//!   4. Hand the handle to wgpu via
//!      `wgpu_hal::dx12::Device::texture_from_raw` (host-driven wiring
//!      lives in `crate::surface::SurfaceRenderer::allocate_shared`).
//!
//! The COM vtables are written as raw `extern "system"` function
//! pointers with placeholder slots for methods we never call. Method
//! order matches the published headers (`d3d11.h`, `dxgi1_2.h`,
//! `dxgi1_3.h`) and is what every Windows runtime ABI guarantees.

// Gated to Windows by the `pub mod d3d12` declaration. FFI types mirror the
// Win32 / COM headers verbatim (acronym names, unsafe fns, unused vtable slots).
#![allow(
    non_camel_case_types,
    non_snake_case,
    dead_code,
    clippy::upper_case_acronyms,
    clippy::missing_safety_doc
)]

use std::ffi::c_void;
use std::ptr;

type HANDLE = *mut c_void;
type HRESULT = i32;
type BOOL = i32;
type UINT = u32;
type DWORD = u32;
type LPCWSTR = *const u16;
type IUnknownPtr = *mut c_void;

const S_OK: HRESULT = 0;

#[repr(C)]
#[derive(Copy, Clone)]
struct GUID {
    data1: u32,
    data2: u16,
    data3: u16,
    data4: [u8; 8],
}

// IID_IDXGIResource1 = 30961379-4609-4a41-998E-54FE567EE0C1
const IID_IDXGIRESOURCE1: GUID = GUID {
    data1: 0x30961379,
    data2: 0x4609,
    data3: 0x4a41,
    data4: [0x99, 0x8E, 0x54, 0xFE, 0x56, 0x7E, 0xE0, 0xC1],
};

// IID_ID3D11Texture2D = 6f15aaf2-d208-4e89-9ab4-489535d34f9c
const IID_ID3D11TEXTURE2D: GUID = GUID {
    data1: 0x6f15aaf2,
    data2: 0xd208,
    data3: 0x4e89,
    data4: [0x9a, 0xb4, 0x48, 0x95, 0x35, 0xd3, 0x4f, 0x9c],
};

const D3D11_SDK_VERSION: UINT = 7;
const D3D_DRIVER_TYPE_HARDWARE: u32 = 1;

const DXGI_FORMAT_B8G8R8A8_UNORM: u32 = 87;

const D3D11_USAGE_DEFAULT: u32 = 0;

const D3D11_BIND_SHADER_RESOURCE: u32 = 0x8;
const D3D11_BIND_RENDER_TARGET: u32 = 0x20;

const D3D11_RESOURCE_MISC_SHARED_NTHANDLE: u32 = 0x800;
const D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX: u32 = 0x100;

// dxgi.h share flags for CreateSharedHandle.
const DXGI_SHARED_RESOURCE_READ: DWORD = 0x80000000;
const DXGI_SHARED_RESOURCE_WRITE: DWORD = 1;

#[repr(C)]
struct DXGI_SAMPLE_DESC {
    count: UINT,
    quality: UINT,
}

#[repr(C)]
struct D3D11_TEXTURE2D_DESC {
    Width: UINT,
    Height: UINT,
    MipLevels: UINT,
    ArraySize: UINT,
    Format: u32,
    SampleDesc: DXGI_SAMPLE_DESC,
    Usage: u32,
    BindFlags: UINT,
    CPUAccessFlags: UINT,
    MiscFlags: UINT,
}

// --- ID3D11Device vtable (only CreateTexture2D is exercised) -----------

#[repr(C)]
struct ID3D11DeviceVtbl {
    // IUnknown
    QueryInterface:
        extern "system" fn(this: *mut c_void, riid: *const GUID, ppv: *mut *mut c_void) -> HRESULT,
    AddRef: extern "system" fn(this: *mut c_void) -> u32,
    Release: extern "system" fn(this: *mut c_void) -> u32,
    // ID3D11Device — order matches d3d11.h. Methods before CreateTexture2D
    // (CreateBuffer @ slot 3, CreateTexture1D @ slot 4) are unused so we
    // stash *const c_void placeholders. CreateTexture2D is slot 5.
    CreateBuffer: *const c_void,
    CreateTexture1D: *const c_void,
    CreateTexture2D: extern "system" fn(
        this: *mut c_void,
        desc: *const D3D11_TEXTURE2D_DESC,
        initial_data: *const c_void,
        out_texture: *mut *mut c_void,
    ) -> HRESULT,
    // Remaining 35+ methods are not called by us. Leaving the vtable
    // truncated is safe so long as we never call them; the runtime
    // never inspects unmentioned slots.
}

#[repr(C)]
struct ID3D11Device {
    vtbl: *const ID3D11DeviceVtbl,
}

// --- IDXGIResource1 vtable ----------------------------------------------
//
// Layout up to CreateSharedHandle:
//   0  QueryInterface
//   1  AddRef
//   2  Release
//   3  SetPrivateData
//   4  SetPrivateDataInterface
//   5  GetPrivateData
//   6  GetParent
//   7  GetDevice                       (end IDXGIObject / IDXGIDeviceSubObject)
//   8  GetSharedHandle                 (IDXGIResource)
//   9  GetUsage
//   10 SetEvictionPriority
//   11 GetEvictionPriority
//   12 CreateSubresourceSurface        (IDXGIResource1)
//   13 CreateSharedHandle

#[repr(C)]
struct IDXGIResource1Vtbl {
    QueryInterface:
        extern "system" fn(this: *mut c_void, riid: *const GUID, ppv: *mut *mut c_void) -> HRESULT,
    AddRef: extern "system" fn(this: *mut c_void) -> u32,
    Release: extern "system" fn(this: *mut c_void) -> u32,
    SetPrivateData: *const c_void,
    SetPrivateDataInterface: *const c_void,
    GetPrivateData: *const c_void,
    GetParent: *const c_void,
    GetDevice: *const c_void,
    GetSharedHandle: *const c_void,
    GetUsage: *const c_void,
    SetEvictionPriority: *const c_void,
    GetEvictionPriority: *const c_void,
    CreateSubresourceSurface: *const c_void,
    CreateSharedHandle: extern "system" fn(
        this: *mut c_void,
        attrs: *const c_void, // SECURITY_ATTRIBUTES — pass null for default
        access: DWORD,
        name: LPCWSTR,
        out_handle: *mut HANDLE,
    ) -> HRESULT,
}

#[repr(C)]
struct IDXGIResource1 {
    vtbl: *const IDXGIResource1Vtbl,
}

// --- D3D11.dll entry ----------------------------------------------------

#[link(name = "d3d11")]
extern "system" {
    fn D3D11CreateDevice(
        adapter: *mut c_void,
        driver_type: u32,
        software_module: *mut c_void,
        flags: UINT,
        feature_levels: *const u32,
        num_feature_levels: UINT,
        sdk_version: UINT,
        out_device: *mut *mut c_void,
        out_feature_level: *mut u32,
        out_context: *mut *mut c_void,
    ) -> HRESULT;
}

#[link(name = "kernel32")]
extern "system" {
    fn CloseHandle(h: HANDLE) -> BOOL;
}

// --- Public ---------------------------------------------------------------

pub struct SharedSurface {
    pub width: u32,
    pub height: u32,
    device: *mut c_void,  // ID3D11Device*
    context: *mut c_void, // ID3D11DeviceContext* (held for liveness)
    texture: *mut c_void, // ID3D11Texture2D*
    handle: HANDLE,       // NT handle from CreateSharedHandle
}

unsafe impl Send for SharedSurface {}
unsafe impl Sync for SharedSurface {}

impl SharedSurface {
    pub fn new(width: u32, height: u32) -> Option<Self> {
        unsafe {
            // 1. Create the D3D11 device. NULL adapter + HARDWARE driver
            // means "default adapter."
            let mut device: *mut c_void = ptr::null_mut();
            let mut context: *mut c_void = ptr::null_mut();
            let mut fl: u32 = 0;
            let hr = D3D11CreateDevice(
                ptr::null_mut(),
                D3D_DRIVER_TYPE_HARDWARE,
                ptr::null_mut(),
                0,           // flags
                ptr::null(), // default feature levels
                0,
                D3D11_SDK_VERSION,
                &mut device,
                &mut fl,
                &mut context,
            );
            if hr != S_OK || device.is_null() {
                return None;
            }

            // 2. CreateTexture2D with SHARED_NTHANDLE | SHARED_KEYEDMUTEX.
            let desc = D3D11_TEXTURE2D_DESC {
                Width: width,
                Height: height,
                MipLevels: 1,
                ArraySize: 1,
                Format: DXGI_FORMAT_B8G8R8A8_UNORM,
                SampleDesc: DXGI_SAMPLE_DESC {
                    count: 1,
                    quality: 0,
                },
                Usage: D3D11_USAGE_DEFAULT,
                BindFlags: D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET,
                CPUAccessFlags: 0,
                MiscFlags: D3D11_RESOURCE_MISC_SHARED_NTHANDLE
                    | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX,
            };
            let dev_vtbl = (*(device as *const ID3D11Device)).vtbl;
            let mut texture: *mut c_void = ptr::null_mut();
            let hr = ((*dev_vtbl).CreateTexture2D)(device, &desc, ptr::null(), &mut texture);
            if hr != S_OK || texture.is_null() {
                Self::release_ptr(device);
                Self::release_ptr(context);
                return None;
            }

            // 3. QueryInterface for IDXGIResource1. Texture's first field
            // is its vtable pointer; QI is vtable slot 0 with the
            // standard IUnknown signature.
            let mut resource: *mut c_void = ptr::null_mut();
            let tex_vtbl = *(texture as *const *const *const c_void);
            let qi_slot = *tex_vtbl.offset(0);
            let qi: extern "system" fn(*mut c_void, *const GUID, *mut *mut c_void) -> HRESULT =
                std::mem::transmute(qi_slot);
            let hr = qi(texture, &IID_IDXGIRESOURCE1, &mut resource);
            if hr != S_OK || resource.is_null() {
                Self::release_ptr(texture);
                Self::release_ptr(device);
                Self::release_ptr(context);
                return None;
            }

            // 4. CreateSharedHandle. Null security attrs + null name =
            // "no other process can open it by name; closing the HANDLE
            // drops the resource."
            let res_vtbl = (*(resource as *const IDXGIResource1)).vtbl;
            let mut handle: HANDLE = ptr::null_mut();
            let hr = ((*res_vtbl).CreateSharedHandle)(
                resource,
                ptr::null(),
                DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE,
                ptr::null(),
                &mut handle,
            );
            // We're done with the IDXGIResource1 interface pointer; the
            // shared NT handle keeps the underlying texture alive on its
            // own reference.
            Self::release_ptr(resource);
            if hr != S_OK || handle.is_null() {
                Self::release_ptr(texture);
                Self::release_ptr(device);
                Self::release_ptr(context);
                return None;
            }

            Some(Self {
                width,
                height,
                device,
                context,
                texture,
                handle,
            })
        }
    }

    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }

    /// Raw NT handle suitable for `wgpu_hal::dx12::Device::texture_from_raw`
    /// or for sharing with another process via `DuplicateHandle`.
    pub fn handle(&self) -> HANDLE {
        self.handle
    }

    /// Raw `ID3D11Texture2D*`. Caller must not Release it.
    pub fn d3d11_texture(&self) -> *mut c_void {
        self.texture
    }

    /// Raw `ID3D11Device*`. Caller must not Release it.
    pub fn d3d11_device(&self) -> *mut c_void {
        self.device
    }

    unsafe fn release_ptr(p: *mut c_void) {
        if p.is_null() {
            return;
        }
        // Release lives at vtable slot 2 with the standard IUnknown sig.
        let vtbl = *(p as *const *const *const c_void);
        let release_slot = *vtbl.offset(2);
        let release: extern "system" fn(*mut c_void) -> u32 = std::mem::transmute(release_slot);
        release(p);
    }
}

impl Drop for SharedSurface {
    fn drop(&mut self) {
        unsafe {
            if !self.handle.is_null() {
                CloseHandle(self.handle);
            }
            Self::release_ptr(self.texture);
            Self::release_ptr(self.context);
            Self::release_ptr(self.device);
        }
    }
}

pub fn is_supported() -> bool {
    true
}
