"""Prepare the Pomodoro assets:

  tomato-top.png       — top half of the tomato (above the dial groove)
  tomato-bottom.png    — bottom half (the dial ring + lower body)
  tomato-timer-1x.png  — closed-state composite (for the demo screenshot)

The split is at the dial-groove line so the animation can hinge the
"top of the tomato" upward (clam-open) and reveal a hollow interior
without splitting through the dial mechanism itself.

Re-derives everything from the originally-knocked-out source so green
leaves + dial markings are preserved this time. White cream-band
pixels in the bottom half are kept transparent (the user wanted them
gone) but the actual red/green structure of the tomato survives.
"""
from __future__ import annotations

import numpy as np
from pathlib import Path
from PIL import Image
from scipy import ndimage


SRC = Path("/Users/KenleyJacquesLamaute/ElysiumUI/examples/pomodoro/assets/tomato-timer-clean.png")
OUT_DIR = SRC.parent
# Taller canvas so the clam-open animation has room above the top
# half — at H=320 a 100-px lift pushed the leaves off-screen.
# Rendered at 408×459 *logical* — but we produce assets at 2× the
# logical size so the eventual Skia draw is a clean 1:1 device-pixel
# blit on Retina (avoids the upscale-truncation bug where rows past
# ~70% of the destination height silently drop).
W, H = 816, 918   # (480 × 540 × 0.85) × 2  — Retina-native size


def colour_mask(arr: np.ndarray) -> np.ndarray:
    """Pixels we consider 'tomato' (red body / cream dial / green leaves)
    — explicitly excludes the floor shadow's neutral grey."""
    r = arr[..., 0]; g = arr[..., 1]; b = arr[..., 2]; a = arr[..., 3]
    opaque = a > 200
    # Saturated red (the body).
    red = opaque & (r > 100) & (r > g.astype(int) + 30) & (r > b.astype(int) + 30)
    # Cream / off-white (the dial ring + numbers).
    cream = opaque & (r > 200) & (g > 180) & (b > 170)
    # Green (the stem + any visible leaves).
    green = opaque & (g > 80) & (g > r.astype(int) + 10) & (g > b.astype(int) + 10)
    return red | cream | green


def cleanup(arr: np.ndarray) -> np.ndarray:
    """Connected-component cleanup — keep only the largest opaque blob
    so the floor shadow gets dropped even if some of its pixels meet
    the colour criteria."""
    mask = colour_mask(arr)
    lbl, _ = ndimage.label(mask)
    if lbl.max() == 0:
        return arr
    sizes = ndimage.sum_labels(mask.astype(int), lbl, range(1, lbl.max() + 1))
    biggest = 1 + int(np.argmax(sizes))
    keep = ndimage.binary_dilation(lbl == biggest, iterations=2)
    out = arr.copy()
    for c in range(4):
        out[..., c] = np.where(keep, arr[..., c], 0)
    return out


