# Explicit custom-normal directions

`mesh.normals_direction_set` accepts a mesh `id`, distinct source `face_ids`, and a finite nonzero local-space XYZ `normal`. The vector is normalized, including very small or large finite inputs. Every corner of the selected faces receives that direction. Before editing, the current source normal policy is evaluated and baked so unselected corner directions remain unchanged. The result uses authored normals; this is explicit vector editing, not a retained per-face smoothing flag.

Geometry, component/corner identities, UVs, material slots, seams and existing sharp flags are preserved. Necessary sharp breaks are added with the same discontinuity handling used by normal transfer. The retained modifier stack is validated and preserved. Invalid vectors, missing/duplicate faces and invalid evaluated candidates are rejected before publication.

Designer exposes Normal X/Y/Z and Set direction in the Normals panel. Select a mesh, enter Face mode, select source faces, then open Normals. Coordinates are local to the mesh. Enter in a vector field applies the direction; Tab/Shift+Tab moves between controls. Each edit is one Undo/Redo operation and persists in a saved project. The expanded panel was inspected in the native GUI; all 32 faces of the 4-ring/8-segment sphere were edited and independently repeated through the public API.

450 framework tests and 258 Designer tests pass. Tests cover unselected-corner preservation, stack retention, geometry and UV retention, atomic errors, extreme-vector normalization, keyboard application, Undo/Redo and reopening. Actual native Undo, Redo, Save and clean-process reopening match exactly. A first rapid automated Redo–Save–Quit sequence reopened the earlier Smooth state; preserved logs show queued input exceeded the frame poll budget. Repeating with state confirmation between actions passes. Fast quit/input ordering remains a separate robustness risk, not a serialization failure demonstrated by the controlled test.

## Independent Blender GUI comparison

Start from the independently GUI-authored low-resolution Smooth sphere. Enter Edit Mode, select all faces, invoke Point Normals to Target, confirm, open F9 settings, enable Align and set Target to (0,0,1). Invert and Spherize stay off. Exit Edit Mode and Save As `blender-normal-direction.blend`. Read-only extraction reports evaluated geometry/normals; no hidden authoring generated this reference.

All 26 vertices, 32 oriented polygons, 112 corners and edges match. Maximum position difference is 1.192092896e-7 m. Designer stores exact (0,1,0); Blender's corresponding vectors differ by up to 1.023763694e-4. A separate automated exact-vector storage probe on the original Blender baseline measures a maximum 2.174630734e-4 displacement through its custom-normal codec. This diagnostic does not replace the independent GUI reference.

The user approved keeping Designer accuracy and accounting for Blender storage precision on 2026-09-10. The fixture therefore passes a measured encoding bound plus the existing 1e-5 arithmetic allowance, while retaining its failed raw-vector result in the evidence. Geometry tolerance is unchanged. This fixture-specific allowance does not apply to geometry, topology, UVs, or unrelated normal operations.

Per-face smoothing flags, per-corner selection, point-target/spherize/invert workflows, gradual fan-discontinuity variants and complete material-preview parity remain open.
