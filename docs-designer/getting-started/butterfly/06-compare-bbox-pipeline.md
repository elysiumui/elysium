# Step 6. Compare the BBox-Warp + Landmark Gaps pipeline

Time: 5 minutes.

## Why a second pipeline

The Polar pipeline you ran in chapter 5 is fast and reads well on
butterfly wings. The second starred recommended pipeline, BBox-Warp
then Landmark Gaps, trades raw speed for fine-grain control. It is
the right choice when:

- The source photo and the model differ in proportions (a stockier
  Monarch with a slim Blue Morpho photo, for instance).
- You need precise pattern alignment on small features (eye spots,
  veins).
- You plan to do touch-ups by hand after the bake.

This chapter runs the BBox pipeline, lets you compare the two bakes
side by side, and helps you decide which to ship.

## Undo back to a clean Monarch

Before running BBox you want a fresh start. Press `Cmd+Z` (macOS) or
`Ctrl+Z` (Windows/Linux) until the canvas shows the original Monarch
albedo (no Blue Morpho tint). The undo history will tell you when
you have rewound past the Polar bake.

Alternatively, set the `butterfly` placement's `texture_path` back
to the original by clicking the Channel Box value and editing it to
`_3ds/texture.bmp`.

Verify the canvas shows the original Monarch orange before you
continue.

## Run BBox-Warp + Landmark Gaps

With the model still selected, choose
`Mesh > Transfer Texture > BBox-Warp then Landmark Gaps + Bake + Normal Map`.

The Designer runs four stages:

1. **BBox-Warp**: maps the source photo into the model's UV
   bounding box. This is faster than TPS but less accurate near
   features.
2. **Landmark Gaps**: identifies where the BBox warp's accuracy
   degrades (typically the wing tips and the body-wing junction) and
   re-runs a thin-plate spline locally over those regions using your
   six landmark pairs.
3. **Bake**: writes the combined result to
   `textures/butterfly_albedo.png`.
4. **Normal map**: derives the same high-frequency normal map and
   writes it to `textures/butterfly_normal.png`.

The HUD shows four progress bars this time, one per stage. End-to-end
runtime is about 8 to 10 seconds.

## Compare the two bakes

The Designer keeps both bakes in its undo history. To do an A/B:

1. Press `Cmd+Z` (macOS) or `Ctrl+Z` (Windows/Linux). The canvas
   reverts to the Polar bake from chapter 5.
2. Press `Cmd+Shift+Z` or `Ctrl+Shift+Z` (or use `Edit > Redo`) to
   come back to the BBox bake.

Toggle back and forth a few times. Pay attention to:

- **Wing tip iridescence**: Polar usually wins (smoother gradient).
- **Vein alignment**: BBox+Landmark usually wins (sharper edges).
- **Body color**: both should preserve the original Monarch orange.

Which wins for your project depends on what kind of app you are
building. For the official Elysium logo banner the rest of this
tutorial assumes we ship Polar (chapter 5's result). If you prefer
BBox+Landmark, simply stay on it; chapters 7 and 8 work the same
either way.

## Pick a winner

Press `Cmd+Z` / `Ctrl+Z` until the canvas shows the bake you want
to ship. The Channel Box's `texture_path` and the Assets tab's
texture files will reflect your choice.

## A note on the other 7 transfer methods

The Mesh > Transfer Texture submenu also lists POLAR, REGIONS,
FLOW, TPS, BBOX_WARP, SWEEP, and LANDMARK as standalone methods
without the bake-and-normal-map steps. They are mainly useful when:

- You want to compose a custom pipeline (e.g. TPS into a separate
  layer, hand-tune, then bake yourself).
- You are debugging a recommended pipeline that did something
  unexpected on your specific model.
- You are porting an existing wing texture from another tool.

The [Rendering > Texture transfer pipelines](../../rendering/texture-transfer-pipelines.md)
reference page explains every method's algorithm and trade-offs.

## Checkpoint

You should see:

- The canvas showing your chosen bake (Polar or BBox+Landmark).
- The same two texture files in the Assets tab as in chapter 5.
- A muscle memory for `Cmd+Z` / `Cmd+Shift+Z` to flip between
  history states.

[Continue to chapter 7 >>](07-render-and-export.md)
