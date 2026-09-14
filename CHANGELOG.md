# Changelog

All notable changes to Elysium are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and from 1.0.0 the
project adheres to [Semantic Versioning](https://semver.org) — see
[API stability](docs/guides/api-stability.md).

## [Unreleased]

## [1.3.0] - 2026-09-13

The native authoring release: everything the Designer needs to author 3D
scenes natively — editable topology, primitives, a document-owned mesh store,
scene transforms and hierarchy, materials, animation — plus a transactional
Aether bridge. All additive under 1.x semver; see API stability.

### Added — native 3D authoring

- **Editable polygon topology** (`elysium.render.topology`): every mesh keeps a
  durable polygon document with stable vertex/edge/face/corner ids, atomic
  validation, and the Blender-parity operator set — extrude (region, individual
  faces, vertices), inset, boundary fill, component deletion with loose-geometry
  retention, edge loop/ring selection, loop cut (1–64 evenly spaced), edge
  slide, bisect with optional cap, bridge edge loops, dissolve, vertex and edge
  bevel/chamfer with multiple segments and a circular profile, merge at
  center, proportional (soft-select) movement, selected-center rotate/scale,
  distance welding, and component transforms in explicit Global/Local/Parent
  coordinate frames.
- **Parameterized native primitives** (`elysium.render.primitives`): Cube,
  Sphere, Cylinder, Cone, Plane and Torus with the Blender defaults (cube size
  2, sphere radius 1 / 16 rings / 32 segments, …), validated ranges, degenerate
  triangle removal, outward winding, authored polygon connectivity, and the
  public tools `mesh.primitive_create` / `mesh.primitive_update` /
  `mesh.primitive_parameters` sharing one geometry builder.
- **Persistent scene identity and mesh document** (`elysium.scene_identity`,
  `elysium.render.mesh_document`): objects carry stable `entity:` ids that
  survive undo, rollback and reopening; edited geometry is embedded in
  `designer_layout.json` and reloads in a fresh process.
- **Scene hierarchy and model-space transforms** (`elysium.render.scene`):
  location in metres, XYZ Euler rotation in degrees, scale and a local pivot
  evaluated as `T(location) T(pivot) Rz Ry Rx S T(-pivot)`; parenting with a
  stored parent inverse, keep-world reparenting, cycle rejection, transform
  groups, apply-transform that preserves UVs, normals, part pivots and child
  world matrices (and flips winding on mirrors), and `detach_children` when a
  parent is deleted. A shared depth-tested viewport renders every object
  through one persisted camera with a 1 m perspective grid, coloured world axes
  and orthographic axis views; the 2D layout stays a separate mode.
- **Retained modifier stack** (`elysium.render.mesh_modifiers`): Mirror, Array,
  Solidify, Subdivision (Catmull-Clark / simple), Edge Split and Weighted
  Normals as a reorderable non-destructive stack with an atomic Apply.
- **UV authoring** (`elysium.render.mesh_uv*`): retained per-corner UVs,
  planar/cylindrical/spherical/cube projection, seams, pins, seam-driven
  conformal unwrap, chart alignment and packing, texture-density
  normalisation, rigid island stitch with seam preservation, and a
  depth-tested UV checker with distortion diagnostics.
- **Normals and tangents**: smooth/flat shading policies with sharp-edge and
  selected-face authoring, custom normal direction editing, normal transfer
  through taper, and MikkTSpace corner tangents (vendored C, zlib licence) for
  tangent-space normal maps.
- **Materials, lights and render passes**: retained material slots with
  per-face assignment and per-slot previews; owned base-colour, packed,
  roughness/metallic and tangent-space normal images embedded content-addressed
  in the document; retained material colour graphs; persistent scene lights
  connected to rendering and export; cancellable numerical render jobs
  producing beauty/diffuse/specular/emission/normal/depth passes.
- **Animation and playback**: named scene actions, isolated transform-channel
  keys, free-handle Bezier curves, atomic multi-object/multi-channel key
  edits, idle-clip export with authored timing, and configurable scene
  playback. `App.playback_time`, `App.paused` and
  `App.set_space_pause_enabled` expose the pausable application clock;
  `elysium.scene_player.run` plays an exported scene bundle.
- **Export and code-behind**: Python code-behind paired with exported scene
  objects (`elysium.scene_code`, `elysium.project_code`), static local imports
  copied into projects, safe packaging of non-identifier filenames, and atomic
  app builds with staged output and safe cancellation.
- **macOS accessibility**: native accessibility connected with preserved
  control semantics, assistive `SetValue` text replacement routed into editable
  controls through a vendored, patched `accesskit_macos` 0.17.4 (MIT /
  Apache-2.0, see NOTICE), `window.poll_a11y_event()` returning
  `(node_id, action, value)`, accessible-tree validation and native target
  scaling.
- `Window.set_title()`, `Window.left_press_position` (the press origin is
  retained across fast drag/release events), and native Quit routed through
  the application command queue so an in-flight Save or Undo finishes first.

### Added — transactional Aether bridge (NP-01, NP-02)

- **Every Aether command is acknowledged with a transactional receipt.**
  `POST /tool` serialises reads and writes through the Designer's UI
  dispatcher (`elysium.concurrency.UiDispatcher`, with an inline serialised
  fallback when a Designer supplies none) and answers with a receipt whose
  `status` is one of `queued | running | committed | failed | cancelled`, plus
  `id`, `revision`, `attempts`, `snapshot` and `warnings`. Retrying a request
  id never executes twice; a still-running operation answers `202` and stays
  queryable at `GET /operations/<id>`; `POST /operations/<id>/cancel` withdraws
  a queued operation; `/state` and `/status` report the document revision and
  the queue; a `tool_result` SSE event is pushed when the command settles,
  202s and cancellations included. `elysium aether call` gained `--id`,
  `--confirm`, `--wait` and the `op` / `cancel` actions, and polls the receipt
  instead of resubmitting when a reply is lost.
- **`elysium.aether.ToolError`** for structured tool failures (`code`,
  `message`, `details`); `ToolResult.warnings` surfaces nested diagnostics
  without failing the call; `ToolResult.rollback_error` records a failed
  rollback.
- **Checkpoints record external assets.** Every checkpoint carries a SHA-256
  manifest of the image, texture and imported-mesh files the document
  references; `snapshot.restore` returns `missing_assets` / `changed_assets`,
  bumps the revision and is undoable.
- `Window.wake()` (native) and automatic `UiDispatcher.set_wake` installation
  by `window.ui_dispatcher()`, so queued UI work wakes an idle frame loop.
- Headless designer: whole-document `undo()` / `redo()`, and the
  `transaction_context()` / `after_commit()` hooks that the shared transaction
  core honours for every bridge, daemon and headless command.

### Added — scene document, primitives and transforms (NP-03, NP-05, NP-06)

- **Document-owned mesh assets** (`elysium.render.mesh_document.MeshStore`):
  every designer document owns exactly the mesh revisions its placements
  reference; `pbr.MESH_LIBRARY` is now read-only presets, plus a deprecated
  read-through shim for the Designer's direct reads that mirrors every key a
  live store holds (owned revisions and named registrations alike), lives
  exactly as long as some live store holds the key, and never shadows a
  genuine factory. Assets are
  stored canonically (float32) and hashed; per-asset and document hashes are
  written by `capture` and verified on load with a clear error, and
  `scene.document_hash` reads them. `designer_layout.json` carries a
  `document_version` (schema in `schemas/designer-layout-1.json`); imported
  meshes are embedded at import time and legacy `file:` meshes migrate on
  load; in-project `pbr_*_map` paths are saved project-relative, so a project
  survives being moved and reopened in a fresh process with identical hashes.
- **Primitive contract completed**: Cone `radius2` (a frustum when non-zero)
  and Cone/Cylinder `cap_fill` (`ngon` / `trifan` / `nothing`); regeneration
  is locked by a geometry hash, so UV, normal and material edits keep the
  parameters editable; parameter metadata survives save, reopen, undo/redo
  and duplication.
- **Object-level transform spaces**: `scene.transform_set` / `transform_get`
  accept `space` (`local` / `parent` / `world`), the new `scene.transform_delta`
  applies gizmo-style moves, rotations and scales with axis, plane and
  free-axis constraints in any space (rejecting shear without mutation), and
  `scene.transform_apply` bakes any subset of location / rotation / scale.
- **Scene collections** (`scene.collection_create/delete/assign/set`,
  `scene.collections_get`) with nesting, visibility and exclusion honoured by
  the viewport, export and render jobs; **named view presets**
  (`scene.view_preset`), **camera bookmarks** and **orthographic reference
  images**; solid shading honours explicit material-slot colours.

### Changed

- **Write tools are transactional everywhere.** A mutation whose checkpoint
  cannot be created fails before the handler runs (the daemon previously
  skipped the checkpoint silently); a failing handler — an interrupt included —
  rolls the document, mesh assets and both history stacks back; invalid
  arguments leave the revision unchanged. Tool input schemas are validated at
  registration and arguments before dispatch, for every caller.
- **Side-effect classification pass.** `dev.eval` is `destructive`, always
  requires confirmation and reports failures (including syntax errors) as
  failures; `dev.reload_module` / `dev.reload_designer_module` require
  confirmation under the destructive policy; diagnostics (`dev.*_info`,
  `dev.dump_*`, `dev.thread_dump`, `dev.probe_designer`, `texture.read_info`)
  are `read`; transient or cache-only operations (`placement.select`,
  `view.set_zoom`, `animation.play`, `run.start`, `texture.flush_caches`,
  `mesh.save_landmarks`, …) are `none` and create no checkpoint or undo
  entry; library-PNG writers are not undoable. See the regenerated tool
  reference.
- Bridge `423` responses distinguish `aether_stopped` from `aether_paused` and
  carry `hint` / `since_last_call_s`; `pace_ms`, `last_call_target`, the
  `tool_call` SSE event and `feedback_observed` are back; the default
  acknowledgement wait is 25 s (was 120 s) so the CLI's 30 s client timeout
  cannot fire first.
- Primitive regeneration stays available after UV, normal and material edits;
  `mesh.import` / `mesh.import_3d` embed geometry as owned assets (`mesh_key`
  is the reusable `mesh_kind`; `mesh.import_3d`'s `mesh_name` is the filename
  stem and is no longer registered as a mesh key); legacy `file:` meshes
  migrate on load; in-project legacy `pbr_*_map` paths are saved
  project-relative.
- `mesh_document.resolve` — and `capture` / `snapshot_store` adoption — rank an
  exact store key, then a read-only preset in any spelling, then a case variant
  held by the current store alone; the process store's case variants are
  matched only when it is the current store (the GUI Designer), never on
  another document's behalf. `mesh.register_from_file` refuses a preset name in
  any spelling (`mesh_document.is_preset_name`).
- A command that shares the undo stacks with a running Designer frame thread
  (no `_aether_dispatcher`) writes history wholesale, together with the
  document, and reports a user undo or redo it discarded as a `history`
  warning on the receipt.
- The `ely-py` build dependency `cc` is unpinned from `=1.4.0` to `1` (there is
  no tracked `Cargo.lock`, so the exact pin blocked fresh resolves).
- `window.publish_a11y_tree` validates the flat node list and raises
  `ValueError` (duplicate ids, repeated or cyclic children, missing child or
  root, orphan nodes, depth > 128, non-finite or negative bounds, missing
  id/role, reserved `u64::MAX` id) instead of silently substituting defaults;
  the previously published tree stays live after a rejected publish.
- The Aether tool registry validates every call against the tool's declared
  JSON schema before dispatch and reports a returned `{"error": ...}` as a
  failed call; `jsonschema` is a new runtime dependency.
- Pillow ≥ 12.3.0 is required (thirteen advisories against earlier versions,
  including heap out-of-bounds writes, decompression-bomb bypasses and a
  Windows command injection).

### Fixed

- Bridge operation receipts could be read while being updated from the frame
  thread; `is_busy` was cleared while an operation was still queued; a stopped
  bridge left queued operations stuck at `queued`; `dev.eval` swallowed the
  original `SyntaxError`.
- `HeadlessDesigner` lacked `_select_placement`, so `mesh.primitive_create` and
  `scene.group_create` failed headlessly; `mesh_document.restore` no longer
  republishes preset names into the global library; `mesh.register_from_file`
  names survive undo, rollback and snapshot restore.
- Importing `cube.obj` / `sphere.obj` through `mesh.import_3d` no longer
  hijacks the `Cube` / `Sphere` preset for every placement (and, on the
  context-less GUI path, for every document in the process); the checkpoint no
  longer persists the import as the preset asset, and viewport, preview and
  export agree on every spelling of a mesh key.
- Render jobs own a private snapshot store, so a geometry edit committed during
  a long render no longer evicts the revision being rendered.
- The source distribution now ships the vendored, patched `accesskit_macos`
  crate. `elysium-native/Cargo.toml` patches crates.io with it unconditionally
  and cargo's resolver is target-agnostic, so every platform reads that path at
  resolve time; because the crate sits outside the packaged crate directory it
  was absent from the sdist, and building from source failed everywhere with
  `failed to load source for dependency accesskit_macos`.
- **`elysium.native.single_instance` no longer refuses the first instance at
  random.** The lock was a loopback TCP port derived from the app id, inside
  every OS's ephemeral port range, so any unrelated outgoing connection that
  happened to get that source port made the bind fail and the app believed it
  was already running (seen as an intermittent test failure on macOS). It is
  now an advisory file lock in the user's temp directory (`flock` /
  `LockFileEx`), released by the OS on exit or crash; the public
  `single_instance(app_id) -> bool` contract is unchanged.
