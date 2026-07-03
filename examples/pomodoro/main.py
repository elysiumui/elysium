"""Pomodoro tutorial app — photoreal tomato that opens like a clam
to reveal a digital LCD.

Features
--------
  * Borderless transparent window — the tomato is the whole app
    silhouette.
  * Click the green leaf-cluster stem to open / close the tomato.
  * When open, a maroon-black LCD panel shows the current mode
    (FOCUS), the 25:00 timer readout, and a Start / Pause button.
  * When closed, a thin slider rides along the dial groove — moves
    right → left as the timer ticks down so the user can see
    progress at a glance without re-opening the tomato.
  * Hitting 0:00 plays a system "ding" via `afplay` on macOS
    (`paplay` on Linux is attempted as a fallback).
  * Drag any empty part of the tomato to move the window.
  * Hover the top-right corner to reveal a × close button; Esc also
    quits.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import elysium as ely
from elysium._native import _native as _n


WIDTH, HEIGHT = 408, 459     # 480 × 540 × 0.85

# Timer config
FOCUS_DURATION_S = 25 * 60   # canonical Pomodoro focus block

# Animation knobs (all pixel values scaled to the 0.85× chassis).
TOP_LIFT       = 93.5        # how far the top half rises when open
OPEN_STEP      = 0.06        # eased open/close progress per frame
CLOSE_FADE     = 0.15        # × button fade speed


def main() -> None:
    here = Path(__file__).resolve().parent
    top_png    = str(here / "assets" / "tomato-top.png")
    bottom_png = str(here / "assets" / "tomato-bottom.png")

    # Stem-cluster artwork lives in its own `.esk` so the Designer can
    # open it and recolour / reshape leaves without touching Python.
    # We compile it once into a DisplayList and stamp it per-frame with
    # a `push_transform` / `extend` / `pop_transform` sandwich — Python
    # still owns the live position (which animates as the clam opens);
    # the .esk owns the look.
    #
    # Canonical authoring centre is (100, 100) in a 200×200 canvas at
    # radius=32 (see scripts/generate-pomodoro-stem-esk.py). Per-frame
    # transform maps (100*s, 100*s) → (sx, sy) where s = BTN_R/32.
    stem_skin = _n.load_skin(str(here / "stem.esk"))
    stem_dl_cache = stem_skin.to_display_list(200, 200)
    STEM_CANON_C = 100.0
    STEM_CANON_R = 32.0

    app = ely.App(title="Pomodoro", identifier="dev.elysium.pomodoro")
    window = app.window(
        transparent=True, title_bar=False, resizable=True,
        initial_size=(WIDTH, HEIGHT),
    )
    try: window.set_has_shadow(False)
    except Exception: pass

    # Dock / Taskbar icon — set to the tomato so the app's running
    # identity matches its silhouette. `elysium.dock` is the
    # cross-platform helper the Designer's wing-flap also uses.
    try:
        from elysium.dock import set_app_icon_from_png
        icon_path = Path(__file__).resolve().parent / "assets" / "tomato-icon.png"
        if icon_path.is_file():
            set_app_icon_from_png(icon_path.read_bytes())
    except Exception: pass

    # --- Layout (all pixel values scaled to the 0.85× chassis) -----
    BTN_R = 32.0                              # leaf cluster radius
    BTN_CX = WIDTH / 2.0
    BTN_CY_CLOSED = 191.0                     # cluster sits ON the red dome
    # Timer slider — single short pill on the dial groove line.
    GROOVE_Y       = HEIGHT * 0.70
    GROOVE_X0      = WIDTH * 0.27
    GROOVE_X1      = WIDTH * 0.73
    KNOB_W         = 12.0
    KNOB_H         = 31.0
    # × close button — sits at the upper-right shoulder of the closed
    # tomato dome (closed silhouette spans x≤362, top at y≈167), so the
    # button reads as part of the tomato rather than a stray glyph
    # floating in the empty corner above it.
    CLOSE_SIZE     = 22.0
    CLOSE_X = 330.0
    CLOSE_Y = 170.0
    CLOSE_CX = CLOSE_X + CLOSE_SIZE / 2.0
    CLOSE_CY = CLOSE_Y + CLOSE_SIZE / 2.0

    # Start / pause button inside the LCD (only hot when open).
    START_W, START_H = 85.0, 24.0
    START_X = BTN_CX - START_W / 2.0
    START_LCD_OFFSET = 73.0

    state = {
        # Open / close animation
        "open_target":   0.0,
        "open_now":      0.0,
        "is_open":       False,
        # × close button fade
        "close_target":  0.0,
        "close_now":     0.0,
        # Input
        "last_press":    int(getattr(window, "press_count", 0)),
        "running":       True,
        "drag_grab":     None,
        # Timer
        "timer_running": False,
        "timer_remaining": float(FOCUS_DURATION_S),
        "timer_last_tick": time.monotonic(),
        "timer_done_fired": False,
    }

    def stem_pos(open_p: float) -> tuple[float, float]:
        return (BTN_CX, BTN_CY_CLOSED - open_p * TOP_LIFT)

    def lcd_rect() -> tuple[float, float, float, float]:
        panel_w, panel_h = 238.0, 134.0
        x = BTN_CX - panel_w / 2.0
        y = HEIGHT * 0.64 - panel_h / 2.0
        return x, y, panel_w, panel_h

    def start_button_rect() -> tuple[float, float, float, float]:
        lx, ly, _lw, _lh = lcd_rect()
        return (START_X, ly + START_LCD_OFFSET, START_W, START_H)

    def fmt_time(s: float) -> str:
        s = max(0.0, s)
        mm = int(s // 60); ss = int(s) % 60
        return f"{mm:02d}:{ss:02d}"

    def play_ding() -> None:
        """Play a system 'ding' on a worker thread so the timer
        callback doesn't block the frame loop."""
        def _go() -> None:
            for cand in (
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
            ):
                try:
                    subprocess.run(cand, check=False,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=5)
                    return
                except FileNotFoundError:
                    continue
                except Exception:
                    return
        threading.Thread(target=_go, daemon=True).start()

    # --- Painting ---------------------------------------------------
    def compose_and_publish() -> None:
        op = state["open_now"]
        cp = state["close_now"]
        dl = _n.DisplayList()

        # 1. Bottom half (dial + lower body) — always visible.
        dl.draw_image_file(bottom_png, 0.0, 0.0, float(WIDTH), float(HEIGHT))

        # 2. (Slider knob now painted AFTER the top image — see step
        #    4 — so the top half can't crop its upper edge.)

        # 3. Interior LCD panel (visible while open) ----------------
        if op > 0.01:
            lx, ly, lw, lh = lcd_rect()
            # Drop shadow
            dl.fill_path(_rounded_rect(lx, ly + 4, lw, lh, 14),
                          (0, 0, 0, int(120 * op)))
            # Body
            dl.fill_path(_rounded_rect(lx, ly, lw, lh, 14),
                          (24, 8, 12, int(245 * op)))
            # Inner bevel
            dl.stroke_path(_rounded_rect(lx + 1, ly + 1, lw - 2, lh - 2, 13),
                            (90, 30, 36, int(220 * op)), 1.0)
            # FOCUS pill at top of LCD (scaled to the 0.85× chassis).
            pill_w, pill_h = 76.0, 19.0
            px = BTN_CX - pill_w / 2.0
            py = ly + 9.0
            dl.fill_path(_rounded_rect(px, py, pill_w, pill_h, pill_h / 2),
                          (232, 62, 92, int(245 * op)))
            dl.draw_text("FOCUS", BTN_CX - 17.0, py + 14.0, 10.0,
                          (255, 255, 255, int(255 * op)))
            # Timer readout — live, LCD-amber.
            time_text = fmt_time(state["timer_remaining"])
            dl.draw_text(time_text, BTN_CX - 44.0, ly + 65.0, 27.0,
                          (255, 196, 124, int(255 * op)))
            # Start / Pause button.
            sx, sy, sw, sh = start_button_rect()
            start_label = "Pause" if state["timer_running"] else "Start"
            btn_col = ((230, 150, 70, int(255 * op))
                       if not state["timer_running"]
                       else (160, 90, 50, int(255 * op)))
            dl.fill_path(_rounded_rect(sx, sy, sw, sh, sh / 2), btn_col)
            dl.draw_text(start_label, sx + sw / 2 - 12, sy + sh / 2 + 4, 11.0,
                          (255, 255, 255, int(255 * op)))

        # 4. Top half — slides up by op × TOP_LIFT ------------------
        # Closed-state offset: +6 px so the top hemisphere visually
        # locks onto the bottom half (the seam between halves was
        # otherwise slightly above where the bottom's dial groove
        # implies it should be).
        closed_offset = 5.0
        top_y = closed_offset - op * (TOP_LIFT + closed_offset)
        dl.draw_image_file(top_png, 0.0, float(top_y),
                              float(WIDTH), float(HEIGHT))

        # 4b. Slider knob — painted AFTER the top image so the
        # tomato cap can't crop its upper edge. Fades out as the
        # tomato opens (the LCD takes over).
        if op < 0.7:
            slider_alpha = 1.0 - op / 0.7
            progress = 1.0 - (state["timer_remaining"] / FOCUS_DURATION_S)
            ix = GROOVE_X1 + (GROOVE_X0 - GROOVE_X1) * progress
            _paint_knob(dl, ix, GROOVE_Y, KNOB_W, KNOB_H, slider_alpha)

        # 5. Leaf-cluster stem button — rides with the top half.
        #    Artwork comes from `stem.esk` (editable in the Designer);
        #    Python only positions/scales it.
        sx, sy = stem_pos(op)
        # `bloom` matches the +10% open-state grow that the old
        # _paint_stem hard-coded — keeps the click target feeling
        # slightly larger when the tomato is fully open.
        bloom = 1.0 + 0.10 * op
        scale = (BTN_R / STEM_CANON_R) * bloom
        dl.push_transform(sx - STEM_CANON_C * scale,
                            sy - STEM_CANON_C * scale,
                            scale, scale)
        dl.extend(stem_dl_cache)
        dl.pop_transform()

        # 6. Hover-fade × close button.
        if cp > 0.01:
            half = CLOSE_SIZE / 2.0
            dl.filled_circle(CLOSE_CX, CLOSE_CY, half,
                              (250, 250, 254, int(225 * cp)))
            dl.filled_circle(CLOSE_CX, CLOSE_CY + 1, half + 1,
                              (0, 0, 0, int(45 * cp)))
            r = CLOSE_SIZE * 0.22
            stroke = (40, 40, 48, int(255 * cp))
            dl.stroke_path(
                f"M {CLOSE_CX - r} {CLOSE_CY - r} L {CLOSE_CX + r} {CLOSE_CY + r}",
                stroke, 2.2)
            dl.stroke_path(
                f"M {CLOSE_CX - r} {CLOSE_CY + r} L {CLOSE_CX + r} {CLOSE_CY - r}",
                stroke, 2.2)

        window.publish_display_list(dl)

    # --- Frame loop -------------------------------------------------
    def loop() -> None:
        last_hash = None
        # First ~60 frames (~1s) we force a republish each tick so the
        # PNG textures have time to land — Skia loads image files
        # async on first use and the very first publish can ship before
        # one of the bitmaps is ready, leaving a transparent half.
        warmup_frames = 60
        while state["running"]:
            cur = None
            try:
                if window.cursor_inside:
                    cur = window.cursor_position
            except Exception: cur = None

            # Tick the timer (real-time, regardless of frame jitter).
            now = time.monotonic()
            dt = now - state["timer_last_tick"]
            state["timer_last_tick"] = now
            if state["timer_running"]:
                state["timer_remaining"] = max(
                    0.0, state["timer_remaining"] - dt)
                if (state["timer_remaining"] <= 0.0
                        and not state["timer_done_fired"]):
                    state["timer_done_fired"] = True
                    state["timer_running"] = False
                    play_ding()

            # Close-button hover — show whenever the cursor is anywhere
            # over the pomodoro window (matches the other example apps
            # via examples/_close_button.py).
            state["close_target"] = 1.0 if cur is not None else 0.0

            # Ease animations.
            for k_now, k_tgt, step in (("open_now",  "open_target",  OPEN_STEP),
                                          ("close_now", "close_target", CLOSE_FADE)):
                tgt, cv = state[k_tgt], state[k_now]
                if abs(tgt - cv) <= step: state[k_now] = tgt
                elif tgt > cv:            state[k_now] = cv + step
                else:                     state[k_now] = cv - step

            # Press / click handling.
            try:
                pc = int(window.press_count); pressed = bool(window.mouse_pressed)
            except Exception:
                pc = state["last_press"]; pressed = False
            if pc != state["last_press"] and cur is not None:
                cx, cy = cur[0], cur[1]
                # × close
                if (state["close_now"] > 0.5
                        and CLOSE_X <= cx <= CLOSE_X + CLOSE_SIZE
                        and CLOSE_Y <= cy <= CLOSE_Y + CLOSE_SIZE):
                    state["running"] = False
                    try: app.quit()
                    except Exception: pass
                    return
                # Start / Pause button (only when open)
                if state["open_now"] > 0.6:
                    sx_, sy_, sw_, sh_ = start_button_rect()
                    if sx_ <= cx <= sx_ + sw_ and sy_ <= cy <= sy_ + sh_:
                        if state["timer_running"]:
                            state["timer_running"] = False
                        else:
                            # Reset if completed.
                            if state["timer_remaining"] <= 0.0:
                                state["timer_remaining"] = float(FOCUS_DURATION_S)
                                state["timer_done_fired"] = False
                            state["timer_running"] = True
                            state["timer_last_tick"] = time.monotonic()
                        state["last_press"] = pc
                        continue
                # Stem button toggle (open/close)
                bx, by = stem_pos(state["open_now"])
                if (cx - bx) ** 2 + (cy - by) ** 2 <= (BTN_R + 6.0) ** 2:
                    state["is_open"] = not state["is_open"]
                    state["open_target"] = 1.0 if state["is_open"] else 0.0
                else:
                    state["drag_grab"] = (cx, cy)
            state["last_press"] = pc

            # Continue dragging.
            if state["drag_grab"] is not None and pressed and cur is not None:
                gx, gy = state["drag_grab"]
                try:
                    ox, oy = window._native.outer_position
                    new_ox = int(ox + cur[0] - gx)
                    new_oy = int(oy + cur[1] - gy)
                    if (new_ox, new_oy) != (int(ox), int(oy)):
                        window.set_outer_position(new_ox, new_oy)
                except Exception: pass
            if not pressed:
                state["drag_grab"] = None

            # Republish on any animated change (or every second while
            # timer ticks, so the slider + LCD update visibly).
            h = (round(state["open_now"], 3),
                 round(state["close_now"], 3),
                 round(state["timer_remaining"], 0),
                 state["timer_running"])
            if h != last_hash or warmup_frames > 0:
                try: compose_and_publish()
                except Exception: pass
                last_hash = h
                if warmup_frames > 0:
                    warmup_frames -= 1
            time.sleep(0.016)

    def quit_on_esc() -> None:
        while state["running"]:
            ev = window.poll_key_event()
            if ev is None:
                time.sleep(0.05); continue
            code, pressed, _mods, _text = ev
            if code == "Escape" and pressed:
                state["running"] = False
                try: app.quit()
                except Exception: pass
                return

    threading.Thread(target=loop, daemon=True, name="pomodoro-loop").start()
    threading.Thread(target=quit_on_esc, daemon=True, name="pomodoro-esc").start()
    compose_and_publish()

    started = time.perf_counter()
    app.run()
    state["running"] = False
    print(f"clean exit after {time.perf_counter() - started:.2f}s")


