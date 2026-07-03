"""Image super-resolution / enhancement.

Tries `realesrgan` (Real-ESRGAN) when installed, falls back to a high-quality
PIL Lanczos upscale + light sharpening so the call always succeeds.

    from elysium.ai.enhance import enhance_image
    out = enhance_image("texture.png", scale=4)
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageFilter


_Backend = Literal["realesrgan", "pil"]


def detect_backend() -> _Backend:
    """Return the best available enhancement backend without importing the
    heavy SDK weights — checks module presence only."""
    try:
        import importlib.util as _u
        if _u.find_spec("realesrgan") is not None:
            return "realesrgan"
    except ImportError:
        pass
    return "pil"


def enhance_image(src: str | Path, *, scale: int = 4,
                  out: str | Path | None = None,
                  backend: _Backend | None = None) -> Path:
    """Upscale a single image. Returns the output path. If `out` is None
    the result lands next to the source as `<stem>@x<scale>.png`."""
    src_p = Path(src)
    if not src_p.is_file():
        raise FileNotFoundError(src_p)
    out_p = (Path(out) if out
             else src_p.with_name(f"{src_p.stem}@x{scale}.png"))
    b = backend or detect_backend()
    if b == "realesrgan":
        _enhance_realesrgan(src_p, out_p, scale)
    else:
        _enhance_pil(src_p, out_p, scale)
    return out_p


def enhance_rgba(rgba: np.ndarray, *, scale: int = 4,
                 backend: _Backend | None = None) -> np.ndarray:
    """In-memory upscale, returning a new (h*scale, w*scale, 4) uint8 array."""
    b = backend or detect_backend()
    img = Image.fromarray(rgba, mode="RGBA")
    if b == "realesrgan":
        try:
            import realesrgan, torch  # type: ignore[import-not-found]
            model = _load_realesrgan_model(scale)
            arr = np.asarray(img.convert("RGB"))
            sr, _ = model.enhance(arr, outscale=scale)
            out = Image.fromarray(sr).convert("RGBA")
        except Exception:
            out = img.resize((img.width * scale, img.height * scale),
                             Image.LANCZOS)
    else:
        out = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2))
    return np.asarray(out, dtype=np.uint8)


def _enhance_pil(src: Path, out: Path, scale: int) -> None:
    img = Image.open(src).convert("RGBA")
    up = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    up = up.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2))
    out.parent.mkdir(parents=True, exist_ok=True)
    up.save(out)


def _enhance_realesrgan(src: Path, out: Path, scale: int) -> None:
    try:
        import realesrgan, torch  # type: ignore[import-not-found]
    except ImportError:
        _enhance_pil(src, out, scale)
        return
    model = _load_realesrgan_model(scale)
    arr = np.asarray(Image.open(src).convert("RGB"))
    sr, _ = model.enhance(arr, outscale=scale)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sr).save(out)


_MODEL_CACHE: dict[int, object] = {}


def _load_realesrgan_model(scale: int):
    if scale in _MODEL_CACHE:
        return _MODEL_CACHE[scale]
    from realesrgan import RealESRGANer  # type: ignore[import-not-found]
    from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore[import-not-found]
    net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                  num_block=23, num_grow_ch=32, scale=scale)
    model = RealESRGANer(scale=scale, model_path="", model=net, half=False)
    _MODEL_CACHE[scale] = model
    return model


__all__ = ["enhance_image", "enhance_rgba", "detect_backend"]
