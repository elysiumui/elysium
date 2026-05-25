"""Generate the Designer's app icons from the blue-morpho butterfly PNG.

Inputs
------
  examples/butterfly/iridescentwinged_butterfly.png   (1536 × 1024 RGBA)

Outputs
-------
  elysium-designer/assets/ElysiumDesigner.icns        (macOS, all sizes)
  elysium-designer/assets/ElysiumDesigner.ico         (Windows, all sizes)
  elysium-designer/assets/ElysiumDesigner.png         (Linux, 1024 × 1024)

How
---
Centre-crops the source to 1024×1024, knocks out the white backdrop so
the icon reads cleanly on any wallpaper, then writes:

  * `.icns`  via the macOS `iconutil` toolchain (a temp .iconset folder
    with Apple's required sizes / @2× retina variants, then collapsed).
  * `.ico`   via Pillow's multi-resolution ICO writer.
  * `.png`   the square master, used directly on Linux + as the
    Pillow input for the `.ico`.

Re-run any time you change the source art:
    .venv/bin/python scripts/generate-icons.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "examples" / "butterfly" / "iridescentwinged_butterfly.png"
ASSETS = REPO_ROOT / "elysium-designer" / "assets"
NAME = "ElysiumDesigner"

# Apple expects these exact file names inside an .iconset folder.
MAC_SIZES: list[tuple[str, int]] = [
    ("icon_16x16.png",       16),
    ("icon_16x16@2x.png",    32),
    ("icon_32x32.png",       32),
    ("icon_32x32@2x.png",    64),
    ("icon_128x128.png",    128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png",    256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png",    512),
    ("icon_512x512@2x.png", 1024),
]

# Sizes Windows Explorer + the taskbar request from a .ico.
WIN_SIZES: list[int] = [16, 24, 32, 48, 64, 128, 256]


def _knock_out_white(im: Image.Image, threshold: int = 215) -> Image.Image:
    """Replace near-white pixels with full transparency.

    The source PNG has a white background that bleeds into the icon
    against dark wallpapers / dark mode. We threshold across R/G/B
    and zero out alpha there. Threshold is tuned so that:

      * 240 was too lax — left an antialiasing halo of "nearly white"
        pixels around the butterfly that pinned the alpha bbox to
        the full source height and made the visible butterfly small.
      * 215 catches the halo so the bbox hugs the butterfly proper,
        while staying high enough that no wing colour is misread as
        background.
    """
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                px[x, y] = (r, g, b, 0)
    return im


def _tight_bbox(im: Image.Image, alpha_threshold: int = 32) -> tuple[int, int, int, int]:
    """Bounding box of the genuinely-opaque pixels.

    `Image.getbbox()` returns the box of any alpha > 0 pixels — which
    includes the antialiased halo around the butterfly's silhouette.
    That halo can extend several pixels past the visible edge, which
    on the source image happens to reach the top + bottom rows and
    pins the bbox to the full source height. We binarise alpha by a
    threshold first so only solid-content pixels count.
    """
    alpha = im.split()[-1]
    # Solid mask: only pixels with alpha >= threshold are kept.
    solid = alpha.point(lambda a: 255 if a >= alpha_threshold else 0)
    bbox = solid.getbbox()
    if bbox is None:
        return (0, 0, im.size[0], im.size[1])
    return bbox


def _square_master(source: Path, size: int = 1024,
                      coverage: float = 0.96) -> Image.Image:
    """Crop the source to the butterfly's tight alpha bbox, then
    scale-to-fit inside the icon canvas with `coverage` as the
    fraction of the canvas filled along the butterfly's longer axis.

    `coverage = 0.96` means the butterfly fills 96% of whichever
    canvas axis matches its long side — leaving just a 2% breathing
    margin so antialiased wing edges don't paint against the canvas
    boundary. The shorter axis fills proportionally; whatever's left
    is transparent.

    The butterfly is naturally ~1.5:1 (wider than tall), so a square
    icon is shape-mismatched: we either letterbox the height
    (current — preserves wing tips) or scale-to-fill and crop wing
    tips. We use the letterbox path because losing wing tips destroys
    butterfly silhouette recognition.
    """
    src = Image.open(source).convert("RGBA")
    src = _knock_out_white(src)
    bx0, by0, bx1, by1 = _tight_bbox(src)
    src = src.crop((bx0, by0, bx1, by1))
    w, h = src.size
    # Scale so the longer axis covers `coverage` of the canvas.
    target_long = int(size * coverage)
    if w >= h:
        new_w = target_long
        new_h = int(round(h * (target_long / w)))
    else:
        new_h = target_long
        new_w = int(round(w * (target_long / h)))
    butterfly = src.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(butterfly, ((size - new_w) // 2, (size - new_h) // 2),
                  butterfly)
    return canvas


def _write_png(master: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    master.save(dest, "PNG")
    print(f"  wrote {dest.relative_to(REPO_ROOT)}  "
            f"({dest.stat().st_size // 1024} KiB)")


def _write_ico(master: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    master.save(dest, "ICO", sizes=[(s, s) for s in WIN_SIZES])
    print(f"  wrote {dest.relative_to(REPO_ROOT)}  "
            f"({dest.stat().st_size // 1024} KiB)")


def _write_icns(master: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("iconutil") is None:
        # iconutil only ships on macOS. On other OSes we still want
        # *something* at the destination path so the build script
        # can reference it, so we drop the master PNG as a stand-in
        # (Pillow can't natively author Apple's .icns container).
        print(f"  iconutil not found (non-macOS); writing PNG as "
                f"placeholder at {dest.relative_to(REPO_ROOT)}")
        master.save(dest.with_suffix(".png"), "PNG")
        return
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / f"{NAME}.iconset"
        iconset.mkdir()
        for fname, size in MAC_SIZES:
            resized = master.resize((size, size), Image.LANCZOS)
            resized.save(iconset / fname, "PNG")
        subprocess.check_call([
            "iconutil", "--convert", "icns",
            "--output", str(dest),
            str(iconset),
        ])
    print(f"  wrote {dest.relative_to(REPO_ROOT)}  "
            f"({dest.stat().st_size // 1024} KiB)")


def main() -> int:
    if not SOURCE.is_file():
        print(f"ERROR: source image missing: {SOURCE}", file=sys.stderr)
        return 1
    print(f"Building icons from {SOURCE.relative_to(REPO_ROOT)}")
    master = _square_master(SOURCE, size=1024)
    _write_png(master,  ASSETS / f"{NAME}.png")
    _write_ico(master,  ASSETS / f"{NAME}.ico")
    _write_icns(master, ASSETS / f"{NAME}.icns")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
