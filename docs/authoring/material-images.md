# Owned base-color images on native material slots

A slot in a version-1 `props.materials3d` table may have an optional `albedo_image` object containing exactly `sha256` (64-character digest of PNG bytes) and `png_base64` (strict base64 PNG data). Absence preserves the slot's previous surface/image binding. The project owns the pixels; the original image path is not retained or needed after import. Slot updates and reindexing preserve this descriptor. JSON save, native export and reopening retain it without external dependencies. Full node graphs and shared image datablocks are separate work.

Import accepts one PNG or JPEG, at most 16 MiB and 2048×2048 pixels. It decodes and converts to RGBA PNG, validates the digest, and validates the prospective material table and retained mesh stack before publishing. Missing, corrupt, oversized, animated or unsupported images reject without changing source or material data. A decoded-image cache holds at most eight immutable arrays; viewport signatures avoid serializing image bytes on every frame.

This image overrides the selected slot's albedo map, multiplies its linear base color, uses piecewise sRGB-to-linear decoding, Closest interpolation, repeating UV coordinates, and an opaque surface. Image alpha does not cut holes. Integer UV tile boundaries wrap to the next tile. The explicit Closest path uses all image texels; legacy materials keep their previous sampling behavior. Source corner UVs drive the image. Assign or project UVs on the intended faces through the native UV workspace; the Materials panel reports assigned faces with missing UVs. This does not generate UVs automatically.

## Native authoring

Select the mesh, open Materials, and choose a slot with Previous/Next. For an untinted image use Base RGB (1,1,1) and Apply surface. Enter a PNG/JPEG path in Image path, then Load image or Enter. Clear image removes only this slot's image override; it preserves surface values, assignments, source geometry and UVs. For an inherited slot, clearing restores the inherited object's image binding. Both actions support Undo/Redo. Save and native Export App retain the image. Existing `material.clear` also removes authored slots and their owned images, matching its reset-all-material-customizations behavior.

## Public authoring

`material.slot_image_set(id, slot_id, path)` is the same mutation used by the native controls. Empty path clears the override. `material.slots_get` returns the retained descriptor with the slot table and stable source-face assignments. Images are imported from local paths; this operation does not fetch URLs. Existing `material.slot_update` controls the multiplying base color and other scalar values. Existing `mesh.uv_project` authors selected source corner UVs.

## Independent acceptance recipe

Start with separate native GUI and API copies of the earlier mixed-shading, two-material cube: Hull on five faces and Red on local Y=1. Set Red base RGB to (1,1,1), load the same 32×32 image with red/green top quadrants and blue/white bottom quadrants. In native Top view, Face mode, select only the top face. Open UVs → Project → XZ, close, switch to Objects and inspect Material view. All four colors appear in that orientation. Clear image produces a white face; Undo restores exact image/source data; Redo clears again. Undo, Save, Quit and clean reopening preserve the exact textured state.

The independent public replay starts from its own API-authored material cube; it updates the slot, loads the source image and projects only the top face through public operations. GUI and API material tables, source topology and normal inspection match exactly.

In Blender 5.2.1 LTS, open the independently authored material cube and Save As a separate reference. In Material Properties, connect Image Texture to Red's Base Color through the socket picker. Open the same file and set Closest; Flat, Repeat and sRGB are retained. In top orthographic Edit Face mode select only the top face and run Project from View (Bounds). Switch to Object mode and Material Preview. Both GUIs show red/green above blue/white. Saved-file read-only inspection confirms exact geometry, oriented faces, edges, assignments and smooth flags; selected-face UV error is 5.960464477539063e-8 (gate 1e-6). Image texels, link, interpolation, extension and color-space settings match. Untextured Blender faces keep their earlier UVs; these are not compared to native unset UVs. Final lighting, radiometric output and color-management equivalence remain open.

Actual native Export App: a new folder, no Close object, size 128, scale 1, end frame 0, hold 0. The portable editable material table/source match exactly, and its frame contains 400 red, 400 green and 400 blue pixels plus the white quadrant. No external script manufactured the export. Unit tests also remove the original image before reopening/exporting, verifying owned-image portability.

Validation: 489 relevant framework tests passed before the final reset-all-materials compatibility test; the subsequent focused suite has 46 passing tests, including that new test. All 265 Designer tests pass. A candidate wheel was built, installed and exercised in the native GUI. Broader image formats, resolutions, filtering modes, texture channels, UV transforms, node graphs, lighting and complete S4 acceptance remain open.
