# Editable polygon topology

Status: implemented foundation, partial operator coverage. September 9, 2026.

Native authoring needs polygon identity independently of triangle rendering. Mesh now carries an optional versioned topology source. Its vertices, edges, faces and face corners each have monotonic durable IDs. Corners own UVs and split normals; faces own material-slot indices. Edges retain seam/sharp flags across edits that preserve the edge. The compiled triangle mesh is evaluated output, with maps back to source vertex and polygon IDs.

Mesh-document schema 2 stores this source alongside its validated compiled output. The loader accepts older schema-1 documents. A legacy triangle mesh migrates without welding coincident or UV-seam vertices. All six native primitive factories now supply explicit polygon connectivity: cube quads; cylinder side quads/end n-gons; cone triangles/base n-gon; plane quads; sphere quad bands/pole triangles; torus quads. Parametric seam aliases connect source vertices while retaining separate corner UVs and normals. Earlier runtimes that only accept schema 1 cannot open new schema-2 editing projects; use the matching framework wheel.

Operations validate a copied source, compile it, and bind one new owned mesh revision. GUI commands publish one undo snapshot; public Aether commands use the serialized acknowledgement/rollback boundary. Component selection is persisted by source IDs in placement properties. Extrusion retains the selected cap's face/corner IDs. Inset retains the inner face/corner IDs. New topology receives new IDs. Undo/redo and document reopen restore the exact source.

## Implemented operator contracts

- Component move translates selected vertices, edge endpoints or face vertices in local meters. It recalculates affected corner normals and retains UV/material assignments.
- Region extrusion translates a selected open face region along the normalized sum of its face normals. It creates boundary side quads and retains the cap selection. Closed regions and invalid normals are rejected. Extrusion along per-vertex normals remains pending; individual-face extrusion is described below.
- Individual inset supports planar convex polygons, with even perpendicular local-space thickness and UV interpolation from the source face. It produces a border ring and retains the inner-face selection. Adjacent selected faces are inset individually. Nonplanar/concave/collinear-corner faces and collapsed offsets are rejected atomically. Connected-region inset and concave offset handling are pending.
- Planar simple concave polygons triangulate by ear clipping. Nonplanar quads use a stable diagonal for deformation. Nonplanar larger n-gons require splitting before deformation.

## Narrow acceptance evidence

The actual Designer GUI and Blender 5.2.1 LTS GUI each extruded the top of a 2-meter cube by 1 meter, then inset its top by 0.25 meters. Saved Blender files were read without authoring scripts. Axis conversion is Designer=(Blender.x, Blender.z, -Blender.y). Vertex positions, edge endpoints and oriented polygon cycles match exactly for both operations. Extrusion: 12 vertices/20 edges/10 faces. Inset: 16/28/14. GUI Undo/Redo/save was exercised.

Independent public Aether creation/extrusion also matches the GUI result. Inset replay checks rejection without mutation and duplicate request-ID idempotence. Evidence lives in the implementation artifacts directory, including request/acknowledgement logs and saved fixtures. These fixtures do not certify the full topology, visual-material, keymap, or authoring matrix.

## Remaining foundation work

Full new-edge attribute semantics, connected-region/concave inset, stronger malformed-source validation, non-manifold regional semantics, and all remaining topology operators require further work. This architecture checkpoint does not close a plan family.

## Visibility and selection checkpoint

Component overlays now query the same composed geometry/BVH as the rendered solid at each projected point. This avoids both back-face bleed-through and lost silhouette corners from approximate pixel-depth comparisons. Lines clip to the view and camera near plane, use perspective-correct screen sampling and cache the result between edits. Face mode displays authored polygon boundaries. Vertex/edge picks use only visible geometry, including silhouette points; Shift-add preserves the object selection. Playback suspends component overlays/edit picks.

The GUI, independent public Aether and Blender GUI also match a single vertex move from Designer [1,1,1] to [1.25,1,1]. Evidence: component-authoring-matrix.json in the implementation artifacts. Designer tests cover perspective/orthographic occlusion, a foreground occluder, silhouette picking, additive selection and near-plane clipping. Cmd/Ctrl+Shift+S now opens Save As; its new-project path was verified in the GUI. The native window title after Save As remains a known UI issue.

