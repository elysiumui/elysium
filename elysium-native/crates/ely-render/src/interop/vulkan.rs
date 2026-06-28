//! Linux Vulkan interop via VK_KHR_external_memory_fd + dma-buf.
//!
//! Flow:
//!   1. `dlopen("libvulkan.so.1")` + load `vkGetInstanceProcAddr`.
//!   2. `vkCreateInstance` with `VK_KHR_external_memory_capabilities`
//!      and `VK_KHR_get_physical_device_properties2`.
//!   3. Pick the first physical device.
//!   4. `vkCreateDevice` with `VK_KHR_external_memory`,
//!      `VK_KHR_external_memory_fd`, and `VK_EXT_external_memory_dma_buf`.
//!   5. `vkCreateImage` with `VkExternalMemoryImageCreateInfo` pointing
//!      to `VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT`.
//!   6. `vkAllocateMemory` with `VkExportMemoryAllocateInfo` +
//!      `VkMemoryDedicatedAllocateInfo` (some drivers require dedicated).
//!   7. `vkBindImageMemory`.
//!   8. `vkGetMemoryFdKHR` (loaded via `vkGetDeviceProcAddr`).
//!
//! The fd can then be imported into wgpu via
//! `wgpu_hal::vulkan::Device::texture_from_raw` (host-driven wiring lives
//! in `crate::surface::SurfaceRenderer::allocate_shared`) and into Skia
//! via `VK_KHR_external_memory_fd` when its Vulkan backend is enabled.

// Gated to Linux by the `pub mod vulkan` declaration. FFI types mirror the
// Vulkan headers verbatim (acronym names, unsafe fns, unused struct fields).
#![allow(
    non_camel_case_types,
    non_snake_case,
    dead_code,
    clippy::upper_case_acronyms,
    clippy::missing_safety_doc,
    clippy::manual_find
)]

use std::ffi::{c_char, c_void, CString};
use std::ptr;

// --- Vulkan minimal type surface (subset of vulkan.h) -------------------

type VkResult = i32;
type VkInstance = *mut c_void;
type VkPhysicalDevice = *mut c_void;
type VkDevice = *mut c_void;
type VkImage = u64; // dispatchable-handle on 64-bit / opaque-u64 in spec
type VkDeviceMemory = u64;
type VkFlags = u32;
type VkDeviceSize = u64;

const VK_SUCCESS: VkResult = 0;

const VK_STRUCTURE_TYPE_APPLICATION_INFO: i32 = 0;
const VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO: i32 = 1;
const VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO: i32 = 2;
const VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO: i32 = 3;
const VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO: i32 = 14;
const VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO: i32 = 5;
const VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO: i32 = 1000072000;
const VK_STRUCTURE_TYPE_EXPORT_MEMORY_ALLOCATE_INFO: i32 = 1000072002;
const VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO: i32 = 1000127001;
const VK_STRUCTURE_TYPE_MEMORY_GET_FD_INFO_KHR: i32 = 1000074002;

const VK_API_VERSION_1_1: u32 = (1 << 22) | (1 << 12);

const VK_IMAGE_TYPE_2D: u32 = 1;
const VK_FORMAT_B8G8R8A8_UNORM: u32 = 44;
const VK_SAMPLE_COUNT_1_BIT: u32 = 1;
const VK_IMAGE_TILING_OPTIMAL: u32 = 0;
const VK_SHARING_MODE_EXCLUSIVE: u32 = 0;
const VK_IMAGE_LAYOUT_UNDEFINED: u32 = 0;
const VK_IMAGE_USAGE_SAMPLED_BIT: u32 = 0x4;
const VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT: u32 = 0x10;
const VK_IMAGE_USAGE_TRANSFER_SRC_BIT: u32 = 0x4 | 0x1; // (kept conservative)

const VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT: u32 = 0x200;
const VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT: u32 = 0x1;

const VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT: u32 = 0x1;

