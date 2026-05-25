"""Synthesise a wing-flap animation from the static blue-morpho PNG.

Output: ``elysium-designer/assets/flap/00.png`` … ``elysium-designer/assets/flap/11.png``
plus ``elysium-designer/assets/flap/00.icns`` … etc. on macOS so the
icon-swap path can ship a single PNG to NSApplication and have it
render at every Dock size (16 / 32 / 128 / 256 / 512 / 1024) without
visible resampling steps.

The flap is a horizontal compression of the butterfly about the body's
vertical axis — wings fold inward and back out. 12 frames over ~500 ms
at 24 fps give a single visible flap; the cosine ease keeps the
midpoint frame the "wings closed" pose and bookends with "wings open".

Re-run any time the source art or the flap shape changes:
    .venv/bin/python scripts/generate-flap-frames.py
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "elysium-designer" / "assets" / "ElysiumDesigner.png"
OUT_DIR = REPO_ROOT / "elysium-designer" / "assets" / "flap"
N_FRAMES = 12
ICON_SIZE = 512  # 512² is plenty for Dock at @2× retina; .icns ships
                  # additional sizes if we ever wire it back in.


def _flap_factor(i: int, n: int) -> float:
    """Cosine ease: 1.0 (open) → 0.30 (closed) → 1.0 (open)."""
    t = i / max(1, n - 1)
    return 1.0 - 0.70 * (1.0 - math.cos(2.0 * math.pi * t)) / 2.0


def _flap_frame(master: Image.Image, factor: float) -> Image.Image:
    """Horizontally compress `master` by `factor` about its centre.

    `factor = 1.0` returns the master untouched. `factor = 0.3` returns
    the master squashed to 30% of its width, then centred in the
    original-size transparent canvas — wings appear folded.
    """
    w, h = master.size
    new_w = max(1, int(round(w * factor)))
    squished = master.resize((new_w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(squished, ((w - new_w) // 2, 0), squished)
    return canvas


def _write_icns(png_path: Path) -> Path | None:
    """Wrap a single PNG in an .icns container at the Dock's expected
    sizes so NSApplication.setApplicationIconImage receives one image
    that renders crisply at every dock size in one call."""
    if shutil.which("iconutil") is None:
        return None
    sizes = [
        ("icon_16x16.png",       16),
        ("icon_16x16@2x.png",    32),
        ("icon_32x32.png",       32),
        ("icon_32x32@2x.png",    64),
        ("icon_128x128.png",    128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png",    256),
        ("icon_256x256@2x.png", 512),
    ]
    icns = png_path.with_suffix(".icns")
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "f.iconset"
        iconset.mkdir()
        master = Image.open(png_path).convert("RGBA")
        for name, size in sizes:
            master.resize((size, size), Image.LANCZOS).save(
                iconset / name, "PNG")
        subprocess.check_call([
            "iconutil", "--convert", "icns",
            "--output", str(icns), str(iconset),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return icns


def main() -> int:
    if not SOURCE.is_file():
        print(f"ERROR: source icon missing: {SOURCE}", file=sys.stderr)
        print(f"Run scripts/generate-icons.py first.", file=sys.stderr)
        return 1
    master = Image.open(SOURCE).convert("RGBA")
    if master.size != (ICON_SIZE, ICON_SIZE):
        master = master.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.png"): old.unlink()
    for old in OUT_DIR.glob("*.icns"): old.unlink()
    print(f"Writing {N_FRAMES} flap frames to {OUT_DIR.relative_to(REPO_ROOT)}/")
    for i in range(N_FRAMES):
        factor = _flap_factor(i, N_FRAMES)
        frame = _flap_frame(master, factor)
        png_path = OUT_DIR / f"{i:02d}.png"
        frame.save(png_path, "PNG")
        icns_path = _write_icns(png_path)
        size_kb = png_path.stat().st_size // 1024
        ext = "+icns" if icns_path else "png-only"
        print(f"  frame {i:02d}  factor={factor:.2f}  ({size_kb} KiB)  {ext}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
