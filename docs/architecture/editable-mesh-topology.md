# Editable polygon topology

Status: implemented foundation, partial operator coverage. September 9, 2026.

Native authoring needs polygon identity independently of triangle rendering. Mesh now carries an optional versioned topology source. Its vertices, edges, faces and face corners each have monotonic durable IDs. Corners own UVs and split normals; faces own material-slot indices. Edges retain seam/sharp flags across edits that preserve the edge. The compiled triangle mesh is evaluated output, with maps back to source vertex and polygon IDs.

Mesh-document schema 2 stores this source alongside its validated compiled output. The loader accepts older schema-1 documents. A legacy triangle mesh migrates without welding coincident or UV-seam vertices. All six native primitive factories now supply explicit polygon connectivity: cube quads; cylinder side quads/end n-gons; cone triangles/base n-gon; plane quads; sphere quad bands/pole triangles; torus quads. Parametric seam aliases connect source vertices while retaining separate corner UVs and normals. Earlier runtimes that only accept schema 1 cannot open new schema-2 editing projects; use the matching framework wheel.

Operations validate a copied source, compile it, and bind one new owned mesh revision. GUI commands publish one undo snapshot; public Aether commands use the serialized acknowledgement/rollback boundary. Component selection is persisted by source IDs in placement properties. Extrusion retains the selected cap's face/corner IDs. Inset retains the inner face/corner IDs. New topology receives new IDs. Undo/redo and document reopen restore the exact source.

## Implemented operator contracts

- Component move translates selected vertices, edge endpoints or face vertices in local meters. It recalculates affected corner normals and retains UV/material assignments.
- Region extrusion translates a selected open face region along the normalized sum of its face normals. It creates boundary side quads and retains the cap selection. Closed regions and invalid normals are rejected. Separate normal/individual extrusion modes are pending.
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

GUI and public Aether sphere (radius 1, rings 4, segments 8) and torus (major radius 1, minor radius .25, segments 8/4) also match Blender GUI topology. The comparison uses a bijective vertex map within 1e-6 meters and requires exact edges and oriented polygon cycles after mapping. Maximum Blender deviation is 6.7435e-7 meters (torus); GUI/Aether positions agree exactly. Decimal rounding was replaced because rounding boundaries are not a Euclidean distance predicate. Blender's local torus operator constructs vertices through mathutils rotation matrices; the native factory uses direct trigonometry. Cone and plane connectivity have regression coverage; their updated GUI reference fixtures remain pending.

Current suites: 196 Designer tests and 93 targeted framework tests pass. Matching framework wheel was installed for the GUI checks. The broader authoring/visual/performance plan remains incomplete.