# ---------------------------------------------------------------------
# (The previous in-Python `_paint_stem` was retired when the leaf
# cluster moved into `stem.esk` — see scripts/generate-pomodoro-stem-esk.py.
# Open that `.esk` in the Designer to recolour or reshape the leaves;
# Python no longer owns the artwork, only the live position+scale.)


def _paint_knob(dl, cx: float, cy: float, w: float, h: float,
                  alpha: float) -> None:
    """Paint one of the timer-slider end knobs — a short vertical pill
    with a dark rim, cream interior, and a glossy centre highlight."""
    half_w = w / 2.0
    half_h = h / 2.0
    # Drop shadow.
    dl.fill_path(_rounded_rect(cx - half_w + 2, cy - half_h + 3, w, h, half_w),
                  (0, 0, 0, int(150 * alpha)))
    # Dark rim.
    dl.fill_path(_rounded_rect(cx - half_w, cy - half_h, w, h, half_w),
                  (28, 12, 16, int(255 * alpha)))
    # Cream-white inner pill.
    pad = 2.0
    dl.fill_path(_rounded_rect(cx - half_w + pad, cy - half_h + pad,
                                  w - 2 * pad, h - 2 * pad, half_w - pad),
                  (250, 244, 232, int(255 * alpha)))
    # Centre highlight band — small bright pill on top of the cream
    # for the glossy 3D look.
    band_h = max(4.0, h * 0.18)
    dl.fill_path(_rounded_rect(cx - half_w + 3, cy - band_h / 2.0,
                                  w - 6, band_h, band_h / 2.0),
                  (255, 255, 251, int(225 * alpha)))


def _rounded_rect(x: float, y: float, w: float, h: float, r: float) -> str:
    return (f"M {x + r} {y} L {x + w - r} {y} "
              f"Q {x + w} {y} {x + w} {y + r} "
              f"L {x + w} {y + h - r} "
              f"Q {x + w} {y + h} {x + w - r} {y + h} "
              f"L {x + r} {y + h} "
              f"Q {x} {y + h} {x} {y + h - r} "
              f"L {x} {y + r} Q {x} {y} {x + r} {y} Z")


if __name__ == "__main__":
    main()
