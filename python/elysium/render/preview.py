"""Offscreen skin renderer for plugin previews.

Loads a ``.esk`` directory through the native compiler, paints it into
a Skia layer at the scene's declared size, and returns a PNG byte
buffer suitable for any image viewer / Swing JLabel / VS Code WebView.

Used by the PyCharm Designer companion tool window and the VS Code
peek preview.
"""
from __future__ import annotations

import json
from pathlib import Path


def paint_skin_png(skin_path: str | Path, width: int | None = None,
                    height: int | None = None) -> bytes:
    """Render `skin_path/document.json` to a PNG. Returns the bytes.

    Width/height default to the scene's declared `size`. The render
    happens entirely offscreen via SkiaLayer — no window, no event loop.
    """
    from elysium._native import _native as _n
    path = Path(skin_path)
    doc = json.loads((path / "document.json").read_text())
    size = doc.get("root", {}).get("size", {})
    w = int(width  or size.get("w", 800))
    h = int(height or size.get("h", 600))

    skin = _n.load_skin(str(path))
    dl = skin.to_display_list(w, h)
    layer = _n.SkiaLayer(w, h)
    layer.clear(0.0, 0.0, 0.0, 0.0)
    layer.execute(dl)
    return layer.encode_png()


__all__ = ["paint_skin_png"]
