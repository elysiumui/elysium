"""Cross-platform Dock / Taskbar icon swap.

Used by the Designer's `IconFlapper` to animate the running app icon.
ctypes-only — no Rust changes, no Python deps beyond stdlib.

Supported surfaces:
  * macOS Dock — `NSApplication.applicationIconImage`
  * Windows Taskbar — `WM_SETICON` (best-effort; needs HWND lookup)
  * Linux — no-op (no portable runtime-icon API across DEs)

Why not PyObjC / pywin32?
  Both would balloon the bundled `.app` by ~50 MiB each and pull in
  build-system fragility on PyInstaller. The Objective-C runtime
  and `user32.dll` are stable C ABIs we can reach via ctypes with
  zero install-time cost.

Public API:
    set_app_icon_from_png(png_bytes: bytes) -> bool
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys


# ---------------------------------------------------------------------------
# macOS — Cocoa via the Objective-C runtime

def _macos_set_icon(png_bytes: bytes) -> bool:
    libobjc = ctypes.util.find_library("objc")
    if libobjc is None:
        return False
    objc = ctypes.cdll.LoadLibrary(libobjc)
    # Force the AppKit framework to load (it brings NSImage + NSApplication).
    appkit = ctypes.util.find_library("AppKit")
    if appkit is None:
        return False
    ctypes.cdll.LoadLibrary(appkit)

    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.objc_msgSend.restype = ctypes.c_void_p
    # objc_msgSend is variadic at the C level — we cast per call site
    # because the argument tuple shape varies (no args, ptr, ptr+len).

    NSData = objc.objc_getClass(b"NSData")
    NSImage = objc.objc_getClass(b"NSImage")
    NSApplication = objc.objc_getClass(b"NSApplication")
    if not (NSData and NSImage and NSApplication):
        return False

    sel_dataWithBytes = objc.sel_registerName(b"dataWithBytes:length:")
    sel_alloc         = objc.sel_registerName(b"alloc")
    sel_initWithData  = objc.sel_registerName(b"initWithData:")
    sel_sharedApp     = objc.sel_registerName(b"sharedApplication")
    sel_setIcon       = objc.sel_registerName(b"setApplicationIconImage:")
    sel_release       = objc.sel_registerName(b"release")

    # `+[NSData dataWithBytes:length:]` is an autoreleased factory; we
    # don't need to release the returned data.
    buf_t = ctypes.c_ubyte * len(png_bytes)
    buf = buf_t(*png_bytes)
    fn_msg_buf = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_ulong))
    data = fn_msg_buf(NSData, sel_dataWithBytes, buf, len(png_bytes))
    if not data:
        return False

    fn_msg_void = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p))
    img_alloc = fn_msg_void(NSImage, sel_alloc)
    if not img_alloc:
        return False
    fn_msg_ptr = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p))
    img = fn_msg_ptr(img_alloc, sel_initWithData, data)
    if not img:
        fn_msg_void(img_alloc, sel_release)
        return False

    app = fn_msg_void(NSApplication, sel_sharedApp)
    if not app:
        fn_msg_void(img, sel_release)
        return False
    fn_msg_ptr(app, sel_setIcon, img)
    # NSApplication retains the icon image; balance our +1 retain
    # count from `initWithData:` so we don't leak per frame.
    fn_msg_void(img, sel_release)
    return True


# ---------------------------------------------------------------------------
# Windows — Win32 via user32.dll

def _windows_set_icon(png_bytes: bytes) -> bool:
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        gdi32  = ctypes.windll.gdi32   # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False
    import io
    try:
        from PIL import Image, ImageWin
    except Exception:
        # Without Pillow we'd have to roll a PNG decoder. The Designer
        # already ships Pillow; this path is best-effort.
        return False
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    # Find our app's HWND via GetForegroundWindow if it's currently
    # focused, otherwise enumerate top-level windows in this process.
    GetCurrentProcessId = ctypes.windll.kernel32.GetCurrentProcessId  # type: ignore[attr-defined]
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    EnumWindows = user32.EnumWindows
    GetWindowThreadProcessId.restype = ctypes.c_ulong
    EnumWindowsProc = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    target_pid = GetCurrentProcessId()
    found = ctypes.c_void_p(0)

    @EnumWindowsProc
    def cb(hwnd, lparam):
        pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == target_pid and not found.value:
            found.value = hwnd
            return False
        return True

    EnumWindows(cb, None)
    if not found.value:
        return False

    # Convert RGBA PIL image to HBITMAP → HICON. Win32 has no direct
    # PNG-to-HICON path; we go via CreateIconIndirect with an ICONINFO
    # built from a colour bitmap + a 1-bpp mask.
    sz = 256
    img = img.resize((sz, sz), Image.LANCZOS)
    bgra = bytearray()
    # Bottom-up DIB (negative biHeight) keeps PIL's top-down order, but
    # CreateIconIndirect wants bottom-up. We flip on the way out.
    for y in range(sz - 1, -1, -1):
        for x in range(sz):
            r, g, b, a = img.getpixel((x, y))
            bgra += bytes([b, g, r, a])

    # BITMAPV5HEADER for a 32-bpp ARGB bitmap.
    class BITMAPV5HEADER(ctypes.Structure):
        _fields_ = [
            ("bV5Size", ctypes.c_uint), ("bV5Width", ctypes.c_long),
            ("bV5Height", ctypes.c_long), ("bV5Planes", ctypes.c_ushort),
            ("bV5BitCount", ctypes.c_ushort), ("bV5Compression", ctypes.c_uint),
            ("bV5SizeImage", ctypes.c_uint), ("bV5XPelsPerMeter", ctypes.c_long),
            ("bV5YPelsPerMeter", ctypes.c_long), ("bV5ClrUsed", ctypes.c_uint),
            ("bV5ClrImportant", ctypes.c_uint),
            ("bV5RedMask", ctypes.c_uint), ("bV5GreenMask", ctypes.c_uint),
            ("bV5BlueMask", ctypes.c_uint), ("bV5AlphaMask", ctypes.c_uint),
            ("bV5CSType", ctypes.c_uint), ("bV5Endpoints", ctypes.c_byte * 36),
            ("bV5GammaRed", ctypes.c_uint), ("bV5GammaGreen", ctypes.c_uint),
            ("bV5GammaBlue", ctypes.c_uint), ("bV5Intent", ctypes.c_uint),
            ("bV5ProfileData", ctypes.c_uint), ("bV5ProfileSize", ctypes.c_uint),
            ("bV5Reserved", ctypes.c_uint),
        ]

    hdr = BITMAPV5HEADER()
    hdr.bV5Size = ctypes.sizeof(BITMAPV5HEADER)
    hdr.bV5Width = sz
    hdr.bV5Height = sz
    hdr.bV5Planes = 1
    hdr.bV5BitCount = 32
    hdr.bV5Compression = 3  # BI_BITFIELDS
    hdr.bV5RedMask   = 0x00FF0000
    hdr.bV5GreenMask = 0x0000FF00
    hdr.bV5BlueMask  = 0x000000FF
    hdr.bV5AlphaMask = 0xFF000000

    DIB_RGB_COLORS = 0
    bits_ptr = ctypes.c_void_p()
    hdc = user32.GetDC(0)
    hbm_color = gdi32.CreateDIBSection(
        hdc, ctypes.byref(hdr), DIB_RGB_COLORS,
        ctypes.byref(bits_ptr), None, 0)
    user32.ReleaseDC(0, hdc)
    if not hbm_color or not bits_ptr:
        return False
    ctypes.memmove(bits_ptr, bytes(bgra), len(bgra))
    hbm_mask = gdi32.CreateBitmap(sz, sz, 1, 1, None)

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", ctypes.c_bool),
                     ("xHotspot", ctypes.c_ulong),
                     ("yHotspot", ctypes.c_ulong),
                     ("hbmMask", ctypes.c_void_p),
                     ("hbmColor", ctypes.c_void_p)]

    info = ICONINFO(True, 0, 0, hbm_mask, hbm_color)
    hicon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(hbm_mask)
    gdi32.DeleteObject(hbm_color)
    if not hicon:
        return False

    WM_SETICON = 0x0080
    ICON_BIG, ICON_SMALL = 1, 0
    user32.SendMessageW(found.value, WM_SETICON, ICON_BIG, hicon)
    user32.SendMessageW(found.value, WM_SETICON, ICON_SMALL, hicon)
    return True


# ---------------------------------------------------------------------------
# Public entrypoint

def set_app_icon_from_png(png_bytes: bytes) -> bool:
    """Swap the running app's Dock / Taskbar icon to the given PNG.

    Returns True if the swap was attempted (or definitely succeeded on
    backends that report it). False when the platform doesn't support
    runtime icon swap or when a required system library is missing.
    """
    try:
        if sys.platform == "darwin":
            return _macos_set_icon(png_bytes)
        if sys.platform.startswith("win"):
            return _windows_set_icon(png_bytes)
        return False  # Linux + others: no portable runtime swap.
    except Exception:
        # The animator loop runs every frame; one transient failure
        # must never crash the app.
        return False