- Texture-cache image ownership: Skia now owns encoded bytes after the caller's
  buffer is dropped (corrupted-PNG regression in exported apps).
- `elysium aether` (the CLI chat driver) returns a non-zero exit code when a
  tool call fails, and no longer aborts a slow turn after 0.5 s of silence.
- Designer snapshots are faithful and read-only (`run.snapshot` no longer
  saves the layout as a side effect).

## [1.2.1] - 2026-08-05

### Fixed

- **The 1.2.0 Linux wheel could not be imported.** `manylinux_2_28` is built on
  AlmaLinux 8, which ships FreeType 2.9.1, while Skia 0.78 calls
  `FT_Palette_Data_Get`, `FT_Palette_Select` and `FT_Get_Color_Glyph_Layer` —
  all added in FreeType 2.10.0. A shared object may keep undefined symbols, so
  the link succeeded and the failure only appeared when something dlopened the
  module (`ImportError: undefined symbol: FT_Palette_Data_Get`). `auditwheel`
  then vendored the container's 2.9.1, so the wheel shipped a module and a
  dependency that disagreed. CI now builds FreeType 2.13.3 in the manylinux
  container and asserts the three symbols before the build proceeds.
- **A `wake_on` object that does not honour the protocol killed the frame
  thread.** `run_animation_thread` sampled `wake_on.input_seq` and called
  `wake_on.wait_for_input(...)` outside the `try` guarding `on_frame`, so an
  exception from either terminated the daemon thread — the window stayed up and
  silently stopped repainting, with nothing in the log connecting the freeze to
  `wake_on`. Reachable from ordinary use: a window proxy from a build predating
  wake-on-input returns a junk object for `input_seq` instead of raising. Both
  calls are now guarded and fall back to timed polling with a diagnostic.

