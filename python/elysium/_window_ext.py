"""Python-side extensions on top of the native `Window`.

Adds:
- `window.on(hook_name)` decorator for event handlers (spec §7.3).
- `window.fire(hook_name, event=None)` for the in-process dispatch path
  used by tests and the future hit-tester.
- Attribute-style hook access (`window.cover.text = "..."`) — the
  dotted-walker spec §7.2.

The native `Window` class is `unsendable=False`, so we attach these as
a Python subclass via `App.window(...)` patching.
"""
from __future__ import annotations

from typing import Any, Callable
import threading


class _WindowProxy:
    """Wraps a native `Window` and adds Python-side dispatch + dot-access."""

    __slots__ = ("_native", "_handlers", "_lock", "_ipc_server",
                 "_input_router", "_ui_dispatcher",
                 "_focus_nodes_provider", "_focused_node_id",
                 "_focus_handlers_on_change")

    def __init__(self, native_window: Any) -> None:
        self._native = native_window
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()
        self._ipc_server = None

    # --- Forwards to native ---------------------------------------------

    def __getitem__(self, key: str):
        return self._native[key]

    def publish_display_list(self, dl):
        self._native.publish_display_list(dl)

    def load_skin(self, path: str, surface_size: tuple[int, int] | None = None):
        """Load an `.esk` bundle as this window's top-level skin.

        Rejects component skins (`manifest.kind == "component"`):
        those don't own a window — they're meant to be composed into
        another skin's DisplayList via the `_n.load_skin(path)` →
        `to_display_list(...)` → `dl.extend(...)` flow. Loading one
        as a window's whole content is almost always a bug.
        """
        try:
            from elysium._native import _native as _n
            probe = _n.load_skin(path)
            if getattr(probe, "kind", "application") == "component":
                raise ValueError(
                    f"{path!r} is a component skin (manifest.kind == "
                    f"'component') and can't be loaded as a window's "
                    f"top-level content. Use it as a sub-skin: "
                    f"`s = _n.load_skin({path!r}); "
                    f"dl.extend(s.to_display_list(w, h))`.")
        except ValueError:
            raise
        except Exception:
            # If the probe itself fails, fall through and let the
            # native loader raise its own canonical error.
            pass
        if surface_size is None:
            return self._native.load_skin(path)
        return self._native.load_skin(path, surface_size)

    def close(self):
        return self._native.close()

    # --- Mouse / position polling --------------------------------------

    @property
    def cursor_position(self):
        return self._native.cursor_position

    @property
    def cursor_inside(self) -> bool:
        return self._native.cursor_inside

    @property
    def mouse_pressed(self) -> bool:
        return self._native.mouse_pressed

    @property
    def press_count(self) -> int:
        return self._native.press_count

    @property
    def mouse_right_pressed(self) -> bool:
        """True while the secondary (right) mouse button is held down.
        Provided for context-menu / alternate-action UIs. Older native
        builds without the getter fall back to False."""
        return bool(getattr(self._native, "mouse_right_pressed", False))

    @property
    def right_press_count(self) -> int:
        """Monotonic counter incremented on every right-button press
        transition. Mirrors ``press_count`` for left-clicks. Returns 0
        on older native builds without the getter."""
        return int(getattr(self._native, "right_press_count", 0))

    # --- Keyboard polling ---------------------------------------------

    @property
    def modifiers(self) -> int:
        """Bitmask of currently-held modifiers: 1=Shift 2=Ctrl 4=Alt 8=Meta."""
        return self._native.modifiers

    def poll_key_event(self):
        """Pop the oldest pending key event as
        (code, pressed: bool, modifiers: int, text: str) or None."""
        return self._native.poll_key_event()

    def keys_held(self) -> list[str]:
        return self._native.keys_held()

    # --- Directional focus navigation ---------------------------------

    def install_focus_nav(self, nodes_provider) -> None:
        """Wire Tab / Shift-Tab / arrow keys to ``elysium.focus.next_focus``.
        ``nodes_provider`` is a zero-arg callable that returns the current
        list of ``FocusNode`` items (typically rebuilt each frame from
        the live placements). Subsequent Tab presses cycle through them
        in document order; arrow keys move spatially."""
        self._focus_nodes_provider = nodes_provider
        self._focused_node_id: str | None = None
        if not getattr(self, "_focus_handlers_on_change", None):
            self._focus_handlers_on_change = []

    def on_focus_changed(self, fn) -> None:
        """Register a callback that receives the new focused node id
        whenever the framework's focus navigation moves focus."""
        if not getattr(self, "_focus_handlers_on_change", None):
            self._focus_handlers_on_change = []
        self._focus_handlers_on_change.append(fn)

    def handle_focus_key(self, code: str, mods: int) -> bool:
        """Call from your frame loop when you've polled a key event.
        Returns True when the key was consumed by focus navigation,
        False otherwise so you can dispatch it elsewhere."""
        if not getattr(self, "_focus_nodes_provider", None):
            return False
        from elysium.focus import next_focus
        shift = bool(mods & 1)
        direction = None
        if code == "Tab":              direction = "prev" if shift else "next"
        elif code == "ArrowUp":        direction = "up"
        elif code == "ArrowDown":      direction = "down"
        elif code == "ArrowLeft":      direction = "left"
        elif code == "ArrowRight":     direction = "right"
        if direction is None: return False
        nodes = self._focus_nodes_provider()
        new_id = next_focus(nodes, self._focused_node_id, direction)
        if new_id is not None:
            self._focused_node_id = new_id
            for cb in getattr(self, "_focus_handlers_on_change", []) or []:
                try: cb(new_id)
                except Exception: pass
        return True

    @property
    def focused_node(self) -> str | None:
        return getattr(self, "_focused_node_id", None)

    # --- Framework input routing (Tier-1) -----------------------------

    def input_router(self):
        """Return this window's :class:`elysium.input.InputRouter`,
        creating it on first use. The router centralizes delivery of
        keystrokes, typed text, IME composition, and clipboard actions to
        the focused editable widget. Register the focusable widgets each
        frame with ``router.set_widgets(...)`` and call ``router.tick()``
        once per frame after polling.

        This supersedes the lower-level ``install_focus_nav`` /
        ``handle_focus_key`` helpers for any app with editable widgets."""
        r = getattr(self, "_input_router", None)
        if r is None:
            from elysium.input import InputRouter
            r = self._input_router = InputRouter(self)
        return r

    # --- Threading → UI marshalling (Tier-2) --------------------------

    def ui_dispatcher(self):
        """Return this window's :class:`elysium.concurrency.UiDispatcher`,
        creating it on first use and installing it as the process default so
        ``call_on_ui_thread`` / ``post`` / ``@ui_thread`` target this window's
        frame loop. Drain it each tick (``FrameLoop`` does this for you)."""
        d = getattr(self, "_ui_dispatcher", None)
        if d is None:
            from elysium.concurrency import UiDispatcher, set_default_dispatcher
            d = self._ui_dispatcher = UiDispatcher()
            set_default_dispatcher(d)
        return d

    def post(self, fn, *args, **kwargs) -> None:
        """Queue ``fn`` to run on the UI thread next tick (fire-and-forget)."""
        self.ui_dispatcher().post(fn, *args, **kwargs)

    def invoke(self, fn, *args, **kwargs):
        """Queue ``fn`` on the UI thread; returns a Future for the result."""
        return self.ui_dispatcher().invoke(fn, *args, **kwargs)

    def set_outer_position(self, x: int, y: int) -> None:
        self._native.set_outer_position(x, y)

    def set_minimized(self, minimized: bool) -> None:
        """Toggle the OS minimised state. Used by borderless apps
        whose custom title-bar traffic lights paint their own
        minimise button (the OS still drives the minimise
        animation). Older native builds without the underlying
        ``set_minimized`` no-op gracefully so callers can fire
        unconditionally."""
        fn = getattr(self._native, "set_minimized", None)
        if fn is not None:
            fn(bool(minimized))

    def set_maximized(self, maximized: bool) -> None:
        """Toggle the OS maximised state. Mirror of
        ``set_minimized``  works on every platform winit supports;
        falls back to no-op when the native build predates the
        feature."""
        fn = getattr(self._native, "set_maximized", None)
        if fn is not None:
            fn(bool(maximized))

    def set_fullscreen(self, fullscreen: bool) -> None:
        """Toggle borderless fullscreen. Stretches the window over
        the active monitor; pass False to restore. Custom title bars
        that paint a "green maximise" traffic light  Mac convention
        for fullscreen  wire this from the green button. No-op on
        older native builds without `set_fullscreen`."""
        fn = getattr(self._native, "set_fullscreen", None)
        if fn is not None:
            fn(bool(fullscreen))

    def set_cursor(self, name: str) -> None:
        """Swap the OS mouse cursor icon. CSS-style names supported:
        ``default | pointer | text | crosshair | move | grab |
        grabbing | not-allowed | ew-resize | ns-resize | nwse-resize |
        nesw-resize | zoom-in | zoom-out``. Unknown names fall back to
        ``default``. No-op on older native builds."""
        fn = getattr(self._native, "set_cursor", None)
        if fn is not None:
            fn(str(name))

    def drag_resize_window(self, direction: str) -> None:
        """Begin an OS-driven interactive resize from one of the
        eight edges / corners (``e | n | ne | nw | s | se | sw | w``).
        Used by borderless-window edge-resize bands: on press inside
        the band, fire this and the OS takes over until mouse-up.
        No-op on older native builds without the binding."""
        fn = getattr(self._native, "drag_resize_window", None)
        if fn is not None:
            fn(str(direction))

    # --- macOS Cocoa polish -------------------------------------------

    def set_blur_behind(self, enabled: bool, material: int = 12) -> None:
        """Attach an NSVisualEffectView backdrop. `material`:
        3=titlebar, 12=HUD (default), 21=under-window, 7=sidebar."""
        self._native.set_blur_behind(enabled, material)

    def set_ignores_mouse(self, ignores: bool) -> None:
        self._native.set_ignores_mouse(ignores)

    def set_has_shadow(self, has_shadow: bool) -> None:
        self._native.set_has_shadow(has_shadow)

    def set_window_level(self, level: int) -> None:
        self._native.set_window_level(level)

    def set_hit_test_path(self, svg_d: str | None) -> None:
        """Define the window's interactive region as an SVG path. Cursor
        positions outside the path pass clicks through to whatever is
        underneath (the OS window's `ignoresMouseEvents` is toggled on
        the transition edge). Pass `None` to disable."""
        self._native.set_hit_test_path(svg_d)

    # --- Hot reload (Phase 2.3) ---------------------------------------

    def enable_hot_reload(self, socket_path: str | None = None) -> Any:
        """Start an IPC server that listens for `SkinChanged` and reloads
        the skin in-place. Returns the IpcServer instance so the caller
        can extend it with additional handlers.

        Default socket path: ~/.elysium/sessions/elysium-default.sock
        Compatible with the `elysium dev <skin>` CLI watcher.
        """
        import json
        import os
        import pathlib
        from elysium._native import _native as _n  # type: ignore[attr-defined]

        if socket_path is None:
            home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
            d = pathlib.Path(home) / ".elysium" / "sessions"
            d.mkdir(parents=True, exist_ok=True)
            socket_path = str(d / "elysium-default.sock")

        server = _n.IpcServer(socket_path)

        def _on_skin_changed(payload_json: str) -> None:
            try:
                body = json.loads(payload_json)
            except Exception:
                return
            path = body.get("path")
            if not path:
                return
            try:
                self.load_skin(path)
                print(f"[elysium] hot-reloaded skin: {path}", flush=True)
            except Exception as e:
                print(f"[elysium] hot-reload failed: {e}", flush=True)

        server.on_message("skin_changed", _on_skin_changed)
        server.start()
        # Keep a reference so the server isn't GC'd.
        self._ipc_server = server
        return server

    # --- Decorator events ----------------------------------------------

    def on(self, hook_name: str) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        """Register `fn` as a handler for `hook_name`.

            @window.on("play_button.click")
            def play(event):
                ...

        The handler fires when `window.fire(hook_name, event)` is called.
        Live OS input → fire wiring lands with the hit-test pipeline.
        """
        def decorate(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
            with self._lock:
                self._handlers.setdefault(hook_name, []).append(fn)
            return fn
        return decorate

    def subscribe(self, hook_name: str, callback: Callable[[Any], Any]) -> Callable[[], None]:
        """Imperative subscription. Returns an unsubscribe callable."""
        with self._lock:
            self._handlers.setdefault(hook_name, []).append(callback)

        def unsubscribe() -> None:
            with self._lock:
                lst = self._handlers.get(hook_name)
                if lst is not None:
                    try:
                        lst.remove(callback)
                    except ValueError:
                        pass

        return unsubscribe

    def fire(self, hook_name: str, event: Any = None) -> int:
        """Dispatch `event` to every handler registered for `hook_name`.

        Returns the number of handlers invoked. Exceptions inside handlers
        are caught and printed — they never propagate into the caller
        (which is often the render thread or OS input thread).
        """
        with self._lock:
            handlers = list(self._handlers.get(hook_name, ()))
        n = 0
        for fn in handlers:
            try:
                fn(event)
            except Exception as e:  # noqa: BLE001
                import traceback
                print(f"[elysium] handler for {hook_name!r} raised:\n{traceback.format_exc()}", flush=True)
                _ = e
            n += 1
        return n

    # --- Dotted attribute access ----------------------------------------

    def __getattr__(self, key: str):
        # Defer to native attributes first — anything the underlying
        # _native.Window exposes (poll_file_drop, set_blur_behind,
        # publish_a11y_tree, etc.) needs to pass through transparently;
        # otherwise the dotted-hook fallback shadows real methods.
        if key.startswith("_"):
            raise AttributeError(key)
        native = object.__getattribute__(self, "_native")
        if hasattr(native, key):
            return getattr(native, key)
        return _DottedAccessor(self, [key])


class _DottedAccessor:
    """Builds up a dotted hook path; commits on attribute set."""
    __slots__ = ("_window", "_parts")

    def __init__(self, window: _WindowProxy, parts: list[str]) -> None:
        self._window = window
        self._parts = parts

    def __getattr__(self, key: str) -> "_DottedAccessor":
        return _DottedAccessor(self._window, self._parts + [key])

    def __setattr__(self, key: str, value: Any) -> None:
        if key in ("_window", "_parts"):
            object.__setattr__(self, key, value)
            return
        full = ".".join(self._parts + [key])
        proxy = self._window[full]
        setattr(proxy, key, value) if False else None  # silence Pyright
        # On the HookProxy the setter is named after the kind — `text`,
        # `value`, `state`. We assume the rightmost dotted segment matches
        # the property the user wants to set.
        setter_name = key
        if not hasattr(proxy, setter_name):
            # Fall back to the hook's natural setter inferred from kind.
            kind = getattr(proxy, "kind", "")
            if "Text" in kind: setter_name = "text"
            elif "Value" in kind: setter_name = "value"
            elif "State" in kind: setter_name = "state"
        setattr(proxy, setter_name, value)


def wrap(native_window: Any) -> _WindowProxy:
    """Wrap a native Window in the Python-side _WindowProxy."""
    return _WindowProxy(native_window)
