# Merge by Distance

The native vertex toolbar exposes **Merge by Distance** with Threshold (m), default 0.0001, and Centroid (Yes/No), default Yes. Apply edits the selected mesh once; Cancel makes no change. Public `mesh.components_edit` exposes operation `merge_distance`, `threshold` and boolean `centroid` with the same defaults. Select durable vertex IDs with `mesh.components_select` first.

Distances are Euclidean in authored mesh-local meters, before placement transforms and modifiers. Only selected vertices in one named part participate; unselected vertices are not targets. A finite nonnegative threshold includes points exactly at that distance. Zero merges exactly coincident points. Selection must contain existing vertices; singleton/no-match input succeeds without a new mesh asset.

Visit selected vertices in source-document order. An unassigned seed groups all still-unassigned selected points within its threshold; previously grouped points are unavailable. This is a radius neighborhood, not a transitive connected-component collapse. For a pair, keep the earlier source identity. For larger groups, keep the member nearest the group mean, with source-order tie breaking. Centroid Yes moves this survivor to the arithmetic mean computed in double precision; No preserves its original position. The resulting source is compiled to the existing float32 renderer representation. The survivor and unmatched selected vertices remain selected.

Remap edges and face corners to survivor identities. Remove collapsed edges, adjacent duplicate polygon corners, polygons with fewer than three corners and duplicate polygon cycles (including reverse winding). Duplicate edges retain the first source edge identity and combine sharp/seam flags with logical OR. Duplicate faces retain the first source face and its corner attributes. Surviving UVs, material indices, corner IDs and face IDs remain owned by their source corners/faces; UVs are not averaged across a seam. Affected face normals are invalidated for recalculation. Unaffected corner normals remain. Nonadjacent repeated polygon vertices reject as a pinched face. Source compilation and the full retained modifier stack must validate before publishing any change. Rejection leaves the mesh, component selection and history intact.

GUI Undo/Redo and saved project reopening use the ordinary scene history and owned mesh document; no script is required to author the operation.

## Blender comparison scope

The independently GUI-authored Blender 5.2.1 LTS wire fixture uses a 0.00005 m vertex-only extrusion followed by a 0.0001 m merge with Centroid Merge enabled. Its result has four vertices, three edges and no faces. The input and output are saved separately; extraction only reads geometry. Blender's GUI exposes Unselected and Sharp Edges options, which are not implemented here.

Blender visits spatial-tree neighborhoods in an internal order. Designer currently uses durable source order. Overlapping neighborhoods with ambiguous seed ordering, complex pinched-face repair, cross-part welding and attribute interpolation beyond the stated preservation rules are not certified as Blender parity. The isolated-pair fixture must not be used to close the whole topology family.