### Changed

- **Built wheels are now load-tested before they can be published**, on all four
  platforms, and again after publishing. Asserting `__version__` alone was not
  enough: `elysium/__init__.py` catches the native extension's `ImportError` and
  continues with `_NATIVE_AVAILABLE = False`, so a wheel whose `.so` cannot load
  still imports *and still reports the correct version*. That is exactly how
  1.2.0's broken Linux wheel passed the post-publish gate.

## [1.2.0] - 2026-08-04

A defect-fix release from an external QA pass. Every item below was reproduced
against 1.1.7 and has a regression test. Three changes that touch shared render
or animation paths are additionally pinned by tests asserting byte-identical
output for well-formed input, and every affected chart and grid configuration
was verified to render pixel-identically.

### Performance

- **Wake-on-input: the frame loop can idle without going deaf.** Idling dropped
  the loop to 4 Hz, and between ticks nothing looked at input — so a click could
  wait up to 250 ms to be noticed, and a press-and-release inside a single tick
  was never seen as a drag at all. The native layer now signals the frame loop
  whenever input arrives; pass `wake_on=window` to
  `run_animation_thread`. Adds `Window.input_seq` and
  `Window.wait_for_input(timeout, since)` (blocks natively with the GIL
  released). Input wakes the loop but does **not** drive the frame rate — a
  wake pulls the next frame forward to the busy cadence rather than running one
  frame per pointer event. `since` is sampled before the frame, so an event
  landing mid-frame still counts. Opt-in: without `wake_on` the behaviour is
  unchanged.