## Primitive and nozzle checkpoint

Cylinder cap inset followed by inward extrusion was performed in both GUIs and replayed independently through public Aether from blank geometry. The 8-sided radius-1/height-2 cylinder, inset 0.2 and extrusion -0.4 yields 32 vertices/56 edges/26 faces. Source connectivity is closed and its measured volume agrees with the analytic cavity volume. New extrusion side corners inherit boundary UVs; parallel cap edges inherit seam/sharp flags. Inconsistent selected-face winding and stale component IDs are rejected. Side UVs may require subsequent unwrap; no unwrap parity is claimed.

GUI and public Aether sphere (radius 1, rings 4, segments 8) and torus (major radius 1, minor radius .25, segments 8/4) also match Blender GUI topology. The comparison uses a bijective vertex map within 1e-6 meters and requires exact edges and oriented polygon cycles after mapping. Maximum Blender deviation is 6.7435e-7 meters (torus); GUI/Aether positions agree exactly. Decimal rounding was replaced because rounding boundaries are not a Euclidean distance predicate. Blender's local torus operator constructs vertices through mathutils rotation matrices; the native factory uses direct trigonometry. Cone (8 segments) and Plane (2×2 quads) also pass the updated GUI/Aether/Blender reference comparisons.

Current suites: 201 Designer tests and 103 targeted framework tests pass. Matching framework wheel was installed for the GUI checks. The broader authoring/visual/performance plan remains incomplete.


## Individual-face extrusion checkpoint (2026-09-09)

`extrude(..., individual=True)` and public `mesh.components_edit` operation `extrude_individual` create separate caps along each selected polygon's own unit normal. The GUI exposes this as **Extrude Each**, with a local-meter distance. All selected groups are evaluated in an unpublished document and bound as one mesh revision only after validation. Cap polygon/corner identities and corner attributes remain stable. New parallel cap edges inherit seam/sharp flags. Source vertex traversal is deterministic.

Designer also exposes component All/None buttons, A to select all, and Alt+A to clear. All includes occluded components on the active mesh. Selection uses the same persisted ID model as public Aether selection.

An independently authored 2 m cube with all six faces extruded by 0.25 m matches GUI-created Blender `Extrude Individual Faces and Move` exactly in vertex positions, edges and oriented polygons: 32 vertices, 60 edges, 30 quads. Designer GUI Undo/Redo/save and Aether replay were exercised. Cone (8 segments) and Plane (2×2 quads) now also pass GUI/Aether/Blender comparisons, bringing this limited matrix to nine fixtures. No full topology/operator or visual-material parity is claimed.


## Deletion, boundary fill and loose geometry checkpoint (2026-09-09)

Editable topology schema 2 permits loose edges and vertices and includes them in compiled vertex arrays. Schema-1 topology retains its previous compilation contract, so older saved projects keep their evaluated geometry. New deletion/fill edits upgrade their topology source to schema 2; older runtimes that lack this schema reject it. Mesh-document container schema remains 2.

`mesh.components_edit` now accepts `delete` and `fill`. Vertex deletion removes incident edges/faces; edge deletion removes incident faces and preserves other edges as wires. Face deletion removes newly unused edges and vertices belonging to deleted faces. The placement, transform, hierarchy and identity survive even when all geometry is deleted. Existing surviving edges retain identity, seam and sharp attributes. Inset/extrusion preserve pre-existing loose edges.

Fill accepts one simple planar closed loop of boundary/wire edges or their vertices. It rejects branches, disconnected loops, crossed/degenerate polygons, nonplanar loops and edges already shared by two faces. Boundary orientation determines the new face winding; inconsistent neighboring winding rejects the edit. The new face receives a new ID, material slot 0 and normalized planar UVs; existing edges retain their identities/flags. This is a face-creation operation, not grid fill or arbitrary ordered-vertex face creation. Blender UV/material parity is not certified by the geometry comparison.

