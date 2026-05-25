"""Offscreen render of every demo + the Designer through the framework's
own paint pipeline. Saves PNGs to /tmp/screens/ for inspection."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples/butterfly"))
sys.path.insert(0, str(ROOT / "examples/components"))

import elysium as ely
from elysium import anim, components as ui, reactive, theme as themes
from elysium._native import _native as _n
import butterfly  # type: ignore


OUT = Path("/tmp/screens")
OUT.mkdir(exist_ok=True)


def render_designer(theme_name: str = "light") -> Path:
    """Paint the Designer's current frame offscreen at logical 1280×800."""
    sys.path.insert(0, str(ROOT / "elysium-designer"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_designer_main", ROOT / "elysium-designer" / "__main__.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["_designer_main"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    themes.set_theme({"light": themes.light, "dark": themes.dark,
                      "midnight_glass": themes.midnight_glass,
                      "frost": themes.frost}[theme_name]())
    d = mod.Designer(ROOT / "examples/hello/hello.esk")
    d.theme_index.set({"light": 0, "dark": 1, "midnight_glass": 2, "frost": 3}[theme_name])

    dl = _n.DisplayList()
    d._paint(dl, None)
    layer = _n.SkiaLayer(mod.WIDTH, mod.HEIGHT)
    layer.execute(dl)
    out = OUT / f"designer_{theme_name}.png"
    out.write_bytes(bytes(layer.encode_png()))
    return out


def render_butterfly_procedural() -> Path:
    layer = _n.SkiaLayer(900, 720)
    layer.clear(0.06, 0.05, 0.09, 1.0)
    butterfly.draw(layer, 900, 720, flap_t=1.0, scale=1.0)
    out = OUT / "butterfly_procedural.png"
    out.write_bytes(bytes(layer.encode_png()))
    return out


def render_butterfly_image() -> Path | None:
    img = ROOT / "examples/butterfly/iridescentwinged_butterfly.png"
    if not img.is_file():
        return None
    layer = _n.SkiaLayer(900, 720)
    layer.clear(0.06, 0.05, 0.09, 1.0)
    # Pretend mid-flap: 70% horizontal squash.
    cx = 900 / 2.0
    img_w = 900 * 0.95 * 0.85
    img_h = 720 * 0.95
    layer.draw_image(str(img), cx - img_w / 2.0, (720 - img_h) / 2.0,
                     img_w, img_h)
    out = OUT / "butterfly_image.png"
    out.write_bytes(bytes(layer.encode_png()))
    return out


def render_components_showcase(theme_name: str) -> Path:
    import subprocess
    subprocess.run(
        [".venv/bin/python", "examples/components/showcase.py",
         "--static", f"--theme={theme_name}"],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    src = Path(f"/tmp/showcase_{theme_name}.png")
    dst = OUT / f"showcase_{theme_name}.png"
    dst.write_bytes(src.read_bytes())
    return dst


def render_hello_skin() -> Path:
    skin = ely.load_skin(str(ROOT / "examples/hello/hello.esk"))
    dl = skin.to_display_list(480, 320)
    layer = _n.SkiaLayer(480, 320)
    layer.execute(dl)
    out = OUT / "hello_skin.png"
    out.write_bytes(bytes(layer.encode_png()))
    return out


def main() -> None:
    print("Rendering every demo through the framework:")
    print(f"  {render_hello_skin()}")
    print(f"  {render_butterfly_procedural()}")
    bi = render_butterfly_image()
    if bi: print(f"  {bi}")
    for theme in ("light", "dark", "midnight_glass", "frost"):
        print(f"  {render_designer(theme)}")
        print(f"  {render_components_showcase(theme)}")
    print(f"\nAll outputs in {OUT}/")


if __name__ == "__main__":
    main()
