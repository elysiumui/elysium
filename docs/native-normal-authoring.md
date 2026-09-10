# Native surface normal authoring

## Retained behavior

Editable topology version 4 optionally stores `shading = {mode, angle, respect_sharp}`. Mode is `flat` or `smooth`; angle is a finite number from 0 to 180 degrees; respect_sharp is boolean. Earlier topology versions remain readable, and cannot contain this policy. Removing the policy returns to the currently retained corner normals, including the existing flat fallback for missing normals. It does not restore normals discarded by an earlier geometry edit.

Flat mode uses one normalized source-polygon normal for every corner. Smooth mode combines polygon normals weighted by each incident corner's angle. It joins corners only across consistently oriented, two-face edges whose face-normal angle is at most the configured limit. Marked sharp edges split the fans when respect_sharp is true. Boundary/nonmanifold edges and disconnected components do not join. UV seams and coincident positions do not merge source vertex identities. Opposing contributions that cancel use the local face normal.

The policy is evaluated during topology compilation, so geometry edits and supported modifier outputs recompute normals. Source positions, component IDs, UVs, pins, seams and material assignments remain independent. Custom corner vectors remain retained while overridden. Policy edits publish only after source and evaluated geometry validate; invalid values or stale edge selections leave the placement unchanged.

## Public tools

- `mesh.normals_set(id, mode, angle=180, respect_sharp=true)` accepts authored, flat or smooth for the entire source mesh.
- `mesh.normals_get(id)` reads policy, sharp edge IDs, compiled source normals and their source vertex identity mapping. It does not evaluate modifiers or world transforms.
- `mesh.edges_sharp_set(id, edge_ids, sharp=true)` marks/clears selected source edge flags without changing UV seam flags.

## Native UI

Select a mesh, open 3D Scene → Normals. Enter the smooth angle, choose respect/ignore sharp, then Smooth. Flat and Authored switch the whole-mesh policy. Mark/Clear Sharp use the source edges selected before opening the panel in Edge mode. Disabled controls explain the prerequisite. Tab/Shift+Tab moves between fields/actions, Enter activates the focused action (or Smooth from the angle field), and Escape closes. Each successful mutation is one Undo transaction.

## Verification and limits

393 focused framework tests and 250 Designer tests pass. Actual native Flat/Smooth, keyboard activation, Mark/Clear Sharp on 992 sphere edges, Undo/Redo, Save and clean-process reopening were exercised. The independent public API replay matches all source geometry, policy and normals exactly.

The existing independently GUI/API-authored radius-1 sphere with 4 rings and 8 segments was used for the three-way Smooth fixture. Blender GUI Shade Smooth produces identical oriented connectivity: 26 vertices and 32 polygons. Position deviation is at most 1.1921e-7 m (existing geometry tolerance 1e-6); normal-vector deviation is at most 4.1656e-6 (normal tolerance 1e-5). The denser 16-ring/32-segment sphere has 3.5848e-6 normal deviation, but 1.2813e-6 position deviation, slightly beyond the existing geometry gate; this remains open.

This accepts one whole-mesh Smooth operation fixture. Per-face shading flags, normal-vector editing, weighted-normal controls, independent Blender angle/sharp variants, broader topology cases, matched studio visuals and full normal-family acceptance remain open. Blender's version-matched primary reference for angle-weighted vertex normals is [mesh_normals.cc](https://github.com/blender/blender/blob/9e2066aef7ef/source/blender/blenkernel/intern/mesh_normals.cc).
