"""Adobe Photoshop `.abr` brush-set reader.

The .abr format has gone through several versions. This module
implements v1/v2 (legacy "sample" brushes) and v6+ (descriptor-based
brushes), which together cover every public .abr you'll find online:

* v1 / v2: header is two big-endian uint16s (version, count). Each
  brush is a fixed header (type, name, length, diameter, …) plus a
  bitmap (uncompressed or RLE per Photoshop's PackBits).
* v6+: outer wrapper is "8BIM" + 4cc + length, sections include
  "samp" (sample brushes, same legacy bitmap layout) and "desc"
  (descriptor-based brushes with size / hardness / spacing / etc.).

For the Phase F ship gate (≥80% fidelity on public .abr files), we
extract the stamp image + the four most-used parameters (diameter,
hardness, spacing, name) per brush. Other parameters get stuffed into
`params["abr_extra"]` so downstream tooling can introspect them
without losing data. Unknown chunk types are skipped without aborting
the whole import — partial recovery beats no import.

References:
  * Adobe File Formats Specification — Brush File Format section
  * Reverse-engineered notes from GIMP's brush importer (abr.c)
  * Public .abr dissection by Andreas Brinck (myPaint contributors)
"""
from __future__ import annotations

import io
import re
import struct
import time
from pathlib import Path

from .preset import Preset


# ---------------------------------------------------------------------
# Low-level binary helpers — big-endian everywhere (Photoshop convention).

def _u16(buf: io.BytesIO) -> int:
    b = buf.read(2)
    if len(b) < 2: return 0
    return struct.unpack(">H", b)[0]

def _u32(buf: io.BytesIO) -> int:
    b = buf.read(4)
    if len(b) < 4: return 0
    return struct.unpack(">I", b)[0]

def _i32(buf: io.BytesIO) -> int:
    b = buf.read(4)
    if len(b) < 4: return 0
    return struct.unpack(">i", b)[0]

def _f64(buf: io.BytesIO) -> float:
    b = buf.read(8)
    if len(b) < 8: return 0.0
    return struct.unpack(">d", b)[0]

def _read_pascal_unicode(buf: io.BytesIO) -> str:
    """Photoshop unicode-string convention: u32 char count then UTF-16BE
    chars (no terminator). Used for v6+ brush names."""
    n = _u32(buf)
    raw = buf.read(n * 2)
    try:
        s = raw.decode("utf-16-be").rstrip("\x00")
    except Exception:
        s = ""
    return s

def _skip_pad4(buf: io.BytesIO, read_bytes: int) -> None:
    """Photoshop blocks align to a 4-byte boundary after each variable
    section. Pad amount = (-read_bytes) mod 4."""
    pad = (-read_bytes) % 4
    if pad: buf.read(pad)


# ---------------------------------------------------------------------
# PackBits decoder — Photoshop's per-scanline RLE.

def _unpackbits(data: bytes, expected_len: int) -> bytes:
    """Photoshop PackBits: each byte n is a header; if n >= 0 the next
    n+1 bytes are literal, if n < 0 the next byte repeats -n+1 times.
    n == -128 is a no-op header."""
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < expected_len:
        h = struct.unpack("b", data[i:i+1])[0]
        i += 1
        if h >= 0:
            n = h + 1
            out += data[i:i+n]
            i += n
        elif h == -128:
            continue
        else:
            n = -h + 1
            out += data[i:i+1] * n
            i += 1
    return bytes(out[:expected_len])


# ---------------------------------------------------------------------
# v1 / v2 reader — sample brushes (legacy bitmap stamp).

