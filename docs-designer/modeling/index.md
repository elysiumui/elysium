# Modeling

The Designer's modeling toolkit is small on purpose. Authoring a
skin is not authoring a feature film: most placements are
rectangles, ellipses, simple curves, and imported 3D models. The
Modeling menu set covers the operations that come up day-to-day,
and pushes you out to a dedicated DCC (Maya, Blender, ZBrush) when
you need more.

## What the Modeling set covers

| Tool | Section |
|---|---|
| Lasso Select | [Lasso selection](lasso-selection.md) |
| Mesh > Inspect | [Inspect tools](inspect-tools.md) |
| Mesh > Render Part Mask | [Render part mask](render-part-mask.md) |
| Path > Combine (Union / Intersect / Subtract / Exclude) | [Path booleans](path-booleans.md) |
| Arrange > Align / Bring Forward / Send Backward | [Arrange and align](arrange-and-align.md) |
| File > Import > 3D Model | Reads `.3ds`, `.obj`, `.gltf`, `.fbx` |

## What it does **not** cover

- Polygon edit operations (extrude, bevel, subdivision surface).
- Topology cleanup (re-meshing, retopology).
- Sculpt-mode displacement.
- UV unwrapping (the Designer reads existing UVs; it does not
  re-author them).

For any of the above, model in your tool of choice, export to
`.gltf` or `.obj`, and import. The
[`from-maya` migration guide](../migration/from-maya.md) covers the
common workflows.

## When the Designer is enough

Most Elysium skins are 2D: a borderless window with shapes, text,
images, and animation. The Modeling set's lasso, path booleans, and
arrange tools cover that completely.

For 3D placements (Mesh3D), the Designer's role is **transfer +
preview**: pick textures and materials, position lights, run the
texture transfer pipelines, render previews. The geometry comes in
from a DCC.

## Workflow tips

- Import models early. The earlier the Mesh3D placement exists,
  the more accurately you can author landmarks, textures, and
  animation against it.
- Bake textures with the transfer pipelines as the **last** step
  before export. Bakes are expensive to re-run.
- For 2D-heavy skins, stay in the Modeling menu set; for 3D
  butterfly-style projects, switch to Rendering (F6) once geometry
  is locked.

## See also

- [Rendering and Lookdev](../rendering/index.md): texture
  transfer pipelines, lights, render quality.
- [Importing 3D models](../importing/3d-models.md): supported
  formats and gotchas.
- [Migration > From Maya](../migration/from-maya.md): full
  workflow guide for Maya users.
