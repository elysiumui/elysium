# Native tangent-space normal images

Normal-map images were stored by the material model but not consumed by the PBR shaders. Both the preview renderer and path tracer now evaluate them. The path tracer also interpolates authored corner/vertex normals before normal mapping, matching the preview's existing authored-normal path.

An optional `normal_image` in a material slot uses the owned PNG descriptor and import limits documented in material-images.md. Public `material.slot_image_set(id, slot_id, path, channel="normal")` imports it; empty path clears only this normal override. In Materials, choose the slot, cycle Image channel to Normal, enter Image path and Load image/Enter. The label states linear RGB tangent normal. Source geometry, UVs, authored normals, other images and material values remain unchanged. Undo/Redo, Save, clean reopening and native export preserve the descriptor and evaluated output.

Pixels are linear RGB direction data, decoded as `2*(RGB/255)-1`; alpha is ignored. Strength is currently fixed at 1 with OpenGL (+Y) convention. Per-triangle UV derivatives produce tangent and bitangent vectors from transformed world positions. Tangents are orthogonalized to the interpolated shading normal, and the UV handedness is retained. The transformed direction is normalized before shading and face-forwarded for the existing two-sided preview behavior. Missing or degenerate UVs retain the original shading normal. Image sampling uses Closest/Repeat for owned images. Existing path-backed normal maps now affect shading using their existing sampler; materials without a normal map keep their previous preview behavior.

This implementation uses a per-triangle derivative basis. It does not yet reproduce MikkTSpace tangent averaging across arbitrary smooth curved neighborhoods. Other normal spaces, strength controls, DirectX convention and full smooth/curved/backface reference acceptance remain open.

## Independent fixture

Start from independent GUI and Aether copies of the earlier material-image cube. The flat top face uses the Red slot with its four-color image and previously projected UVs. Import a 16×16 RGB PNG with every pixel (204,128,230) into Normal. Native Undo restores the exact previous table/source/normal inspection; Redo, Save, Quit and clean reopening reproduce the normal-image state exactly. The independent API project loads the same image through the public command and matches all inspected native data.

In Blender 5.2.1 LTS's independent image-material cube, add Image Texture and Normal Map in the Shader Editor. Open the same PNG, choose Closest, Non-Color and Repeat/Flat. Link Image Color → Normal Map Color → Principled Normal, retaining the existing Base Color link. Normal Map uses Tangent Space, OpenGL convention, Displaced Base, strength 1 and the active UV map. Save through the GUI. Read-only extraction confirms links, settings, image data, geometry, face assignments, shading flags, source corner UVs and Blender's computed Mikk tangent basis.

For the flat top face, native evaluated directions are (0.598117352, 0.801398993, -0.003909322) in Designer coordinates. Decoding the saved Blender image and transforming by its saved-mesh tangent basis differs by at most 8.112983749238857e-9 (gate 1e-5). Assigned-face UV error is 5.960464477539063e-8 (gate 1e-6). This is an independent shader-input/basis/math comparison, not a rendered Blender normal pass or final radiometric proof.

Native Export App uses a new folder, no close object, size 128, scale 1, end 0 and hold 0. Material table and editable source match exactly, and the nonempty exported frame differs from the unmapped fixture. All 14 matrix checks pass. The relevant regression set passes 516 framework and 270 Designer tests. Tests exercise UV mirroring, positive/negative nonuniform scale, object rotation, degenerate/missing UVs, source-file removal, channel-specific persistence/export, and actual changes in both preview and path-traced output without geometry mutation.

Broader tangent/normal-space variants and final matched-lighting/visual acceptance remain required. Evidence is under the plan's `evidence/normal-image-20260910/` directory.