The GUI provides Boundary, Delete and Fill Loop buttons plus Backspace/Delete/X and F shortcuts in component mode. Switching vertex/edge/face mode converts the selection. Undo/redo snapshots include the component mode, so undoing Fill restores the selected boundary in Edges mode rather than leaving a misleading face-mode selection. Loose geometry is visible and pickable in Object mode and remains editable in component mode; its overlay uses the same scene occlusion queries.

Four additional GUI/Aether/Blender comparisons pass exactly: cube top-face deletion (8 vertices/12 edges/5 polygons), boundary fill (8/12/6), deletion of a Plane edge (4/3/0), and deletion of all Cube faces (0/0/0, one retained mesh object). All thirteen saved comparisons pass. Actual Designer GUI checks cover deletion/fill Undo/Redo, face-edge-vertex mode conversion, loose endpoint picking/movement/Undo, Object-mode wire picking and clean-process reopening of individual extrusion, open-top, empty and wire projects.

Remaining work includes the full deletion matrix (the single-vertex Blender fixture is still pending), other topology operators, arbitrary new edges/vertices, grid fill/bridge, complete corner-attribute semantics, stronger malformed-source validation, modifiers, UV tools and full visual/performance acceptance. No complete plan family is closed by this checkpoint.

## Point and wire construction checkpoint (2026-09-09)

Public `mesh.components_edit` now supports `add_vertex` at a local-meter `position`, `connect` for exactly two selected vertices, and `extrude_vertices` by a local-meter `offset`. Designer exposes the same operations as Add Vertex, Connect and Extrude Vertices. Add Vertex works on an active mesh, including an empty one, and selects the new point. Connect creates a loose edge without splitting faces and selects the edge. Vertex-only extrusion preserves every old edge/face, duplicates each chosen point with a connecting edge, and selects the new endpoints. It does not extrude faces between selected edges. Parts are inherited by duplicated points; existing corner and edge attributes remain intact. Coordinates must be finite; duplicate edges, coincident connections, zero extrusion offsets and stale selections reject before publication. Nearby vertices are never silently welded.

The independently authored point/wire fixture adds points (0,0,0) and (1,0,0), connects them, and extrudes both by (0,1,0). Designer GUI, public Aether and Blender GUI agree exactly: four vertices, three edges, no faces. Blender used native merge-at-center to create the origin point, duplicate along X, Make Edge and Extrude Vertices along Z. Designer GUI undo/redo/save and persisted selection were verified. A separate cube-corner vertex deletion fixture also matches Blender exactly (7 vertices, 9 edges, 3 faces). Fifteen geometry fixtures pass; 202 Designer tests and 110 targeted framework tests pass. These supersede the earlier pending vertex-deletion and point-creation notes, without certifying the entire topology family or visual/UV/material parity.

## Edge extrusion checkpoint (2026-09-09)

`extrude_edges` sweeps selected boundary/wire chains or loops by a finite nonzero local-meter offset into quads. Shared endpoints create one shared new vertex. Existing faces/corners and surviving wires remain unchanged. New parallel edges inherit seam/sharp flags and become the selection, enabling repeated extrusion. New side polygons inherit the neighboring polygon's material slot (or slot 0 for wire-only input) and receive distance-based rectangular UVs. Interior edges already shared by two faces, branches, inconsistent boundary winding and degenerate sweeps reject atomically. This does not certify unrestricted nonmanifold edge extrusion or UV parity.

Boundary neighbors determine the new face winding. The first wire-only GUI comparison caught opposite winding despite identical vertex positions and edges. The fallback wire-chain orientation was corrected to reverse the base edge, then both Designer GUI and Aether authoring were repeated from their independent inputs. The saved Blender reference was unchanged. The corrected two-step extrusion of a one-meter edge produces 6 vertices, 7 edges and 2 quads with exact oriented connectivity in all three paths. The failed comparison is retained as evidence rather than treated as a pass. Sixteen fixtures now pass; 203 Designer and 113 targeted framework tests pass. GUI undo/redo/save passed; the earlier point-wire project also reopened in a clean process.

