"""Phase 2.5 component-library showcase.

Renders a gallery of every polished built-in component at multiple
states (idle / hover / pressed / focused) under each of the four
built-in themes. Drops PNGs in /tmp for visual inspection AND can be
launched as a live window:

    python examples/components/showcase.py            # live window
    python examples/components/showcase.py --static   # write PNG only
    python examples/components/showcase.py --theme=midnight_glass
"""
from __future__ import annotations

import argparse
import threading
import time
from typing import Iterable

import elysium as ely
from elysium import anim, theme as themes
from elysium._native import _native as _n
from elysium.components import (
    Button, Card, IconCloseButton, Label, ProgressBar, Slider,
    Stack, TextField, Toggle,
)


WIDTH, HEIGHT = 960, 720


def build_components() -> list[tuple[str, "ely.Component", dict]]:
    """Returns (caption, component, state_to_settle) for every showcase row."""
    rows: list[tuple[str, object, dict]] = []
    # Buttons in every variant + state.
    for variant in ("solid", "outline", "ghost", "glass", "danger"):
        for label_state, state in [("idle", {}), ("hover", {"hover": True}),
                                   ("pressed", {"pressed": True}),
                                   ("focused", {"focused": True})]:
            rows.append((
                f"Button {variant} {label_state}",
                Button(w=160, h=40, label=variant.title(), variant=variant),
                state,
            ))
    # Slider variants.
    for v, s in [(0.2, {}), (0.6, {"hover": True}), (0.9, {"focused": True})]:
        rows.append((f"Slider v={v}", Slider(w=200, h=36, value=v), s))
    # Toggles.
    rows.append(("Toggle off", Toggle(w=56, h=30, value=False), {}))
    rows.append(("Toggle on",  Toggle(w=56, h=30, value=True),  {}))
    rows.append(("Toggle on hover", Toggle(w=56, h=30, value=True), {"hover": True}))
    # TextFields.
    rows.append(("TextField empty", TextField(w=240, h=48, label="Email"), {}))
    rows.append(("TextField focused",
                 TextField(w=240, h=48, label="Email"), {"focused": True}))
    rows.append(("TextField with value",
                 TextField(w=240, h=48, label="Email", value="hi@elysium.dev"), {}))
    # ProgressBars.
    rows.append(("Progress 30%", ProgressBar(w=240, h=10, value=0.30), {}))
    rows.append(("Progress 80%", ProgressBar(w=240, h=10, value=0.80), {}))
    rows.append(("Progress indeterminate",
                 ProgressBar(w=240, h=10, indeterminate=True), {}))
    return rows


def settle(component, state: dict, ticks: int = 80, dt: float = 0.02) -> None:
    """Step the component's smoother long enough to settle each state."""
    for _ in range(ticks):
        component.update(dt, state)


def paint_gallery(dl, theme_obj: themes.Theme,
                  rows: list[tuple[str, object, dict]]) -> None:
    """Lay out + paint every row in a uniform grid into the given DisplayList."""
    themes.set_theme(theme_obj)
    dl.clear_color(theme_obj.surface[0] / 255.0, theme_obj.surface[1] / 255.0,
                   theme_obj.surface[2] / 255.0, theme_obj.surface[3] / 255.0)
    # Title.
    dl.draw_text(f"Elysium UI — {theme_obj.name}", 24, 36, 22, theme_obj.on_surface)
    dl.draw_text("Phase 2.5 component library showcase", 24, 60,
                 theme_obj.font_size_body, theme_obj.on_surface_muted)

    # Grid.
    grid_x, grid_y = 24.0, 96.0
    col_w, row_h = 280.0, 80.0
    cols = 3
    for i, (caption, comp, state) in enumerate(rows):
        col = i % cols
        row = i // cols
        ox = grid_x + col * col_w
        oy = grid_y + row * row_h

        # Caption.
        dl.draw_text(caption, ox, oy + 14, theme_obj.font_size_caption,
                     theme_obj.on_surface_muted)

        # Position component centered horizontally in its cell.
        comp.x = ox + (col_w - 20 - comp.w) / 2.0
        comp.y = oy + 24
        # Settle states and paint.
        settle(comp, state)
        comp.paint(dl)


def render_static(out_path: str, theme_obj: themes.Theme) -> None:
    """Render the showcase to a PNG."""
    rows = build_components()
    dl = _n.DisplayList()
    paint_gallery(dl, theme_obj, rows)
    layer = _n.SkiaLayer(WIDTH, HEIGHT)
    layer.execute(dl)
    with open(out_path, "wb") as f:
        f.write(bytes(layer.encode_png()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Polished component showcase.")
    parser.add_argument("--theme", choices=["light", "dark", "midnight_glass", "frost"],
                        default="light")
    parser.add_argument("--static", action="store_true",
                        help="Render to /tmp/showcase.png and exit (no window).")
    args = parser.parse_args()
    theme_obj = {
        "light": themes.light, "dark": themes.dark,
        "midnight_glass": themes.midnight_glass, "frost": themes.frost,
    }[args.theme]()

    if args.static:
        out = f"/tmp/showcase_{args.theme}.png"
        render_static(out, theme_obj)
        print(f"wrote {out}")
        return

    app = ely.App(title=f"Elysium — {theme_obj.name}",
                  identifier="dev.elysium.showcase")
    win = app.window(transparent=False, title_bar=True, resizable=True,
                     initial_size=(WIDTH, HEIGHT))
    rows = build_components()

    state = {"running": True}
    clock = anim.AnimationClock()

    def on_frame():
        if not state["running"]: return
        dl = _n.DisplayList()
        paint_gallery(dl, theme_obj, rows)
        win.publish_display_list(dl)

    threading.Thread(target=lambda: (time.sleep(6.0), app.quit()), daemon=True).start()
    anim.run_animation_thread(clock, on_frame, target_hz=60.0,
                              running=lambda: state["running"])
    app.run()
    state["running"] = False


if __name__ == "__main__":
    main()
