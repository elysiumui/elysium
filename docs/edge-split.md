# Retained Edge Split

EdgeSplit creates separate evaluated vertices where selected edges disconnect the incident faces into different connected groups. It preserves all source positions, UVs, corner identities, vertex parts, material assignments and edge flags. The editable source asset remains unchanged until Apply stack. Coincident positions are never welded. A single selected edge on a closed cube does not disconnect its vertex fans and therefore leaves its topology intact, matching Blender.

Parameters: angle is a finite 0–180 degrees (default 30); use_angle and use_sharp are booleans (both true by default). Angle splitting applies strictly beyond the threshold, with Blender's small boundary slack. At zero/near-zero angle all shared edges split, including coplanar edges. At 180 degrees angle splitting is disabled. Nonmanifold shared edges split whenever angle splitting is active below 180 degrees. Marked sharp edges are considered independently when use_sharp is true. Both switches off bypass evaluation. Source loose edges and isolated vertices remain present; broader Blender wire/nonmanifold correspondence remains unverified.

Native UI: select a mesh, open Modifiers → Add Edge Split; edit angle and Yes/No switches, then Update. Existing stack bypass/reorder/remove/Apply controls and native Undo/Redo apply. Public API uses mesh.modifier_add or mesh.modifier_update with kind EdgeSplit. mesh.modifiers_get exposes the unchanged source and evaluated topology. Apply stack bakes the evaluated geometry as editable source.

422 relevant framework tests and 252 Designer tests pass. The installed candidate was exercised through the actual native UI: Add, Undo, Redo, Save and clean-process reopening. Independent Aether replay matches exactly. Blender 5.2.1 GUI authoring on its own previously saved radius-1, 4-ring/8-segment sphere used Add Edge Split Modifier with 30 degrees and both switches enabled, then saved a separate reference. Its prior Weighted Normal modifier was removed through the GUI before this operation, restoring the independent original source. Blender extraction is read-only.

All three produce 82 vertices, 96 edges and 32 polygons. Comparison identifies coincident vertices by their incident source-face groups, verifies bijective vertex correspondence and exact edge/polygon connectivity, and compares 112 corners. Position error is at most 1.1920928955078125e-7 m (gate 1e-6); normal error is at most 1.9314112360500873e-7 (gate 1e-5). Source geometry/attributes, Undo restoration and clean reopening match exactly.

This accepts one manifold sphere modifier fixture. Full normal-family acceptance, broader modifier ordering, nonmanifold/wire/custom-normal variants and matched studio visuals remain open. Nothing was pushed or merged.

Primary semantics reference: [installed Blender commit 9e2066aef7ef Edge Split implementation](https://github.com/blender/blender/blob/9e2066aef7ef/source/blender/modifiers/intern/MOD_edgesplit.cc).
