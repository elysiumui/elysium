# Step 3. Import the Blue Morpho reference image

Time: 4 minutes.

## Find the image

The reference photo of an iridescent-winged Blue Morpho ships with the
Designer's examples folder at:

```
examples/butterfly/iridescentwinged_butterfly.png
```

The file is about 2.5 MB at 1536 by 1024 pixels. The photo is taken
straight on so the wings sit flat in the frame, which is exactly what
the texture transfer pipelines want.

## Run the import

From the menu bar choose `File > Import > Image`. Navigate to
`examples/butterfly/iridescentwinged_butterfly.png` and click Open.

The Designer creates an Image placement and drops it at the center of
the canvas, on top of the Monarch model. The Project Explorer's Objects
tab gains a row called `BlueMorphoSrc` (the Designer names it from the
filename and a hint from the importer).

## Move the reference next to the model

The two placements are now stacked. With the new Image placement
selected, press `W` to switch to the Move tool, then drag the photo to
the left of the model so you can see both at once. A small gap of about
40 pixels between the two looks tidy.

Alternatively, use the Arrange menu: `Arrange > Align Left` will snap
the selected placements to their leftmost edge, useful for getting a
clean side-by-side composition.

If the photo is much larger or smaller than the model, the Designer
also offers a helper to equalize them. Choose
`Mesh > Inspect > Match Reference Image Size to Selected Mesh` and the
Designer scales the photo to match the model's bounding box. This
keeps the landmark pairs in chapter 4 within the same approximate
scale.

## Lock the reference for landmarks

We want the photo to act as the source of truth for the texture
transfer; we do not want to accidentally nudge it once landmarks are
placed. With the `BlueMorphoSrc` placement selected, expand the
Properties pane at the bottom of the right column and find the
**Locked** checkbox. Tick it. The placement is now read-only until you
unlock it.

## Verify in the Assets tab

Click the Assets tab in the Project Explorer. You now see two entries
plus the Reveal in Finder row at the top:

```
butterfly.esk  · Reveal in Finder
+ Import Asset...
Textures · 1
  ../butterfly/iridescentwinged_butterfly.png   ↗ external
3D Models · 1
  _3ds/butterfly.3ds   ↗ external
```

Both source assets are external (they live outside the `.esk` folder).
That is the right setup for this tutorial; the bake we run in chapter 5
will land inside the `.esk` folder.

## Checkpoint

You should see:

- The Monarch model on the right of the canvas.
- The Blue Morpho photo on the left, locked.
- Both visible at roughly the same height.
- Two entries in the Assets tab (one Texture, one 3D Model), both
  flagged external.

If the photo is hiding the model, click the photo and choose
`Arrange > Send Backward` to drop it behind the model, then move it
left. If you accidentally locked the wrong placement, expand
`BlueMorphoSrc` in the Properties pane and untick **Locked**.

[Continue to chapter 4 >>](04-set-up-landmarks.md)
