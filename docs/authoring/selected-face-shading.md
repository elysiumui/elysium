# Retained selected-face Smooth and Flat shading

Editable topology version 5 adds an optional boolean `smooth` attribute to each source face. Versions 1–4 remain readable; version 4 and earlier reject the new field. Absent flags inherit the retained whole-mesh computed policy (`flat` or `smooth`). Explicit face flags override that policy. Source geometry, edge flags, UV/pin/corner data, materials and identities are unchanged by face shading.

Public `mesh.faces_smooth_set(id, face_ids, smooth=True)` requires distinct current face identities and a boolean. It requires an existing computed normal policy: first choose whole-mesh Smooth or Flat. Authored custom-normal mode rejects rather than silently replacing custom vectors. `mesh.normals_get` exposes the explicit `face_smooth_overrides` map; source topology retains the flags. Whole-mesh `mesh.normals_set` deliberately clears all face overrides. Custom-vector and transfer operations switch to Authored mode, where computed face overrides are inactive. Complete imported custom-normal/face-flag interaction remains a separate acceptance case.

Smooth fans connect only smooth faces through consistently wound manifold edges that pass the angle and sharp-edge settings. Flat faces always use their polygon normal and contribute nothing to adjacent smooth fans. Weighted normals similarly exclude flat-face contributions and retain flat polygon directions, including with Keep sharp off. Normals recompute after source geometry edits.

Subdivision children, extrusion walls/caps, inset borders, cut faces, duplicated/mirrored faces and Solidify surfaces inherit their originating face attributes. New bevel/bridge/edge-extrusion faces follow the same source-neighbor choice as their material inheritance. Faces created without an originating face inherit the whole-mesh default. Dissolving faces with different effective shading modes rejects atomically rather than discarding that boundary. Broader independent Blender comparisons for these combinations remain open.

Native workflow: select a mesh, open Normals, choose whole-mesh Smooth or Flat, close the panel, enter Face mode and select the intended faces, reopen Normals and choose Face smooth or Face flat. Actions affect the selected source faces and create one Undo transaction. Numeric custom direction remains separately available. All twelve actions and four numeric fields fit the inspected 1300×768 normal window. Keyboard Tab/Shift-Tab/Enter and Escape follow the existing panel behavior.

## Independent acceptance fixture

Designer GUI: create a fresh 2 m cube from the Sculpting primitive shelf, choose Smooth at 180 degrees with sharp edges respected, switch to Top view and Face mode, select only the top face, and choose Face flat. Undo must restore the entirely smooth source. Redo, Save and clean-process reopening must restore the exact mixed source document and normal inspection.

Public API: independently create a 2 m cube with `mesh.primitive_create`, set whole-mesh Smooth, discover the top source face by its vertices at local Y=1, then call `mesh.faces_smooth_set` with smooth=false. This replay does not reuse native GUI geometry.

Blender 5.2.1 LTS build 9e2066aef7ef: create a fresh default 2 m cube, Object Shade Smooth, enter Edit mode and Face selection, Top view, click only the top face, run Shade Flat, return to Object mode and save. No camera/light remains in the reference scene. Compare in Designer coordinates D=(Bx,Bz,-By).

The independent GUI/API/Blender comparison matches all 8 vertex positions, 12 edges, 6 oriented faces, 24 corner normals and 6 effective smooth flags exactly: five smooth, top flat. Native Undo and Redo/Save/clean reopening are exact. Public API source and normal inspection are exact. 469 relevant framework tests and 262 Designer tests pass; native wheel builds and installs. Analytic cube tests independently check that top-adjacent smooth normals omit the top face's contribution. Tests also cover a flat default with selected smooth faces, weighted flat preservation, version validation, invalid/stale selection, persistence and child attribute inheritance.

Evidence lives in Designer plan `evidence/face-shading-20260910/`. This certifies the stated mixed-cube case, not all normal, modifier, topology or visual-parity families. No normal or geometry tolerance was changed, and no Blender encoding allowance was needed.