## Source validation checkpoint (2026-09-09)

Retained topology validation now checks complete record/container shapes, supported fields, canonical ASCII component prefixes with globally unique positive serials below next_id, numeric finite float32-representable vectors, boolean edge flags, material index range, and named-part/pivot consistency. Invalid records reject as document validation errors without repairing or mutating their input. Mesh-document validation also requires retained and compiled part names to agree. Both source schema versions remain supported; valid stored geometry is unchanged.

The compatibility probe loaded 104 assets across 45 saved projects, including the accepted X-wing, with zero failures. Twenty-seven additional malformed-input/atomic-restore cases pass. Latest full Designer suite: 204 passing tests; targeted framework suite: 140. Native project title updates were separately verified through the actual Save As UI and the event-thread request test.

## Edge loop/ring selection checkpoint (2026-09-09)

Public mesh.components_expand accepts loop or ring and uses the current persisted edge seeds. Designer exposes matching Loop and Ring buttons. Rings traverse opposite edges of quads, terminating at nonmanifold fans. Loops traverse opposite edges at regular four-edge vertices whose surrounding faces are all quads; boundaries, poles and non-quad neighborhoods stop traversal. This limited, explicit definition does not claim full Blender boundary-loop selection. Selection expansion does not bind a new mesh revision or alter geometry/attributes. Stale seeds reject without changing selection.

An 8×4 torus seed from (1.25,0,0) to (0.883883476,0,0.883883476) was selected in the actual Designer and Blender GUIs. Blender Select → Select Loops → Edge Loops / Edge Rings and the public Aether commands produce the same selected endpoint pairs: 8 loop edges and 4 ring edges. All 32 vertices, 64 edges and 32 oriented quads remain unchanged. Designer GUI ring Undo restored the single seed; Redo and Save preserved the ring. The separate selection matrix and GUI-saved input/reference files are retained. Latest suites: 205 Designer and 142 targeted framework tests pass; 16 geometry fixtures plus 2 selection fixtures pass.

## Smooth proportional movement checkpoint (2026-09-09)

Component movement accepts a finite nonnegative local-meter radius; zero retains selected-only movement. A positive radius applies smooth Euclidean falloff from the nearest selected source vertex, w²(3−2w), with w=max(0,1−distance/radius). Selected points retain full influence. IDs, edges, corner UVs and material assignments survive; affected corner normals are recalculated. The GUI exposes Radius (0=off) beside the three move amounts, and public mesh.components_edit accepts radius. This covers smooth unconnected movement; other falloff profiles, connected influence and proportional rotation/scale remain unfinished.

A 2×2-quad Plane with its center moved upward 0.5 m at radius 1.5 m was independently authored in Designer GUI, public Aether and Blender GUI. All nine vertices, twelve edges and four oriented quads match within 1e−6 m; GUI/Aether positions are identical and Blender maximum deviation is 2.7595e−9 m. Actual GUI Undo restores the plane; Redo and Save preserve the deformation. Seventeen geometry fixtures and two selection fixtures pass. Tests: 206 Designer, 148 targeted framework.

## Merge at center checkpoint (2026-09-09)

Designer Merge Center and public mesh.components_edit operation merge_center weld two or more selected vertices at their arithmetic mean. The earliest source vertex identity survives. The operation preserves placement and named-part metadata, retains surviving face/corner identities and UVs/material slots, removes collapsed edges and faces, and unions seam/sharp flags when edges coincide. Merging across named parts or producing a pinched polygon rejects atomically; other merge modes/by-distance and polygon splitting remain pending. Merging all cube vertices retains an editable loose point.

Actual Designer GUI edge selection converted to its two endpoints, Merge Center, Undo/Redo and Save were exercised. The same top rear cube edge was selected in Blender and merged at center. Independently created public Aether geometry matches both GUI results exactly: 7 vertices, 11 edges, 6 oriented faces. The matrix now contains 18 geometry fixtures and 2 selection fixtures. Full Designer suite: 207 tests; topology suite: 79 tests. UV semantics are retained and regression-tested, but Blender UV parity is not claimed.

