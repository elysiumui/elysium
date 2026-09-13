# Portable roughness and metallic images

Native material slots now accept owned images for `base_color`, `roughness` and `metallic`. The existing base-color path is unchanged. Roughness and metallic descriptors are stored as optional `roughness_image` and `metallic_image` fields in the version-1 material slot table. Each uses the same validated `sha256` and `png_base64` descriptor, PNG/JPEG import limits (16 MiB, 2048×2048, one frame), immutable decode cache and project ownership as base-color images.

Scalar maps use the red channel as linear data: sampled byte / 255 multiplied by the corresponding surface scalar. Use a scalar of 1 for the full image range. Green, blue and alpha are ignored; there is no sRGB decoding, alpha cutout or luminance conversion. Sampling is Closest/Repeat with the same explicit integer-tile boundary convention as owned base-color images. Source corner UVs drive all images. Missing UVs are reported in the native panel. Zero scalar keeps the resulting channel zero.

These explicit owned scalar maps override the corresponding result of any inherited packed metallic/roughness image. Clearing a scalar image removes only that override and restores the scalar/inherited behavior. Other channel images, source topology, UVs, assignments, normals, graphs and modifier inputs remain unchanged. All image descriptors participate in cache invalidation, Undo/Redo, save/reopen and native export; original file paths are not dependencies after import.

## Native authoring

Select the mesh, open Materials and choose the intended material slot. Set Metallic/Roughness multipliers and Apply surface. The bottom-right Image channel button cycles Base color → Roughness → Metallic. Enter Image path and Load image (or Enter) for the currently selected channel. Clear image affects only that channel. The panel reports the channel's sampling and interpretation; channel navigation does not create a model edit. The selection starts at Base color whenever the Materials panel is opened.

## Public authoring

`material.slot_image_set(id, slot_id, path, channel="base_color")` now takes an optional channel enum: `base_color`, `roughness`, `metallic`. Existing callers retain base-color behavior. Empty path clears the selected channel. Invalid channels, paths, images or prospective material/source/modifier states reject before publication. `material.slots_get` exposes the retained descriptors. `material.slot_update` sets multiplying surface values.

## Independent acceptance recipe

Use independent GUI and Aether copies of the earlier two-material cube with the top face carrying the four-color base image and projected UVs. Set the top-face material's Metallic and Roughness to 1. Import a 32×32 greyscale PNG into both scalar channels: upper-left/lower-right pixels 64, other quadrants 192. Preserve the base-color image. Undo after importing Metallic removes only Metallic. Redo, Save, Quit and clean reopening reproduce the complete material table, topology and normal inspection exactly.

In the independent Blender 5.2.1 LTS image-material reference, add Image Texture in the Shader Editor, open the same scalar image, select Closest and Non-Color, retaining Flat/Repeat. Wire Color to both Principled Roughness and Metallic; preserve the prior base-color image. The fixture is greyscale, so Blender's Color-to-scalar conversion agrees with native red-channel sampling. Colored maps require explicit channel separation in Blender; no claim of generic luminance equivalence is made. Read-only saved-reference inspection confirms both links/settings and scalar samples within 5.960464477539063e-8, using a 1e-6 gate. Source geometry, oriented faces, material assignments and smooth flags match exactly; assigned-face UV error is also 5.960464477539063e-8. Untextured faces' prior Blender UVs are outside this bounded fixture comparison.

Actual native Export App uses a new folder, no close target, size 128, scale 1, end 0, hold 0. It retains exact material/source data and produces a nonempty frame differing from the base-only fixture. Independent public replay agrees exactly with native GUI state. The matrix has 14 passing checks. Regression results: 508 relevant framework and 269 Designer tests pass. Tests additionally cover colored red-channel sampling, source-file removal, simultaneous channels, failed channel rejection, cache changes and actual channel-specific render changes.

This checkpoint does not certify packed glTF channel conventions, tangent-space normal mapping, non-grey Blender conversion, other filtering modes or final matched-lighting/radiometric parity. Those remain required work.
