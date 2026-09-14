# Document-owned mesh assets

Status: implemented (NP-03). September 13, 2026.

Authored geometry is owned by the document that references it. `pbr.MESH_LIBRARY` is now a read-only table of preset factories; the database is `elysium.render.mesh_document.MeshStore`. Preset names are never written back into the library (store keys — owned revisions and named registrations alike — are mirrored there only as a [deprecated read-through shim](#deprecated-mesh_library-shim) that carries no geometry), and a fresh process rebuilds every store from the saved document alone.

## Key namespaces

| Key shape | Meaning | Lookup |
| --- | --- | --- |
| `mesh:<label>:<uuid>` | An owned, immutable revision created by `mesh_document.bind`. | Current store, process store, then every other registered store (uuid keys are globally unambiguous). Also indexable through the deprecated `MESH_LIBRARY` shim while a live store holds it. |
| named legacy key (`"Cube"`, `"butterfly"`) | A preset name, or a name registered by `mesh.register_from_file` (never a preset name, in any spelling). | Exact key in the current store and the process store, then the preset library (exact, then case-insensitive), then a case-insensitive match in the current store alone. Never searched across other documents' stores, and a preset is never shadowed by a case variant. Also indexable through the deprecated shim while a live store holds it, unless a genuine factory already owns the name. |
| `file:<path>` | Legacy on-disk import, parsed on every resolve. | Read directly; the headless loader converts it to an owned asset (below). |
| preset (`Sphere`, `Cube`, ...) | Read-only factory in `pbr.MESH_LIBRARY`. | Last fallback of `resolve`. |

## MeshStore and discovery order

`MeshStore` holds `{key: pbr.Mesh}` behind an `RLock`, memoizes each key's asset hash (`semantic_hash(to_json(mesh))`) and geometry hash (positions and connectivity only), and drops both whenever the key is rewritten. Every store registers itself in a weak registry so owned keys can be resolved from worker threads that did not inherit the context variable, and across documents open in one process.

Everything a store holds is canonical: `put(key, mesh)` stores `from_json(to_json(mesh))` (float32/int32 arrays), which is exactly what `restore` rebuilds from a saved document, so the asset hash recorded on save always matches a reload. Callers may hand over float64 meshes (Designer deformers register `pbr.Mesh(verts=<float64 math>, ...)` under derived names; third-party importers vary) without thinking about it; `capture` adopts referenced presets and legacy factories the same way and serializes the stored copy, never the raw factory output. `snapshot_store(placements, *, source=None)` builds a private store holding every key the placements reference, sharing the immutable canonical objects of the source store and normalising anything that only a factory provides.

Which store a store-less call uses is decided by `mesh_document.default_store()`:

1. inside `with mesh_document.using(owner)`, the owner's `mesh_store` attribute (looked up lazily, so a designer may swap its store inside the block), or the store itself when a `MeshStore` was passed;
2. otherwise `_PROCESS_STORE`, the compatibility fallback used by the GUI Designer and by `SimpleNamespace`-based tests.

`resolve(kind, *, store=None)` follows: `file:` import → exact key in `store or default_store()` → exact key in the process store → (owned keys only) exact key in every other registered store → preset library (exact, then case-insensitive) → (named keys only) case-insensitive match in `store or default_store()`, then in the process store → `ValueError("missing mesh asset: ...")`. `bind`, `capture` and `restore` accept the same keyword, and `capture` / `snapshot_store` adopt through the same order.

The case-insensitive tier preserves the contract of the old process-wide library: `mesh.register_from_file(name="Butterfly")` registers a CamelCase name while saved skins may carry the placement's `mesh_kind` lowercased (`"butterfly"`), and `_build_mesh_for_placement` / `designer_preview` rely on that match. Exact keys always win; a preset in any spelling beats a case variant a store holds, so a store key `"cube"` (a legacy document's asset, say) is served for `"cube"` only while `"Cube"` and `"CUBE"` stay the preset — the same order the Designer's own `MESH_LIBRARY` scan follows, so viewport and preview / export agree on every spelling; owned `mesh:` keys are exact identities and are never matched by case; the process store's case variants are matched on every document's behalf, exactly as its exact keys are — it is not another document but the fallback a Designer that has not adopted a per-document store registers into, so binding reads to a document context must not hide `"Butterfly"` from a placement saved as `"butterfly"` (no other *document's* store is ever scanned by case, so one document's import cannot change what another document's placements mean); and `capture` adopts a case-matched mesh under the key the placement actually references, so the saved document reloads by exact key in a fresh process. `mesh.register_from_file` refuses a preset name in any spelling (`mesh_document.is_preset_name`), and `mesh.import_3d` never registers its filename stem: `cube.obj` cannot become `"Cube"` for anyone.