def _read_brush_v1(buf: io.BytesIO, version: int) -> dict | None:
    """One brush record. Layout (v1/v2):
       u16 brush_type (1 = computed, 2 = sample)
       u32 brush_size  — bytes remaining in this brush record
       u16 misc
       u16 spacing     — 0..100 (% of diameter)
       Pascal-ASCII name (length byte + bytes, pad to 4)
       Bitmap header: u16 width, u16 height, u16 depth, u16 mode_bit?
                       i32 top, i32 left, i32 bottom, i32 right
                       u16 compression (0=raw, 1=RLE)
       Bitmap data.
    """
    pos0 = buf.tell()
    brush_type = _u16(buf)
    brush_size = _u32(buf)
    if brush_size == 0:
        return None
    record_end = buf.tell() + brush_size
    misc = _u16(buf)  # noqa
    spacing = _u16(buf)
    # Pascal ASCII name (1-byte length + bytes), but pad to 4-byte
    # boundary AFTER the length+name bytes.
    name_len_b = buf.read(1)
    name_len = name_len_b[0] if name_len_b else 0
    name_bytes = buf.read(name_len)
    try:    name = name_bytes.decode("latin-1", errors="ignore")
    except: name = ""
    _skip_pad4(buf, 1 + name_len)
    # Computed brush — small param block, no bitmap. v1 stores 6
    # int16s (diameter, roundness, angle, hardness, etc.). Skip
    # gracefully and just record the params.
    if brush_type == 1:
        diameter = _u16(buf)
        # Other fields — pull what we can but tolerate ragged endings.
        try:
            roundness = _u16(buf); angle = _u16(buf)
            hardness  = _u16(buf); spacing2 = _u16(buf)
        except Exception:
            roundness = angle = hardness = spacing2 = 0
        buf.seek(record_end)
        return {
            "name": name, "type": "computed",
            "diameter": diameter, "spacing": spacing or spacing2 or 25,
            "hardness": hardness, "roundness": roundness, "angle": angle,
            "bitmap": None,
        }
    # Sample brush — bitmap follows.
    try:
        w = _u16(buf); h = _u16(buf); depth = _u16(buf); mode = _u16(buf)
        top = _i32(buf); left = _i32(buf); bottom = _i32(buf); right = _i32(buf)
        compression = _u16(buf)
    except Exception:
        buf.seek(record_end)
        return None
    bw = max(0, right - left)
    bh = max(0, bottom - top)
    if bw == 0 or bh == 0:
        buf.seek(record_end)
        return {"name": name, "type": "sample",
                "diameter": max(w, h), "spacing": spacing or 25,
                "bitmap": None}
    bytes_per_pixel = max(1, depth // 8)
    bitmap_bytes_expected = bw * bh * bytes_per_pixel
    raw = buf.read(record_end - buf.tell())
    bitmap = _unpackbits(raw, bitmap_bytes_expected) if compression else raw[:bitmap_bytes_expected]
    return {
        "name": name, "type": "sample",
        "diameter": max(bw, bh), "spacing": spacing or 25,
        "hardness": 0, "bitmap": bitmap, "bw": bw, "bh": bh,
        "depth": depth,
    }


def _read_v1_set(buf: io.BytesIO, version: int, count: int) -> list[dict]:
    out = []
    for _ in range(count):
        try:
            rec = _read_brush_v1(buf, version)
        except Exception:
            break
        if rec is None:
            break
        out.append(rec)
    return out


# ---------------------------------------------------------------------
# v6+ reader — descriptor-based.
# Outer chunks are "8BIM" + 4-char-code + u32 length + payload.

def _read_v6_set(data: bytes) -> list[dict]:
    """Walk the file scanning for "8BIM" markers. Brushes can live in
    either a "samp" chunk (legacy sample brush) or a "desc" chunk
    (descriptor-driven). We extract whichever we can recognise; the
    rest is logged and skipped."""
    out: list[dict] = []
    buf = io.BytesIO(data)
    # Skip the v6 header: u16 version, u16 sub-version.
    buf.seek(0)
    _u16(buf); _u16(buf)
    # Iterate "8BIM" + 4cc + u32 length blocks.
    while True:
        sig = buf.read(4)
        if len(sig) < 4: break
        if sig != b"8BIM":
            # Drift past a non-marker byte — try again one byte later.
            buf.seek(buf.tell() - 3)
            continue
        fourcc = buf.read(4)
        length = _u32(buf)
        if length == 0 or length > len(data):
            break
        payload = buf.read(length)
        _skip_pad4(buf, length)
        if fourcc == b"samp":
            # Sample brushes inside a v6 container — same body as v2
            # but no leading version/count header.
            inner = io.BytesIO(payload)
            while inner.tell() < len(payload) - 4:
                rec = _read_brush_v1(inner, version=2)
                if rec is None: break
                out.append(rec)
        elif fourcc == b"desc":
            # Descriptor block — parse the common fields. The
            # descriptor structure is recursive + complex; we extract
            # by SCANNING for known key 4cc tokens rather than walking
            # the full grammar. Practical, robust, fits the ship gate.
            rec = _scan_descriptor(payload)
            if rec: out.append(rec)
        # else: skip unknown chunk type
    return out


_DESC_KEY_PATTERNS = {
    "name":     re.compile(b"Nm  " b".", re.DOTALL),       # b"Nm  " then unicode count
    "diameter": re.compile(b"Dmtr"),
    "hardness": re.compile(b"Hrdn"),
    "spacing":  re.compile(b"Spcn"),
    "angle":    re.compile(b"Angl"),
    "roundness": re.compile(b"Rndn"),
    "use_sample_size": re.compile(b"useT"),
}

def _scan_descriptor(payload: bytes) -> dict | None:
    """Best-effort key-value extraction from a v6+ descriptor block.
    Returns a dict with whatever fields we recognized; missing ones
    fall back to engine defaults at preset-build time."""
    rec: dict = {"name": "", "type": "descriptor", "diameter": 0,
                  "hardness": 0, "spacing": 25,
                  "angle": 0, "roundness": 100, "bitmap": None}
    # Name token: "Nm  " key then a unicode string after the
    # immediately-following "TEXT" type tag (4 bytes) + uint32 length
    # + UTF-16BE chars. Be tolerant of layout drift — just scan.
    nm_idx = payload.find(b"Nm  ")
    if nm_idx >= 0:
        sub = io.BytesIO(payload[nm_idx + 4:])
        type_tag = sub.read(4)  # expect b"TEXT"
        if type_tag == b"TEXT":
            name = _read_pascal_unicode(sub)
            if name: rec["name"] = name
    # Numeric tokens. Each follows the pattern "<4cc><type_tag>...":
    #   "doub" → 8-byte big-endian float64
    #   "long" → 4-byte int32
    #   "UntF" → uint32 unit-4cc + 8-byte float64 (used for diameter)
    for key, tok in (("diameter", b"Dmtr"),
                      ("hardness", b"Hrdn"),
                      ("spacing",  b"Spcn"),
                      ("angle",    b"Angl"),
                      ("roundness", b"Rndn")):
        idx = payload.find(tok)
        if idx < 0: continue
        sub = io.BytesIO(payload[idx + 4:])
        type_tag = sub.read(4)
        if type_tag == b"doub":
            rec[key] = float(_f64(sub))
        elif type_tag == b"long":
            rec[key] = int(_i32(sub))
        elif type_tag == b"UntF":
            sub.read(4)  # unit fourcc (#Pxl / #Prc / #Ang)
            rec[key] = float(_f64(sub))
    return rec if (rec["diameter"] or rec["name"]) else None


# ---------------------------------------------------------------------
# Bitmap → PNG conversion.

def _stamp_to_png_bytes(bitmap: bytes, w: int, h: int, depth: int) -> bytes | None:
    """Convert a Photoshop sample-brush bitmap (8-bit grayscale or
    16-bit grayscale; depth in bits) into RGBA PNG bytes. Returns
    None on failure (e.g. PIL missing). Black pixels become opaque
    black; white becomes transparent — matches Photoshop convention
    where the stamp ENCODES the alpha mask, not RGB."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if depth == 16:
        try:
            import numpy as np
            arr = np.frombuffer(bitmap, dtype=">u2").astype(np.float32) / 65535.0
        except ImportError:
            return None
    else:
        try:
            import numpy as np
            arr = np.frombuffer(bitmap, dtype=np.uint8).astype(np.float32) / 255.0
        except ImportError:
            return None
    arr = arr.reshape(h, w)
    # Photoshop convention: black = opaque ink, white = empty canvas.
    # Convert to RGBA where alpha = (1 - intensity).
    import numpy as np
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    alpha = ((1.0 - arr).clip(0.0, 1.0) * 255.0).astype(np.uint8)
    rgba[..., 3] = alpha
    img = Image.fromarray(rgba, mode="RGBA")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


# ---------------------------------------------------------------------
# Public API.

def read_abr(src: str | Path,
              assets_dir: str | Path | None = None) -> list[Preset]:
    """Parse a .abr file into a list of Presets. Stamp images are
    extracted as PNGs into `assets_dir` (defaults to a sibling
    `abr_stamps/` next to the source) so the Pattern engine can
    consume them via `params["pattern_path"]`."""
    src = Path(src)
    if not src.is_file():
        return []
    data = src.read_bytes()
    if len(data) < 4:
        return []
    out_dir = Path(assets_dir) if assets_dir else (src.parent / "abr_stamps")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Detect version.
    version = struct.unpack(">H", data[0:2])[0]
    raw_records: list[dict] = []
    if version in (1, 2):
        buf = io.BytesIO(data)
        _u16(buf)  # version
        count = _u16(buf)
        raw_records = _read_v1_set(buf, version, count)
    elif version >= 6:
        raw_records = _read_v6_set(data)
    else:
        return []
    presets: list[Preset] = []
    src_stem = re.sub(r"[^A-Za-z0-9]+", "_", src.stem).strip("_") or "abr"
    category = f"Imported / Photoshop / {src.stem}"
    for i, rec in enumerate(raw_records):
        if not rec: continue
        name = rec.get("name") or f"{src.stem} #{i + 1}"
        # Choose an engine: pattern when a bitmap is present, round
        # stamp otherwise.
        if rec.get("bitmap"):
            stamp_path = out_dir / f"{src_stem}_{i:03d}.png"
            png = _stamp_to_png_bytes(rec["bitmap"], rec["bw"], rec["bh"],
                                       rec.get("depth", 8))
            if png:
                stamp_path.write_bytes(png)
                engine = "Pattern"
                params = {
                    "size": float(rec.get("diameter", 40) or 40),
                    "opacity": 1.0,
                    "flow": 1.0,
                    "spacing": float(rec.get("spacing", 25) or 25) / 100.0,
                    "rotation": "follow",
                    "scale_jitter": 0.0,
                    "hue_jitter": 0.0,
                    "pattern_path": str(stamp_path),
                }
            else:
                # PIL/numpy unavailable — fall back to RoundStamp.
                engine = "RoundStamp"
                params = {
                    "size": float(rec.get("diameter", 40) or 40),
                    "opacity": 1.0,
                    "hardness": float(rec.get("hardness", 50) or 50) / 100.0,
                    "flow": 1.0,
                    "spacing": float(rec.get("spacing", 25) or 25) / 100.0,
                    "jitter": 0.0,
                }
        else:
            # Computed brush (no bitmap) — round stamp with the
            # extracted hardness + spacing.
            engine = "RoundStamp"
            params = {
                "size": float(rec.get("diameter", 40) or 40),
                "opacity": 1.0,
                "hardness": float(rec.get("hardness", 50) or 50) / 100.0,
                "flow": 1.0,
                "spacing": float(rec.get("spacing", 25) or 25) / 100.0,
                "jitter": 0.0,
            }
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"brush_{i}"
        pid = f"imported.{src_stem.lower()}.{slug}"
        preset = Preset(
            id=pid, name=name, engine=engine, params=params,
            color_mode="active",
            category=category,
            tags=["imported", "photoshop", "abr"],
            source=f"imported:abr:{src.name}",
            imported_from=str(src),
            created_t=time.time(),
        )
        # Preserve every extra field we extracted but didn't map to
        # canonical params — gives downstream tooling a way to see
        # what Photoshop intended.
        extras = {k: v for k, v in rec.items()
                   if k not in ("name", "type", "bitmap", "bw", "bh", "depth",
                                  "diameter", "spacing", "hardness")}
        if extras:
            preset.params["abr_extra"] = extras
        presets.append(preset)
    return presets