- **The main event loop no longer busy-spins.** `new_events` re-asserted
  `ControlFlow::Poll` on every iteration — solely so the quit flag and
  Python-posted window requests were noticed promptly — which ran the loop
  continuously. Measured on the Designer with an **empty canvas and no user
  interaction: ~150% process CPU**, with the profile dominated by timer
  arm/cancel churn. Nothing needed that: rendering runs on its own thread and
  this loop only pumps OS events and drains a queue, which a bounded 8 ms tick
  serves equally well. OS events still wake it immediately. **Idle CPU on that
  same empty canvas is now ~11%.**
- **The frame loop paces to a deadline instead of a fixed delay.** It slept
  `period` *after* running the frame, so the achieved rate was
  `1/(work + period)` — `target_hz` was an unreachable ceiling that sagged as
  the scene grew (60 Hz with a 10 ms frame delivered 37 Hz). An overrun now
  drops the missed frames rather than running a catch-up burst, which would
  steal time from a frame already late.

### Added

- **Windows size themselves to the display.** `initial_size` is now a request:
  it is clamped to the target display's usable area and the window is centred
  there, so a window never opens larger than the screen it lands on. Pass
  `fit_to_display=False` to opt out. Previously every window was created at a
  hardcoded 1200x800 with no monitor query anywhere in the native layer — which
  does not fit a 1366x768 laptop, nor a 1920x1080 panel at 150% scaling
  (1280x720 logical), and a borderless window that opens taller than the screen
  has no title bar to drag back into view.
- **`Window.monitor`** — the display the window is on (name, position, size,
  usable work area, scale factor, primary flag) in logical pixels, or `None`
  when the platform reports no monitors. Lets an app do its own placement.
- **`Window.scale_factor`** — the live display scaling. Python previously had no
  way to observe DPI at all.
- **`UndoStack.macro(text)`** — a context manager that closes the macro even on
  the exception path. `begin_macro`/`end_macro` remain the low-level API; the
  `with` form removes the footgun described under *Fixed* below.
- **`elysium.core.clamp(v, lo, hi)`** — NaN-safe clamp. The obvious idiom,
  `min(max(v, lo), hi)`, returns NaN unchanged (every comparison against NaN is
  false, so both calls fall through), which let a NaN escape a clamp and only
  surface a frame later somewhere unrelated.
- **`ItemModel.is_view_identity()`** — True when `view()` is the source list in
  source order; callers translating a view index into a source mutation must
  check it.
- **`DataGrid.new_row`** — optional factory used when a paste grows a model whose
  rows are not dicts.

### Fixed

- **`WindowEvent::ScaleFactorChanged` was not handled.** Moving a window to a
  display with different scaling, or changing the current display's scaling,
  left the reported scale stale.
- **`Window.outer_position` read (0, 0) until the window was first moved**,
  because it was only recorded on `Moved`. An app persisting window geometry at
  startup saved the wrong position.
- **Docs described `ely.platform.screens()`**, which has never existed —
  calling it raises `AttributeError`. The windowing guide now documents the
  real API.
- **Charts froze the UI thread on small-magnitude data.** The gridline loop
  terminated on an absolute epsilon while stepping by a relative increment, so a
  data range near 1e-15 put the bound ~1e9 steps away and the loop never
  realistically finished — no traceback, just a hang. At 1e-9 it emitted 2,009
  draw calls where clean data emits 9, stacking 2,000 gridlines into a 200px
  plot. Affected `LineChart`, `AreaChart` and `BarChart`.
- **Charts crashed or silently lied on non-finite data.** `inf` raised
  `OverflowError` and an all-`NaN` series raised `ValueError`, while a partially
  `NaN` series raised nothing at all and produced the same draw-call count as
  clean data — in fact worse than "drawn wrong", since a `nan` token in path
  data makes Skia's parser abort and drop the entire series. All five chart
  types now treat a non-finite value as a **gap**: not plotted, excluded from
  the axis scale, and not shifting anything stacked above it. See
  [Missing data](docs/guides/charts-and-dashboards.md).
- **Springs diverged after one slow frame.** `SpringValue` used explicit Euler
  with no dt bound; with the default parameters any frame over ~0.13 s (a GC
  pause, a breakpoint, a laptop resume) diverged geometrically to ~1e73, which
  then went straight into a widget's position. `stiffness=999999` or `mass=1e-9`
  reached NaN at a normal 60 Hz tick. Now sub-steps at a stable step size —
  bit-identical for every frame below the stability limit.
