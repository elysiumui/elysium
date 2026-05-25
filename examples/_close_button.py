"""Borderless-window close-on-hover helper for example apps.

Each example's `.esk` paints a static scene loaded once by
`window.load_skin(...)`. We layer a small × close button on top by
spawning a daemon thread that re-publishes the DisplayList whenever
the hover state changes (or on click).

Usage:
    from examples._close_button import install_close_button
    install_close_button(app, window, skin_path,
                          width=480, height=320)
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from elysium._native import _native as _n


def install_close_button(app, window, skin_path: str, *,
                            width: int, height: int,
                            margin: float = 12.0,
                            size: float = 26.0,
                            hover_radius: float = 80.0) -> None:
    """Wire a hover-fade close button into a borderless example.

    Args:
        app: the `ely.App`.
        window: the `ely.Window` returned by `app.window(...)`.
        skin_path: same .esk path that was passed to `load_skin`. We
            re-load it to cache the static base DisplayList, so the
            overlay thread can compose `base + button` per frame
            without ripping the skin apart.
        width / height: window logical size in pixels.
        margin: padding from the top-right corner.
        size: button diameter in pixels.
        hover_radius: cursor must be within this distance of the
            button centre for it to appear.
    """
    skin = _n.load_skin(str(Path(skin_path).resolve()))

    btn_x = float(width) - size - margin
    btn_y = float(margin)
    btn_cx = btn_x + size / 2.0
    btn_cy = btn_y + size / 2.0
    half = size / 2.0

    state = {
        "visible_target": 0.0,   # 0.0 hidden, 1.0 shown — tweened
        "visible_now":    0.0,
        "last_press":     int(getattr(window, "press_count", 0)),
        "running":        True,
        # Drag-anywhere state. `grab` is the cursor's window-relative
        # position when the press started; while it's set and the
        # mouse is held, every frame moves the window so the cursor
        # stays at the same window-relative offset.
        "drag_grab":      None,
    }

    def compose_and_publish() -> None:
        """Build a fresh DisplayList that's the base skin + the close
        button at the current opacity, and push it to the window."""
        dl = skin.to_display_list(width, height)
        opacity = state["visible_now"]
        if opacity > 0.01:
            # Background pill — semi-translucent white so it reads over
            # any skin theme without clashing.
            bg_alpha = int(220 * opacity)
            dl.filled_circle(btn_cx, btn_cy, half,
                              (250, 250, 254, bg_alpha))
            # Drop-shadow halo: faint dark circle behind, offset 0.
            shadow_alpha = int(40 * opacity)
            dl.filled_circle(btn_cx, btn_cy + 1, half + 1,
                              (0, 0, 0, shadow_alpha))
            # × glyph — two diagonal strokes, dark grey.
            r = size * 0.22
            stroke_alpha = int(255 * opacity)
            stroke_col = (40, 40, 48, stroke_alpha)
            dl.stroke_path(
                f"M {btn_cx - r} {btn_cy - r} L {btn_cx + r} {btn_cy + r}",
                stroke_col, 2.2)
            dl.stroke_path(
                f"M {btn_cx - r} {btn_cy + r} L {btn_cx + r} {btn_cy - r}",
                stroke_col, 2.2)
        window.publish_display_list(dl)

    def loop() -> None:
        """Per-frame poll. Cheap when nothing's changing — we only
        re-publish when the visible opacity moves."""
        last_published = -1.0
        while state["running"]:
            # Cursor → button distance.
            cur = None
            try:
                if window.cursor_inside:
                    cur = window.cursor_position
            except Exception:
                cur = None
            if cur is not None:
                dx = cur[0] - btn_cx
                dy = cur[1] - btn_cy
                dist = (dx * dx + dy * dy) ** 0.5
                state["visible_target"] = 1.0 if dist < hover_radius else 0.0
            else:
                state["visible_target"] = 0.0

            # Ease toward target. Linear over ~120 ms is plenty.
            tgt = state["visible_target"]
            cur_op = state["visible_now"]
            step = 0.15
            if abs(tgt - cur_op) < step:
                state["visible_now"] = tgt
            elif tgt > cur_op:
                state["visible_now"] = cur_op + step
            else:
                state["visible_now"] = cur_op - step

            try:
                pc = int(window.press_count)
                pressed = bool(window.mouse_pressed)
            except Exception:
                pc = state["last_press"]; pressed = False

            # New press? Decide: close-button click vs start a drag.
            if pc != state["last_press"] and cur is not None:
                on_close_btn = (state["visible_now"] > 0.5
                                  and btn_x <= cur[0] <= btn_x + size
                                  and btn_y <= cur[1] <= btn_y + size)
                if on_close_btn:
                    state["last_press"] = pc
                    try: app.quit()
                    except Exception: pass
                    return
                # Not on the close button → start a window drag from
                # this cursor position. The skin's own click handlers
                # (e.g. greeting_button.click) still fire because the
                # framework's hook dispatch is independent — they ride
                # alongside the drag, and a press-without-move leaves
                # the window in place.
                state["drag_grab"] = (cur[0], cur[1])
            state["last_press"] = pc

            # Continue dragging while held. Drag math:
            #   new_outer = current_outer + (cur_in_window - grab)
            # The window follows the cursor, so cur_in_window oscillates
            # around `grab` and the delta is the user's drag velocity.
            if state["drag_grab"] is not None and pressed and cur is not None:
                gx, gy = state["drag_grab"]
                try:
                    ox, oy = window._native.outer_position
                    new_ox = int(ox + cur[0] - gx)
                    new_oy = int(oy + cur[1] - gy)
                    if (new_ox, new_oy) != (int(ox), int(oy)):
                        window.set_outer_position(new_ox, new_oy)
                except Exception:
                    pass
            if not pressed:
                state["drag_grab"] = None

            # Only re-publish on visible change so we don't thrash the
            # render thread.
            if abs(state["visible_now"] - last_published) > 0.01:
                try: compose_and_publish()
                except Exception: pass
                last_published = state["visible_now"]
            time.sleep(0.02)   # ~50 Hz polling

    # Push the initial frame (no button) so the window starts in a
    # known state.
    compose_and_publish()
    threading.Thread(target=loop, daemon=True,
                      name="example-close-btn").start()
