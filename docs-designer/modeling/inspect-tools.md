# Inspect tools

The `Mesh > Inspect` submenu groups read-only and assistive
operations: queries about your scene, helpful one-shots that adjust
the canvas, and asset-size diagnostics. Nothing here is destructive.

## Submenu contents

| Entry | What it does |
|---|---|
| Show Vertex Count | Status-line toast: "Mesh3D `butterfly`: 8,412 vertices" |
| Show Face Count | Same, but face count |
| Show Texture Memory | Status-line toast: total VRAM committed to mesh + image placements |
| Match Reference Image Size to Selected Mesh | Scales the selected Image placement so its bounding box matches the selected mesh's projected bounding box |
| Match Selected Meshes to Same Size | Picks the bounding box of the first selected mesh and rescales the rest to match |
| Bounding Box → Console | Logs the selection's bbox as `(min_x, min_y, min_z) - (max_x, max_y, max_z)` |
| Validate Mesh | Checks for degenerate triangles, NaN positions, broken UVs |
| Recompute Normals | Rebuilds vertex normals from current geometry |

## Match Reference Image Size to Selected Mesh

The most-used Inspect entry. The flow:

1. Select your Mesh3D placement (the model).
2. Shift-click the Image placement (the reference photo).
3. `Mesh > Inspect > Match Reference Image Size to Selected Mesh`.

The image scales to match the model's projected bounding box. This
is exactly the step used in chapter 3 of the
[Blue Morpho tutorial](../getting-started/butterfly/03-import-the-reference-image.md)
to keep the photo and the model at the same approximate scale
before placing landmarks.

## Validate Mesh

For imported `.3ds` / `.obj` / `.fbx` files that came from a DCC
with sloppy export settings:

- Degenerate triangles (zero area): flagged and optionally
  auto-removed.
- NaN positions: flagged; cannot auto-fix; surfaces in the
  toast as "5 vertices with NaN positions; re-export from source".
- Broken UVs (NaN, infinite, or wildly out-of-range coords)  
  flagged; affected vertices show as red dots in the View Panel
  with an overlay.

A clean mesh shows: "Mesh validates: 0 degenerate, 0 NaN, 0 broken
UVs."

## Recompute Normals

After deformers, lasso-based vertex moves, or imports from formats
that did not carry normals, `Recompute Normals` rebuilds them
from the current triangle topology. Smooth shading and PBR
lighting need correct normals; if your model looks flat-lit or
crystalline, this is usually the fix.

## Texture memory accounting

`Show Texture Memory` is useful before exporting a `.esk` bundle:
it surfaces the total VRAM the skin will commit at runtime. The
framework's default budget for a runtime skin is 64 MB; toasts in
red if you exceed that.

If you blow the budget, reach for `Mesh > Inspect > Validate
Texture Sizes`, which lists every texture in the project sorted by
memory cost.

## Validate Texture Sizes

Lists every texture in the project with: name, dimensions, bytes,
mip-level count. Sort by clicking a column header. Use to find:

- A 4096 x 4096 reference image you forgot to downsize.
- A texture stored as 32-bit float when 8-bit unorm would suffice.
- A normal map stored at higher resolution than the albedo it
  pairs with.

The status line warns when total committed memory exceeds the
runtime budget set in `Preferences > Runtime > Texture Budget`.

## Bounding box logging

`Mesh > Inspect > Bounding Box → Console` writes the current
selection's bounding box to the
[Aether chat panel's console section](../interface/aether-chat-panel.md)
(or to a paired Python file's logging surface if Code Link is on).
Useful when you want to position a placement programmatically and
need the source coordinates.

## See also

- [Render part mask](render-part-mask.md): the next step after
  selecting a region of vertices.
- [Texture transfer pipelines](../rendering/texture-transfer-pipelines.md)
 : how the texture-memory budget interacts with bakes.
