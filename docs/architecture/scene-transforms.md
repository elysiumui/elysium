# Scene transforms, spaces, collections and views

Status: implemented (NP-05, NP-06). September 13, 2026.

## Matrix order

Object transforms are Y-up meters with XYZ Euler degrees. `scene.matrix` is `T(location) · T(pivot) · Rz Ry Rx · S · T(-pivot)`; `pbr._euler_rot(x, y, z)` builds `Rz Ry Rx` and `scene.euler_degrees` inverts it (gimbal lock folds X into Z). A child's world matrix is `parent_world · parent_inverse · matrix(child)`, where `parent3d.inverse` retains the affine offset recorded at parenting time (`scene.parent_matrix(placements, p)` returns `parent_world · parent_inverse`, the frame the local matrix is expressed in).

## The three spaces

`scene.SPACES = ("local", "parent", "world")`; object tools use lower-case names (`mesh.components_transform` keeps its capitalised Global/Local/Parent enum).

| Space | `location` means | `rotation` / `scale` mean |
| --- | --- | --- |
| local | the stored channel | the stored channels |
| parent | position of the object's local origin in the parent frame (`matrix(p)[:3, 3]`) | the stored channels |
| world | world position of the local origin (`world[:3, 3]`) | decomposition of the world linear part |

Origin versus pivot: the origin is `location + pivot − L·pivot`, so setting an origin position in parent or world space writes `location = origin − pivot + L'·pivot` using the (possibly updated) rotation/scale. Rotation and scale always act about the pivot, whose world position stays fixed when only rotation or scale change.

`scene.decompose_linear` splits a 3×3 linear part into a proper rotation and per-axis scale (a negative determinant is folded into the X scale). If the residual is not orthonormal it raises `ValueError("Transform would introduce shear; use local space or apply transforms first")`; `describe(space="world")`, world-space `set_transform` and the rotation/scale deltas below reject rather than approximate. A location delta does not decompose anything, so it does not reject (see the Deltas section).

Do not match on the shear message. `describe` and `set_transform` raise `decompose_linear`'s wording verbatim, but `transform_delta` composes its own remedy in `scene._shear_message`: it re-runs the same delta in the other two spaces and names only a space it verified (`"…; use local or parent space or apply transforms first"`), falling back to `"…; apply the parent chain's transforms first"` when no space works. The stable part is the `Transform would introduce shear;` prefix.

`scene.set_transform(placements, p, values, space=...)` validates every requested channel, converts to local channels, then validates a deep-copied candidate (`update` + `world_matrices`) before writing. `space="local"` is exactly `scene.update`.

## Deltas (the gizmo contract)

`scene.transform_delta(placements, p, group, amount, *, axis=None, space="world", plane=False, free_axis=None)` is the single implementation the Designer gizmo and `scene.transform_delta` share. The direction `v` is the unit axis, the normalised `free_axis` expressed in the chosen space, or (plane) the free direction with the axis component removed.

Frame `F` is the basis of the chosen space in world terms — the identity (world), the parent frame (parent) or the object's own world frame (local) — and how it is taken depends on the group, because only two of the three decompose their result:

- **rotation and scale** take `F` from `scene.decompose_linear`, which insists on a rigid frame and rejects a sheared chain. Unchanged.
- **location** takes `F` from `scene._axis_directions`: the frame's columns normalised (with the same reflection-into-scale convention), which agrees with the rotation whenever the chain is shear-free and still answers when it is not. On a sheared chain those columns are *not* a rotation — they are unit directions that are no longer mutually orthogonal, which is all a move needs. Only a degenerate (non-invertible) chain rejects, with `"Transform is degenerate"`.

| group | constraints | math (`Pl` = parent linear, `L` = local linear) |
| --- | --- | --- |
| location | axis or free_axis required; plane needs an axis | `loc' = loc + Pl⁻¹ · (F v / ‖F v‖) · amount` |
| rotation | axis or free_axis required; plane rejected | `L' = Pl⁻¹ · rot(F v, amount) · Pl · L`, location unchanged (pivot fixed) |
| scale | no axis = uniform; plane = the two other axes; amount 0 rejected | `L' = Pl⁻¹ · (F diag(f) Fᵀ) · Pl · L` |

Normalising `F v` keeps `amount` a world distance on a sheared chain, where the columns of `F` are skewed; on an unsheared one it is a no-op, so the move is unchanged from before. `L'` (rotation and scale only) is decomposed — shear rejected, naming a space that was verified — and committed atomically; the result carries the stored transform and the new world matrix. Non-finite amounts, unknown axes/spaces/groups, a zero free axis and plane-without-axis all reject without mutation.

**Gizmo note (behaviour change).** A location drag used to raise on a chain no rigid frame can describe (a non-uniformly scaled ancestor above a rotated one); it now commits in all three spaces. Rotation and scale drags still refuse there.

## Apply subsets