## Component rotation and scaling checkpoint (2026-09-09)

Public mesh.components_edit supports rotate with three rotation degrees and scale with three factors. Both operate in local mesh axes around the arithmetic mean of the selected source vertices (including vertices expanded from selected edges/faces). Rotation applies X then Y then Z. A positive smooth radius weights rotation angles and scale-factor deltas from one; zero affects selection only. Surviving IDs, topology and UV/material data remain; affected normals are recalculated. Degenerate results reject before binding. Designer exposes Rotate Components / Scale Components and component-mode R/S shortcuts, with XYZ fields and an optional radius.

The GUI-authored merged cube reopened correctly in a clean process. All seven vertices were selected, rotated around local Y by 30 degrees, then scaled in X by 0.5; separate native outputs were saved. Independent public Aether construction and Blender GUI R Z 30 / S X 0.5 match the same selected-center pivot and oriented connectivity. GUI/Aether coordinates are identical; Blender errors are 4.9023e−8 m (rotation) and 5.9693e−8 m (scale). Scale GUI Undo/Redo/Save passed. Twenty geometry fixtures and two selection fixtures pass; 209 full Designer tests and 83 topology tests pass. This does not certify every axis combination, pivot mode, proportional falloff or visual/material parity.

## Interior-edge dissolve checkpoint (2026-09-09)

Public dissolve_edges and Designer Dissolve Edges join coplanar face regions across selected edges shared by exactly two faces. Boundary vertices/edges and surviving UV corners are retained, new face regions reuse their first source face ID/material, and orphaned interior points are removed. Existing loose geometry survives. Holes, nonplanar/nonmanifold regions and mixed material regions reject atomically. This limited command does not implement vertex dissolve, limited dissolve, face splitting or Blender’s optional redundant-boundary-vertex removal.

Actual GUI selection of the center-to-rear edge of a 2×2-quad plane, Dissolve Edges, Undo (restoring Edges mode), Redo and Save passed. Independently constructed Aether geometry and Blender GUI Dissolve Edges with Dissolve Vertices, Face Split and Preserve Quads disabled match exactly: 9 vertices, 11 edges, 3 oriented faces. Twenty-one geometry fixtures and two selection fixtures pass. Full Designer suite: 210 tests; topology suite: 88 tests.

## Centered quad loop-cut checkpoint (2026-09-09)

Public loop_cut and Designer Loop Cut accept one selected edge and traverse opposite edges across a manifold quad strip. Each reached edge is split at its midpoint, with shared source vertices and preserved seam/sharp flags on both halves; one half retains the original edge ID. Each quad splits into two quads. Existing corners are distributed unchanged; new midpoint corners interpolate UVs and available normals separately per face, preserving seams. Named part/material assignments remain. New center edges become the selection. Non-quad/nonmanifold strips, self-crossing cuts and interpolation across parts reject atomically. One centered cut is supported; multiple cuts and edge sliding remain pending.

Actual Designer GUI selected the center-to-rear edge of the original 2×2-quad plane and clicked Loop Cut; Undo/Redo/Save passed. Aether independently constructed and cut its own plane. Blender GUI used Ctrl-R over the matching edge, confirmed one cut and canceled Edge Slide at zero. The saved native results match exactly: 12 vertices, 17 edges, 6 oriented quads. Twenty-two geometry fixtures and two selection fixtures pass. The full Designer suite has 211 passing tests; the topology suite has 92.

## Multiple evenly spaced loop cuts (2026-09-09)

loop_cut now accepts integer cuts from 1 through 64. Every crossed edge is divided into cuts+1 equal intervals; shared vertices, winding, seam/sharp inheritance and per-corner UV/normal interpolation remain consistent when neighboring faces traverse edges in opposite directions. The Designer Loop Cut button now opens a Cuts (1-64) numeric dialog. Invalid counts reject without mutation.

