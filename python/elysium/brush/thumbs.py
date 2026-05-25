"""HD preset thumbnails.

Each builtin preset renders a small sample stroke into a 128×64 PNG
that the Library modal's preview pane displays. Thumbnails live next
to the preset JSON in the user brushes dir (``thumbnail`` field of
the Preset references it).

This is a one-shot offline render — the thumbnails are baked once and
shipped in `python/elysium/brush/builtin/thumbs/`. The user-dir seed
on first launch copies them alongside the preset JSONs.
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Iterable

from .preset import Preset, load_preset
from .engine import get_engine, apply_dynamics


THUMB_W = 128
THUMB_H = 64


def _bg_color(preset: Preset) -> tuple[int, int, int]:
    """Pick a thumbnail background tinted by the preset's category so
    Ink / Wet Media / Bristle / etc. read at a glance in the Library
    grid."""
    cat = (preset.category or "").lower()
    if "ink" in cat:      return (245, 244, 240)
    if "wet" in cat:      return (235, 240, 248)
    if "bristle" in cat:  return (240, 234, 226)
    if "airbrush" in cat: return (242, 242, 245)
    if "pattern" in cat:  return (238, 246, 240)
    if "dry"  in cat or "pencil" in cat: return (244, 242, 232)
    if "special" in cat:  return (250, 245, 226)
    return (242, 242, 242)


def render_thumbnail(preset: Preset, *,
                       width: int = THUMB_W,
                       height: int = THUMB_H,
                       stroke_color: tuple[int, int, int, int] = (40, 40, 40, 255),
                       ) -> bytes | None:
    """Render a single preset to a PNG byte string. Uses the real
    engine's stamp/stroke methods, so the thumbnail looks like an
    actual stroke from this brush.

    The sample stroke is a sinusoidal arc spanning the width, with
    velocity-based pressure (0.3 at the start → 1.0 in the middle →
    0.3 at the end) so any pressure-driven dynamics show up in the
    preview."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    try:
        from elysium.render.texture import PaintMask
    except Exception:
        return None
    engine = get_engine(preset.engine)
    if engine is None:
        return None
    # Build the base param dict the way the live brush would.
    params = engine.defaults()
    for k, v in (preset.params or {}).items():
        if k in params: params[k] = v
    params["color"] = stroke_color
    mask = PaintMask(int(width), int(height))
    # Sinusoidal arc — 32 samples across the width.
    samples = 32
    prev_xy = None
    for i in range(samples):
        f = i / max(1, samples - 1)
        # x sweeps left → right; y wobbles around the middle.
        sx = 8 + f * (width - 16)
        sy = height / 2 + math.sin(f * math.pi * 2.0) * (height * 0.22)
        # Pressure curve: low at ends, full in the middle.
        pressure = math.sin(f * math.pi) * 0.7 + 0.3
        live = apply_dynamics(params,
                               preset.dynamics if preset.dynamics else None,
                               pressure=pressure, velocity=0.5)
        if prev_xy is None:
            engine.stamp(mask, sx, sy, live, erase=False)
        else:
            engine.stroke(mask, prev_xy[0], prev_xy[1], sx, sy, live,
                           erase=False)
        prev_xy = (sx, sy)
    # PaintMask returns a PNG directly (its to_bytes is sparse RLE,
    # not WxHx4). Decode the PNG → RGBA → composite over the
    # category-tinted background.
    try:
        stroke_png = mask.to_png_bytes()
        stroke_img = Image.open(io.BytesIO(stroke_png)).convert("RGBA")
    except Exception:
        return None
    arr = np.array(stroke_img, dtype=np.uint8)
    if arr.shape[0] != height or arr.shape[1] != width:
        # PaintMask should hand us a width×height image, but stay
        # defensive in case future versions resize internally.
        stroke_img = stroke_img.resize((width, height))
        arr = np.array(stroke_img, dtype=np.uint8)
    bg_r, bg_g, bg_b = _bg_color(preset)
    bg = np.zeros((height, width, 4), dtype=np.uint8)
    bg[..., 0] = bg_r; bg[..., 1] = bg_g
    bg[..., 2] = bg_b; bg[..., 3] = 255
    alpha = arr[..., 3:4].astype(np.float32) / 255.0
    fg = arr[..., :3].astype(np.float32)
    out = bg[..., :3].astype(np.float32) * (1.0 - alpha) + fg * alpha
    bg[..., :3] = out.clip(0, 255).astype(np.uint8)
    img = Image.fromarray(bg, mode="RGBA")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


def render_all_builtins(*, out_dir: Path | None = None,
                          presets: Iterable[Preset] | None = None
                          ) -> list[Path]:
    """Render thumbnails for every builtin preset, write them as PNGs
    in `out_dir` (default `python/elysium/brush/builtin/thumbs/`).
    Each preset's JSON's `thumbnail` field is updated to point at the
    new file (path relative to the preset)."""
    if out_dir is None:
        out_dir = Path(__file__).resolve().parent / "builtin" / "thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)
    if presets is None:
        builtin_dir = Path(__file__).resolve().parent / "builtin"
        presets = []
        for p in sorted(builtin_dir.glob("*.json")):
            pres = load_preset(p)
            if pres: presets.append(pres)
    written: list[Path] = []
    import json
    for preset in presets:
        png = render_thumbnail(preset)
        if png is None:
            continue
        slug = preset.id.replace(".", "_")
        dst = out_dir / f"{slug}.png"
        dst.write_bytes(png)
        written.append(dst)
        # Patch the preset JSON to record the thumbnail path
        # (relative to the preset file so the on-disk copy survives
        # a user moving the brush dir).
        if preset._path:
            try:
                with open(preset._path) as f:
                    data = json.load(f)
                data["thumbnail"] = f"thumbs/{dst.name}"
                with open(preset._path, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
    return written


if __name__ == "__main__":
    # `python -m elysium.brush.thumbs` regenerates every builtin thumb.
    written = render_all_builtins()
    print(f"wrote {len(written)} thumbnail(s)")
