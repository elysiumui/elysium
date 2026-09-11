# Retained material color graphs

A material slot may store `color_graph` alongside its surface and owned base-color image. This checkpoint supports constant-color graphs with Color, Value, Add, Multiply and Mix nodes. It does not yet implement the full Hypershade surface/texture graph contract.

The graph contains exactly `schema_version: 1`, positive integer `next_id`, a `nodes` list (at most 64 nodes), and `output` (a current node id or null). Every node has exactly `id`, `name`, `kind`, `value`, and `inputs`. IDs are monotonic `n1`, `n2`, etc.; removal never reuses an ID. Names contain 1–100 nonblank characters and need not be unique. Connections use stable IDs.

Color stores three linear RGB numbers in [0,1]. Value stores a scalar in [0,1]. Mix stores its literal factor in [0,1]. Add/Multiply store an unused scalar in [0,1], initially zero. New Color and Value nodes default to 0.5; Mix defaults to factor 0.5. Invalid or nonfinite values reject rather than silently clamp. Booleans are not numbers for this contract.

Only Add, Multiply and Mix accept `a` and `b` input links. Unconnected A is RGB zero; unconnected B is RGB one. Scalars broadcast to RGB. Add computes A+B; Multiply computes A*B; Mix computes (1-factor)*A+factor*B. Every evaluated result is clamped to [0,1]. A linked Value may also be the output, broadcasting to RGB. All nodes, including disconnected ones, are validated for cycles, missing references, valid fields and values before the material is published.

A non-null output overrides the slot's surface base color before the existing image multiplier. Other material channels, face assignments, UVs, normals, source geometry and modifiers remain unchanged. Null output restores the numeric/inherited surface base color while retaining the graph. Removing a node removes references to it, using input defaults; removing the output node clears the output. `material.clear` removes the slot table, including graphs, as part of its reset-all behavior.

## Native UI

Select a mesh and open Materials. Choose the intended slot with Previous/Next, then Color graph. Add nodes with the top-row controls. Select a node in the list, enter its name and RGB/Value/Factor fields, and Apply node (or Enter). Input A/B cycle through valid sources and the default; self/dependent nodes that would create cycles are excluded. Use as base color assigns the selected node. Clear output restores surface RGB; Remove node deletes the selected node and its references. Close returns to the scene. The node list provides Earlier/Later navigation for more than 12 nodes. Changes use the shared scene history, persist on Save and participate in native Export App.

## Public Aether

Every operation takes object `id` and stable `slot_id`:

- `material.color_graph_get` returns `graph` and evaluated `base_color` (null if there is no output).
- `material.color_node_add` takes `kind`, returning the graph and new `node_id`.
- `material.color_node_update` takes `node_id`, optional `name`, `value`, and `inputs`. Supplied inputs replace the whole map; omitted inputs remain unchanged.
- `material.color_output_set` takes `node_id`, including null to clear the output.
- `material.color_node_remove` takes `node_id`.

The existing prospective material/source/modifier validation runs before publication. Invalid operations leave material data unchanged. Graph reads are read-only; mutations use the normal command/history path.

## Independent acceptance

Use separate GUI and Aether copies of the earlier native mixed-shading cube: five Hull faces and one flat top face assigned Red. On Red, add Color named Red with RGB (1,0,0), Color named Blue with RGB (0,0,1), and Mix with factor 0.25. Link A to Red and B to Blue. Assign Mix as base color. Expected linear output is (0.75,0,0.25). Native Undo restores the pre-output graph; Redo followed by Save/Quit and clean reopening restores the exact assigned state.

In the independently GUI-authored Blender 5.2.1 LTS material cube, use the Base Color socket picker to connect Mix (Legacy), set mode Mix, Clamp on, factor 0.25, Color1 linear RGB (1,0,0), Color2 (0,0,1). Save the Blender project and inspect it read-only. Blender's literal colors are compared semantically to native Color nodes; graph structures are not claimed identical. Geometry, oriented faces, edges, material assignments, smooth flags and Mix inputs/factor match exactly. GUI and Aether material/source/normal results agree exactly.

Native Export App uses a new folder, no close object, logical size 128, scale 1, end frame 0 and hold 0. The exported graph/table and source topology match exactly. Its actual frame has 453 visible purple pixels. No external script manufactures the export. The saved matrix has 13 passing checks. Relevant regressions: 503 framework and 267 Designer tests pass.

Final radiometric/color-management/lighting comparisons, texture-driven graph inputs, other surface channels, spatial wire editing and broader node/large-graph GUI acceptance remain open. Evidence is preserved in the plan's `evidence/material-graph-20260910/` directory.