`scene.apply_transform(placements, p, *, location=True, rotation=True, scale=True)` resets the chosen channels (location → 0, rotation → 0, scale → 1; pivot → 0 only when all three are applied), computes `B = inv(M_new) · M_old` and bakes it into positions, inverse-transposed normals, part pivots and the topology source, flipping winding when `det(B) < 0`. Children receive `inverse' = inv(M_new) · M_old · inverse`, so world geometry, child world matrices and UVs are unchanged. Taper is baked and removed; the modifier stack is validated against the new source. Applying nothing, or applying to a scene group, rejects.

## Collections and visibility

`render/collections.py` keeps `AppWindow.scene_collections`: `{"schema_version": 1, "next_id", "items": [{"id": "col<n>", "name", "parent", "members", "visible", "exclude"}]}`. Names are unique case-insensitively, nesting is acyclic, an object belongs to at most one collection, and members are scene entity ids (never names or indices). `excluded_entities(window, placements)` returns the members of every collection that is hidden or excluded or has such an ancestor; `scene.compose/frame/render` take `excluded=` and skip those objects while their transforms keep driving visible children. Export, render jobs and snapshot PNGs pass the set. `prune` drops dangling members on load and after `placement.remove`; `placement.duplicate` puts the copy in the source's collection.

## View presets

`scene.VIEW_PRESETS` (yaw, pitch) for `pbr.render_mesh`'s orbit camera:

| name | yaw | pitch | camera at | screen right | screen up |
| --- | --- | --- | --- | --- | --- |
| front | 0 | 0 | +Z | +X | +Y |
| back | π | 0 | −Z | −X | +Y |
| right | π/2 | 0 | +X | −Z | +Y |
| left | −π/2 | 0 | −X | +Z | +Y |
| top | 0 | π/2 | +Y | +X | −Z |
| bottom | 0 | −π/2 | −Y | −X | −Z |

These match Blender's numpad views under Designer = (Blender X, Blender Z, −Blender Y). `scene_views.view_preset(current, name)` keeps target, distance and orthographic scale and switches to orthographic; `"perspective"` restores the default orbit angles. `view_name(camera)` returns the axis view an orthographic camera matches exactly, else `None`.

## Bookmarks

`AppWindow.scene_bookmarks` stores up to 64 `{"id": "b<n>", "name", "camera"}` entries with unique names; `bookmark_set` replaces an existing name, `bookmark_go` (by id or name) restores the camera and enables the 3D scene view, `bookmark_remove` deletes.

## Reference images

`AppWindow.scene_references` stores one owned PNG (via `material_image.import_image`) per axis view with `opacity` (default 0.5), world-anchored `offset` `[u, v]` and `size` `[w, h]` in meters (default 2 m tall at the image aspect). `scene.render(..., reference=scene_views.reference_for_camera(window))` blends it — nearest sampling, alpha = texel alpha × opacity — onto background pixels of the matching orthographic axis view before the grid is drawn, so grid lines and geometry stay on top. It is drawn only when `grid=True`; exports, render jobs and snapshots never include it, and any other camera ignores it.

## Solid-mode material colours

Solid shading stays a neutral viewport override for inherited slots and for objects without a slot table (byte-identical output, pinned by a test). Faces whose slot has explicit parameters or a colour-graph output are tinted with `clip(255 · srgb(base_color) · (0.65 + 0.35·max(n·l, 0)))` from `mesh_materials.solid_colors`. Material mode, the exporter and render jobs already evaluate slots through `render_materials`; the runtime plays pre-rendered frames. Known gaps, not fixed here: `mesh.render_final` / `_build_mesh_for_placement` ignore slots, and legacy `pbr_ao_map` / `pbr_emissive_map` and `mesh_part_textures` have no slot channel.

## Parameterized primitives

`primitives.PARAMETERS["Cone"]` gains `radius2` (top radius; 0 keeps the apex, positive builds a frustum) and `primitives.CHOICES` adds `cap_fill` (`ngon`, `trifan`, `nothing`) for Cone and Cylinder. `primitives.attach` is the single metadata write: it binds the built mesh, clears a stale component selection and records `{"kind", "parameters", "mesh_key", "geometry_hash"}`. `settings` locks regeneration to the geometry hash (positions and connectivity), so UV, normal and material publishes keep it available, while legacy metadata without a hash keeps the `mesh_key == mesh_kind` rule; optional keys absent from older metadata read as their defaults.

## GUI shared-function contract

The Designer calls the same functions the public tools call: `scene.set_transform` / `scene.describe` for the inspector's space selector, `scene.transform_delta` for the gizmo, `scene.apply_transform(..., location=, rotation=, scale=)` for the apply menu, `collections.*` for the outliner, `scene_views.view_preset` / `bookmark_*` / `reference_*` for view menus. Every one validates a complete candidate before writing and raises `ValueError` without mutating on failure.
