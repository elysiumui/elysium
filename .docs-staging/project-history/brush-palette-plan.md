# Brush Palette Redesign — Procreate + CSP Hybrid

## Goal
Replace the current swatch-grid brush palette with a system that combines Procreate's gestural immediacy and CSP's pro-grade modularity, while staying native to Elysium's existing architecture (Placement + props, hot-reload, .esk bundling, AnimState, theme-aware paint).

The non-negotiables:
1. The artist's hand never needs to leave the canvas for the common case.
2. Power users can author + share custom brushes with full parameter control.
3. Standard formats (.abr from Photoshop, .sut from CSP if technically feasible) import via drag-and-drop.
4. The *brush engine* and the *brush preset* are decoupled — one engine can spawn infinite presets, and importing a preset never requires changes to the engine code.

---

## Conceptual model — Engine + Preset + Tray

Three orthogonal layers, named to match the user's mental model:

### Layer 1 — Brush Engine (the "how")
A registered Python class that owns *stroke rendering*: how a sequence of (x, y, pressure, tilt, velocity, time) samples becomes pixels on the PaintMask. Engines are immutable in a session; users don't edit them — they pick one and parameterise it.

**Initial engine set (v1):**
- `RoundStamp` — single-dot stamp at each sample, controllable spacing + jitter (the existing Elysium brush).
- `WetMix` — Procreate's signature: samples blend with the underlying mask via alpha-weighted averaging instead of replacement.
- `Bristle` — multi-strand bristle simulation; each strand has its own offset + pressure curve (covers ink / charcoal / dry-media looks).
- `Airbrush` — Gaussian-falloff dot, density-modulated by flow + pressure.
- `Pattern` — tiles a sampled image along the stroke (chains / scales / leaves — CSP's "decoration" brushes).
- `Texture` — applies a grain mask to a base stamp (paper/canvas grain over a flat ink).

Each engine declares its own parameter schema (a list of `(name, type, min, max, default)` tuples). The UI auto-generates sliders from that schema, so adding a new engine is a single-file change in `python/elysium/brush/engines/`.

### Layer 2 — Brush Preset (the "what")
A dict-backed record:
```
{
  "id":            "elysium.ink.fineliner",
  "name":          "Fineliner",
  "engine":        "RoundStamp",         # references a registered engine
  "params":        {"size": 6, "flow": 0.85, "spacing": 0.08, ...},
  "color_mode":    "active",             # "active" | "fixed" | "image"
  "fixed_color":   (0, 0, 0, 255),
  "thumbnail":     "presets/ink_fineliner.png",
  "category":      "Ink / Liners",
  "tags":          ["ink", "line", "thin"],
  "source":        "builtin",            # "builtin" | "imported:abr" | "user"
  "imported_from": "",                   # path of the .abr / .sut if imported
  "created_t":     1715000000,
  "last_used_t":   1715200000,
}
```

Presets are JSON files under `examples/butterfly/butterfly.esk/brushes/` (in-skin presets ship with the project) or `~/Library/Application Support/Elysium/brushes/` (user library — shared across skins). Both directories are walked at startup and on hot-reload.

### Layer 3 — Tray (the "where it lives")
Three trays compose the runtime UI:
- **Library** — full nested tree of every available preset, organised by Category › Sub-category › Preset (CSP's three-level hierarchy). Modal panel, opened by clicking the active-brush chip.
- **Quick Wheel** — a radial menu of 8 favourited presets, summoned by holding a hotkey (`B` for Brush — re-using the existing marking-menu infrastructure). Closes on release; the slice under the cursor becomes active. This is Procreate's QuickMenu.
- **Recents** — bottom strip showing the last 8 presets used, auto-updated. Single click activates; right-click pins to the Quick Wheel.

---

## UI surfaces

### Brush Chip (always visible)
A 48 × 48 thumbnail in the status line showing the active preset. Hover reveals: name + engine + size + flow at a glance. Click → opens the Library. Right-click → opens the Tool Properties dock (below).

### Tool Properties Dock (CSP-style, always-on)
A new collapsible panel that lives at the bottom of the right column (below the Properties pane). When a brush tool is active, the dock shows live sliders for the *current preset's* most-used parameters — size, flow, spacing, jitter, smoothing (stabilisation), opacity. Changes write back to a *session-scoped override* of the preset; an explicit **"Save as preset"** button persists the change to a new JSON file.

Critically: sliders don't open a modal. Drag = continuous, the canvas previews the change in real time. This is the CSP property-palette behaviour.

### Quick Wheel (Procreate gestural)
Holding `B` for > 180 ms (or right-clicking the Brush Chip) opens an 8-slice radial menu centred on the cursor. Each slice shows a 32 × 32 thumbnail + the preset name. Release-on-slice activates. The user pins / reorders via long-press on a slice → drag.

Slices are pre-populated with the 8 most-recent presets on first launch, then the user curates them.

### Library Modal (CSP workspace)
Full-form modal with three columns:
- **Left** — category tree (folder icons, expandable, drag-and-drop reorder).
- **Centre** — preset grid (4 × N, thumbnails + names, scroll).
- **Right** — preview pane: live stroke render of the highlighted preset on a small canvas, plus the full parameter dump (read-only here — to edit, hit "Open in Brush Studio…").

A search box at the top filters by name + tags + engine name. Esc closes; clicking a preset in the grid sets it active without closing (so the user can audition multiple before committing).

### Brush Studio (deep customisation, Procreate-style)
Reached via "Open in Brush Studio…" from the Library preview pane. A larger modal organised into tabs that map to the engine's parameter groups:
- **Shape** — stamp / bristle / pattern source, jitter, taper.
- **Grain** — texture mask (an imported Asset image), scale, rotation.
- **Stroke Dynamics** — pressure curve, tilt curve, velocity curve (three editable bezier curves with a live preview stroke).
- **Wet Mix** — only shown when engine = WetMix; controls blend weight, wetness decay.
- **Colour Dynamics** — hue/sat/val jitter per stamp.
- **Apple Pencil / Tablet** — pressure + tilt mappings (will respect existing native input plumbing).

Each tab has a "Reset to default" button. The footer has Save / Save As / Cancel.

---

## Smart organisation

### Recents
Track last 8 presets in `self.brush_recents: list[str]` (preset IDs). Updated on every stroke commit. Persisted to user prefs.

### Favorites
The 8 slices of the Quick Wheel. Stored as a fixed-length list of preset IDs in user prefs; the special value `None` for empty slots.

### Smart-link (Procreate parity)
Right-click a Recents preset → "Reveal in Library". The Library opens with the preset's category expanded and the preset highlighted. Same for Quick Wheel slices.

### Search index
On startup, build `self._brush_search_index: dict[str, list[str]]` mapping every word in (name + tags + category + engine) to the preset IDs containing it. The Library search box queries this index — instant filter even with thousands of presets.

---

## Import / Export

### Drag-and-drop import
The existing `_handle_file_drop` already triages by extension. Add three new branches:
- `.abr` — Photoshop brush set. Parsed by a new `python/elysium/brush/abr.py` module (well-documented format; the stamp images + parameters extract cleanly). Each brush becomes a preset under category "Imported › Photoshop / `<filename>`". Multi-brush .abr files create a folder.
- `.sut` — CSP brush. Parser lives in `python/elysium/brush/sut.py`. CSP's .sut is a zipped SQLite database with a documented schema; viable but a larger build-out than .abr — flag as "best-effort, may not capture every CSP-specific dynamic".
- `.elybrush` (native) — a single preset's JSON + thumbnail PNG zipped together. Used for sharing presets between Elysium users.

A drop OUTSIDE the canvas (status line / Library modal / Project Explorer Assets) imports as library entries; a drop ON the canvas would still be ambiguous so we'll route it to the Library too with a "Imported N brush(es) — open Library to use" status message.

### Export
Right-click any preset → "Export…" → file dialog → writes a `.elybrush`. Multi-select export packs into a single `.elybrush-set` zip.

### Project Explorer Assets integration
Imported brush sets become a new asset category, **"Brush Sets"**, next to Textures / Models / Audio etc. Each `.abr` / `.sut` / `.elybrush-set` file in the skin folder shows there, with the same eye + trash buttons. Trash-deleting the file also un-registers every preset it contributed (with the same confirmation modal).

---

## Mechanics vs. Presets — the separation in code

```
python/elysium/brush/
├── __init__.py          # public API: register_engine, list_presets, get_preset
├── engine.py            # abstract BrushEngine base + sample-dispatch helpers
├── engines/
│   ├── round_stamp.py
│   ├── wet_mix.py
│   ├── bristle.py
│   ├── airbrush.py
│   ├── pattern.py
│   └── texture.py
├── preset.py            # Preset dataclass + JSON load/save
├── library.py           # walks builtin + user dirs, builds search index
├── abr.py               # Photoshop .abr importer
├── sut.py               # CSP .sut importer (best-effort)
└── elybrush.py          # native .elybrush import/export
```

Adding a 7th engine is one file in `engines/`. Adding 50 new presets is dropping 50 JSON files into the library dir — no code change. This is the "engine ≠ preset" contract that lets the system scale without bloating the codebase.

---

## Phased rollout — what ships when

### Phase A — Foundation (no UI changes yet)
- `python/elysium/brush/` package + the base `BrushEngine` class.
- Port the existing brush behaviour into `engines/round_stamp.py` — exact pixel-for-pixel parity, no regressions.
- Library walker reads builtin presets from `python/elysium/brush/builtin/` (~15 starter presets across the 6 engines).
- The existing brush palette swatch grid stays as the UI; nothing in user workflows changes.

**Ship gate:** every existing brush stroke still works pixel-identically.

### Phase B — Brush Chip + Tool Properties Dock
- Status-line Brush Chip replaces the old palette swatch.
- Tool Properties Dock added to the right column. Live sliders for size, flow, spacing, jitter.
- Recents tracking starts; bottom strip in the dock shows last 8.

**Ship gate:** an artist can change brush size + flow while actively painting, without entering a modal.

### Phase C — Library Modal
- Full Library modal with category tree, preset grid, preview pane.
- Search index.
- Smart-link "Reveal in Library".

**Ship gate:** ≥ 30 starter presets organised across 6 engines; library opens in < 100 ms even with 500+ presets.

### Phase D — Quick Wheel + Favourites
- Marking-menu radial trigger on `B`-hold.
- Pin / reorder via long-press drag.
- Favourites persist in user prefs.

**Ship gate:** brush switching is < 1 second hand-on-tablet (hold-B → release-on-slice).

### Phase E — Brush Studio
- Deep parameter editor with tabbed UI.
- Bezier curve editors for pressure / tilt / velocity dynamics.
- Save / Save As.

**Ship gate:** user can author a custom brush from scratch and have it persist across Designer restarts.

### Phase F — Imports
- `.abr` import (the high-leverage one — millions of Photoshop brushes exist).
- `.elybrush` native format + drag-and-drop.
- `.sut` import (best-effort, behind a feature flag).
- Project Explorer "Brush Sets" asset category.

**Ship gate:** drag a public .abr from the desktop onto the Designer → see ≥ 80 % of the brushes' stamps faithfully imported and usable on the next stroke.

### Phase G — Polish
- Apple Pencil / tablet pressure + tilt plumbing through to engines (native side already exposes these — Brush Studio surfaces them).
- HD thumbnails for builtin presets.
- Migration doc + the keyboard-shortcut help update.

---

## Open questions for the next conversation

1. **Hotkey for the Quick Wheel.** I proposed hold-`B`, which conflicts with Maya's Soft Select toggle (also `B`). Two options: (a) move Soft Select to a less-used key, (b) use a different hotkey for the Quick Wheel — say hold-Tab or hold-`F12`. The user's preference here will affect the marking-menu wiring.
2. **Where Brush Sets live in the .esk bundle.** Two options: (a) per-skin (`butterfly.esk/brushes/`) — the skin is self-contained but brushes don't travel between projects, (b) user-global (`~/Library/Application Support/Elysium/brushes/`) — brushes follow the user but a shared skin won't have the same brush available everywhere. Industry convention is (b) with optional per-project overrides; I'd recommend that.
3. **`.sut` parser depth.** CSP's format is documented but vast — supporting every dynamic is a multi-week effort. Cheapest viable cut: parse the stamp image + brush size + flow + spacing, leave everything else at the engine's defaults. Worth doing?
4. **Per-stroke undo granularity.** Today the canvas brush commits one undo per *down-up*. Procreate commits per *stamp* (so you can erase the last few pixels). The hybrid is per-stroke undo + a "stroke-trail" overlay that highlights the last stroke's coverage so the user can spot mistakes before lifting. Worth the complexity, or stick with per-stroke?
5. **GPU compute path.** Bristle + WetMix are CPU-friendly only up to ~512 × 512 strokes/sec. Beyond that we need the wgpu compute shader. The existing render pipeline has the wgpu device wired in for PBR — I'd reuse it. Confirm direction before Phase A starts.

---

## Why this hybrid, not Procreate-only or CSP-only

- **Procreate-only** would mean a slick wheel-and-recent UX but no nested categories, no Tool Properties dock, no .abr import. Power users would hit the ceiling within their first week of pro work.
- **CSP-only** would mean a vast palette of always-visible panels (Sub Tool, Tool Property, Sub View, Brush Material, Color History…) that crowd the screen and disrupt Elysium's "minimal chrome over canvas" identity.
- **The hybrid** keeps the immersive Quick Wheel + Brush Chip + Recents on top (Procreate), backed by a CSP-style Library + Tool Properties + Brush Studio for when the user genuinely needs depth. The artist's *common case* (switch brush, change size, paint) stays gestural; the *uncommon case* (build a custom brush, import a brush pack) gets the full pro toolkit.

The decoupled Engine + Preset layer is the architectural move that makes both halves coexist without doubling the codebase: one engine powers thousands of presets, and the UI surfaces are just different views over the same preset registry.
