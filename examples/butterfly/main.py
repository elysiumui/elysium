"""Butterfly showcase — exercises the full Phase 2 framework stack.

Run with `python examples/butterfly/main.py` for the procedural Blue
Morpho. Pass `--image=PATH` to swap in a butterfly image you own or
are licensed to use; the framework's `TextureCache` decodes once and
re-draws each frame at 60 FPS.

What this demo exercises in the framework:

  • `elysium.anim.AnimationClock` + `Tween` (ping_pong, ease-in-out-sine)
        — drives the flap value; no manual cosine math
  • `elysium.anim.run_animation_thread`
        — 60 Hz daemon thread ticks the clock + publishes frames
  • `elysium.reactive.signal` + `effect`
        — cursor / hover / drag state as reactive cells
  • `elysium.components.IconCloseButton`
        — real component with hit_test + hover-driven paint
  • `elysium._native.DisplayList` + path/text/image draw commands
        — lock-free producer → render thread consumer
  • `elysium._native.SkiaLayer` texture cache + transforms
        — only used when `--image` is supplied
  • `Window.cursor_position` / `press_count` / `mouse_pressed`
        — non-blocking mouse-state polling from any thread
  • `Window.set_outer_position` + `Window.publish_display_list`
        — programmatic window move + lock-free frame publication
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import elysium as ely
from elysium import anim, reactive
from elysium._native import _native as _n
from elysium.components import IconCloseButton

sys.path.insert(0, os.path.dirname(__file__))
import butterfly  # noqa: E402


WIDTH, HEIGHT = 900, 720
SCALE = 1.0


def point_in_butterfly(x: float, y: float) -> bool:
    cx = WIDTH // 2
    cy = HEIGHT // 2 + int(30 * SCALE)
    return (
        cx - int(460 * SCALE) <= x <= cx + int(460 * SCALE)
        and cy - int(220 * SCALE) <= y <= cy + int(290 * SCALE)
    )


def _draw_image_butterfly(dl, image_path: str, flap_t: float) -> None:
    """Photographic path — single image, flap simulated by horizontal squash.

    For per-wing rotation, split the image into a sprite atlas
    (left wing, right wing, body) and use
    `dl.draw_image_file_region` for each layer.
    """
    cx = WIDTH / 2.0
    img_w_full = WIDTH * 0.95
    img_h_full = HEIGHT * 0.95
    flap_scale_x = 0.25 + 0.75 * flap_t
    img_w = img_w_full * flap_scale_x
    img_h = img_h_full
    dl.draw_image_file(image_path, cx - img_w / 2.0, (HEIGHT - img_h) / 2.0, img_w, img_h)


def main() -> None:
    global WIDTH, HEIGHT
    parser = argparse.ArgumentParser(description="Live butterfly on your desktop.")
    parser.add_argument("--image", type=str, default=None,
                        help="Path to a butterfly image (PNG / JPEG / WebP). "
                             "If omitted, the procedural Blue Morpho is rendered.")
    parser.add_argument("--width",  type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--duration", type=float, default=2.4,
                        help="Seconds per full flap cycle (open→closed→open).")
    args = parser.parse_args()
    WIDTH, HEIGHT = args.width, args.height
    image_path = args.image
    if image_path and not os.path.isfile(image_path):
        print(f"image not found: {image_path}", file=sys.stderr); sys.exit(2)

    app = ely.App(title="butterfly", identifier="dev.elysium.butterfly")
    win = app.window(transparent=True, title_bar=False, resizable=False,
                     initial_size=(WIDTH, HEIGHT))

    # --- Reactive state -------------------------------------------------
    hover_butterfly  = reactive.signal(False)
    hover_close      = reactive.signal(False)
    window_pos       = reactive.signal((200, 200))
    win.set_outer_position(*window_pos.peek())

    # An effect tracks position changes and pushes them to the OS.
    reactive.effect(lambda: win.set_outer_position(*window_pos()))

    # --- Animation engine: flap is one Tween, looped ping-pong ----------
    clock = anim.AnimationClock()
    flap_value = reactive.signal(1.0)
    anim.Tween(
        0.0, 1.0,
        duration=args.duration / 2.0,
        easing="ease-in-out-sine",
        loop="ping_pong",
        on_update=lambda v: flap_value.set(v),
    ).start(clock)

    # --- Close button: a real component, hit-tests itself --------------
    close_btn = IconCloseButton(
        x=WIDTH // 2 + int(420 * SCALE) - 50,
        y=HEIGHT // 2 - int(180 * SCALE) + 22,
        w=28, h=28,
        on_click=lambda: (state.update(running=False), app.quit()),
    )

    # --- Drag/quit state ------------------------------------------------
    state = {"running": True, "drag": None, "last_press": 0}

    def on_frame() -> None:
        if not state["running"]:
            return

        cursor = win.cursor_position
        press = win.press_count
        pressed = win.mouse_pressed

        # Update reactive state from polled OS state.
        hover_butterfly.set(cursor is not None and point_in_butterfly(*cursor))
        hover_close.set(cursor is not None and close_btn.hit_test(*cursor))

        # New press → maybe click, maybe drag-start.
        if press != state["last_press"]:
            state["last_press"] = press
            if pressed and cursor is not None:
                if hover_close.peek():
                    close_btn.fire_click()
                    return
                elif hover_butterfly.peek():
                    state["drag"] = (window_pos.peek(), cursor)
            elif not pressed:
                state["drag"] = None

        # Continue drag → reactive position update.
        if state["drag"] is not None and pressed and cursor is not None:
            (wx0, wy0), (cx0, cy0) = state["drag"]
            window_pos.set((wx0 + (cursor[0] - cx0), wy0 + (cursor[1] - cy0)))

        # --- Build this frame's DisplayList ---------------------------
        dl = _n.DisplayList()
        dl.clear(0.0, 0.0, 0.0, 0.0)
        if image_path:
            _draw_image_butterfly(dl, image_path, flap_value.peek())
        else:
            butterfly.draw(dl, WIDTH, HEIGHT, flap_t=flap_value.peek(), scale=SCALE)

        # Component-rendered close button — appears only on hover.
        # The component handles its own smooth state interpolation now.
        close_btn.update(1.0 / 60.0, {"hover": hover_close.peek()})
        if hover_butterfly.peek():
            close_btn.paint(dl)

        win.publish_display_list(dl)

    # Preload the image so the first frame doesn't stall on decode.
    if image_path:
        _n.SkiaLayer(64, 64).preload_image(image_path)

    anim.run_animation_thread(clock, on_frame, target_hz=60.0,
                              running=lambda: state["running"])

    app.run()
    state["running"] = False


if __name__ == "__main__":
    main()