#[repr(C)]
struct VkApplicationInfo {
    sType: i32,
    pNext: *const c_void,
    pApplicationName: *const c_char,
    applicationVersion: u32,
    pEngineName: *const c_char,
    engineVersion: u32,
    apiVersion: u32,
}

#[repr(C)]
struct VkInstanceCreateInfo {
    sType: i32,
    pNext: *const c_void,
    flags: u32,
    pApplicationInfo: *const VkApplicationInfo,
    enabledLayerCount: u32,
    ppEnabledLayerNames: *const *const c_char,
    enabledExtensionCount: u32,
    ppEnabledExtensionNames: *const *const c_char,
}

#[repr(C)]
struct VkDeviceQueueCreateInfo {
    sType: i32,
    pNext: *const c_void,
    flags: u32,
    queueFamilyIndex: u32,
    queueCount: u32,
    pQueuePriorities: *const f32,
}

#[repr(C)]
struct VkDeviceCreateInfo {
    sType: i32,
    pNext: *const c_void,
    flags: u32,
    queueCreateInfoCount: u32,
    pQueueCreateInfos: *const VkDeviceQueueCreateInfo,
    enabledLayerCount: u32,
    ppEnabledLayerNames: *const *const c_char,
    enabledExtensionCount: u32,
    ppEnabledExtensionNames: *const *const c_char,
    pEnabledFeatures: *const c_void,
}

#[repr(C)]
struct VkExtent3D {
    width: u32,
    height: u32,
    depth: u32,
}

#[repr(C)]
struct VkImageCreateInfo {
    sType: i32,
    pNext: *const c_void,
    flags: u32,
    imageType: u32,
    format: u32,
    extent: VkExtent3D,
    mipLevels: u32,
    arrayLayers: u32,
    samples: u32,
    tiling: u32,
    usage: u32,
    sharingMode: u32,
    queueFamilyIndexCount: u32,
    pQueueFamilyIndices: *const u32,
    initialLayout: u32,
}

#[repr(C)]
struct VkExternalMemoryImageCreateInfo {
    sType: i32,
    pNext: *const c_void,
    handleTypes: u32,
}

#[repr(C)]
struct VkMemoryRequirements {
    size: VkDeviceSize,
    alignment: VkDeviceSize,
    memoryTypeBits: u32,
}

#[repr(C)]
struct VkMemoryAllocateInfo {
    sType: i32,
    pNext: *const c_void,
    allocationSize: VkDeviceSize,
    memoryTypeIndex: u32,
}

#[repr(C)]
struct VkExportMemoryAllocateInfo {
    sType: i32,
    pNext: *const c_void,
    handleTypes: u32,
}

#[repr(C)]
struct VkMemoryDedicatedAllocateInfo {
    sType: i32,
    pNext: *const c_void,
    image: VkImage,
    buffer: u64,
}

#[repr(C)]
struct VkMemoryGetFdInfoKHR {
    sType: i32,
    pNext: *const c_void,
    memory: VkDeviceMemory,
    handleType: u32,
}

#[repr(C)]
struct VkPhysicalDeviceMemoryProperties {
    memoryTypeCount: u32,
    memoryTypes: [VkMemoryType; 32],
    memoryHeapCount: u32,
    memoryHeaps: [VkMemoryHeap; 16],
}

#[repr(C)]
#[derive(Copy, Clone)]
struct VkMemoryType {
    propertyFlags: u32,
    heapIndex: u32,
}

#[repr(C)]
#[derive(Copy, Clone)]
struct VkMemoryHeap {
    size: VkDeviceSize,
    flags: u32,
}

// --- Function pointer table ---------------------------------------------

type PFN_vkGetInstanceProcAddr =
    unsafe extern "system" fn(VkInstance, *const c_char) -> *mut c_void;
type PFN_vkGetDeviceProcAddr = unsafe extern "system" fn(VkDevice, *const c_char) -> *mut c_void;

