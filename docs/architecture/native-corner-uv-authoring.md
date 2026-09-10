# Native corner UV authoring

Status: projection, transforms, seams and island operations have accepted GUI comparison fixtures. Persistent pins and seam-driven conformal unwrap pass a pinned-plane GUI comparison; unpinned layout correction is undergoing GUI verification. The full UV family remains open.

## Authoritative data and atomic edits

UV coordinates belong to polygon corners in the retained topology document. Two corners referencing one vertex can have different UV coordinates. Public commands and the native Designer UV editor call `elysium.render.mesh_uv`; edits compile a new owned mesh revision, validate its complete prospective modifier evaluation, then bind the revision. Geometry positions, connectivity, stable component identities, custom normals, per-face materials, named parts, transforms and the retained modifier stack remain unchanged. Save/reopen and Undo/Redo store the corner UVs with the owned mesh. The legacy `mesh.uv_unwrap` now uses this same path rather than replacing render-vertex UVs while leaving topology stale.

## Projection

`mesh.uv_project(id, mode, face_ids?, yaw?, pitch?)` projects all source faces when `face_ids` is omitted. Explicit IDs must be distinct, nonempty and current. Planar projection bounds are normalized independently in U and V over the selected source vertices. A collapsed projection dimension stays zero. The axes are:

| Mode | U axis | V axis |
|---|---|---|
| planar_xy | +X | +Y |
| planar_xz | +X | -Z |
| planar_yz | -Z | +Y |
| planar / camera | camera right | camera up |

Yaw/pitch are radians. The camera basis uses Y up, with -Z as the pole fallback. The XZ mode corresponds to Blender Top under Designer=(Blender X, Blender Z, -Blender Y).

Cylindrical projection uses longitude `(atan2(z,x)+pi)/(2*pi)` and normalized Y height. Spherical projection uses that longitude and `acos(y/r)/pi`; vertices at the origin reject. Per-face periodic discontinuities lift low longitude values by one when needed; pole longitude is the mean of the face's non-pole corners. These are projection modes, not a seam-driven unwrap solver, and their complete Blender option comparisons remain pending.

## Transforms and seams

`mesh.uv_transform(id, corner_ids?, offset?, scale?, angle?)` scales selected UV coordinates around their arithmetic mean, rotates around that mean, then translates. Positive numeric UV rotation is **clockwise**, matching the observed Blender UV editor convention. Defaults are offset=(0,0), scale=(1,1), angle=0. Negative scale mirrors. Every selected corner must already have UVs. Invalid/stale IDs or non-finite inputs reject before publication.

`mesh.uv_seams_set(id, edge_ids, enabled=True)` changes source seam flags without unwrapping or moving UVs. `mesh.uv_get` returns face/corner identities, coordinates and marked seam edge identities.

## Native controls

Select a mesh and click **UVs** in the 3D Scene toolbar. Projection buttons expose XY, XZ, YZ, Cylinder and Sphere. Face mode projects only selected faces; Object mode projects all. The checker chart fits the UV coordinates together with the 0–1 tile. Clicking a point toggles all corners at that UV coordinate. All/None select or clear corners. Move U/V, Scale U/V and Angle (clockwise degrees) are applied with Transform or Enter. Mark/Clear seam uses the scene's current selected source edges in Edge mode. Close or Escape dismisses the editor. Each successful mutation is one undo transaction.

## Verified fixture and remaining work

Independent GUI / Aether / Blender GUI plane projection and scale=0.5, clockwise rotation=90°, offset=(0.25,-0.5) pass. Geometry (4 vertices / 4 edges / 1 oriented polygon) matches exactly, GUI/Aether corner UVs match exactly, and Blender's maximum UV error is 5.960464477539063e-8 at tolerance 1e-6. Native Undo/Redo and clean-process reopening pass. The first comparison exposed the opposite rotation convention and was corrected; pre-correction evidence is retained.

The extensions below add island operations, pins and a bounded seam-driven unwrap solver. Smart/cube projection, stitching, texture distortion review, richer selection, drag transforms, material texture display and broader projection/attribute comparisons remain required by the approved plan.

## Island authoring extension

`mesh.uv_islands_get` identifies connected face sets sharing mesh edges whose endpoint UV coordinates match exactly. A seam flag does not split already-continuous UVs; a UV discontinuity does. Faces with unassigned corner UVs are excluded. Each returned island includes face/corner IDs and bounds. Native **Island** expands selected corner seeds to their complete islands.

`mesh.uv_normalize_scale` scales complete selected islands about their corner means so UV area / local source surface area is equal, while preserving the total selected UV area. Surface area and UV area use the retained polygon's triangulation. Uniform scaling preserves each island's shape and orientation; zero-area islands reject atomically. Unselected islands remain unchanged. Native **Normalize scale** invokes this command on islands touched by selected UV corners.

`mesh.uv_pack` packs complete selected islands inside the 0–1 tile using height-sorted bounding boxes, one common scale, and no rotation. It preserves island shape, winding and relative scale. **Margin is padding around each island**: adjacent boxes have twice the margin, while the tile border has one margin, matching Blender's Fraction mode in the verified fixture. Values satisfy 0 <= margin < 0.5; impossible/degenerate arrangements reject. Unselected islands remain unchanged and are not treated as obstacles. Native **Pack** uses the **Pack margin (UV)** field. This deterministic shelf packer does not promise globally optimal occupancy or the full Blender concave/convex/rotation/pinned/UDIM packing options.

