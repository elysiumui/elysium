# Topology normal transfer

`mesh.normals_transfer` takes target `id`, `source_id`, and `space` (`world`, default, or `local`). It copies the source's evaluated corner normals to the target's editable source mesh once. Both must be distinct current-scene meshes with identical vertex count and ordered face/corner vertex-index loops. Positions may differ. Incompatible topology is rejected before mutation; no nearest-surface mapping is inferred.

World mode converts row-vector normals with inverse(source world linear matrix) × target world linear matrix, then normalizes. Hierarchy, rotation, nonuniform scale and reflection participate; translation does not. Local mode copies vectors unchanged. The target switches to authored normals, retaining geometry, UVs, IDs, seams and its modifier stack. Source data stays unchanged. Existing sharp edges remain; consistently oriented two-face edges gain sharp flags where endpoint normals differ by more than Blender's 1e-4 dot-product threshold. Gradual differences around a fan have not yet been proven equivalent to Blender's fan-reference algorithm.

The Designer Normals panel exposes world/local space and Copy normals. Select a source and then the target last; with exactly two mesh objects, Select All makes the last object the target. Copy is one undoable operation and survives project save/reopening. This is a one-time copy, not a retained live source dependency. Nearest/interpolated mapping, mixing, vertex groups, UV/color/weight transfer and arbitrary topology transfer remain pending.

## Inspector correction

Object inspection records neutral taper settings even when only a name or position changes. Evaluation now recognizes unit factors on the axes perpendicular to the taper axis and skips that no-op deformation. This preserves authored corner normals and permits zero-span neutral tapers. Previously `with_vertices` discarded those normals despite unchanged geometry, producing a GUI/API discrepancy. Actual deformation continues to recalculate normals according to existing policy.

## Verification

436 framework tests cover atomic rejection, ordered topology, evaluated source, retained target stack, world/local transforms, hierarchy, nonuniform/reflected scale, flags, persistence and neutral taper. 256 Designer tests include native normal-copy history and inspector regression.

Independent Designer GUI and public API fixtures each contain a 4-ring/8-segment radius-1 sphere source at X=-2 and target at X=2. Source is Flat, target initially Smooth; world-space copy produces 26 vertices, 32 polygons, 112 corners and 56 sharp target edges. GUI Undo restores the preceding source exactly; clean reopening retains the copy. GUI/API source and evaluated documents match exactly after the neutral-taper correction (object entity IDs differ by design).

An independently GUI-authored Blender 5.2.1 LTS file uses Data Transfer, TransferSource, Face Corner Data / Custom Normals, Topology, Object Transform enabled, Replace 1.0. Geometry and oriented connectivity match; maximum position error is 1.884864366e-7 m and normal-vector error is 2.345337040e-7. Both pass unchanged 1e-6 geometry and 1e-5 normal gates. All 56 sharp target edges match. The reference is evaluated, while Designer stores a one-time copy. This bounded fixture does not close the normal/data-transfer family.
