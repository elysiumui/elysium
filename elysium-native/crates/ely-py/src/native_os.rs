//! Native OS integration — single-instance, notifications, system tray, and
//! global hotkeys. Tray / hotkeys / native notifications are gated to macOS +
//! Windows (so Linux pulls no GTK / libdbus / X11 build deps); Linux uses a
//! `notify-send` subprocess for notifications and reports tray / hotkeys as
//! unsupported through `capabilities()`. Tray + hotkey *creation* should run on
//! the app's main thread during setup; their events are polled each frame from
//! any thread via global channels.

use pyo3::prelude::*;
use std::sync::OnceLock;

// --- single instance (pure std, all platforms) -----------------------------

// Held advisory file locks, one per app id, kept open for the process
// lifetime so the lock stays held; the OS releases them when the process
// exits (crash included). `std::fs::File::try_lock` is `flock` on Unix and
// `LockFileEx` on Windows, so a *different* process is refused immediately.
//
// This used to bind a loopback TCP port derived from the id. That port lived
// inside every OS's ephemeral range, so an unrelated outgoing connection that
// happened to receive the same source port made bind() fail and the first
// instance was wrongly refused (observed as a flaky test on macOS).
static INSTANCE_LOCKS: OnceLock<
    parking_lot::Mutex<std::collections::HashMap<String, std::fs::File>>,
> = OnceLock::new();

/// Lock file for `app_id`, in the temp directory, scoped to the current user
/// (the user name is folded into the hash) so one user's instance never
/// interferes with another's on a shared `/tmp`. The FNV-1a hash keeps the
/// name short and filesystem-safe; a sanitised prefix keeps it recognisable.
fn instance_lock_path(app_id: &str) -> std::path::PathBuf {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("LOGNAME"))
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_default();
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in user.bytes().chain([0u8]).chain(app_id.bytes()) {
        h = (h ^ u64::from(b)).wrapping_mul(0x0100_0000_01b3);
    }
    let prefix: String = app_id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_'))
        .take(48)
        .collect();
    std::env::temp_dir().join(format!("elysium-instance-{prefix}-{h:016x}.lock"))
}

/// Try to become the single instance for `app_id`. Returns true if this
/// process acquired the lock (or already holds it for this id), false if
/// another process holds it. If the lock file cannot be created or locked
/// for any reason other than being held elsewhere, returns true so the app
/// still starts (same fail-open policy as the Python wrapper).
#[pyfunction]
pub fn single_instance(app_id: &str) -> bool {
    let map = INSTANCE_LOCKS.get_or_init(|| parking_lot::Mutex::new(Default::default()));
    let mut guard = map.lock();
    if guard.contains_key(app_id) {
        return true; // this process already holds it
    }
    let file = match std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(instance_lock_path(app_id))
    {
        Ok(f) => f,
        Err(_) => return true,
    };
    match file.try_lock() {
        Ok(()) => {
            guard.insert(app_id.to_string(), file);
            true
        }
        Err(std::fs::TryLockError::WouldBlock) => false,
        Err(std::fs::TryLockError::Error(_)) => true,
    }
}

// --- notifications ----------------------------------------------------------

/// Show an OS notification. Native on macOS / Windows; `notify-send` on Linux.
/// Returns true on success (best-effort).
#[pyfunction]
#[pyo3(signature = (title, body="", app_name="Elysium"))]
pub fn notify(title: &str, body: &str, app_name: &str) -> bool {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        use notify_rust::Notification;
        Notification::new()
            .summary(title)
            .body(body)
            .appname(app_name)
            .show()
            .is_ok()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = app_name;
        std::process::Command::new("notify-send")
            .arg(title)
            .arg(body)
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
}

// --- system tray (macOS / Windows) -----------------------------------------

#[cfg(any(target_os = "macos", target_os = "windows"))]
mod tray_impl {
    use tray_icon::menu::{Menu, MenuEvent, MenuItem};
    use tray_icon::{Icon, TrayIconBuilder};

    /// Create the tray icon with a menu of `(id, label)` items. The TrayIcon
    /// is leaked so it lives for the process; menu clicks arrive on the global
    /// `MenuEvent` channel. Must be called on the main thread.
    pub fn create(tooltip: &str, items: &[(String, String)]) -> bool {
        let menu = Menu::new();
        for (id, label) in items {
            let item = MenuItem::with_id(id.clone(), label, true, None);
            if menu.append(&item).is_err() {
                return false;
            }
        }
        // A 16x16 transparent-ish icon (a filled square) — apps can ship their
        // own later; this keeps the tray visible without an asset.
        let mut rgba = vec![0u8; 16 * 16 * 4];
        for px in rgba.chunks_mut(4) {
            px[0] = 90;
            px[1] = 120;
            px[2] = 240;
            px[3] = 255;
        }
        let icon = match Icon::from_rgba(rgba, 16, 16) {
            Ok(i) => i,
            Err(_) => return false,
        };
        match TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip(tooltip)
            .with_icon(icon)
            .build()
        {
            Ok(tray) => {
                std::mem::forget(tray); // keep alive for process lifetime
                true
            }
            Err(_) => false,
        }
    }

    pub fn poll() -> Option<String> {
        MenuEvent::receiver().try_recv().ok().map(|e| e.id.0)
    }
}