- **Every default-constructed `SpringValue` shared one `Spring`.** The default
  argument was evaluated once at class-definition time, so retuning one spring
  retuned them all.
- **`DataGrid` construction accepted invalid values and crashed later.**
  `model=None` (the declared default) died on the first repaint with an
  `AttributeError` pointing at `paint()`; `row_h=0` was a `ZeroDivisionError` in
  the scroll maths; a negative `row_h` raised nothing and silently rendered a
  blank grid; a negative `frozen_cols` silently painted the last column twice.
  These now raise at construction, naming the field.
- **Hiding a frozen column crashed the next repaint** with `IndexError`. Both
  freezing and hiding are ordinary supported operations. The hit-test path
  already clamped the frozen count and paint did not — that asymmetry was the
  bug.
- **`DataGrid.paste` corrupted every Excel paste.** Splitting on `"\n"` alone
  left an invisible carriage return on the last field of every CRLF row — it
  looks correct on screen, then breaks equality, joins, lookups and exports much
  later. A trailing `"\r\n"` also wrote a phantom empty row.
- **`DataGrid.paste` silently discarded rows past the end of the model** — 500
  rows into a 3-row grid lost 497 with no error and no visual difference from
  success. The model now grows to fit; growth is declined (and the shortfall
  made visible in the return value) under an active sort or filter, where a
  grown row's position would be undefined.
- **`DataGrid.paste`'s return value was untrustworthy** in both directions: it
  counted rows in range rather than cells written, so it reported 3 having
  written 1. `set_cell` now returns `bool`; `fill_down` is corrected too.
- **Hit-testing selected the item underneath the visible one.** `sorted(...,
  reverse=True)` is stable and does not reverse ties, so for any two items
  sharing a z value `item_at()` returned the one painted *first*. Since `z`
  defaults to 0 this affected every item created without an explicit z — in an
  app with layers it presents as "selection picks the wrong layer".
- **`Scene.raise_to_top`/`lower_to_bottom` mutated non-members** — they guarded
  on the scene being non-empty rather than on membership.
- **`GraphicsView.fit()` was a silent no-op on an empty scene**, leaving exactly
  the stale zoom and pan that "reset view" was pressed to clear.
- **`GraphicsView(zoom=0)` raised `ZeroDivisionError`** from every coordinate
  conversion, including the pointer hot path; `set_zoom(nan)` stored NaN and
  poisoned the pan. The constructor now clamps as `set_zoom` always did.
- **A dock panel closing mid-drag crashed on mouse release** with `IndexError`
  inside a pointer handler, where an unhandled exception takes the frame or the
  event loop with it. `close()` now repairs the in-flight drag as it already did
  for the active tab.
- **`DockManager.add`/`move` accepted any area name**, but painting and
  persistence enumerate the four known areas — so a typo'd area produced an
  invisible panel that vanished on save/restore with no error at any stage.
  They now reject unknown names.
- **A splitter in a pane narrower than `2 * min_px` produced a ratio above 1.0**
  (4.8 at `w=10`), drawing the handle outside the widget.
- **`DockManager.restore` trusted a persisted active-tab index** that a stale
  blob can put out of range.
- **`UndoStack.end_macro()` reported a diverged document as saved.** It
  discarded the redo branch without the `_clean_index` fix-up `push()` performs,
  so `is_clean()` returned True for a document that had genuinely changed — the
  app showed no modified marker and closed without prompting. The branch-discard
  is now shared between the two so they cannot drift apart again.
- **An unclosed `begin_macro()` made every later edit un-undoable.** Commands
  still executed but were recorded nowhere, so undo silently stopped working for
  the rest of the session. `push()` also now notifies observers during a macro,
  so a modified indicator or autosave trigger still fires.
- **`MotionPreset.step` returned NaN for a NaN frame time** (pinning the animated
  value there permanently) and raised `OverflowError` for a large negative one.
- **`Tween` accepted a non-finite duration**, poisoning every `elapsed/duration`;
  an empty looping `Timeline` divided by zero.
- **`AnimationClock.tick_realtime()` now caps a stalled frame** at 0.25 s.
  `tick(dt)` is unchanged and still applies exactly the dt given — it is the
  deterministic stepping API.

### Notes

- `theme.mix` was reported as a NaN-clamp failure. It is not: its argument order
  makes it accidentally NaN-safe. Left as-is deliberately.
- Springs below ~18 fps now take multiple sub-steps, so their trajectory differs
  slightly from 1.1.7 in a regime that was already numerically degraded. At 30
  and 60 fps the arithmetic is bit-identical.

## [1.1.7] - 2026-07-09

### Fixed

- **Windows: typed text was dropped by hand-rolled key loops.** The framework
  enabled the OS IME at window creation for every window, but on Windows an
  IME-allowed window delivers typed characters only via `Ime::Commit` and
  leaves `KeyboardInput.text` empty — so any consumer reading `KeyEvent.text`
  without handling the commit path received nothing (this dead-keyboarded the
  Designer on Windows). IME now stays at winit's default (off) on Windows; the
  `InputRouter` still enables it per focus for router-driven text fields (which
  handle `on_ime_commit`), so CJK/dead-key composition keeps working. macOS and
  Linux are unchanged.

### Added

