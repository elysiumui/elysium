# Painting workflow

End-to-end paint pass on a placement: from selecting the target,
through brushwork, to bundling the result into the exported `.esk`.

## 1. Select the target

Click the placement you want to paint on. For a 3D model, that is
the Mesh3D placement; the Designer routes brushwork to the model's
albedo texture (or, if you choose, to a named mask channel). For a
2D shape, the brushwork goes to the shape's mask layer.

Verify the target in the status line: it reads
"Painting into: butterfly.albedo" or
"Painting into: panel.mask".

## 2. Pick a brush

`B` to activate the Brush tool. Hold `B` to open the Quick Wheel
and switch engine. Open `Window > Brush Library` for a full preset
picker.

Set:

- **Size**: `[` / `]`.
- **Opacity**: `Shift+[` / `Shift+]`.
- **Color**: click the color swatch in the
  [Tool Properties dock](../interface/tool-properties-dock.md), or
  Alt-click anywhere on the canvas to sample.

## 3. Block in

Lay down broad strokes first. The Wet Mix engine's "Watercolor
Wet" preset is good for backgrounds and atmospheres; Round Stamp's
"Felt Tip" for blocky base shapes; Airbrush for gradients.

Toggle to a low-opacity brush (`Shift+[` a couple times) to keep
the block-in soft. You will tighten with a harder brush in step 5.

## 4. Refine with masks

A render-part mask narrows brushwork to a region of the placement.
Activate one to keep yourself from painting outside the lines:

1. Switch to vertex mode (`V`) on a Mesh3D, or use a Region
   placement on a 2D shape.
2. Lasso the area you want paint to land in.
3. `Mesh > Render Part Mask > From Vertex Selection` (3D) or
   `Mesh > Render Part Mask > From Selected Placements` (2D).
4. Resume painting; strokes outside the mask are ignored.

Clear the mask afterward with `Mesh > Render Part Mask > Clear`.

## 5. Detail

Switch to a harder, smaller brush (Round Stamp "Felt Tip" or
"Hard Edge", size 4-8 px) and add the details. Tablet users:
press more lightly for tapered strokes.

For mistakes, **Shift+B** swaps to Erase. Same controls as Brush.
Toggle back with Shift+B.

## 6. Inspect

`View > Toggle HUD` (or `0`) is on by default and shows the active
brush + size + opacity at the top of the View Panel. Zoom in to
verify edges at the resolution the framework will display them at:
press `+` (or scroll) repeatedly until pixels are visible.

If anti-aliasing introduces unwanted softness, lower the brush's
`smoothing` parameter in the
[Brush Studio](../brush/brush-studio.md) (engine-dependent;
defaults are documented in
[Touch and dynamics](../brush/touch-and-dynamics.md)).

## 7. Save

Painting is destructive on the placement's RGBA / mask. Saving the
project (`File > Save`) writes the painted state into the project
file (and into the live `.esk` folder if one exists).

The Project Explorer's [History tab](../interface/project-explorer.md#history-tab)
shows the brush stroke history (one entry per stroke). Undo as
far back as you like; bookmark a state you want to return to with
the ★ icon.

## 8. Export

`File > Export > .esk Bundle` writes the painted textures into
`butterfly.esk/textures/<placement_id>_albedo.png` (or the mask
equivalent for 2D shapes). The bundle's `manifest.json` records
which placement uses which texture so the framework loads them at
runtime.

You can also write only the painted PNGs without bundling the rest
of the project: `File > Export > Painted Textures as PNG`. Useful
when handing off a partial result to a teammate.

## Performance

A typical painting session uses ~100 MB of GPU memory per painted
placement (one stroke buffer + one history layer). For long
sessions consider:

- `View > Flatten Brush History` collapses the stroke history into
  a single state, freeing memory but losing per-stroke undo.
- Painting on a downsampled proxy with `View > Use Proxy
  Resolution` halves the working texture; export uses the original
  resolution.

## See also

- [Brush > Quick start](../brush/quick-start.md): orient to the
  brush tool itself.
- [Erase and Fill](erase-and-fill.md): the two non-brush paint
  tools.
- [Magic Polish](../ai/magic-polish.md): AI cleanup of painted
  results.