def main() -> None:
    src_im = Image.open(SRC).convert("RGBA")
    arr = cleanup(np.array(src_im))

    # Tomato bbox + midline.
    opaque = arr[..., 3] > 0
    ys, xs = np.where(opaque)
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    # The clam hinge is along the dial-groove line — roughly 58% from
    # the top (the groove sits below the tomato's equator because the
    # dial cap is shorter than the body).
    hinge_y = y0 + int((y1 - y0) * 0.58)
    print(f"bbox: x=[{x0},{x1}]  y=[{y0},{y1}]  hinge={hinge_y}")

    # --- Top half ---
    top = arr.copy()
    top[hinge_y:, :, 3] = 0   # zero alpha below the hinge
    top_crop = crop_and_fit(top, W, H, vertical_anchor="top")
    Image.fromarray(top_crop).save(OUT_DIR / "tomato-top.png")
    print(f"wrote tomato-top.png  ({top_crop.shape[1]}x{top_crop.shape[0]})")

    # --- Bottom half ---
    bottom = arr.copy()
    bottom[:hinge_y, :, 3] = 0    # zero alpha above the hinge
    # Also knock out white-ish pixels in the bottom (the cream dial
    # band + numbers + ticks — user wanted them transparent). The
    # criterion catches pure white (RGB≈255,255,255), cream
    # (~220,210,190) AND the JPEG-tinted pink-whites that are the
    # actual number / tick-mark pixels (RGB≈224,101,100). The latter
    # have low G,B so we test that BOTH non-red channels are
    # meaningfully above 0 — pure red has G,B≈0.
    rr, gg, bb = bottom[..., 0], bottom[..., 1], bottom[..., 2]
    brightness = ((rr.astype(int) + gg.astype(int) + bb.astype(int)) // 3)
    min_channel = np.minimum.reduce([rr, gg, bb]).astype(int)
    # Pixel is "white-derived" if it's bright enough AND both G and B
    # are above a tinted-white floor (pure red body has G,B near 0
    # so it survives).
    white = ((brightness >= 130) & (min_channel >= 75)
             & (bottom[..., 3] > 0))
    bottom[..., 3] = np.where(white, 0, bottom[..., 3])
    bottom_crop = crop_and_fit(bottom, W, H, vertical_anchor="bottom")
    Image.fromarray(bottom_crop).save(OUT_DIR / "tomato-bottom.png")
    print(f"wrote tomato-bottom.png  ({bottom_crop.shape[1]}x{bottom_crop.shape[0]})")

    # --- Closed composite (just for completeness) ---
    composite = top.copy()
    composite[hinge_y:, :, :] = arr[hinge_y:, :, :]
    composite[hinge_y:, :, 3] = np.where(white[hinge_y:, :], 0,
                                           arr[hinge_y:, :, 3])
    closed = crop_and_fit(composite, W, H, vertical_anchor="center")
    Image.fromarray(closed).save(OUT_DIR / "tomato-timer-1x.png")
    print(f"wrote tomato-timer-1x.png  ({closed.shape[1]}x{closed.shape[0]})")


def crop_and_fit(arr: np.ndarray, w: int, h: int,
                    *, vertical_anchor: str) -> np.ndarray:
    """Tight-crop the opaque content + paste into a `w`×`h` canvas.

    `vertical_anchor` controls where the cropped content lives within
    the canvas:
      "top"    → cropped content sits at the top of the canvas
                 (so an upward animation moves it OUT of frame).
      "bottom" → cropped content sits at the bottom of the canvas.
      "center" → centred (used for the closed composite preview).
    """
    opaque = arr[..., 3] > 0
    if not opaque.any():
        return np.zeros((h, w, 4), dtype=np.uint8)
    # Zero the RGB of transparent pixels so LANCZOS resampling doesn't
    # bleed their colour into the surviving alpha edges (otherwise
    # alpha=0 white-numbers ghost back in as semi-opaque whites in the
    # resized output).
    arr = arr.copy()
    arr[..., 0] = np.where(opaque, arr[..., 0], 0)
    arr[..., 1] = np.where(opaque, arr[..., 1], 0)
    arr[..., 2] = np.where(opaque, arr[..., 2], 0)
    ys, xs = np.where(opaque)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = arr[y0:y1 + 1, x0:x1 + 1, :]
    cw, ch = crop.shape[1], crop.shape[0]
    # Scale the tomato up to fill the available width nicely; the
    # canvas now has extra headroom above so the open animation can
    # lift the whole top half without clipping the leaves.
    ratio = min((w * 0.78) / cw, (h * 0.54) / ch)
    new_w = int(cw * ratio); new_h = int(ch * ratio)
    pil = Image.fromarray(crop).resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if vertical_anchor == "top":
        # Tomato top sits a third of the way down the canvas. With
        # `H=540` and a `TOP_LIFT=160`, the leaves (which sit at the
        # very top of this image) land at canvas y≈180 closed and
        # window y≈20 fully open — staying on-screen the whole time.
        ax = (w - new_w) // 2; ay = int(h * 0.35)
    elif vertical_anchor == "bottom":
        # Bottom half hugs the lower edge with a small breathing
        # margin — the dial ring + lower body need to land at the
        # window's bottom so the open animation reveals controls
        # ABOVE the dial, not floating in space.
        ax = (w - new_w) // 2; ay = h - new_h - int(h * 0.05)
    else:
        ax = (w - new_w) // 2; ay = (h - new_h) // 2
    canvas.paste(pil, (ax, ay), pil)
    return np.array(canvas)


if __name__ == "__main__":
    main()