- **Real OS-level input test** (`examples/input-probe` + `tests/test_os_input.py`,
  run by `input-e2e.yml`): injects actual OS keyboard/mouse events (xdotool on
  Linux, pywinauto on Windows) and asserts the round-trip via `KeyboardInput` —
  the coverage the launch-only smoke test couldn't provide, and which now guards
  the Windows regression above.

## [1.1.6] - 2026-07-04

### Added

- **TableView column resize**: `TableView` gains the same drag-to-resize
  affordance as `DataGrid` — `header_border_at()` hit-tests the border between
  two headers, `on_mouse_press` / `on_mouse_drag` / `on_mouse_release` drive the
  resize (grabbing a border takes priority over sorting; width clamps to 40px),
  `resize_col(key, width)` sets a width directly, and `cursor_at(mx, my)`
  returns `"ew-resize"` (↔) over a border or mid-resize so the app can show the
  affordance via `win.set_cursor`.

## [1.1.5] - 2026-07-04

### Fixed

- **Dialog body text overflowed the modal**: `MessageDialog` rendered its body
  with single-line `draw_text`, so any message longer than the card is wide ran
  off the edge instead of wrapping. It now uses `draw_paragraph`, wrapped to the
  card interior. The same fix is applied to the `InputDialog` prompt and the
  `ProgressDialog` label (all three now share a `BaseDialog._paint_body_text`
  helper).

### Added

- **DataGrid column-resize cursor affordance**: `DataGrid.cursor_at(mx, my)`
  returns `"ew-resize"` (the horizontal double-arrow ↔) over a column-header
  border or while a resize is in progress, so an app can show users where to
  click-and-drag. Apply it each frame with
  `win.set_cursor(grid.cursor_at(*win.cursor_position) or "default")` — see the
  data-grid guide.

## [1.1.4] - 2026-07-04

### Fixed