## capture / restore contract

`capture(placements, *, store=None)` validates the hierarchy, tracks, taper and modifier stacks, then serializes every key in `referenced_keys(placements)` (ordered, unique `mesh_kind` plus `props["skin_source_mesh"]`, excluding `file:`). Keys the store does not yet own (presets, legacy names) are adopted into it so the store mirrors the document exactly.

`capture(..., unresolved=[name, ...])` names legacy **named** keys this process cannot resolve at all — a skin saved before geometry was embedded names a mesh (`"Butterfly"`) that used to live in the process-wide `MESH_LIBRARY`. Such a key is omitted from `assets` instead of raising, and `restore` accepts a named referenced key the document does not embed (a missing owned `mesh:` revision stays fatal, and hand-deleting an embedded asset is still caught by the recorded set hash). The placement keeps the name, so the reference round-trips and a later `mesh.register_from_file` embeds the real geometry on the next save. This is what makes a legacy project *editable* rather than merely openable: `capture` sits on both `HeadlessDesigner._snapshot` (the checkpoint before every command) and `layout_payload` (every save), so without it one unresolvable name failed every write in the document, including the rebind that fixes it. `HeadlessDesigner` passes `missing_mesh_names`, keeps it in `menu_status` for `GET /state`, and clears a name from it in `after_commit` once it resolves. The result is

```json
{"schema_version": 2,
 "assets": {"<key>": {...mesh JSON...}},
 "hashes": {"assets": {"<key>": "<sha256>"}, "document": "<sha256>"}}
```

`hashes.assets[key]` is the semantic hash of the serialized asset; `hashes.document` is the sha256 of `"\n".join(f"{key} {hash}")` over sorted keys. `SCHEMA_VERSION` stays 2 because older readers ignore the extra key.

`restore(document, placements=None, *, store=None)` parses every asset first (all-or-nothing), checks that every referenced key is present, then, when `hashes` is present, verifies each recomputed asset hash and the set hash. A mismatch raises `ValueError("mesh asset <key> does not match its recorded hash; the document was corrupted or edited outside the Designer")` and publishes nothing. Only then are the assets put into the target store. Legacy schema-1/2 documents whose assets carry preset names (`"Cube"`) are put into the document store under that name; the preset library is untouched.

## Hashes and `scene.document_hash`

`mesh_document.document_hash(payload)` is the sha256 of the canonical JSON of a complete layout payload. The read-only tool `scene.document_hash` returns `{"document_version", "document_hash", "mesh_document": {"assets": {...}, "document": ...}}` computed from `HeadlessDesigner.layout_payload()`. Two loads of the same project in different processes, or before and after moving the project folder, return identical values (pinned by `tests/test_mesh_document_relocation.py`).

`mesh_document.geometry_hash(mesh)` hashes `{"positions": [[id, x, y, z]...], "polygons": [[vertex ids]...], "wires": [[a, b]...]}` from the topology source (or raw vertex/triangle arrays for legacy meshes). UVs, normals, materials, seam/sharp flags, pins, shading policy and parts are excluded; parameterized primitives use it as their regeneration lock so attribute-only publishes keep regeneration available.

## Sweep rule and self-contained snapshots

A store holds exactly the owned revisions referenced by the live placements:

- Snapshots (`HeadlessDesigner._snapshot`) embed asset JSON, so undo, redo and rollback rebuild a fresh store from the snapshot (`_restore` swaps `mesh_store`, then `retain`s the superseded store down to the keys the new one holds — that is the eviction, and it also removes the shims of the dropped revisions).
- Each committed transaction calls `mesh_document.sweep(placements, store=...)`, which drops every `mesh:` key no longer referenced. The shared transaction core (`elysium.aether.execution.run_transaction`) honours two optional designer hooks: `transaction_context()` (a context manager wrapping checkpoint, handler, persist and rollback — `HeadlessDesigner` returns `mesh_document.using(self)`) and `after_commit()` (run once the command is persisted and published — `HeadlessDesigner` sweeps there). Because the bridge, the daemon and `dispatch_persistent_tool` all go through `run_transaction`, every path gets the same store context and sweep.
- Named (non-`mesh:`) keys are never swept, and they are process state rather than document state: `mesh.register_from_file` puts them into the current document store without a placement, so snapshots do not embed them. `_restore` and `load_layout` therefore carry every named key of the previous store into the new one (`MeshStore.adopt_named`), exactly as the old process-wide library survived rollback, undo and reload. Once a placement references the name, `capture` embeds it and a fresh process restores it from the document. `forget(key)` removes a key from every store (and its shim); tests use it to simulate a fresh process.
- Long-running readers own their geometry. `scene_render_job.start` copies every referenced revision into a private `snapshot_store` on the calling thread and runs the worker under `using(store)`; the direct `scene_render_job.render` path does the same. A sweep triggered by an edit committed while a 3600-frame render runs can therefore never pull a revision out from under the frame loop — the job renders the document it started with.

