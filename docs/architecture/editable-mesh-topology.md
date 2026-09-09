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
