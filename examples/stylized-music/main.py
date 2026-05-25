"""Stylized Music tutorial app — renders the playback faceplate.

Matches the docs/getting-started/stylized-music-* chapters' visual
target: a borderless dark-violet faceplate with a gradient album-art
square on the left, track title + artist on the right, a 20-bar
equalizer visualizer, a scrubber bar (currently at ~48%), and three
playback buttons (prev / play / next). v1 is the visual shell; the
audio playback + scrubber drag-and-hit-test wiring is added in the
tutorial chapters' Python code.

Run for a 3-second visual smoke test:
    python examples/stylized-music/main.py
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import elysium as ely


def main() -> None:
    skin_path = str(Path(__file__).parent / "stylized-music.esk")
    app = ely.App(title="Stylized Music", identifier="dev.elysium.stylized-music")
    # Borderless showcase — see examples/hello/main.py for the rationale.
    window = app.window(
        transparent=True, title_bar=False, resizable=True,
        initial_size=(600, 480),
    )
    try: window.set_has_shadow(False)
    except Exception: pass
    window.load_skin(skin_path)

    def quit_on_esc():
        while True:
            ev = window.poll_key_event()
            if ev is None:
                time.sleep(0.05); continue
            code, pressed, _mods, _text = ev
            if code == "Escape" and pressed:
                app.quit(); return
    threading.Thread(target=quit_on_esc, daemon=True).start()

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from _close_button import install_close_button
    install_close_button(app, window, skin_path, width=600, height=480)

    started = time.perf_counter()
    app.run()
    print(f"clean exit after {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
