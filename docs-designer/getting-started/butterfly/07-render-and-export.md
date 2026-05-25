# Step 7. Render and export

Time: 5 minutes.

## Add a light

The Designer ships with a default ambient light that is enough to
preview a model but is not enough to make the iridescent normal map
sing. Add a directional light to give the wings something to catch.

Choose `Rendering > Light > Add Directional`. The Designer creates a
Light placement in the Objects tab; it does not appear visually in
the canvas (lights are invisible in the viewport) but its effect is
immediate if you are in Textured + Lit mode.

The default directional light points down and slightly forward, which
suits a butterfly facing the camera. If you want to fine-tune, select
the Light placement and rotate it with the Rotate gizmo (`E`).

## Choose a render quality

Pick a render quality preset from the Rendering > Render Quality
submenu. The four presets are:

| Preset | Samples per pixel | Best for |
|---|---|---|
| Draft (4 spp) | 4 | Live preview while you tweak |
| Preview (12 spp) | 12 | This tutorial's chapter 7 render |
| Production (64 spp) | 64 | Marketing screenshots |
| Final (256 spp) | 256 | Print, hero shots, the logo gif |

For this chapter, choose `Rendering > Render Quality > Preview (12 spp)`.
The 12 spp preset takes 4 to 6 seconds per render on most hardware
and produces a clean butterfly with crisp iridescence.

## Pick a color space

For the official logo we use sRGB output. Choose
`Rendering > Color Space > sRGB` if it is not already selected. The
other options (Linear, ACEScg, Rec.709) are useful for VFX pipelines
that color-grade the output downstream; for a standalone skin, sRGB
is the right call.

## Render

Open the View Panel toolbar (right edge of the canvas) and click the
**Render Selected** button. The selected Mesh3D placement renders at
the chosen quality and the result appears as a still image overlay in
the canvas.

You can also use the menu: `Rendering > Render Selected`.

Watch the lower-left HUD for progress. At 12 spp the bar fills in
roughly 5 seconds.

## Export a PNG

To save the render to disk, choose `File > Export > PNG`. The
Designer saves the current render at full resolution to your project
folder. By default the filename is
`butterfly_render.png`; rename it from the file dialog if you want.

This PNG is useful for documentation hero shots and for confirming the
bake looks right at the size you intend to ship.

## Export the .esk bundle

The big export is the `.esk` skin bundle. Choose
`File > Export > .esk Bundle`. The Designer:

1. Writes a fresh `manifest.json` if one does not exist.
2. Writes the current `document.json` reflecting every placement on
   the canvas.
3. Bundles the textures you baked in chapter 5 (or 6) inside
   `textures/`.
4. References the source `.3ds` and the Blue Morpho PNG (still
   external; the bundle does not copy them in, but the
   `manifest.json` records their paths).

The status bar confirms with "Exported butterfly.esk".

## Inspect the .esk on disk

Open the Assets tab and click `butterfly.esk · Reveal in Finder`.
You should see this layout:

```
butterfly.esk/
  manifest.json
  document.json
  textures/
    butterfly_albedo.png
    butterfly_normal.png
```

`manifest.json` carries the skin's metadata (id, name, version,
color space). `document.json` carries every placement on the
canvas. Together they make the bundle loadable by the framework with
a single call:

```python
import elysium as ely
app = ely.App(title="Butterfly")
win = app.window(transparent=True, title_bar=False,
                 resizable=False, initial_size=(960, 540))
win.load_skin("butterfly.esk/")
app.run()
```

The Framework Butterfly Banner tutorial walks through exactly this
in chapter 1 of its track.

## Checkpoint

You should have:

- A directional light in the scene.
- The model rendered at 12 spp Preview quality.
- A `butterfly_render.png` next to your `.esk` (or somewhere on
  disk you can find).
- An `examples/butterfly/butterfly.esk/` folder with `manifest.json`,
  `document.json`, and a `textures/` subfolder containing the two
  baked PNGs.

[Continue to chapter 8 >>](08-animate-and-ship.md)