Designer GUI authored two cuts across the upper strip of the original 2×2-quad Plane and saved the result. Public Aether independently reproduced it. Blender GUI Ctrl-R with numeric count 2, followed by canceling slide, matches: 15 vertices, 22 edges, 8 quads; GUI/Aether exact, Blender maximum deviation 3.9737e−8 m. All 23 geometry fixtures pass, plus two edge-selection fixtures. Full Designer suite: 212 tests; topology suite: 102 tests. Counts 2/3/8/64 additionally pass cube spacing, winding and volume regression checks. Edge sliding remains pending.

## Edge slide checkpoint (2026-09-09)

Designer Slide Edges and public slide_edges move one connected interior quad edge loop or boundary-to-boundary chain along adjacent rails. The finite factor is strictly between -1 and 1; endpoints that collapse faces reject. Positive direction follows the higher coordinate on the dominant local axis at a geometrically chosen seed, then propagates consistently across the chain. This rule is independent of face/edge ordering and corner starting index. Existing IDs, connectivity, corner UVs, materials and edge flags remain; affected normals recalculate. Branches, ambiguous rails, disconnected selections and non-quad neighborhoods reject atomically. Even/offset slide, UV correction and unrestricted topology remain pending.

Actual Designer GUI slid the two newly cut Plane edges halfway toward local z=0, exercised Undo/Redo, and saved edge-slide-fixed-gui.esk. Public Aether independently constructed and slid its plane. Blender GUI G G 0.5, Even/Flipped off, Clamp on and Correct UVs off moved the same line from Blender y=0.5 to y=0.25. All 12 vertices, 17 edges and 6 oriented quads agree exactly. The source-order direction regression was corrected before the accepted GUI/API comparison. Twenty-four geometry fixtures and two selection fixtures pass. Full Designer suite: 213 tests; targeted framework suite: 180 tests, including 111 topology tests.

## Bridge boundary loops and chains checkpoint (2026-09-09)

Designer Bridge Edges and public bridge_edges join exactly two separate boundary/wire loops or open chains with equal vertex counts. Nearest total endpoint distance chooses alignment subject to consistent adjacent-face winding. Existing geometry/IDs, corner attributes and edge flags remain; new quads receive unit-square UVs and the first boundary face material (or slot 0). Wire-only bridges use positive dominant-axis winding. Branches, unequal loops, interior edges, existing connecting edges, cross-part bridges and degenerate results reject atomically. Twist, subdivisions, merging, unequal-count bridges and UV interpolation remain pending.

Actual GUI removed the base from the previously GUI-authored point/wire fixture, selected both remaining chains, bridged them, and exercised Undo/Redo/Save. The first three-path comparison found opposite face winding despite identical positions/edges. The wire-only orientation was corrected; fresh GUI and Aether projects were authored against the unchanged Blender reference. The corrected bridge matches exactly: 4 vertices, 4 edges, one oriented quad. Blender Bridge Edge Loops used Open Loop, Merge off, Twist 0 and Cuts 0. Failed and corrected evidence is retained. Closed-cap bridging additionally restores a watertight cube with unchanged old attributes in kernel tests; closed-loop GUI comparison remains pending. All 25 geometry fixtures and 2 selection fixtures pass; 214 Designer / 189 targeted framework tests pass (120 topology).

## Single-segment vertex bevel checkpoint (2026-09-09)

Designer Bevel Vertices and public bevel_vertices truncate closed convex three-edge corners by a positive offset distance measured along incident edges. Shortened original edges retain their IDs/flags; surviving face/corner identities and materials remain, and new face corners interpolate the old UVs along each edge. Each removed corner is capped with a new triangle and planar UVs. New caps become the face selection. Boundary/nonmanifold, stale, non-three-edge and concave corners reject; distances that collapse an edge reject atomically. Other valences, profiles, segments and edge beveling remain unfinished.