- **`elysium.__version__` lagged the release**: it was sourced from the native
  module's compiled-in `CARGO_PKG_VERSION`, and 1.1.3 was published with the
  Rust workspace still at 1.1.2 — so the 1.1.3 wheel reported `__version__ ==
  "1.1.2"`. `__version__` now comes from the installed distribution metadata
  (always the wheel's version), the Rust workspace version is bumped in lockstep
  with `pyproject.toml`, and CI fails the build if the two ever disagree. (No
  API or behavior change beyond the reported version string. 1.1.4 carries the
  same fixes as 1.1.3; upgrade to get a correct version string.)

## [1.1.3] - 2026-07-04

### Fixed

- **macOS keyboard input**: text fields silently ignored the keyboard on
  macOS. `InputRouter` positioned the OS IME candidate area but never called
  `set_ime_allowed`, the call that registers the window as a text-input
  client. The native window enables IME once at creation, but on macOS that
  is too early to take effect and nothing re-asserted it. `InputRouter.tick()`
  now enables IME while a text-accepting widget is focused (and disables it
  otherwise), toggling only on change so an in-flight IME composition is never
  reset.
- **macOS Designer crash on Apple Silicon**: the native `set_application_menu`
  installed the NSMenu (`setMainMenu:` / activation policy) on the calling
  thread. The Designer drives it from a background frame thread, and AppKit's
  main menu is main-thread-only, so the app could abort at launch
  (`NSInternalInconsistencyException`: "setting the main menu on a non-main
  thread"). The install now runs on the macOS main dispatch queue.

## [1.1.2] - 2026-07-03

### Fixed

- **Release packaging**: the Linux wheel build failed in the manylinux_2_28
  container (missing fontconfig/freetype dev libraries that Skia links
  against) and the macOS Intel wheel targeted GitHub's retired `macos-13`
  runner (queued forever). First version published to PyPI as `elysium-ui`.

## [1.1.1] - 2026-06-29

### Fixed

- **Designer release build** now succeeds on all platforms (the published distro
  had been stale ~a month). `scripts/build-designer.spec` anchored its
  PyInstaller `datas` source paths to `REPO_ROOT` (they were resolved against
  the spec dir and failed); dropped stale hidden imports (`aether.tools.render`,
  the removed `elysium.ai.*` providers → `elysium.ai.enhance`); and added the
  missing `scripts/windows-installer.iss` (+ a robust iscc invocation with a
  portable-zip fallback) so the Windows installer step stops failing.

### Documentation

- Added `examples/butterfly/BLUE_MORPHO_INTRO_SPEC.md` — a 3D model + animation
  spec for the Blue Morpho logo-intro asset, written against the Designer's
  Mesh3D pipeline.

## [1.1.0] - 2026-06-29

### Documentation

- New API reference pages for every public module added since 1.0 (`shell`,
  `graphics`, `charts`, `commands`, `styling`, `dnd`, `text.richtext`,
  `components.completer` / `.daterange` / `.dashboard`, `modelview.grid`).
- New guides: charts & dashboards, the data grid, wizards & flows, commands &
  undo, rich text, drag-and-drop, completer, and a developer-handoff index.
- An end-to-end tutorial ("Build a Shopify-style desktop app"), a component
  gallery, an expanded Qt porting map, and a green `--strict` Designer site.

### Added

- **DataGrid sorting & filtering** (both optional + configurable): click a
  header to sort a column (asc → desc → unsorted, honouring `Column.sortable`
  and the grid `sortable` flag), and opt into a per-column **filter row** with
  `DataGrid(filterable=True)` — a live search box per `Column.filterable`
  column, with a pluggable `filter_match`. Both delegate to `ItemModel`
  (`toggle_sort` / `filter`), so virtualization and identity-keyed cell state
  keep working.

- **Tabular numerals** — `DisplayList.draw_paragraph(..., tabular=True)` now
  enables the OpenType `tnum`+`lnum` features (equal-width lining figures) so
  monetary / metric columns reconcile to the digit. Opt in per widget via
  `Label(tabular=True)` and `MetricCard(tabular=True)`. (Rust: threaded through
  `ely-render`'s Skia paragraph layer via `TextStyle::add_font_feature`.)
- **Reference apps** under `examples/`: `storeprofitlens-dashboard/` (KPI cards,
  net-profit area chart, cost donut + legend, profit table, alert inbox) and
  `variantproof-grid/` (Excel-grade `DataGrid` with frozen columns, pending
  edits, validation badges, saved-views rail, pending-changes tray) — each with
  a headless `build_*()`/`paint_*()` split and a smoke test.

- **DataGrid** (`elysium.modelview.grid`, Tier 8 — Excel-grade editable grid over
  `ItemModel`): **frozen/pinned leading columns**, column **resize / reorder /
  show-hide**, **rectangular range selection**, **copy / paste TSV** (paste an
  Excel block into a cell range), **fill-down**, **per-cell validation badges**
  and **pending-edit highlighting** — with virtualized row painting (100k rows)
  and cell state keyed by row identity (survives sort/filter). Complements the
  existing read-oriented `TableView`. Closes the bulk-editor grid gap.

- **Dashboard & flow widgets** (Tier 8): `components.dashboard.MetricCard` (KPI
  tile — eyebrow + big value + direction-aware delta badge + inline sparkline),
  `Alert` + `NotificationInbox` (a persistent "needs attention" panel, distinct
  from transient Toast/Snackbar); `components.daterange.SegmentedControl` +
  `DateRangePicker` (preset Today/Yesterday/7d/30d/Custom bar with range math);
  and `shell.Drawer` (slide-out content panel), `shell.Stepper` / `shell.Wizard`
  (numbered multi-step flow with Back/Next). For dashboards + import wizards.

- **Charts** (`elysium.charts`, Tier 8 — Qt QtCharts class): immediate-mode,
  theme-recolouring chart widgets built purely on the existing `DisplayList`
  (polylines + SVG-arc donut wedges, no native dependency) — `LineChart` /
  `AreaChart` (incl. stacked), `BarChart` (stacked/grouped), `DonutChart` /
  `PieChart`, `Sparkline`, and a `Legend`, with `Series` data, a categorical
  `chart_palette`, `nice_ticks` axis helper, and `format_money` / `format_pct` /
  `format_compact` number formatters. Closes the dashboard-charting gap for
  data/finance apps.

- **Styling & accessibility** (Tier 7 — Qt QSS / `QCompleter` / `QAccessible`):
  - `elysium.styling.StyleSheet` — a QSS-like selector→property resolver
    (type / `#id` / `.class` / `:state`, CSS specificity, `resolve` + `apply`).
  - `elysium.components.completer.Completer` — autocomplete popup (prefix →
    contains → fuzzy, history-first, keyboard nav, prefix highlight).
  - `elysium.accessibility` gained a semantic layer: `Role` constants,
    `AccessibleNode` (→ accesskit-bridge `to_dict`, incl. table row/col/header),
    a live-region `Announcer` + `announce()`, and `paint_focus_ring` (scales
    with high-contrast prefs).
  - Per-widget fonts: `Label(font_family=…, weight=…)` (opt-in; the default path
    is unchanged so goldens don't move).
- **Documents & editing** (Tier 6 — Qt `QUndoStack` / `QTextDocument` / `QDrag`):
  - `elysium.commands` — `Command` (+ `FunctionCommand` / `MacroCommand`) and an
    `UndoStack` (undo/redo, merge/coalesce by `merge_id`, macros, history limit,
    clean-state index, `on_change`); `Action`, one shared trigger for a menu
    item + toolbar button + shortcut (`to_menu_item()` / `to_tool_button()`).
  - `elysium.text.richtext` — `RichDocument` of styled `Run`s + inline `Image`s
    + paragraph `Break`s, word-wrapped + baseline-aligned via `measure_text_run`;
    `RichTextView` renders through the Skia paragraph path (real bold weight +
    italic slant axis) with hyperlink hit-testing.
  - `elysium.dnd` — `MimeData` / `DropZone` / `DragController` for in-app
    widget-to-widget drag-and-drop (press→threshold→drag, accepting-zone
    highlight, drag ghost, delivered drop). `examples/notes-demo/` ties all
    three together (rich-text notes, undoable drag-reorder).
- **Interactive 2D canvas** (`elysium.graphics`, Tier 5 — Qt `QGraphicsScene` /
  `QGraphicsView` / `QGraphicsItem` parity):
  - `Scene` owning a z-ordered list of `Item`s with scene-space bounds,
    shape-accurate hit-testing, and a `paint(dl)` in scene coordinates. Built-in
    items `RectItem` / `EllipseItem` / `LineItem` (distance hit-test) /
    `PathItem` / `TextItem`. Scene queries: `items_at` (topmost-first),
    `items_in_rect` (intersect or contained — the rubber-band query),
    `bounding_rect`, z-order raise/lower, selection helpers.
  - `GraphicsView` — a pan/zoom viewport with `to_view`/`to_scene` mapping,
    cursor-anchored `zoom_at`, `fit()`, and off-screen culling.
  - `SceneController` — select / Shift-multi-select / rubber-band / move (grid
    `snap`) / 8 screen-space resize handles for a single selection.
  - `examples/graphics-demo/` flowchart editor + `docs/guides/graphics.md`.
- **App-shell widgets** (`elysium.shell`, Tier 4 — Qt `QMainWindow` parity).
  Immediate-mode Components that recolour with the theme:
  - `GroupBox` (titled bordered container with a content rect), `StatusBar`
    (transient message + right-aligned permanent sections), `Splitter`
    (draggable two-pane divider, H/V, min-size clamped), `MenuBar` (persistent
    in-window menu bar over the existing `Menu`/`MenuItem`).
  - `ToolButton`/`ToolBar` (icon/text tool strips with separators + a flexible
    spacer; pluggable icon painter; checked/disabled states), `TabWidget`
    (content-width closable tabs + content routing).
  - `DockWidget`/`DockManager` (`QDockWidget` parity): left/right/bottom/centre
    dock areas, per-area tabbing, splitter resize between areas, drag-a-tab to
    re-dock with drop-zone overlays, and layout save/restore via `serialize()` /
    `restore()` (wire to `elysium.settings`).
- **Studio theme + design tokens** (Designer redesign, part A1): new
  `elysium.theme.studio_dark()` / `studio_light()` built-ins (the clean
  professional "Studio" direction), plus new `Theme` tokens — a spacing scale
  (`space_xs..xl`), state opacities (`opacity_disabled/hover/focus`), and
  `font_family`. Exported the previously-internal `oled()` theme.
- **App-wide UI font:** `elysium.theme.set_ui_font(family_or_path)` and native
  `set_ui_font` / `register_ui_font` — set a preferred UI font family or
  register a bundled `.ttf`/`.otf`. `set_theme` now applies the theme's
  `font_family`. The no-preference default is unchanged (opt-in).

## [1.0.0]

First stable release. Elysium commits to a stable public API under strict
semver. This release consolidates the Qt-parity work (Tiers 1–3) into a
production baseline.

### Added

**Tier 1 — Qt day-one parity**
- Robust text editing: `elysium.text.EditableText`, `TextField`, multi-line
  `TextArea`, caret/selection/undo-redo/word-jump, validators
  (`IntValidator`, `DoubleValidator`, `RegexValidator`) and input `Mask`s.
- IME composition (CJK) and system clipboard integration, routed centrally by
  `elysium.input.InputRouter` + `FocusManager`.
- Standard dialogs: native file pickers (`open_file`/`save_file`/`pick_folder`)
  plus Elysium-rendered `MessageDialog`/`InputDialog`/`ProgressDialog`/
  `ColorDialog`/`FontDialog` via `DialogHost`.
- Model/View: `ItemModel` (+ `QtItemModelAdapter`), virtualized `TableView`/
  `ListView`/`TreeView`, and delegates incl. a GPU `Mesh3DDelegate`.
- Data-entry widgets: `SpinBox`, `DoubleSpinBox`, `DateEdit`, `TimeEdit`,
  `CalendarWidget`, `EditableComboBox`.

**Tier 2 — scale & services**
- True dirty-rect compositing in the render thread (partial repaint +
  skip-when-clean) and reusable virtualization (`VirtualList`, `VirtualForm`).
- Scroll system: `ScrollView`, `ScrollBar`, mouse-wheel routing, `PushClip`.
- Threading → UI marshalling: `elysium.concurrency` (`UiDispatcher`,
  `call_on_ui_thread`, `post`, `@ui_thread`, `run_async`, `FrameLoop`).
- Multi-window depth: `elysium.windowing.WindowManager` (owned/modal windows,
  inter-window messaging).
- Native OS integration: `elysium.native` (single-instance, notifications,
  system tray, global hotkeys) — GTK-free on Linux, capability-gated.
- i18n / RTL / locale: `elysium.i18n` (gettext `tr`/`tr_n`, RTL layout) and
  `elysium.locale` (Babel-backed formatting); paragraph base-direction.
- Settings: `elysium.settings.Settings` (QSettings-equivalent, atomic writes).
- UI test automation: `elysium.testing.UiHarness` (QTest-equivalent).

**Tier 3 — maturity**
- This `CHANGELOG.md`, the [API stability policy](docs/guides/api-stability.md),
  a public-API surface-lock test, and the `elysium.deprecated` /
  `deprecated_alias` deprecation mechanism.
- Pattern guides (CRUD, forms, tables, dialogs), API-reference pages for the
  Tier-1/2 modules, and an explicit [scope/batteries statement](docs/resources/scope-and-batteries.md).
- Broadened end-to-end, scale, and error-path test coverage; `pytest-cov`
  reporting in CI.

### Changed

- **Version → 1.0.0**; package status is now Production/Stable.
- CI (`build.yml`) is green and the test suite (`cargo test` + `pytest`, three
  platforms) now gates merges — the workspace `cargo fmt`/`clippy` debt that
  previously blocked it has been cleared.

### Deprecated

- _Nothing yet — the deprecation path is in place for future changes._

[Unreleased]: https://github.com/elysiumui/elysium/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/elysiumui/elysium/releases/tag/v1.0.0
