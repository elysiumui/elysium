"""Flood-fill the four corners of a product photo to make its white
background transparent — keeps interior white pixels (LCD screens,
tick marks, etc.) intact because they aren't connected to the corner
seeds. The borderless demo windows can then display the bare object
floating without a paper-rect halo.

Usage:
    .venv/bin/python scripts/knockout-photo-bg.py INPUT.png OUTPUT.png
"""
from __future__ import annotations

import sys
from collections import deque
from PIL import Image


def knockout(src_path: str, dst_path: str, *, threshold: int = 180,
              feather: int = 2) -> None:
    im = Image.open(src_path).convert("RGBA")
    w, h = im.size
    px = im.load()

    # Identify candidate background pixels by R+G+B brightness +
    # neutral chroma — bright AND close-to-grey.
    def is_bg(x, y) -> bool:
        r, g, b, _a = px[x, y]
        if min(r, g, b) < threshold:
            return False
        spread = max(r, g, b) - min(r, g, b)
        return spread < 25

    # Multi-source BFS from EVERY edge pixel that already qualifies as
    # background. Seeding only from the four corners misses cases where
    # one corner sits inside a soft drop-shadow and fails the is_bg
    # check — the rest of that side then never enters the BFS frontier.
    seen = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                queue.append((x, y)); seen[y * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                queue.append((x, y)); seen[y * w + x] = 1
    while queue:
        x, y = queue.popleft()
        px[x, y] = (255, 255, 255, 0)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                if is_bg(nx, ny):
                    seen[ny * w + nx] = 1
                    queue.append((nx, ny))

    # Feather: along the just-cleared edge, soften surviving white
    # pixels' alpha so the object's silhouette doesn't paint a hard
    # white halo.
    if feather > 0:
        for _ in range(feather):
            kill: list[tuple[int, int]] = []
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if a == 0:
                        continue
                    if r + g + b < (threshold - 10) * 3:
                        continue
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] == 0:
                            kill.append((x, y))
                            break
            for x, y in kill:
                r, g, b, a = px[x, y]
                px[x, y] = (r, g, b, max(0, a - 96))

    im.save(dst_path, "PNG")
    print(f"  wrote {dst_path}  ({Image.open(dst_path).size})")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    knockout(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