## Relocation policy

- `mesh.import` and `mesh.import_3d` parse the file once and bind the geometry as an owned asset (`props["import_source"] = {"name", "path"}` records provenance). The document no longer depends on the file. The owned `mesh_key` is the handle for further placements; `mesh.import_3d`'s `mesh_name` is the filename stem the placement is named after and is never registered as a mesh key (a stem that matches a preset would otherwise hijack it for every placement, and for every document in the process on the context-less GUI path).
- Legacy `file:` mesh kinds are migrated on load by `HeadlessDesigner._migrate_file_meshes`: an existing absolute path is used as is; otherwise the loader tries `<project>/<raw>`, `<project parent>/<raw>`, `<project>/<name>` and `<project parent>/<name>`. A missing file raises `ValueError("Missing mesh file <name>; move it next to the project or re-import it")` and nothing is published.
- Every file a placement points at and that lies inside the project folder is saved project-relative (POSIX) by `_portable_placement_json` and resolved back to an absolute path on load by `_resolve_asset_paths`. `mesh_document.rewrite_asset_paths(placement, rewrite)` is the single rule for what counts — `mesh_document.ASSET_PATH_FIELDS` (`image_path`, `texture_path` and the five `pbr_*_map` fields) plus `mesh_document.ASSET_PATH_COLLECTIONS` (`mesh_part_textures` values and `texture_layers[].path`) — and it is the source of truth: read it rather than re-listing fields at a call site. A document is portable only when *all* of its references move together, so relocation (`_project_relative` / `_project_absolute`) and bundle export (`scene_export.export_bundle`, which stages each file into the package's `assets/` and then spells it relative to the package) apply the same rule. Live objects are never mutated on save — the rewrite runs on a shallow copy. Files outside the project keep their absolute path — a documented limitation.
- **Widened in this release, and the Designer must follow.** Before it, only the five `pbr_*_map` fields were relativised; `image_path`, `texture_path`, `mesh_part_textures` and `texture_layers[].path` were written absolute. A project saved by this build therefore hands a reader relative paths in four places that used to be absolute. `HeadlessDesigner._resolve_asset_paths` already resolves all of them, but the separate GUI Designer repository reads `designer_layout.json` directly and must adopt the same rewrite (both directions) or those placements render untextured. `scene.document_hash` hashes the layout payload, so a hash recorded before this change no longer matches a document carrying any of the four.
- **Which references are hard dependencies.** `rewrite(value)` may return `None` to *decline* a reference, leaving the value exactly as it was. `export_bundle` uses that for a file that is no longer on disk: only `mesh_document.REQUIRED_ASSET_PATH_FIELDS` (the five `pbr_*_map` fields, and only on a `Mesh3D` placement) abort the export with `ValueError("Missing material dependency: <name>")` — a mesh missing a material map renders *wrong* rather than plainly. Every other reference degrades: the file is not staged, the value travels into the packaged `designer_layout.json` unchanged (so rebinding it repairs the source document too), and its name is returned in the export result's `missing_dependencies` list for the caller to show. This is deliberate: nothing in the framework validates `image_path` or `texture_path` when they are edited, so a reference the author has since moved or deleted is an ordinary state of a working document, and the widened staging rule above must not turn it into a failed export on projects that packaged fine before.
- Material slot images and reference images are embedded (`material_image`), so they need no relocation.

## `document_version`

`designer_layout.json` carries a top-level `document_version` (`LAYOUT_VERSION = 1`). Readers accept any version `<= LAYOUT_VERSION` (a missing key means 0) and reject greater versions with `ValueError("designer_layout.json document_version N requires a newer Elysium (this build reads up to 1)")`. Adding optional keys never bumps the version; only an incompatible reinterpretation does. `schemas/designer-layout-1.json` (JSON Schema draft 2020-12, every object open) describes the document; saved layouts validate against it in the relocation tests.

`load_layout` validates the complete document — window, placements, identities, assets, hashes, file migration, texture paths, collection pruning and every mesh key — before swapping `window_doc`, `placements` and `mesh_store`.

## Three pivots

Three unrelated notions of "pivot" coexist and are deliberately not unified:

1. `transform3d.pivot` — the object-local point about which `scene.matrix` rotates and scales (`T(location) T(pivot) R S T(-pivot)`). Persisted in `props`; `scene.apply_transform` bakes it (and resets it only when all three channels are applied).
2. `part_pivots` — one mesh-local point per named part, used by the legacy flap rig. `apply_transform` transforms them with the baked matrix.
3. `pivot_x_norm` / `pivot_y_norm` — the 2D canvas box pivot of a placement, serialized as `pivot: [x, y]`. Unrelated to 3D.

## Deprecated `MESH_LIBRARY` shim

The GUI Designer still indexes `pbr.MESH_LIBRARY` directly with a placement's `mesh_kind` at seven sites (its render worker, preview, loft/deformers, Bind Skin, Skin Deform, Paint Weights and mesh info), using `key in MESH_LIBRARY`, `MESH_LIBRARY[key]()`, `.get(key)` and a case-insensitive scan over `.items()`. Until those sites go through `mesh_document.resolve`, every key a live store holds — owned `mesh:` revisions and named keys alike (`mesh.register_from_file` names, named assets restored from a legacy document) — is mirrored in the library as a thin read-through entry (`mesh_document._ReadThrough`) whose call forwards to `resolve(key)`:

- installed whenever a store takes the key: `MeshStore.put`, `bind`, `restore`, and adoption by `capture` / `snapshot_store`;
- never installed over a genuine factory: preset names (`"Cube"`) and factories the Designer registers itself (its loft and deformer results) are neither shadowed on put nor removed on pop, so `restore` of a legacy document whose asset is named `"Cube"` publishes it into the store only;
- removed once no live store holds the key any more: `sweep` / `retain`, `pop`, `clear`, `forget`, the superseded store's `retain` after `_restore` / `load_layout`, and a `weakref.finalize` on the store itself, so a render job's private snapshot store or a superseded document store that is garbage-collected takes its shims with it;
- skipped by `resolve` itself, so a stale entry reports `missing mesh asset` instead of recursing;
- carries no geometry and resolves through the *current* document context: `using(designer)` selects the store, and without it (the GUI Designer, which keeps everything in the process store) the process store is used. Owned keys resolve from any registered store; named keys are never searched across documents, so a named shim called outside its document's context reports `missing mesh asset`;
- `capabilities.mesh_library` lists presets and named registrations, as the old library did, and omits owned-revision shims.

This is a compatibility measure, not a second database: the mesh always comes from a store, and the library never holds authored geometry. It is removed once the Designer routes its seven direct `MESH_LIBRARY` sites through `mesh_document.resolve`.

## Designer integration notes

- Implement the two transaction hooks on the Designer class — `transaction_context()` returning `mesh_document.using(self)` and `after_commit()` calling `mesh_document.sweep(self.placements, store=self.mesh_store)` — and expose `mesh_store`; `run_transaction` then applies them on every bridge, daemon and headless command (GUI-only mutation paths that bypass the transaction core still need `with mesh_document.using(self):` and a sweep after `_push_undo`). Without `using`, store-less `bind`/`capture`/`restore`/`resolve` calls go to the process store: that fallback alone keeps `mesh_document.resolve` callers working, while the Designer's direct `MESH_LIBRARY[...]` reads keep working only through the deprecated shim above. Once the Designer adopts a per-document store, names registered into that store satisfy the direct reads only while that context is current (its render worker has none), so migrate the seven sites to `mesh_document.resolve(kind, store=self.mesh_store)` in the same change, before the shim is removed.
- `AppWindow.from_json` in the Designer constructs fields explicitly; add `scene_collections`, `scene_bookmarks` and `scene_references` (validated by `collections.settings`, `scene_views.bookmarks`, `scene_views.references`) or they are dropped on save.
- Designer tests that call `pbr.MESH_LIBRARY.pop(key)` now remove only the shim, not the asset; use `mesh_document.forget(key)`.
- Worker threads do not inherit the context variable; owned keys resolve through the registry, and `scene_render_job.start` gives its worker a private `snapshot_store` under `using(store)`.
