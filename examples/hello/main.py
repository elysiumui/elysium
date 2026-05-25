"""Phase 1 hello: load examples/hello/hello.esk from disk, render it
through the full pipeline, run for 3 s, exit cleanly.

This is the spec's §7.1 hello-world reduced to first principles. The
.esk file is the source of truth for visual layout; this Python file
only wires behaviour (click handlers).

Run with `python examples/hello/main.py`. First launch is slow (~30 s)
while macOS Gatekeeper inspects the freshly-built .so; subsequent runs
start in ~150 ms.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import elysium as ely


def main() -> None:
    skin_path = str(Path(__file__).parent / "hello.esk")

    app = ely.App(title="Hello, Elysium", identifier="dev.elysium.hello")
    # Borderless showcase: transparent surface + no OS title bar so the
    # rounded card *is* the whole visible app silhouette. Dropping the
    # OS rect shadow keeps the rounded shape from revealing its
    # bounding box.
    window = app.window(
        transparent=True,
        title_bar=False,
        resizable=True,
        initial_size=(480, 320),
    )
    try: window.set_has_shadow(False)
    except Exception: pass
    window.load_skin(skin_path)

    @window.on("greeting_button.click")
    def say_hello(event):
        print(f"click! event={event}", flush=True)

    # Borderless windows have no OS close button. Wire Esc as a
    # fallback + install a custom hover-fade × button in the
    # top-right corner.
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
    install_close_button(app, window, skin_path, width=480, height=320)

    started = time.perf_counter()
    app.run()
    print(f"clean exit after {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