The two-plane comparison starts with 2 m planes at X=0 and X=3 in one mesh. Designer uses native Plane → Array(count=2, offset X=3) → Apply stack. Blender duplicates the plane in Edit Mode by X=3. Both project from Top to UV bounds. Select the left island and double U scale; select both, normalize, then pack at margin 0.05. Blender uses Average Islands Scale, then Pack Islands: Bounding Box, Scale on, Rotate off, Margin Method Fraction, margin 0.05, Lock Pinned/Merge Overlapping off, Closest UDIM.

Three independent GUI/Aether/Blender stages pass: selected-island scale, normalization, packing. Geometry is 8 vertices / 8 edges / 2 oriented quads. Maximum UV deviations are 1.549721e-7, 1.162025e-7 and 1.556959e-7 respectively at tolerance 1e-6. Each normalized island has area 0.6; packing preserves a common scale and a 0.10 gap. Native Undo/Redo and clean-process reopening pass. The initial packer used one margin between neighbors; that failed convention was corrected and retained as pre-correction evidence.

Native component view now draws unselected marked seam edges in red; selected edges retain selection highlighting. A separate plane seam/single-corner fixture matches all geometry, UVs and four seam endpoint pairs exactly across the three authoring paths, including Clear Seam and GUI Undo preservation.

Full seam-driven unwrap, smart/cube projection, stitching/pinning, distortion/material texture display and broader packing/normalization variants remain open. These fixtures extend the UV foundation and do not close the complete UV family.

## Persistent pins and conformal unwrap candidate

`mesh.uv_pins_set(id, corner_ids, enabled=True)` sets or clears a boolean pin on selected corners. Every selected corner must have a UV coordinate. Pins use retained topology schema version 3; existing version 1 and 2 documents remain readable. Older versions reject the new field, and pinning promotes the document to version 3. Schema version 3 survives subsequent topology and modifier operations. Existing copied corners retain their pins; newly interpolated corners are unpinned. `mesh.uv_get` includes a boolean `pin` for every corner, defaulting to false when absent in the document. Save/reopen and Undo/Redo retain pins.

Native **Pin** and **Unpin** operate on selected UV corners. Pinned points receive red outlines, and the editor shows the number of pinned corners. Explicit manual transforms, projections, Normalize scale and Pack can move pinned UVs; pins constrain the unwrap solver. A packing option to lock pinned islands remains unimplemented.

`mesh.uv_unwrap_seams(id, face_ids?, fit_tile=True, margin=0.02)` cuts the selected source surface at marked seam edges and solves least-squares conformal charts. Omitted face IDs mean all source faces. Native **Unwrap** uses selected faces in Face mode and all faces in other modes. It selects the affected corners after success. This is separate from the legacy projection command `mesh.uv_unwrap`.

Each chart must be a consistently oriented, edge-manifold disk with one simple boundary and no holes. Closed surfaces need seams; an open cylinder still needs a longitudinal seam. Current limits are 50,000 selected corners and 2,048 boundary edges per chart. Conflicting pins joined across an uncut edge reject. At least two distinct UV anchor locations are required: authored pins supply them when possible, and a chart with fewer than two pinned nodes gets deterministic anchors using source distances. Entirely unpinned selections align each chart to a minimum-area bounding rectangle and fit the unit tile using the shared no-rotation shelf packer. Margin is per-island UV padding. Native **Fit tile: on/off** exposes the option, and **Pack margin (UV)** applies to both Unwrap and Pack. Turning Fit tile off retains the raw solved strip. If any chart is pinned, tile fitting is skipped for the selection: pins remain fixed and free charts are placed beside the pinned charts. Multiple pinned charts can overlap because their coordinates are authored constraints. Unselected faces are unchanged and are not treated as packing obstacles.

The solver uses the retained polygon triangulation, area-weighted conformal equations and sparse LSQR with finite-result and convergence checks. It accepts an exact zero solution as success. It rejects collapsed/flipped UV triangles and a self-intersecting chart boundary. It computes all charts and validates the complete prospective modifier stack before publishing, so a rejected solve preserves the source and undo history. Pinned corner coordinates remain exactly as authored. Local object coordinates determine surface distances; object scale is not implicitly applied.

Code fixtures cover restoration of distorted plane UVs with pins, a folded plane, a closed cube requiring seams, an open cylinder requiring a longitudinal seam, conflicting pins, reversed fully pinned UVs, selected-face isolation and an exact-zero free-corner solution. Native editor integration fixtures cover Pin/Unpin, Undo/Redo, serialization and atomic failure. The pinned-plane comparison passes independently through Designer GUI, public Aether and Blender GUI. Distorted input UVs, geometry and pins match exactly; maximum solved UV deviation is 5.960464499743523e-8. Native Undo/Redo, Unpin/Undo and clean-process reopening pass. The uncut cube rejects without mutation or an Undo entry in the actual GUI; marking all twelve source edges recovers six charts. Its initial raw strip layout differed visibly from Blender and motivated automatic unpinned chart alignment and tile fitting. The corrected unpinned GUI comparison is still pending; exact Blender island orientation/order and all packing variants are not certified.

Measured unwrap-only times on this Mac were 0.058 seconds for 100 quads, 0.234 for 400 and 0.943 for 1,600. The operation is synchronous. These measurements do not establish GUI responsiveness, maximum-size performance or rendered frame rate. Blender algorithm variants, holes, broader chart geometry and matched material/distortion display remain outside this candidate's acceptance.