type PFN_vkCreateInstance = unsafe extern "system" fn(
    *const VkInstanceCreateInfo,
    *const c_void,
    *mut VkInstance,
) -> VkResult;
type PFN_vkDestroyInstance = unsafe extern "system" fn(VkInstance, *const c_void);
type PFN_vkEnumeratePhysicalDevices =
    unsafe extern "system" fn(VkInstance, *mut u32, *mut VkPhysicalDevice) -> VkResult;
type PFN_vkGetPhysicalDeviceMemoryProperties =
    unsafe extern "system" fn(VkPhysicalDevice, *mut VkPhysicalDeviceMemoryProperties);
type PFN_vkCreateDevice = unsafe extern "system" fn(
    VkPhysicalDevice,
    *const VkDeviceCreateInfo,
    *const c_void,
    *mut VkDevice,
) -> VkResult;
type PFN_vkDestroyDevice = unsafe extern "system" fn(VkDevice, *const c_void);
type PFN_vkCreateImage = unsafe extern "system" fn(
    VkDevice,
    *const VkImageCreateInfo,
    *const c_void,
    *mut VkImage,
) -> VkResult;
type PFN_vkDestroyImage = unsafe extern "system" fn(VkDevice, VkImage, *const c_void);
type PFN_vkGetImageMemoryRequirements =
    unsafe extern "system" fn(VkDevice, VkImage, *mut VkMemoryRequirements);
type PFN_vkAllocateMemory = unsafe extern "system" fn(
    VkDevice,
    *const VkMemoryAllocateInfo,
    *const c_void,
    *mut VkDeviceMemory,
) -> VkResult;
type PFN_vkFreeMemory = unsafe extern "system" fn(VkDevice, VkDeviceMemory, *const c_void);
type PFN_vkBindImageMemory =
    unsafe extern "system" fn(VkDevice, VkImage, VkDeviceMemory, VkDeviceSize) -> VkResult;
type PFN_vkGetMemoryFdKHR =
    unsafe extern "system" fn(VkDevice, *const VkMemoryGetFdInfoKHR, *mut i32) -> VkResult;

// libc dlopen surface — avoid pulling the `libc` crate just for these.
const RTLD_NOW: i32 = 2;

#[link(name = "dl")]
extern "C" {
    fn dlopen(filename: *const c_char, flags: i32) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    fn dlclose(handle: *mut c_void) -> i32;
}

#[link(name = "c")]
extern "C" {
    fn close(fd: i32) -> i32;
}

// --- Public ---------------------------------------------------------------

pub struct SharedSurface {
    pub width: u32,
    pub height: u32,
    lib: *mut c_void,
    instance: VkInstance,
    device: VkDevice,
    image: VkImage,
    memory: VkDeviceMemory,
    fd: i32,
    /// Cached destroy callbacks so Drop doesn't have to re-load them.
    destroy_image: PFN_vkDestroyImage,
    free_memory: PFN_vkFreeMemory,
    destroy_device: PFN_vkDestroyDevice,
    destroy_instance: PFN_vkDestroyInstance,
}

unsafe impl Send for SharedSurface {}
unsafe impl Sync for SharedSurface {}

impl SharedSurface {
    pub fn new(width: u32, height: u32) -> Option<Self> {
        unsafe { try_allocate(width, height) }
    }

    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }
    pub fn fd(&self) -> i32 {
        self.fd
    }

    pub fn vk_image(&self) -> VkImage {
        self.image
    }
    pub fn vk_memory(&self) -> VkDeviceMemory {
        self.memory
    }
    pub fn vk_device(&self) -> VkDevice {
        self.device
    }
}

