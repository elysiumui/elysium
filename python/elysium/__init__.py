"""Elysium UI — GPU-accelerated, freeform Python UI framework."""

from __future__ import annotations

# The maturin-built extension lands at elysium._native._native. Import is
# lazy + tolerant so pure-Python subpackages (elysium.reactive, .anim, ...)
# remain usable during early development before the native wheel is built.
try:
    from elysium._native import _native as _n  # type: ignore[attr-defined]
    App = _n.App
    Window = _n.Window
    HookProxy = _n.HookProxy
    Canvas = _n.Canvas
    Path = _n.Path
    SkiaLayer = _n.SkiaLayer
    DisplayList = _n.DisplayList
    Skin = _n.Skin
    load_skin = _n.load_skin
    IpcServer = _n.IpcServer
    ElysiumError = _n.ElysiumError
    SkinError = _n.SkinError
    HookNotFound = _n.HookNotFound
    ShaderValidationError = _n.ShaderValidationError
    CanvasExpired = _n.CanvasExpired
    _NATIVE_AVAILABLE = True
except ImportError as _e:
    _NATIVE_AVAILABLE = False
    _import_error = _e

    class _NotBuiltYet:
        """Placeholder raised when the native extension hasn't been compiled."""
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "Elysium native extension not built. Run `maturin develop` "
                f"from the repository root. (Original error: {_import_error})"
            )

    App = Window = HookProxy = Canvas = Path = SkiaLayer = DisplayList = Skin = IpcServer = _NotBuiltYet  # type: ignore

    def load_skin(*a, **kw):  # type: ignore
        raise RuntimeError("Elysium native extension not built. Run `maturin develop`.")
    ElysiumError = SkinError = HookNotFound = ShaderValidationError = CanvasExpired = RuntimeError  # type: ignore

# Package version — authoritative from the installed distribution metadata, so
# it always tracks the released wheel and never lags. Do NOT surface
# ``_n.__version__`` (the native crate's compiled-in CARGO_PKG_VERSION) as the
# public version: it is bumped separately and silently lagged the wheel once
# (1.1.3 shipped a 1.1.2-stamped .so). The native value is kept only as a
# fallback for frozen apps that bundle the .so but not the dist metadata; the
# literal is the last resort for an uninstalled source tree (keep it in sync
# with pyproject.toml — CI enforces pyproject == the Rust workspace version).
try:
    from importlib.metadata import version as _dist_version
    __version__ = _dist_version("elysium-ui")
except Exception:
    _nmod = globals().get("_n")
    __version__ = getattr(_nmod, "__version__", None) or "1.1.4"

from elysium import layout, theme, components, anim, reactive  # re-export
from elysium._deprecation import deprecated, deprecated_alias

__all__ = [
    "App", "Window", "HookProxy", "Canvas", "Path", "SkiaLayer", "DisplayList",
    "Skin", "load_skin",
    "IpcServer",
    "ElysiumError", "SkinError", "HookNotFound",
    "ShaderValidationError", "CanvasExpired",
    "__version__",
    "layout", "theme", "components", "anim", "reactive",
    "deprecated", "deprecated_alias",
]


# Decorator events and dotted hook access ride on a lightweight Python proxy
# around the native Window. The Python-side `App` wraps the native class so
# `app.window(...)` returns the proxy, which exposes `window.on(...)`,
# `window.fire(...)`, and `window.cover.text = "..."`.
if _NATIVE_AVAILABLE:
    from elysium._window_ext import wrap as _wrap_window
    _NativeApp = App  # type: ignore[misc]

    class App:  # type: ignore[no-redef]
        """Application object. Wraps the native App and returns Python-side
        Window proxies that support the decorator-based event API."""

        def __init__(self, title: str, identifier: str, **kwargs):
            self._native = _NativeApp(title=title, identifier=identifier, **kwargs)

        @property
        def identifier(self) -> str:
            return self._native.identifier

        def window(self, **kwargs):
            return _wrap_window(self._native.window(**kwargs))

        def run(self) -> None:
            self._native.run()

        def quit(self) -> None:
            self._native.quit()

    __all__.append("App")
