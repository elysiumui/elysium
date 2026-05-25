# Custom brush from a photo

Time: 25 minutes. Difficulty: Beginner.

Use the Eyedrop tool plus the Brush Studio to author a brush whose
stamp is a tileable extracted from a photograph (concrete, foliage,
fabric, etc.).

## Prerequisites

- A source photo (any JPG / PNG).
- Familiarity with the [Brush quick start](../brush/quick-start.md).

## Import the photo

1. `File > Import > Image…` and pick your photo.
2. The image lands as an Image placement.

## Extract a tileable

1. With the image selected, `File > Extract Texture from Image…`.
2. The Designer finds a seamless tile (a square crop with edges
   stitched to match) and writes it to `~/.elysium/textures/`.
3. A small dialog confirms with the path of the extracted tile.

The extractor uses simple seam-aware cropping; the result tiles
without visible edges in most cases. For tough source photos, try
a different crop area in the dialog.

## Build the brush

1. `Window > Brush Studio` (or click Studio in the Brush Library).
2. Pick engine **Texture**.
3. In the Texture column, click "Pick file" and select the
   extracted tile you just made.
4. Set `texture_scale = 1.0`, `texture_rotation = 0`.
5. In the parameters column: `size_px = 60`, `opacity = 0.8`.
6. Author dynamics: bind `pressure → opacity` with a linear curve.

## Preview

The Studio's preview canvas shows a sample stroke. Adjust `tint_strength`
to taste: at 0 the stroke is pure texture color; at 1 it picks up
the brush's color.

## Save

Click **Save** in the Studio footer. Name the brush ("Concrete",
"Foliage", "Burlap" etc.). It lands in the Brush Library under
**My Presets**.

## Use it

`B` to activate Brush, open the Library, click your new preset.
Paint on any selected placement.

## Export to share

Right-click your preset in the Library > **Export to .elybrush…**.
The resulting file embeds the tile as base64; share it directly
with teammates.

## What you exercised

- `File > Extract Texture from Image…`.
- Brush Studio engine selection.
- Dynamics curve authoring.
- Saving to the user Library.
- `.elybrush` export.

## See also

- [Brush Studio](../brush/brush-studio.md): full editor reference.
- [Importing Photoshop brushes](13-importing-photoshop-brushes.md)
 : for `.abr` packs.
- [Native .elybrush format](../brush/native-elybrush-format.md)
