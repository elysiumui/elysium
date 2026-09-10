# Retained weighted normals

WeightedNormals changes evaluated corner normals while leaving source vertices, polygons, UVs, sharp/seam flags and source normal policy editable. It can be bypassed, reordered, removed or applied through the existing modifier stack. Apply bakes the evaluated custom corner vectors. Subsequent geometry-changing modifiers may recompute those vectors; put WeightedNormals after shape modifiers when its shading should be final.

## Specification

- `mode`: `face_area`, `corner_angle`, or `face_angle` (area times incident corner angle).
- `weight`: integer 1–100, default 50. Contributions sort by descending mode value. Different value bands receive inverse powers of a bias derived from weight. Weight 50 uses the mode values directly; larger values favor larger contributions.
- `threshold`: finite number 0–10, default 0.01. Consecutive sorted values remain in the same band until they differ from that band's leading value by more than the threshold.
- `keep_sharp`: boolean, default false. True weights each connected smooth fan independently, preserving the source smoothing angle and marked sharp boundaries. False aggregates all incident face contributions at each source vertex.

Whole-mesh Flat remains flat. Authored meshes without a shading policy are treated as flat if every retained corner is missing a normal or matches its source face normal; otherwise their edge connectivity and sharp flags define smoothing. Explicitly choose Smooth or Flat to avoid ambiguity. Per-face smoothing flags, face-strength influence and vertex-group masks are not implemented. No existing source custom vectors are silently discarded: only evaluated output corners are replaced. Weighting uses stable logarithmic scaling to avoid overflow at extreme weights and high valence. Degenerate cancelling sums fall back to the local source face normal.

Native UI: select a mesh, open Modifiers, choose Add Weighted, edit Mode/Weight/Threshold/Keep sharp and Update. A visible change requires smooth shading. Each mutation participates in normal Undo/Redo. Public authoring uses `mesh.modifier_add` and `mesh.modifier_update` with kind `WeightedNormals`; `mesh.modifiers_get` includes evaluated corner vectors.

## Verification and unresolved acceptance

408 relevant framework tests and 251 Designer tests pass. Tests include analytic asymmetric-box normals for all three modes, bias/threshold behavior, sharp and angle discontinuities, source immutability, Apply, invalid-input atomicity, native editor Undo/Redo and save/reload. The native wheel builds successfully. Live native GUI and independent public replay have not yet been tested for this modifier because the Mac locked during the test setup.

A clearly labeled automated Blender 5.2.1 comparison covers 30 mode/weight/keep-sharp combinations on the independently saved low-resolution sphere baseline. It is diagnostic, not GUI acceptance. Position error remains 1.1921e-7 m. Only corner-angle weight 50 meets the existing 1e-5 normal gate; other maximum corner-vector errors range from 1.7213e-5 to 7.5609e-5. Default face-area weight 50 differs by 2.5032e-5. These cases remain open; no threshold was relaxed. Blender stores custom normals as two signed 16-bit angular coordinates, while this candidate retains full vectors. A separate diagnostic round-trip sends the candidate default face-area vectors through Blender's custom-normal encoder. All 112 decoded corners then match Blender's independently calculated weighted output exactly (zero error). This isolates the default discrepancy to encoding; it does not constitute an independent GUI fixture or erase the raw-vector gate failure. Other parameter combinations have not yet had this encoding attribution checked.

Primary references, matched to installed Blender commit `9e2066aef7ef`: [weighted modifier algorithm](https://github.com/blender/blender/blob/9e2066aef7ef/source/blender/modifiers/intern/MOD_weighted_normal.cc), [polygon area and angle definitions](https://github.com/blender/blender/blob/9e2066aef7ef/source/blender/blenkernel/intern/mesh_evaluate.cc), and [custom normal encoding](https://github.com/blender/blender/blob/9e2066aef7ef/source/blender/blenkernel/intern/mesh_normals.cc).