/// Create a system-tray icon with a context menu of `(id, label)` items.
/// Returns false where unsupported (Linux) or on failure.
#[pyfunction]
#[pyo3(signature = (tooltip="", items=Vec::new()))]
pub fn tray_create(tooltip: &str, items: Vec<(String, String)>) -> bool {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        tray_impl::create(tooltip, &items)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = (tooltip, items);
        false
    }
}

/// Pop the id of the next clicked tray-menu item, if any.
#[pyfunction]
pub fn tray_poll() -> Option<String> {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        tray_impl::poll()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        None
    }
}

// --- global hotkeys (macOS / Windows) --------------------------------------

#[cfg(any(target_os = "macos", target_os = "windows"))]
mod hotkey_impl {
    use global_hotkey::hotkey::{Code, HotKey, Modifiers};
    use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager};
    use std::cell::RefCell;

    // The manager holds OS handles that are !Send/!Sync on Windows, so it
    // can't live in a `static`. It must be created + used on the same
    // (main) thread that calls `register`; a thread_local satisfies both.
    // `poll` never touches it — it reads the library's global event channel.
    thread_local! {
        static MANAGER: RefCell<Option<GlobalHotKeyManager>> = const { RefCell::new(None) };
    }

    fn code_from(name: &str) -> Option<Code> {
        // Accept "KeyR", "F5", "Digit1", "Space", etc. (winit-style names).
        Some(match name {
            "Space" => Code::Space,
            "Enter" => Code::Enter,
            "Escape" => Code::Escape,
            _ => return name.parse::<Code>().ok(),
        })
    }

    pub fn register(mods_bits: u8, key: &str) -> u32 {
        let Some(code) = code_from(key) else {
            return 0;
        };
        let mut mods = Modifiers::empty();
        if mods_bits & 1 != 0 {
            mods |= Modifiers::SHIFT;
        }
        if mods_bits & 2 != 0 {
            mods |= Modifiers::CONTROL;
        }
        if mods_bits & 4 != 0 {
            mods |= Modifiers::ALT;
        }
        if mods_bits & 8 != 0 {
            mods |= Modifiers::META;
        }
        let hk = HotKey::new(Some(mods), code);
        let id = hk.id();
        MANAGER.with(|cell| {
            let mut slot = cell.borrow_mut();
            if slot.is_none() {
                match GlobalHotKeyManager::new() {
                    Ok(m) => *slot = Some(m),
                    Err(_) => return 0,
                }
            }
            match slot.as_ref().unwrap().register(hk) {
                Ok(()) => id,
                Err(_) => 0,
            }
        })
    }

    pub fn poll() -> Option<u32> {
        GlobalHotKeyEvent::receiver().try_recv().ok().map(|e| e.id)
    }
}

/// Register a global (system-wide) hotkey. `mods` bits: 1=Shift 2=Ctrl 4=Alt
/// 8=Meta; `key` is a winit-style code ("KeyR", "F5", "Space"). Returns a
/// non-zero hotkey id on success, 0 on failure / unsupported.
#[pyfunction]
pub fn hotkey_register(mods: u8, key: &str) -> u32 {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        hotkey_impl::register(mods, key)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = (mods, key);
        0
    }
}

/// Pop the id of the next fired global hotkey, if any.
#[pyfunction]
pub fn hotkey_poll() -> Option<u32> {
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        hotkey_impl::poll()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        None
    }
}

// --- capability matrix ------------------------------------------------------

/// Report which native features are supported on this platform, as
/// `(feature, supported)` pairs the Python layer turns into a dict.
#[pyfunction]
pub fn capabilities() -> Vec<(String, bool)> {
    let native = cfg!(any(target_os = "macos", target_os = "windows"));
    vec![
        ("single_instance".into(), true),
        ("notifications".into(), true), // native on mac/win, notify-send on linux
        ("tray".into(), native),
        ("global_hotkeys".into(), native),
        ("power_events".into(), true), // via window.poll_lifecycle_event (Phase 0)
    ]
}

#[cfg(test)]
mod single_instance_tests {
    use super::*;

    #[test]
    fn lock_path_is_per_id_and_lives_in_the_temp_dir() {
        let a = instance_lock_path("dev.elysium.test.path.A");
        let b = instance_lock_path("dev.elysium.test.path.B");
        assert_ne!(a, b);
        assert_eq!(a, instance_lock_path("dev.elysium.test.path.A"));
        assert!(a.starts_with(std::env::temp_dir()));
        let name = a.file_name().unwrap().to_string_lossy().into_owned();
        assert!(name.starts_with("elysium-instance-dev.elysium.test.path.A-"));
        assert!(name.ends_with(".lock"));
    }

    #[test]
    fn lock_path_sanitises_the_id() {
        let name = instance_lock_path("weird id/with:chars*")
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        assert!(!name.contains('/') && !name.contains(':') && !name.contains('*'));
        assert!(!name.contains(' '));
    }

    #[test]
    fn same_process_keeps_the_lock_and_a_second_handle_is_refused() {
        let id = "dev.elysium.test.singleinstance.rust";
        assert!(single_instance(id));
        assert!(single_instance(id));
        // Another open file description on the same path (what a second
        // process would hold) must be refused while this process holds it.
        let other = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(instance_lock_path(id))
            .unwrap();
        assert!(matches!(
            other.try_lock(),
            Err(std::fs::TryLockError::WouldBlock)
        ));
    }
}
