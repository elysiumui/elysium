"""Phase 0 demo: open a real window, Skia paints the spec's hero card,
wgpu composites at 60 FPS, exits cleanly when a worker thread fires app.quit().

This is the milestone the spec calls Phase 0.2: window opens, Skia paths +
gradient + shadow render through the wgpu compositor, clean cross-thread
shutdown via `app.quit()`.

Run with `python examples/hello/window_smoke.py`. Set
`ELYSIUM_LOG=debug` for verbose wgpu tracing. First launch may take
~30 s on a fresh build while macOS Gatekeeper inspects the new .so;
subsequent runs start in ~150 ms.
"""
from __future__ import annotations

import threading
import time

import elysium as ely


def main() -> None:
    app = ely.App(title="Elysium — hero card", identifier="dev.elysium.hero")
    app.window(
        transparent=False,
        title_bar=True,
        resizable=True,
        initial_size=(800, 560),
    )

    duration = 3.0
    threading.Thread(target=lambda: (time.sleep(duration), app.quit()), daemon=True).start()

    started = time.perf_counter()
    app.run()
    print(f"clean exit after {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
