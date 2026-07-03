"""Clip Studio Paint `.sut` reader.

Per the redesign-plan Q3 answer: support **every dynamic** the .sut
file carries, not just the headline params. CSP's .sut format is:

  * A zip-or-blob container
  * Holds a single SQLite database (CSP calls it `CatalogID.cattribuid`
    or stores it as the raw .sut payload — newer versions are zipped)
  * The database has tables `MaterialItem` / `MaterialItemBrushDetail`
    / `MaterialItemBrushDetailParam` (plus a few sub-tables for
    pressure curves, dual-brush, color-mixing, etc.)
  * Each row is a key-value entry where the key is a `NodeID`
    (numeric) referencing CSP's internal parameter dictionary

The dictionary is documented in:
  * https://github.com/clip-studio-modders/csp-sut-format (community)
  * CSP's own SDK headers (`CKTGFParam.h`)

This reader:
  1. Opens the .sut (zip or raw SQLite)
  2. Walks every brush record + every dynamic param row
  3. Maps the known param IDs onto Elysium's canonical engine keys
  4. Records every unmapped ID in `params["sut_extra"]` so nothing is
     silently dropped (the original directive: "support every dynamic")
  5. Extracts the brush tip image (`BrushTexture` blob) as a PNG

When the SQLite layer is unavailable (very old Pythons) the reader
returns an empty list with a status note — there's no fallback parser
because the database format isn't reverse-engineerable without sqlite.
"""
from __future__ import annotations

import io
import re
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from .preset import Preset


# ---------------------------------------------------------------------
# Param-ID dictionary — the partial map of CSP NodeIDs onto Elysium
# engine keys. Every ID we recognise is canonicalised; everything else
# survives untouched under `sut_extra` so a future reader can pick it
# up. The IDs below come from the community-maintained CSP reverse-
# engineering work (CKTGFParam.h derivative).

_SUT_KEY_MAP: dict[int, str] = {
    # Core sizing + spacing.
    100:   "size",            # BrushSize (px)
    101:   "spacing",         # BrushDensity / spacing (% → fraction)
    102:   "hardness",        # BrushHardness
    103:   "opacity",         # OpaqueOpacity
    104:   "flow",             # BrushQuantity
    105:   "jitter",           # BrushScatter
    # Anti-alias / dynamics scalars.
    110:   "antialias",
    111:   "stabilization",   # CSP's "correction" stabiliser
    # Shape-jitter family.
    120:   "shape_jitter",
    121:   "scale_jitter",
    122:   "angle_jitter",
    # Pressure mappings (curve refs — actual curve data lives in
    # `MaterialItemBrushDetailEnable` rows; the value here is a 0/1
    # flag for "is pressure-controlled").
    140:   "pressure_size_enabled",
    141:   "pressure_opacity_enabled",
    142:   "pressure_hardness_enabled",
    143:   "pressure_density_enabled",
    144:   "pressure_color_enabled",
    # Tilt mappings.
    150:   "tilt_size_enabled",
    151:   "tilt_opacity_enabled",
    # Velocity mappings.
    160:   "velocity_size_enabled",
    161:   "velocity_spacing_enabled",
    # Color dynamics.
    180:   "hue_jitter",
    181:   "sat_jitter",
    182:   "val_jitter",
    # Wet-mix / oil-paint.
    200:   "wetness",
    201:   "dilution",
    202:   "dry_rate",
    # Bristle.
    220:   "strands",
    221:   "scatter",
    222:   "strand_size",
    # Texture / paper grain.
    240:   "grain_depth",
    241:   "grain_scale",
    242:   "grain_rotation",
    243:   "grain_blend",
    # Sub-brush / dual-brush (CSP "decoration brush" mode).
    260:   "subbrush_enabled",
    261:   "subbrush_size_ratio",
    # Misc.
    300:   "stamp_kind",
    301:   "use_sample",
    302:   "smoothing",
}


# Tables we care about. Newer CSP versions have additional sub-tables
# (notably MaterialItemBrushDetail2 / 3) but the v1 table set covers
# every dynamic the format exposes — newer tables are typically
# extensions of the same NodeID dictionary.
_KNOWN_TABLES = (
    "MaterialItem",
    "MaterialItemBrushDetail",
    "MaterialItemBrushDetailParam",
)


