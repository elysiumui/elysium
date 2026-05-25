# Step 2. Import the Monarch 3D model

Time: 5 minutes.

## Find the model on disk

The Monarch model ships with the Designer's examples folder at:

```
examples/butterfly/_3ds/butterfly.3ds
```

The file is small (about 15 KB) because it carries geometry only. The
original Monarch albedo texture is alongside it at
`examples/butterfly/_3ds/texture.bmp`; we will replace that texture in
chapters 5 and 6.

## Run the import

From the menu bar choose `File > Import > 3D Model`. The file picker
opens. Navigate to `examples/butterfly/_3ds/butterfly.3ds` and click
Open.

The Designer parses the `.3ds` file, registers it in the mesh library
under the name `butterfly`, and creates a Mesh3D placement at the center
of the canvas. The Project Explorer's Objects tab gains a row called
`butterfly` with a tiny mesh thumbnail.

## Frame the model

The default placement may put the butterfly off-center or at an
inconvenient zoom. Press `A` (Frame All) or choose `View > Frame All` to
fit the entire scene to the viewport. You should see the Monarch
silhouette filling most of the canvas, oriented with the body pointing
up and the wings spread.

If the model loaded sideways, your `.3ds` import inherited the file's
native coordinate system. Press `E` to switch to the Rotate tool and use
the on-canvas gizmo to rotate the model 90 degrees around the X axis.
The Designer's importer normally handles the Y-up to Z-up flip
automatically; if it didn't, file an issue, but proceed with the manual
fix for now.

## Switch to Textured shading

By default the Designer renders meshes in Smooth Shaded mode (no
textures, just lighting). To see the original Monarch albedo, choose
`View > Textured` from the menu bar, or press `6` on your keyboard. The
butterfly now shows its bundled Monarch wing pattern.

You can also try `View > Textured + Lit` (or press `7`) to add PBR
lighting on top of the texture. For this tutorial we will stay in
Textured mode (key `6`) until the final render in chapter 7.

## Look at the Channel Box

With the `butterfly` placement still selected (it should have a thin
accent-color outline), look at the Channel Box in the right column. You
will see numeric fields for `x`, `y`, `w`, `h` plus a `mesh_kind`
showing `butterfly` and a `texture_path` pointing at `texture.bmp`. The
Channel Box is where Maya users will feel at home: it surfaces every
keyable attribute on the selection.

## Verify in the Assets tab

Click the Assets tab in the Project Explorer (next to Objects). You
should see one entry under the **3D Models** group:

```
3D Models
  _3ds/butterfly.3ds   ↗ external
```

The `↗ external` tag means the file lives outside your project's
`.esk` folder. That is fine for the source `.3ds`; we will export
finished bakes into the `.esk` later.

## Checkpoint

You should see:

- The Monarch model centered and framed in the viewport.
- View mode set to Textured (key `6`).
- A `butterfly` row in the Objects tab.
- A `_3ds/butterfly.3ds ↗ external` entry in the Assets tab.

If the model is sideways or off-screen, hit `A` to reframe or use the
Rotate tool to correct orientation before continuing.

[Continue to chapter 3 >>](03-import-the-reference-image.md)