impl Drop for SharedSurface {
    fn drop(&mut self) {
        unsafe {
            if self.fd >= 0 {
                close(self.fd);
            }
            if self.image != 0 && !self.device.is_null() {
                (self.destroy_image)(self.device, self.image, ptr::null());
            }
            if self.memory != 0 && !self.device.is_null() {
                (self.free_memory)(self.device, self.memory, ptr::null());
            }
            if !self.device.is_null() {
                (self.destroy_device)(self.device, ptr::null());
            }
            if !self.instance.is_null() {
                (self.destroy_instance)(self.instance, ptr::null());
            }
            if !self.lib.is_null() {
                dlclose(self.lib);
            }
        }
    }
}

pub fn is_supported() -> bool {
    true
}

// --- Implementation -------------------------------------------------------

unsafe fn try_allocate(width: u32, height: u32) -> Option<SharedSurface> {
    // 1. dlopen + vkGetInstanceProcAddr.
    let lib = dlopen(c_str("libvulkan.so.1"), RTLD_NOW);
    if lib.is_null() {
        return None;
    }
    let get_ipa: PFN_vkGetInstanceProcAddr = transmute_sym(lib, "vkGetInstanceProcAddr")?;

    let create_instance: PFN_vkCreateInstance = load_global(get_ipa, "vkCreateInstance")?;

    // 2. Create instance.
    let app = VkApplicationInfo {
        sType: VK_STRUCTURE_TYPE_APPLICATION_INFO,
        pNext: ptr::null(),
        pApplicationName: c_str("elysium"),
        applicationVersion: 1,
        pEngineName: c_str("elysium"),
        engineVersion: 1,
        apiVersion: VK_API_VERSION_1_1,
    };
    // Two instance extensions: external_memory_capabilities + pdp2.
    let ext_emc = c_str("VK_KHR_external_memory_capabilities");
    let ext_pdp2 = c_str("VK_KHR_get_physical_device_properties2");
    let instance_exts = [ext_emc, ext_pdp2];
    let ci = VkInstanceCreateInfo {
        sType: VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        pNext: ptr::null(),
        flags: 0,
        pApplicationInfo: &app,
        enabledLayerCount: 0,
        ppEnabledLayerNames: ptr::null(),
        enabledExtensionCount: instance_exts.len() as u32,
        ppEnabledExtensionNames: instance_exts.as_ptr(),
    };
    let mut instance: VkInstance = ptr::null_mut();
    if create_instance(&ci, ptr::null(), &mut instance) != VK_SUCCESS {
        dlclose(lib);
        return None;
    }

    // Load destroy fns up-front so Drop is safe at any failure point below.
    let destroy_instance: PFN_vkDestroyInstance =
        load_instance(get_ipa, instance, "vkDestroyInstance")?;
    let enum_phys: PFN_vkEnumeratePhysicalDevices =
        load_instance(get_ipa, instance, "vkEnumeratePhysicalDevices")?;
    let get_mem_props: PFN_vkGetPhysicalDeviceMemoryProperties =
        load_instance(get_ipa, instance, "vkGetPhysicalDeviceMemoryProperties")?;
    let create_device: PFN_vkCreateDevice = load_instance(get_ipa, instance, "vkCreateDevice")?;

    // 3. Pick a physical device.
    let mut count: u32 = 0;
    enum_phys(instance, &mut count, ptr::null_mut());
    if count == 0 {
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }
    let mut phys: Vec<VkPhysicalDevice> = vec![ptr::null_mut(); count as usize];
    enum_phys(instance, &mut count, phys.as_mut_ptr());
    let phys = phys[0];

    let mut mem_props: VkPhysicalDeviceMemoryProperties = std::mem::zeroed();
    get_mem_props(phys, &mut mem_props);

    // 4. Create logical device with three extensions.
    let queue_prio: f32 = 1.0;
    let queue_ci = VkDeviceQueueCreateInfo {
        sType: VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        pNext: ptr::null(),
        flags: 0,
        queueFamilyIndex: 0,
        queueCount: 1,
        pQueuePriorities: &queue_prio,
    };
    let ext_em = c_str("VK_KHR_external_memory");
    let ext_emfd = c_str("VK_KHR_external_memory_fd");
    let ext_dma = c_str("VK_EXT_external_memory_dma_buf");
    let dev_exts = [ext_em, ext_emfd, ext_dma];
    let dev_ci = VkDeviceCreateInfo {
        sType: VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        pNext: ptr::null(),
        flags: 0,
        queueCreateInfoCount: 1,
        pQueueCreateInfos: &queue_ci,
        enabledLayerCount: 0,
        ppEnabledLayerNames: ptr::null(),
        enabledExtensionCount: dev_exts.len() as u32,
        ppEnabledExtensionNames: dev_exts.as_ptr(),
        pEnabledFeatures: ptr::null(),
    };
    let mut device: VkDevice = ptr::null_mut();
    if create_device(phys, &dev_ci, ptr::null(), &mut device) != VK_SUCCESS {
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }

    let get_dpa: PFN_vkGetDeviceProcAddr = load_instance(get_ipa, instance, "vkGetDeviceProcAddr")?;
    let destroy_device: PFN_vkDestroyDevice = load_device(get_dpa, device, "vkDestroyDevice")?;
    let create_image: PFN_vkCreateImage = load_device(get_dpa, device, "vkCreateImage")?;
    let destroy_image: PFN_vkDestroyImage = load_device(get_dpa, device, "vkDestroyImage")?;
    let get_image_mem_req: PFN_vkGetImageMemoryRequirements =
        load_device(get_dpa, device, "vkGetImageMemoryRequirements")?;
    let alloc_mem: PFN_vkAllocateMemory = load_device(get_dpa, device, "vkAllocateMemory")?;
    let free_mem: PFN_vkFreeMemory = load_device(get_dpa, device, "vkFreeMemory")?;
    let bind_image_mem: PFN_vkBindImageMemory = load_device(get_dpa, device, "vkBindImageMemory")?;
    let get_mem_fd: PFN_vkGetMemoryFdKHR = load_device(get_dpa, device, "vkGetMemoryFdKHR")?;

    // 5. Create image with external-memory extension struct chained in pNext.
    let ext_image_ci = VkExternalMemoryImageCreateInfo {
        sType: VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO,
        pNext: ptr::null(),
        handleTypes: VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT,
    };
    let image_ci = VkImageCreateInfo {
        sType: VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        pNext: &ext_image_ci as *const _ as *const c_void,
        flags: 0,
        imageType: VK_IMAGE_TYPE_2D,
        format: VK_FORMAT_B8G8R8A8_UNORM,
        extent: VkExtent3D {
            width,
            height,
            depth: 1,
        },
        mipLevels: 1,
        arrayLayers: 1,
        samples: VK_SAMPLE_COUNT_1_BIT,
        tiling: VK_IMAGE_TILING_OPTIMAL,
        usage: VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
        sharingMode: VK_SHARING_MODE_EXCLUSIVE,
        queueFamilyIndexCount: 0,
        pQueueFamilyIndices: ptr::null(),
        initialLayout: VK_IMAGE_LAYOUT_UNDEFINED,
    };
    let mut image: VkImage = 0;
    if create_image(device, &image_ci, ptr::null(), &mut image) != VK_SUCCESS {
        destroy_device(device, ptr::null());
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }

    // 6. Allocate memory: dedicated + exportable as dma-buf.
    let mut req: VkMemoryRequirements = std::mem::zeroed();
    get_image_mem_req(device, image, &mut req);
    let type_idx = pick_memory_type(
        &mem_props,
        req.memoryTypeBits,
        VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
    )
    .unwrap_or(0);

    // pNext chain: dedicated -> export -> null.
    let dedicated = VkMemoryDedicatedAllocateInfo {
        sType: VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO,
        pNext: ptr::null(),
        image,
        buffer: 0,
    };
    let export = VkExportMemoryAllocateInfo {
        sType: VK_STRUCTURE_TYPE_EXPORT_MEMORY_ALLOCATE_INFO,
        pNext: &dedicated as *const _ as *const c_void,
        handleTypes: VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT,
    };
    let alloc_info = VkMemoryAllocateInfo {
        sType: VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        pNext: &export as *const _ as *const c_void,
        allocationSize: req.size,
        memoryTypeIndex: type_idx,
    };
    let mut memory: VkDeviceMemory = 0;
    if alloc_mem(device, &alloc_info, ptr::null(), &mut memory) != VK_SUCCESS {
        destroy_image(device, image, ptr::null());
        destroy_device(device, ptr::null());
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }

    // 7. Bind + export fd.
    if bind_image_mem(device, image, memory, 0) != VK_SUCCESS {
        free_mem(device, memory, ptr::null());
        destroy_image(device, image, ptr::null());
        destroy_device(device, ptr::null());
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }

    let fd_info = VkMemoryGetFdInfoKHR {
        sType: VK_STRUCTURE_TYPE_MEMORY_GET_FD_INFO_KHR,
        pNext: ptr::null(),
        memory,
        handleType: VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT,
    };
    let mut fd: i32 = -1;
    if get_mem_fd(device, &fd_info, &mut fd) != VK_SUCCESS || fd < 0 {
        free_mem(device, memory, ptr::null());
        destroy_image(device, image, ptr::null());
        destroy_device(device, ptr::null());
        destroy_instance(instance, ptr::null());
        dlclose(lib);
        return None;
    }

    Some(SharedSurface {
        width,
        height,
        lib,
        instance,
        device,
        image,
        memory,
        fd,
        destroy_image,
        free_memory: free_mem,
        destroy_device,
        destroy_instance,
    })
}

