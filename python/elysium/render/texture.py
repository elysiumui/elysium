"""Texture Extractor & Painter.

  • Loads an image (PNG / JPG / WebP / BMP via PIL).
  • Turns any rectangular crop into a seamless tileable texture using a
    classic "wrap-shift + edge feather" algorithm. Edges blend with their
    opposite sides, eliminating visible seams when the texture is tiled.
  • Image adjustments (brightness, contrast, saturation, denoise).
  • Renders a tiled, scaled, rotated, tinted, optionally-blended fill into
    a target bounding box — used by the Designer to paint a textured
    surface on any placement.
  • Persists the user's texture library in `~/.elysium/textures/`.
"""
from __future__ import annotations

import math
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


# --- I/O ------------------------------------------------------------------

LIBRARY_DIR = Path(os.path.expanduser("~/.elysium/textures"))
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def load_rgba(path: str | Path) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    return np.asarray(img, dtype=np.uint8).copy()


def save_rgba(rgba: np.ndarray, path: str | Path) -> None:
    Image.fromarray(rgba, "RGBA").save(path, format="PNG", optimize=True)


# --- Seamless tiling ------------------------------------------------------

def make_tileable(rgba: np.ndarray, blend_radius: int | None = None) -> np.ndarray:
    """Make `rgba` seamlessly tileable.

    Strategy: shift the image by (h/2, w/2) so the previously-interior pixels
    sit at the edges. Then cross-blend the shifted image with the original
    using a smooth radial "edge-feather" mask: edges blend toward the
    opposite-edge content, eliminating any visible seam when the texture is
    tiled.
    """
    h, w = rgba.shape[:2]
    if blend_radius is None:
        blend_radius = max(1, min(h, w) // 8)

    # Build a 2-D edge-feather mask: 1.0 in the interior, 0.0 at the edges,
    # linearly ramping over `blend_radius` pixels.
    y = np.arange(h, dtype=np.float32)
    x = np.arange(w, dtype=np.float32)
    fy = np.minimum(y, (h - 1) - y) / blend_radius
    fx = np.minimum(x, (w - 1) - x) / blend_radius
    fy = np.clip(fy, 0.0, 1.0)
    fx = np.clip(fx, 0.0, 1.0)
    mask = np.minimum(fy[:, None], fx[None, :])           # (h, w) ∈ [0, 1]
    # Smoothstep so the blend looks natural.
    mask = mask * mask * (3.0 - 2.0 * mask)
    mask3 = mask[..., None].astype(np.float32)

    # Roll image by half so opposite edges meet in the middle.
    shifted = np.roll(rgba, shift=(h // 2, w // 2), axis=(0, 1))

    src = rgba.astype(np.float32)
    blend = shifted.astype(np.float32)
    out = src * mask3 + blend * (1.0 - mask3)
    return np.clip(out, 0, 255).astype(np.uint8)


# --- Image adjustments ---------------------------------------------------

def adjust(rgba: np.ndarray, *,
           brightness: float = 0.0, contrast: float = 0.0,
           saturation: float = 0.0, gamma: float = 1.0) -> np.ndarray:
    """All controls in [-1.0, 1.0]; `gamma` is multiplicative (1.0 = no-op)."""
    rgb = rgba[..., :3].astype(np.float32) / 255.0
    a   = rgba[..., 3:4]
    # Brightness (additive in linear space).
    rgb = rgb + brightness * 0.5
    # Contrast around 0.5.
    rgb = (rgb - 0.5) * (1.0 + contrast) + 0.5
    # Saturation in HSV-ish (lerp toward greyscale).
    grey = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    grey = np.repeat(grey[..., None], 3, axis=-1)
    rgb = grey + (rgb - grey) * (1.0 + saturation)
    # Gamma.
    if abs(gamma - 1.0) > 1e-3:
        rgb = np.power(np.maximum(rgb, 0.0), 1.0 / gamma)
    rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    return np.concatenate([rgb, a], axis=-1)


# --- Crop helpers --------------------------------------------------------

def crop(rgba: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    H, W = rgba.shape[:2]
    x0 = max(0, x); y0 = max(0, y)
    x1 = min(W, x + w); y1 = min(H, y + h)
    return rgba[y0:y1, x0:x1].copy()


# --- Apply: tile, scale, rotate, tint, blend ----------------------------

@dataclass
class FillOptions:
    scale:    float = 1.0
    offset_x: float = 0.0      # in tile-units (fractional shift)
    offset_y: float = 0.0
    rotation: float = 0.0      # degrees
    tint:     tuple[int, int, int, int] | None = None
    blend:    str   = "normal"  # normal | multiply | overlay | screen


def apply_fill(tex_rgba: np.ndarray, w: int, h: int,
               opt: FillOptions, base_color: tuple[int, int, int, int] = (128, 128, 128, 255)
               ) -> np.ndarray:
    """Tile `tex_rgba` across an `(h, w)` canvas with scale/offset/rotation/tint,
    optionally blended over `base_color`."""
    th, tw = tex_rgba.shape[:2]
    s = max(0.05, opt.scale)
    # Build sample-coordinate grid.
    j, i = np.meshgrid(np.arange(h, dtype=np.float32),
                       np.arange(w, dtype=np.float32),
                       indexing="ij")
    cx, cy = w * 0.5, h * 0.5
    x = (i - cx) / s
    y = (j - cy) / s
    # Rotate.
    if abs(opt.rotation) > 1e-3:
        rad = math.radians(opt.rotation)
        cr, sr = math.cos(rad), math.sin(rad)
        xr = x * cr - y * sr
        yr = x * sr + y * cr
        x, y = xr, yr
    # Offset (in tile-units).
    x += opt.offset_x * tw
    y += opt.offset_y * th
    # Wrap to tile.
    u = (np.mod(x, tw)).astype(np.int32)
    v = (np.mod(y, th)).astype(np.int32)
    tile = tex_rgba[v, u]                  # (h, w, 4)

    # Blend with base.
    if opt.blend != "normal":
        base = np.broadcast_to(np.array(base_color, dtype=np.uint8),
                               tile.shape).copy()
        tile = _blend(base, tile, opt.blend)

    # Tint as multiplicative overlay (preserves detail).
    if opt.tint is not None:
        tnt = np.array(opt.tint, dtype=np.float32) / 255.0
        rgb = tile[..., :3].astype(np.float32) / 255.0
        rgb = rgb * tnt[:3]
        tile = np.concatenate([
            np.clip(rgb * 255.0, 0, 255).astype(np.uint8),
            (tile[..., 3:4].astype(np.float32) * tnt[3]).astype(np.uint8),
        ], axis=-1)
    return tile


def _blend(base: np.ndarray, layer: np.ndarray, mode: str) -> np.ndarray:
    b = base[..., :3].astype(np.float32) / 255.0
    l = layer[..., :3].astype(np.float32) / 255.0
    a = layer[..., 3:4].astype(np.float32) / 255.0
    if mode == "multiply":
        r = b * l
    elif mode == "screen":
        r = 1.0 - (1.0 - b) * (1.0 - l)
    elif mode == "overlay":
        r = np.where(b < 0.5, 2 * b * l, 1.0 - 2 * (1 - b) * (1 - l))
    else:                      # "normal" — alpha-composite
        r = l
    out = b * (1.0 - a) + r * a
    rgb = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return np.concatenate([rgb, base[..., 3:4]], axis=-1)


# --- High-level: extract texture from a file path ------------------------

def extract_from_file(src_path: str | Path, *, crop_rect: tuple[int, int, int, int] | None = None,
                      brightness: float = 0.0, contrast: float = 0.0,
                      saturation: float = 0.0,
                      tile: bool = True, name: str | None = None,
                      ) -> tuple[Path, np.ndarray]:
    """Read `src_path`, optionally crop, adjust, make seamless, save to the
    library, return (saved_path, rgba)."""
    raw = load_rgba(src_path)
    if crop_rect is not None:
        x, y, w, h = crop_rect
        raw = crop(raw, x, y, w, h)
    raw = adjust(raw, brightness=brightness, contrast=contrast,
                 saturation=saturation)
    if tile:
        raw = make_tileable(raw)
    if name is None:
        name = Path(src_path).stem
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    # Ensure uniqueness.
    base = LIBRARY_DIR / f"{safe}.png"
    i = 1
    out = base
    while out.exists():
        i += 1
        out = LIBRARY_DIR / f"{safe}-{i}.png"
    save_rgba(raw, out)
    return out, raw


def list_library() -> list[Path]:
    """All textures in the library, sorted by filename."""
    return sorted(LIBRARY_DIR.glob("*.png"))


@dataclass
class TextureLayer:
    """One layer in a texture stack. Composed bottom-up with `blend` over
    `opacity`. Each layer carries its own UV transform + tint."""
    path:     str
    scale:    float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation: float = 0.0
    tint:     tuple[int, int, int, int] | None = None
    blend:    str   = "normal"
    opacity:  float = 1.0

    def to_json(self) -> dict:
        d = {"path": self.path, "scale": self.scale,
             "offset_x": self.offset_x, "offset_y": self.offset_y,
             "rotation": self.rotation, "blend": self.blend,
             "opacity": self.opacity}
        if self.tint is not None: d["tint"] = list(self.tint)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "TextureLayer":
        t = d.get("tint")
        return cls(path=d["path"], scale=d.get("scale", 1.0),
                   offset_x=d.get("offset_x", 0.0),
                   offset_y=d.get("offset_y", 0.0),
                   rotation=d.get("rotation", 0.0),
                   tint=tuple(t) if t else None,
                   blend=d.get("blend", "normal"),
                   opacity=d.get("opacity", 1.0))


def composite_layers(layers: list[TextureLayer], w: int, h: int,
                     base_color: tuple[int, int, int, int] = (0, 0, 0, 0)
                     ) -> np.ndarray:
    """Render a stack of texture layers into an (h, w, 4) RGBA buffer.

    Bottom layer is layers[0]; each subsequent layer is composited on top
    using its blend mode, opacity, and tint."""
    accum = np.broadcast_to(np.array(base_color, dtype=np.uint8),
                            (h, w, 4)).copy()
    for L in layers:
        if not L.path:
            continue
        try:
            src = load_rgba(L.path)
        except Exception:
            continue
        opt = FillOptions(scale=L.scale, offset_x=L.offset_x,
                          offset_y=L.offset_y, rotation=L.rotation,
                          tint=L.tint, blend="normal")
        rendered = apply_fill(src, w, h, opt)
        # Apply per-layer opacity by scaling alpha then composite.
        if L.opacity < 1.0:
            a = (rendered[..., 3:4].astype(np.float32) * L.opacity).astype(np.uint8)
            rendered = np.concatenate([rendered[..., :3], a], axis=-1)
        accum = _blend(accum, rendered, L.blend)
    return accum


# --- Helper: encode an RGBA ndarray to a PNG bytes object ---------------

def rgba_to_png_bytes(rgba: np.ndarray) -> bytes:
    h, w = rgba.shape[:2]
    stride = w * 4
    raw = bytearray()
    arr = rgba.tobytes()
    for row in range(h):
        raw.append(0)
        raw.extend(arr[row * stride : (row + 1) * stride])
    compressed = zlib.compress(bytes(raw), 6)

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b""))


# --- Paint mask + brush strokes -------------------------------------------

class PaintMask:
    """Per-placement RGBA brush layer composited over a base texture.

    Strokes are accumulated into a numpy buffer with soft falloff. The
    Designer renders this on top of the texture; the buffer is serialised
    via `to_bytes()` / `from_bytes()` so it round-trips with the .esk."""

    def __init__(self, w: int, h: int) -> None:
        self.w = int(w)
        self.h = int(h)
        self.buf = np.zeros((self.h, self.w, 4), dtype=np.uint8)

    def clear(self) -> None:
        self.buf[:] = 0

    def stamp(self, x: float, y: float, radius: float,
              color: tuple[int, int, int, int], opacity: float = 1.0,
              hardness: float = 0.5, erase: bool = False) -> None:
        """Soft brush stamp centred at (x, y). 'hardness' is the fraction
        of the radius where alpha == 1; beyond that alpha falls to 0."""
        r = max(1.0, float(radius))
        x0 = max(0, int(math.floor(x - r)))
        y0 = max(0, int(math.floor(y - r)))
        x1 = min(self.w, int(math.ceil(x + r)) + 1)
        y1 = min(self.h, int(math.ceil(y + r)) + 1)
        if x0 >= x1 or y0 >= y1:
            return
        ys = np.arange(y0, y1, dtype=np.float32)[:, None]
        xs = np.arange(x0, x1, dtype=np.float32)[None, :]
        d = np.sqrt((xs - x) ** 2 + (ys - y) ** 2) / r
        h0 = max(0.0, min(0.95, float(hardness)))
        falloff = np.clip(1.0 - (d - h0) / max(1.0 - h0, 1e-3), 0.0, 1.0)
        # Smoothstep for a nicer rolloff.
        falloff = falloff * falloff * (3.0 - 2.0 * falloff)
        stamp_a = (falloff * float(opacity) * (color[3] / 255.0)).astype(np.float32)

        tile = self.buf[y0:y1, x0:x1].astype(np.float32)
        if erase:
            new_a = np.maximum(tile[..., 3] - stamp_a * 255.0, 0.0)
            tile[..., 3] = new_a
        else:
            src_rgb = np.array(color[:3], dtype=np.float32)
            dst_a = tile[..., 3:4] / 255.0
            src_a = stamp_a[..., None]
            out_a = src_a + dst_a * (1.0 - src_a)
            # Avoid div-by-zero where both source and dest are transparent.
            denom = np.maximum(out_a, 1e-6)
            out_rgb = (src_rgb[None, None, :] * src_a
                       + tile[..., :3] * dst_a * (1.0 - src_a)) / denom
            tile[..., :3] = out_rgb
            tile[..., 3:4] = out_a * 255.0
        self.buf[y0:y1, x0:x1] = np.clip(tile, 0, 255).astype(np.uint8)

    def stroke(self, x0: float, y0: float, x1: float, y1: float,
               radius: float, color: tuple[int, int, int, int],
               opacity: float = 1.0, hardness: float = 0.5,
               spacing: float = 0.25, erase: bool = False) -> None:
        """Densely stamp from (x0,y0) → (x1,y1). 'spacing' is in units of
        radius (0.25 = stamp every quarter-radius)."""
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        step = max(1.0, radius * max(0.05, spacing))
        n = max(1, int(dist / step))
        for k in range(n + 1):
            u = k / max(n, 1)
            self.stamp(x0 + dx * u, y0 + dy * u, radius, color,
                       opacity=opacity, hardness=hardness, erase=erase)

    def stamp_texture(self, x: float, y: float, radius: float,
                       tile: np.ndarray, opacity: float = 1.0,
                       hardness: float = 0.5, scale: float = 1.0,
                       tint: tuple[int, int, int, int] | None = None) -> None:
        """Soft brush stamp that samples colors from a small *tileable*
        RGBA `tile` (shape (th, tw, 4), uint8) instead of using a flat
        colour. The tile is wrapped (np.mod) over the stamp's footprint
        so seamless textures look continuous as the brush moves. Circular
        soft-falloff alpha is multiplied with the tile's own alpha so
        transparent regions of the source stay transparent."""
        r = max(1.0, float(radius))
        x0 = max(0, int(math.floor(x - r)))
        y0 = max(0, int(math.floor(y - r)))
        x1 = min(self.w, int(math.ceil(x + r)) + 1)
        y1 = min(self.h, int(math.ceil(y + r)) + 1)
        if x0 >= x1 or y0 >= y1: return
        if tile is None or tile.size == 0: return
        th, tw = tile.shape[:2]
        s = max(0.05, float(scale))
        ys = np.arange(y0, y1, dtype=np.float32)[:, None]
        xs = np.arange(x0, x1, dtype=np.float32)[None, :]
        d = np.sqrt((xs - x) ** 2 + (ys - y) ** 2) / r
        h0 = max(0.0, min(0.95, float(hardness)))
        falloff = np.clip(1.0 - (d - h0) / max(1.0 - h0, 1e-3), 0.0, 1.0)
        falloff = falloff * falloff * (3.0 - 2.0 * falloff)
        # Sample tile in placement-pixel space — anchored to (0,0) of the
        # mask so adjacent stamps line up seamlessly.
        u = (xs / s).astype(np.int32) % tw
        v = (ys / s).astype(np.int32) % th
        # Broadcast to a full grid.
        u_g = np.broadcast_to(u, (y1 - y0, x1 - x0))
        v_g = np.broadcast_to(v, (y1 - y0, x1 - x0))
        # IMPORTANT: the brush is strictly additive — the tile's alpha
        # is treated as fully opaque so transparent pixels in the
        # source never erase the underlying model. The circular brush
        # `falloff` is the only thing that softens the stamp edge.
        rgb = tile[v_g, u_g, :3].astype(np.float32)
        tile_a = np.full(rgb.shape[:2], 255.0, dtype=np.float32)
        if tint is not None:
            t = np.array(tint[:3], dtype=np.float32) / 255.0
            rgb = rgb * t[None, None, :]
            if len(tint) >= 4:
                tile_a = tile_a * (tint[3] / 255.0)
        stamp_a = (falloff * float(opacity) * (tile_a / 255.0)).astype(np.float32)
        tile_buf = self.buf[y0:y1, x0:x1].astype(np.float32)
        dst_a = tile_buf[..., 3:4] / 255.0
        src_a = stamp_a[..., None]
        out_a = src_a + dst_a * (1.0 - src_a)
        denom = np.maximum(out_a, 1e-6)
        out_rgb = (rgb * src_a + tile_buf[..., :3] * dst_a * (1.0 - src_a)) / denom
        tile_buf[..., :3] = out_rgb
        tile_buf[..., 3:4] = out_a * 255.0
        self.buf[y0:y1, x0:x1] = np.clip(tile_buf, 0, 255).astype(np.uint8)

    def stroke_texture(self, x0: float, y0: float, x1: float, y1: float,
                        radius: float, tile: np.ndarray,
                        opacity: float = 1.0, hardness: float = 0.5,
                        spacing: float = 0.25, scale: float = 1.0,
                        tint: tuple[int, int, int, int] | None = None) -> None:
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        step = max(1.0, radius * max(0.05, spacing))
        n = max(1, int(dist / step))
        for k in range(n + 1):
            u = k / max(n, 1)
            self.stamp_texture(x0 + dx * u, y0 + dy * u, radius, tile,
                                opacity=opacity, hardness=hardness,
                                scale=scale, tint=tint)

    def composite_over(self, base_rgba: np.ndarray) -> np.ndarray:
        """Return base with this mask alpha-composited on top. base must
        be (h, w, 4) of the same size."""
        if base_rgba.shape[:2] != (self.h, self.w):
            # Fall back: nearest-resample the mask to base.
            return base_rgba
        b = base_rgba.astype(np.float32)
        m = self.buf.astype(np.float32)
        m_a = m[..., 3:4] / 255.0
        b_a = b[..., 3:4] / 255.0
        out_a = m_a + b_a * (1.0 - m_a)
        denom = np.maximum(out_a, 1e-6)
        out_rgb = (m[..., :3] * m_a + b[..., :3] * b_a * (1.0 - m_a)) / denom
        out = np.concatenate([out_rgb, out_a * 255.0], axis=-1)
        return np.clip(out, 0, 255).astype(np.uint8)

    def to_png_bytes(self) -> bytes:
        return rgba_to_png_bytes(self.buf)

    def to_bytes(self) -> bytes:
        """Compressed serialisation for storing in skin JSON / .esk."""
        return zlib.compress(self.buf.tobytes(), 6)

    @classmethod
    def from_bytes(cls, data: bytes, w: int, h: int) -> "PaintMask":
        raw = zlib.decompress(data)
        mask = cls(w, h)
        mask.buf = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4).copy()
        return mask