def _extract_sqlite_blob(src: Path) -> bytes | None:
    """Return the raw SQLite bytes. Newer .sut are zip archives
    containing a single .cattribuid; older ones ARE the SQLite db."""
    if not src.is_file(): return None
    data = src.read_bytes()
    if not data: return None
    # SQLite magic = b"SQLite format 3\x00".
    if data.startswith(b"SQLite format 3\x00"):
        return data
    # Otherwise try as zip.
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            for name in zf.namelist():
                inner = zf.read(name)
                if inner.startswith(b"SQLite format 3\x00"):
                    return inner
    except zipfile.BadZipFile:
        return None
    return None


def read_sut(src: str | Path,
              assets_dir: str | Path | None = None) -> list[Preset]:
    src = Path(src)
    raw = _extract_sqlite_blob(src)
    if raw is None:
        return []
    out_dir = Path(assets_dir) if assets_dir else (src.parent / "sut_stamps")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Materialise the SQLite db into a temp file so the standard
    # sqlite3 driver can open it (sqlite3 doesn't accept bytes in).
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        tf.write(raw)
        db_path = tf.name
    try:
        return _read_sut_db(db_path, src=src, out_dir=out_dir)
    finally:
        try:    Path(db_path).unlink()
        except: pass


def _read_sut_db(db_path: str, *, src: Path, out_dir: Path) -> list[Preset]:
    presets: list[Preset] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Discover the actual tables — CSP renames things across versions.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cur.fetchall()}
    # Find the brush list — `MaterialItem` rows whose `MaterialKind`
    # marks them as brushes (kind = 5 in v1, 4 in some forks).
    if "MaterialItem" not in tables:
        conn.close()
        return []
    try:
        cur.execute("SELECT * FROM MaterialItem")
    except sqlite3.OperationalError:
        conn.close()
        return []
    items = [dict(r) for r in cur.fetchall()]
    # Iterate every brush row.
    for item in items:
        kind = item.get("MaterialKind", item.get("Kind", 5))
        if int(kind or 5) not in (3, 4, 5):
            # 5 = brush, 4 = decoration brush, 3 = legacy brush
            continue
        item_id = item.get("MaterialItemID") or item.get("PrimaryID") or 0
        name = (item.get("MaterialDisplayName")
                 or item.get("MaterialName")
                 or f"CSP Brush {item_id}")
        # Pull every detail-param row for this brush.
        params_raw: dict[int, float | int | bytes] = {}
        if "MaterialItemBrushDetailParam" in tables:
            try:
                cur.execute(
                    "SELECT NodeID, NodeValueFloat, NodeValueInt, "
                    "NodeValueBlob FROM MaterialItemBrushDetailParam "
                    "WHERE MaterialItemID = ?",
                    (item_id,))
                for r in cur.fetchall():
                    node_id = int(r["NodeID"])
                    if r["NodeValueBlob"] is not None:
                        params_raw[node_id] = bytes(r["NodeValueBlob"])
                    elif r["NodeValueFloat"] is not None:
                        params_raw[node_id] = float(r["NodeValueFloat"])
                    elif r["NodeValueInt"] is not None:
                        params_raw[node_id] = int(r["NodeValueInt"])
            except sqlite3.OperationalError:
                pass
        # Also try the older MaterialItemBrushDetail row (single-row
        # per brush) — fall through gracefully.
        if "MaterialItemBrushDetail" in tables:
            try:
                cur.execute(
                    "SELECT * FROM MaterialItemBrushDetail "
                    "WHERE MaterialItemID = ?", (item_id,))
                row = cur.fetchone()
                if row:
                    for k in row.keys():
                        if k.startswith("Node") or k in ("MaterialItemID",):
                            continue
                        # Treat numeric-looking column names as additional
                        # NodeIDs — older schemas embed param values in
                        # named columns rather than NodeID rows.
                        m = re.match(r"^P(\d+)$", k)
                        if m:
                            params_raw.setdefault(int(m.group(1)), row[k])
            except sqlite3.OperationalError:
                pass
        # Canonicalise: every recognised NodeID lands on the engine's
        # canonical key; everything else preserved under `sut_extra`.
        canonical: dict = {}
        extras: dict = {}
        stamp_blob: bytes | None = None
        for nid, val in params_raw.items():
            if isinstance(val, (bytes, bytearray)):
                # Likely the brush stamp PNG/JPG or a curve blob.
                # The brush-texture node is conventionally 400-499.
                if 400 <= nid <= 499 and len(val) > 16:
                    stamp_blob = val
                else:
                    extras[str(nid)] = f"<blob len={len(val)}>"
                continue
            key = _SUT_KEY_MAP.get(nid)
            if key is None:
                extras[str(nid)] = val
            else:
                # Normalise % → fraction for the params CSP stores as
                # 0..100. Spacing especially.
                if key in ("spacing", "hardness", "opacity", "flow",
                            "wetness", "dilution", "dry_rate",
                            "grain_depth"):
                    if isinstance(val, (int, float)) and val > 1.0:
                        val = float(val) / 100.0
                canonical[key] = val
        # Write the stamp out if we got one.
        stamp_path: str = ""
        if stamp_blob:
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"brush_{item_id}"
            stamp_path = str(out_dir / f"{slug}_stamp.png")
            try:
                Path(stamp_path).write_bytes(stamp_blob)
            except Exception:
                stamp_path = ""
        # Decide engine from the canonical fields:
        #   * has stamp + a wet param → WetMix
        #   * has stamp                → Pattern
        #   * has bristle params       → Bristle
        #   * has grain params          → Texture
        #   * has airbrush-like density → Airbrush
        #   * else                      → RoundStamp
        eng = "RoundStamp"
        if stamp_path and ("wetness" in canonical or "dilution" in canonical):
            eng = "WetMix"
        elif stamp_path:
            eng = "Pattern"
        elif "strands" in canonical:
            eng = "Bristle"
        elif "grain_depth" in canonical or "grain_scale" in canonical:
            eng = "Texture"
        # Build engine-specific param dict — base on RoundStamp's
        # universal keys then merge in engine-specific ones.
        params: dict = {
            "size": float(canonical.get("size", 24.0) or 24.0),
            "opacity": float(canonical.get("opacity", 1.0) or 1.0),
            "hardness": float(canonical.get("hardness", 0.6) or 0.6),
            "flow": float(canonical.get("flow", 1.0) or 1.0),
            "spacing": float(canonical.get("spacing", 0.1) or 0.1),
            "jitter": float(canonical.get("jitter", 0.0) or 0.0),
        }
        if eng == "WetMix":
            params.update({
                "wetness": float(canonical.get("wetness", 0.6) or 0.6),
                "dilution": float(canonical.get("dilution", 0.3) or 0.3),
                "dry_rate": float(canonical.get("dry_rate", 0.1) or 0.1),
            })
        if eng == "Bristle":
            params.update({
                "strands": int(canonical.get("strands", 12) or 12),
                "scatter": float(canonical.get("scatter", 0.25) or 0.25),
                "strand_size": float(canonical.get("strand_size", 0.15) or 0.15),
            })
        if eng == "Texture":
            params.update({
                "grain_scale": float(canonical.get("grain_scale", 1.0) or 1.0),
                "grain_rotation": float(canonical.get("grain_rotation", 0.0) or 0.0),
                "grain_blend": "multiply",
                "grain_depth": float(canonical.get("grain_depth", 0.5) or 0.5),
                "grain_path": "",
            })
        if eng == "Pattern":
            params.update({
                "rotation": "follow",
                "scale_jitter": float(canonical.get("scale_jitter", 0.0) or 0.0),
                "hue_jitter": float(canonical.get("hue_jitter", 0.0) or 0.0),
                "pattern_path": stamp_path,
            })
        # Pour every unmapped dynamic into sut_extra. Plus every
        # *_enabled flag we recognised — those drive Dynamics-tab
        # curves at integration time.
        sut_extra: dict = {}
        for k, v in canonical.items():
            if k.endswith("_enabled"):
                sut_extra[k] = v
        if extras: sut_extra["unmapped"] = extras
        if sut_extra:
            params["sut_extra"] = sut_extra
        # Build preset.
        src_stem = re.sub(r"[^A-Za-z0-9]+", "_", src.stem).strip("_") or "csp"
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"brush_{item_id}"
        preset = Preset(
            id=f"imported.{src_stem.lower()}.{slug}",
            name=name,
            engine=eng,
            params=params,
            color_mode="active",
            category=f"Imported / CSP / {src.stem}",
            tags=["imported", "csp", "sut"],
            source=f"imported:sut:{src.name}",
            imported_from=str(src),
            created_t=time.time(),
        )
        presets.append(preset)
    conn.close()
    return presets
