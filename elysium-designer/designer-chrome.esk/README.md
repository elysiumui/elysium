# Designer Chrome Skin

The Elysium Designer's own chrome, authored as a `.esk` skin and
loaded into the Designer window at startup. Stage 3a of the
self-host migration (see
[`docs-designer/internals/self-host-design.md`](../../docs-designer/internals/self-host-design.md))
ships the empty scaffold; subsequent stages author the menu bar,
toolbar, shelf, toolbox, brush palette, side panels, time slider,
and Aether FAB into `document.json`.

During the migration the hand-rolled `_paint_*` methods in
[`elysium-designer/__main__.py`](../__main__.py) run side-by-side
with this skin. As each surface is authored here, the matching
paint method is removed. By Stage 3g `document.json` owns every
pixel of chrome and `__main__.py` is a pure behavior shell.

## Layout

- `manifest.json`: bundle identity.
- `document.json`: default scene tree (the "light" theme variant per
  spec §12 answer 1).
- `hooks.json`: hook declarations (auto-generated; empty until
  Stage 3b adds the first interactive element).
- `variants/high_contrast.json`: a11y variant.
- `variants/reduce_motion.json`: motion-sensitive variant.
- `assets/icons/`: toolbox + menu glyph sprite atlas (Stage 3c).
- `animations/`: named animation definitions (Stage 3g).

Edit this skin directly. There is no visual editor for it yet:
`document.json` is hand-authored JSON until the Designer's own
chrome editor is built (out of scope for the migration).