Actual GUI created a size-2 Cube, selected all vertices, applied 0.25 m and exercised Undo/Redo/Save. Independent public Aether and Blender GUI Ctrl-Shift-B (Vertices, Offset 0.25 m, Segments 1, Profile 0.5, Clamp Overlap off) agree exactly: 24 vertices, 36 edges and 14 oriented polygons (six octagons and eight triangles). Kernel checks additionally verify single-corner bevel, volume removed, closed opposite-edge winding, UV interpolation and preserved flags. All 26 geometry fixtures and two selection fixtures pass. Full Designer suite: 215 tests; targeted framework suite: 199, including 130 topology tests. This remains an incremental authoring checkpoint; no complete plan family is closed.

## Plane bisect checkpoint (2026-09-09)

Designer Bisect and public bisect require all mesh faces selected and accept a local plane_point, nonzero plane_normal, keep both/negative/positive, and optional fill when retaining one side. Shared edge intersections create one retained source vertex; split edge flags and corner UV/normal interpolation survive. Existing face/corner IDs are retained where possible, duplicated corners receive unique IDs, and surviving wire segments/isolated points remain. Cuts through existing vertices avoid duplicate points. Fill requires a closed input surface and one simple boundary loop; disconnected concave face cuts and multi-loop fills reject rather than creating incorrect caps. Partial-face bisect and general concave/multiple-boundary fill remain pending.

Actual GUI created a Cube, selected all faces, set Point X=0.25, Normal X=1, Keep side=Negative and Fill cut=Yes, then exercised Undo/Redo/Save. Independent Aether construction and Blender GUI Bisect with plane (0.25,0,0), normal (1,0,0), Fill and Clear Outer enabled agree exactly: 8 vertices, 12 edges, 6 oriented faces. Kernel tests cover both-side splitting, both clear directions, exact half-volume, existing-vertex cuts, UV seams, edge flags, invalid requests and empty retained objects. All 27 geometry fixtures and two selection fixtures pass; 216 Designer / 210 targeted framework tests pass (141 topology). Full plan remains open.

## Single-edge bevel checkpoint (2026-09-09)

Designer Bevel Edge and public bevel_edges chamfer exactly one edge of a closed convex solid with planar faces, using a positive offset distance. The shared bisect kernel creates the cut and cap while retaining surviving source IDs, interpolated UV corners and edge flags. The chamfer inherits the first adjacent face material and becomes the selection. Offsets reaching neighboring vertices, nonconvex/open solids, coplanar edges and multiple selected edges reject atomically. Multiple segments, profiles, multiple-edge intersections and nonconvex beveling remain pending.

Actual Designer GUI selected the vertical Cube edge at local X=1/Z=1, applied 0.25 m, and exercised Undo/Redo/Save. Independent public Aether and Blender GUI bevel of X=1/Y=-1 (Offset 0.25 m, Edges, Segments 1, Clamp Overlap off) match: 10 vertices, 15 edges and 7 oriented faces. GUI/Aether positions agree exactly; Blender deviation is 2.22e−16 m. Kernel regression checks cover each of the 12 cube edges, removed volume, closed winding and source attributes. All 28 geometry fixtures and two selection fixtures pass; 217 Designer / 229 targeted framework tests pass (160 topology). Full plan remains open.

## Rounded edge bevel checkpoint (2026-09-09)

Bevel Edge now exposes Segments (1-64); public bevel_edges accepts the matching segments parameter. The selected edge is rounded with a circular profile between the two adjacent face normals, preserving the requested offset on both faces. Each segment produces one selected surface strip. The existing single-edge/closed-convex/planar-face restrictions remain; arbitrary profiles, multiple-edge intersections and nonconvex bevels remain pending.

Actual Designer GUI independently created a Cube, selected X=1/Z=1, entered Distance 0.25 m and Segments 3, applied and saved. Public Aether independently repeated it. Blender GUI used Offset 0.25 m, Segments 3 and Profile 0.5. The results match: 14 vertices, 21 edges, 9 oriented faces; GUI/Aether exact, Blender maximum deviation 1.1016e−8 m. Counts 2/3/8/16/64 pass circular-arc, volume and closed-winding tests. The volume helper now accumulates in double precision to avoid float32 summation error without widening tolerance. All 29 geometry fixtures and two selection fixtures pass; 218 Designer / 239 targeted framework tests pass (170 topology). No complete plan family is closed.
