"""Owned, immutable PNG images for native material slots."""

import base64
import hashlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

MAX_SIDE = 2048
MAX_BYTES = 16 * 1024 * 1024


def _rgba(raw):
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG") or image.n_frames != 1:
                raise ValueError("Use a single PNG or JPEG image")
            if not 1 <= image.width <= MAX_SIDE or not 1 <= image.height <= MAX_SIDE:
                raise ValueError("Material images must be at most 2048 × 2048 pixels")
            return image.convert("RGBA")
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot decode material image") from exc


def import_image(path):
    source = Path(path).expanduser()
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError("Choose a PNG or JPEG image no larger than 16 MiB")
    image = _rgba(source.read_bytes())
    output = BytesIO()
    image.save(output, format="PNG")
    raw = output.getvalue()
    result = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "png_base64": base64.b64encode(raw).decode("ascii"),
    }
    pixels(result)
    return result


@lru_cache(maxsize=8)
def _decode(digest, encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid embedded material image") from exc
    if hashlib.sha256(raw).hexdigest() != digest or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Embedded material image digest or PNG data does not match")
    result = np.array(_rgba(raw), dtype=np.uint8)
    result.setflags(write=False)
    return result


def pixels(image):
    if (
        not isinstance(image, dict)
        or set(image) != {"sha256", "png_base64"}
        or not isinstance(image["sha256"], str)
        or len(image["sha256"]) != 64
        or not isinstance(image["png_base64"], str)
        or not 0 < len(image["png_base64"]) <= (MAX_BYTES * 4 // 3 + 4)
    ):
        raise ValueError("Invalid embedded material image descriptor")
    return _decode(image["sha256"], image["png_base64"])
