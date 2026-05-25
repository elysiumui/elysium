"""Aurora Clock tutorial app — renders the analog face.

Matches the docs/getting-started/aurora-clock-* chapters' visual
target: a round clockface with an iridescent aurora-green-to-violet
ring, deep blue/black recessed face, four cardinal ticks + eight
diagonal ticks, three hands (hour, minute, second), and an AURORA
wordmark. Reactive-time + animation wiring lives in the tutorial
chapters' Python code.

Run for a 3-second visual smoke test:
    python examples/aurora-clock/main.py
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import elysium as ely


def main() -> None:
    skin_path = str(Path(__file__).parent / "aurora-clock.esk")
    app = ely.App(title="Aurora Clock", identifier="dev.elysium.aurora-clock")
    # Borderless showcase — see examples/hello/main.py for the rationale.
    window = app.window(
        transparent=True, title_bar=False, resizable=True,
        initial_size=(420, 420),
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
    install_close_button(app, window, skin_path, width=420, height=420)

    started = time.perf_counter()
    app.run()
    print(f"clean exit after {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
