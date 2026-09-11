# Native source-face material slots

A Mesh3D object can retain a version-1 `props.materials3d` table: `schema_version`, monotonic `next_id`, and 1–64 ordered slots. Each slot has a stable `m<number>` id, a 1–100-character name, and `parameters`. Source faces retain integer material indices; the public inspection maps them back to stable slot ids. Slot removal reindexes integer indices without changing surviving stable assignments. Material ids are local to the object; shared material datablocks and node graphs remain separate work.

Null parameters retain the live existing object material, including its textures. An object with no authored table renders exactly as before. On first authoring, existing source indices receive inherited object-material slots so adding a slot does not change existing faces. Creating explicit parameters on an inherited slot replaces that slot's object binding; other slots remain unchanged. This initial explicit surface supports linear RGB base color, metallic, roughness, specular, coat weight, coat roughness, and linear RGB emission. Surface/base values are 0–1; emission components are 0–64. All numbers must be finite and not boolean. Unknown fields reject. Image maps, transmission and graph inputs on explicit slots are not yet supported.

Public operations:

- `material.slots_get(id)` reads the table and source face assignments without mutation.
- `material.slot_add(id, name='Material', values=None)` adds an explicit surface and returns its stable id. Existing faces retain their slots.
- `material.slot_update(id, slot_id, name=None, values=None)` renames or updates supplied surface parameters.
- `material.faces_assign(id, slot_id, face_ids)` assigns distinct current source faces. It preserves positions, UVs, normals, seams, pins, identities and other face assignments.
- `material.slot_remove(id, slot_id)` removes an unused slot. Used slots and the last remaining slot reject; users first assign its faces elsewhere.

Every mutation validates the complete prospective table, source and retained modifier stack before publication. Invalid names, values, stale/duplicate face identities, absent slots or out-of-range source/evaluated indices reject without changing the object. Source topology material inheritance also carries assignments through the existing child-face, duplicate and modifier operations.

The shared scene composer now offsets each object's evaluated face-material indices into the composed material list. It previously assigned one surface to every triangle of an object. Neutral Solid mode remains a viewport override. Material mode uses retained assignments. The native scene exporter uses this same renderer and serializes the editable material table and source mesh. The individual Layout preview, its cached-PNG fallback, and public snapshot renderer also evaluate retained meshes and material slots. Their cache keys include explicit and inherited surface changes; asynchronous workers capture placement state before rendering. Legacy objects without a slot table retain their previous path.

## Native controls

The 3D toolbar exposes **Materials**. Select a mesh and open it to enter Material preview. Previous/Next navigate slots; Add slot creates a named surface. Numeric RGB/surface fields and Name are applied together by Apply surface or Enter. Close the panel, enter Face mode, select source faces, reopen it, choose the intended slot and Assign faces. Select faces selects all source faces assigned to the current slot. Remove slot rejects with an explanation if that slot is used. Changing slots alone does not mutate the project. Successful surface/assignment changes are Undo transactions. Tab/Shift-Tab/Enter/Escape work throughout the panel.

## Independent GUI/API/Blender acceptance

Start from separately authored 2 m cubes with five smooth faces and the top face flat (the earlier mixed-shading fixture). Native GUI: open Materials, rename the inherited first slot Hull and make its base RGB (.55,.55,.55), metallic 0, roughness .5, specular .5, coat 0, coat roughness .05, emission (0,0,0). Add Red with the same scalar parameters and base RGB (1,0,0). Select only the local Y=1 face and assign Red. The native perspective viewport visibly shows red on top and grey on the sides. Undo restores every face to Hull while keeping both slots; Redo, Save and clean-process reopening restore the exact assigned state.

The independent public API replay starts from its own API-authored cube and invokes the public slot update/add/face assignment operations. It does not reuse GUI mesh data. GUI and API source, normal inspection, slot tables and assignments match exactly.

Blender 5.2.1 LTS build 9e2066aef7ef: use the independently saved mixed cube; create Hull and Red Principled materials in Material Properties. Use the color popup's Linear and RGB controls to enter the same values. Set coat roughness explicitly to .05 on both materials; Blender defaults to .03, and the initial mismatch is preserved. In Edit Face mode select only the top face, choose Red and Assign. Save as a separate `.blend` reference. Geometry, edges, oriented faces, material names, all six assignments and smooth flags match exactly. Maximum surface parameter difference is 1.1920928910669204e-8 against the recorded 1e-6 numerical gate. This compares authored parameters and assignment, not final radiometric/image equivalence.

Actual native GUI Export App was also exercised on the independently API-authored material cube: a new folder, blank Close object, size 128, asset scale 1, end frame 0 and hold frames 0. The resulting frame contains 453 red and 1,846 neutral opaque pixels; the portable project retains the exact material table and source topology. No external script manufactured or repaired this export. Standalone packaging for this fixture was not required or claimed.

480 relevant framework tests and 263 Designer tests pass; the wheel builds and installs. Tests include actual rendered pixels, multi-object slot offsets, unused-slot removal/reindexing, stable ids, modifier propagation, atomic failure, native control actions, Undo/Redo and persistence. Evidence is archived in Designer plan `evidence/material-slots-20260910/`.

Full material graphs, textures on explicit slots, shared datablocks, lighting/transmission, color-management/image parity, broader GUI variants and complete S4 acceptance remain open. The accepted X-wing is unchanged.

## Layout and snapshot follow-up

A separate copy of the API-authored cube was opened in the native GUI. Layout camera tilt revealed the red assigned top. The Materials panel changed its RGB to (0,0,1); 3D Scene, Layout and GET /snapshot showed blue with unchanged grey sides. Undo restored red; Redo, Save, Quit and clean reopening restored the exact blue surface, source, normals and modifier state. The snapshot uses the project canvas, so this fixture extending beyond 800×600 is clipped. This is a surface/cache check, not cross-view camera or lighting equivalence. All 264 Designer tests and 36 focused framework tests pass, including rendered red/blue pixels through all three individual preview implementations.