fn pick_memory_type(
    props: &VkPhysicalDeviceMemoryProperties,
    type_bits: u32,
    required_flags: u32,
) -> Option<u32> {
    for i in 0..props.memoryTypeCount {
        if (type_bits & (1u32 << i)) == 0 {
            continue;
        }
        let mt = props.memoryTypes[i as usize];
        if (mt.propertyFlags & required_flags) == required_flags {
            return Some(i);
        }
    }
    // Fallback: any matching type, ignore required flags.
    for i in 0..props.memoryTypeCount {
        if (type_bits & (1u32 << i)) != 0 {
            return Some(i);
        }
    }
    None
}

unsafe fn c_str(s: &str) -> *const c_char {
    // Leak the CString — caller passes these to Vulkan, which copies.
    // For one-shot allocation it's the simplest correct option.
    CString::new(s).unwrap().into_raw()
}

unsafe fn transmute_sym<T>(lib: *mut c_void, name: &str) -> Option<T> {
    let cs = CString::new(name).ok()?;
    let p = dlsym(lib, cs.as_ptr());
    if p.is_null() {
        None
    } else {
        Some(std::mem::transmute_copy(&p))
    }
}

unsafe fn load_global<T>(ipa: PFN_vkGetInstanceProcAddr, name: &str) -> Option<T> {
    let cs = CString::new(name).ok()?;
    let p = ipa(ptr::null_mut(), cs.as_ptr());
    if p.is_null() {
        None
    } else {
        Some(std::mem::transmute_copy(&p))
    }
}

unsafe fn load_instance<T>(
    ipa: PFN_vkGetInstanceProcAddr,
    inst: VkInstance,
    name: &str,
) -> Option<T> {
    let cs = CString::new(name).ok()?;
    let p = ipa(inst, cs.as_ptr());
    if p.is_null() {
        None
    } else {
        Some(std::mem::transmute_copy(&p))
    }
}

unsafe fn load_device<T>(dpa: PFN_vkGetDeviceProcAddr, dev: VkDevice, name: &str) -> Option<T> {
    let cs = CString::new(name).ok()?;
    let p = dpa(dev, cs.as_ptr());
    if p.is_null() {
        None
    } else {
        Some(std::mem::transmute_copy(&p))
    }
}
