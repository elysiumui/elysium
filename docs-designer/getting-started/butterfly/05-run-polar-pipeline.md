# Step 5. Run the Polar + Bake + Normal Map pipeline

Time: 5 minutes.

## What the pipeline does

The Polar pipeline is the first of two starred recommended workflows
in the Mesh menu. It does three things in sequence:

1. **Polar warp**: maps the Blue Morpho photo onto the Monarch's UV
   space using polar coordinates centered on the body. The wings get
   the iridescent pattern; the body stays correct.
2. **Bake**: writes the warped result as a flat albedo PNG inside your
   `.esk` folder at `textures/butterfly_albedo.png`.
3. **Normal map generation**: derives a high-frequency normal map from
   the photo's luminance, writing it to
   `textures/butterfly_normal.png`. This gives the wings their
   characteristic PBR sparkle when lit.

Polar warp is fast (about 3 seconds on an M2; about 5 on a current
Intel chip) because the math is closed-form. It also handles
non-flat butterfly wings well because the body acts as a stable
center.

## Make sure the model is selected

Click the Monarch model in the canvas (not the reference photo). It
should pick up the accent-color selection outline. The Channel Box
should show `mesh_kind = butterfly`.

If you accidentally select the photo or a landmark, the pipeline
will refuse to run with a status bar message: "Polar transfer needs
a Mesh3D selection."

## Run it

From the menu bar choose
`Mesh > Transfer Texture > Polar + Bake + Normal Map (PBR)`. The
starred entry sits near the top of the Transfer Texture submenu.

The Designer opens a small progress HUD in the lower-left corner of
the canvas:

```
Polar warp           ████████████████ 100%
Bake to atlas        ████████░░░░░░░░  52%
Generate normal map  ░░░░░░░░░░░░░░░░   0%
```

When all three bars fill, the HUD disappears and the model in the
canvas updates to show the new Blue Morpho-tinted wings.

## See the result

In the canvas, the Monarch's wings now carry the Blue Morpho's
iridescent pattern. The body stays its original Monarch orange. The
abdomen retains its black-and-white stripe.

If you switch to Textured + Lit mode (press `7` or choose
`View > Textured + Lit`), the normal map kicks in and you see the
wings catch highlights as you orbit. Orbit by holding Alt + middle
mouse and dragging; or use the orbit gizmo in the upper-right corner
of the canvas.

## Inspect the files on disk

Open the Assets tab in the Project Explorer. The Textures group now
shows two new entries inside your `.esk` folder:

```
butterfly.esk  · Reveal in Finder
+ Import Asset...
Textures · 3
  textures/butterfly_albedo.png
  textures/butterfly_normal.png
  ../butterfly/iridescentwinged_butterfly.png   ↗ external
3D Models · 1
  _3ds/butterfly.3ds   ↗ external
```

The two newly baked textures live inside the `.esk` bundle, which
means they will travel with the skin when you export at the end of
chapter 7.

Click `butterfly.esk · Reveal in Finder` to open the folder in your
OS file browser if you want to inspect the PNGs directly.

## Where the texture path lives

The `butterfly` placement's `texture_path` in the Channel Box now
points at `textures/butterfly_albedo.png` (relative to the `.esk`
root). The framework loads the path with the same relative
resolution at runtime, so the bake travels with the skin no matter
where the `.esk` ends up.

## Checkpoint

You should see:

- The Monarch model wearing Blue Morpho wings in the canvas.
- Two new files in the Assets tab: `textures/butterfly_albedo.png`
  and `textures/butterfly_normal.png`.
- The Channel Box's `texture_path` pointing at the new albedo.
- In Textured + Lit mode, the wings sparkle as you orbit.

If the wings look wrong (for example, the pattern is rotated 90
degrees or one wing is mirrored), check your landmarks in chapter 4
and re-run the pipeline. The most common cause of a bad Polar bake
is two landmarks accidentally swapped.

[Continue to chapter 6 >>](06-compare-bbox-pipeline.md)
