# Step 4. Set up landmarks

Time: 8 minutes.

## Why landmarks

Landmarks are matched pairs of points: one on the source photo, one on
the model's surface. The texture transfer pipelines you run in
chapters 5 and 6 use these pairs to figure out how the Blue Morpho's
pattern should warp to fit the Monarch's geometry. Six pairs is the
sweet spot for butterflies. Fewer than six and the warp gets unstable;
more than six adds work without much accuracy gain.

The Designer ships a Thin-Plate Spline (TPS) solver behind the
landmark transfer. TPS smoothly warps the source image so every
landmark on the source lands exactly on its matching landmark on the
target.

## Activate the Landmark tool

From the toolbox on the left, click the Landmark tool. Its icon shows
two pins connected by a dashed line. Or press `L` on the keyboard.

A small instruction strip appears at the top of the canvas explaining
the workflow: click a point on the reference Image first, then the
matching point on the Mesh3D part. The Designer holds your first click
as a half-pair until you commit the second.

## Place the six pairs

We will place six landmark pairs in this order. Click the named point
on the photo first, then the corresponding point on the model.

| # | Landmark | Where on the photo | Where on the model |
|---|---|---|---|
| 1 | Left wing tip | Upper-left corner of the photo's left wing | The forwardmost point of the model's left wing |
| 2 | Right wing tip | Upper-right corner of the photo's right wing | The forwardmost point of the model's right wing |
| 3 | Body center | Center of the body where wings meet | Center of the model's body |
| 4 | Left antenna root | Where the left antenna meets the head | Same point on the model |
| 5 | Right antenna root | Where the right antenna meets the head | Same point on the model |
| 6 | Abdomen tip | Tip of the photo's abdomen | Tip of the model's abdomen |

Each successful pair shows two filled-circle dots, numbered 1 to 6,
connected by a faint line. The number is also stamped in the corner
of each dot so you can confirm which pair you are looking at.

Tip: zoom in with the mouse wheel or with `+` and `-` before placing
the tip landmarks. Wing tips benefit from precise placement.

## Save the landmarks

When all six pairs are placed, choose `Mesh > Landmarks > Save` from
the menu bar. The Designer writes a small JSON file alongside the
photo on disk so you can reload the exact same landmark set if you
need to re-run the transfer later. The status bar at the bottom of
the window confirms with a brief "Landmarks saved" toast.

If you make a mistake, you can:

- Click the Landmark tool icon again, then click any existing dot to
  delete that pair (the deletion confirms with a toast).
- Choose `Mesh > Landmarks > Clear` to wipe all pairs and start over.
- Choose `Mesh > Landmarks > Load` to restore the last saved set.

## Inspect

Switch the Project Explorer to the Objects tab. Expand the
`BlueMorphoSrc` placement; you will see six child rows, one per
landmark. Each carries `(x, y)` coordinates on the photo. The model
side of each pair is stored as a UV coordinate on the mesh, not as
an `(x, y)` on the canvas; you will not see those in the tree.

## Checkpoint

You should see:

- Six numbered dot pairs across the canvas, connected by faint lines.
- A "Landmarks saved" toast (or, if it has faded, a saved file at
  `examples/butterfly/iridescentwinged_butterfly.landmarks.json`).
- Six child rows under `BlueMorphoSrc` in the Objects tab.

If you see fewer than six pairs, retrace the table above; if you see
more than six, use `Mesh > Landmarks > Clear` and start again. Six
well-placed pairs beats nine sloppy ones.

[Continue to chapter 5 >>](05-run-polar-pipeline.md)
