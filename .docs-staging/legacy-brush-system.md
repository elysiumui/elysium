# Brush System — User Guide

Elysium Designer's brush system blends Procreate's gestural immediacy
with Clip Studio Paint's pro-grade modularity. Three layers compose
the workflow:

* **Engine** — how a stroke renders pixels (RoundStamp, WetMix,
  Bristle, Airbrush, Pattern, Texture). Engines ship with the
  Designer; you pick one and parameterize it.
* **Preset** — a saved engine + parameter snapshot + optional
  Dynamics curves. Presets are individual JSON files on disk.
* **Tray** — the runtime UI that exposes presets: Brush Chip,
  Tool Properties Dock, Quick Wheel, Library Modal, Brush Studio.

## Brush switching — fastest to slowest

| Path | Speed | When |
|------|-------|------|
| **Quick Wheel** — hold `B`, release on slice | < 1 s | Mid-stroke brush change to one of your 8 favorites |
| **Recents strip** — bottom of the dock | < 1 s | Switch to a brush you used in the last few minutes |
| **Library Modal** — click the Brush Chip | 2–4 s | Browse all presets by category or search |
| **Brush Studio** — Library → "Open in Brush Studio…" | 5+ s | Author or fine-tune a brush; persist changes to disk |

## Tool Properties Dock

Floats at the bottom-center of the canvas whenever a brush tool is
active. Six live sliders write to the active brush:

* **Size** (1–120 px) — also mirrored to the Properties pane's
  `brush_radius` so the legacy slider stays in sync
* **Opacity** (0–1) — stroke alpha
* **Hardness** (0–1) — edge softness; 0 = soft falloff, 1 = hard edge
* **Flow** (0–1) — per-stamp alpha contribution; lower = build-up
  over many stamps
* **Spacing** (0.01–1) — distance between stamps as a fraction of
  brush size
* **Jitter** (0–1) — per-stamp position randomness (deterministic
  from the sample index — same stroke produces the same pixels)

Slider changes apply mid-stroke; the next stamp uses the new value.

## Library Modal

Click the Brush Chip to open. Three columns:

* **Categories** (left) — `All` row + every category from the preset
  set. Click to filter.
* **Preset grid** (center) — 4-column tile grid. Hover highlights;
  click activates without closing (Procreate-style audition).
* **Preview pane** (right) — name + engine + category + tags, an HD
  thumbnail rendered from a sample stroke, full parameter dump,
  `Pin to Quick Wheel` slot buttons, `Set as Active Brush`, and
  `Open in Brush Studio…`.

Search box across the top filters by name + tags + engine + category.
Esc closes. Library opens in under 100 ms even at 500+ presets.

## Brush Studio (deep customization)

Reached via the Library preview pane. Engine-aware tab bar:

* **Shape** — sliders for every numeric param in the engine's schema
* **Grain** — only when the engine has grain params (Texture)
* **Wet Mix** — only when engine is WetMix
* **Color** — hue / saturation / value jitter
* **Dynamics** — four touch-input curves: `Pressure → Size`,
  `Pressure → Opacity`, `Pressure → Flow`, `Velocity → Spacing`.
  Each is a 4-point polyline editable by dragging control points;
  Y range is [0, 2] so curves can both attenuate and amplify.
* **Touch / Input** — live telemetry showing the current pressure
  and velocity values. **Tilt is intentionally absent** — Windows
  touch screens (the Designer's target hardware) don't report tilt.

Footer: Cancel | Reset Tab | Save As… | Save.

* **Save** overwrites the active preset's JSON in-place
* **Save As** creates a new preset (`user.<slug>`) in your user
  brushes dir
* **Reset Tab** restores just the current tab's params to engine
  defaults (Dynamics tab → flat 1.0 curves)

## Input — Windows touch pressure

The Designer reads per-sample pressure from Windows' WM_POINTER
pipeline on touch-capable hardware. On mouse hardware (and any
device that doesn't report pressure) `brush_pressure` stays at 1.0
("full press"), which evaluates every Dynamics curve at x = 1.0 —
typically the curve's right endpoint, often the maximum value.

Velocity is sampled from the stamp-to-stamp cursor delta over
elapsed time. Normalized so ~600 px/s ≈ 1.0.

There is no tilt channel.

## Where brushes live on disk

* User-global: `~/Library/Application Support/Elysium/brushes/` on
  macOS, `%APPDATA%\Elysium\brushes\` on Windows, `~/.config/elysium/
  brushes/` on Linux.
* Per-skin override (optional): `<skin>.esk/brushes/` — beats the
  user-global dir for the same preset ID.
* Builtin source: `python/elysium/brush/builtin/` inside the
  installed package. Copied into the user dir on first launch;
  subsequent launches respect any user edits.

Each preset is a single `.json` file. Adding a new preset is dropping
a JSON into the user brushes dir — no Designer restart required.

### Favorites + Quick Wheel persistence

`favorites.json` (a top-level 8-element list of preset IDs) sits
alongside the presets. The Quick Wheel reads this file on first hold-
`B`; pinning a preset via the Library preview pane writes back
immediately.

## Importing brushes

Drag a `.abr` (Photoshop), `.sut` (Clip Studio Paint), or `.elybrush`
(Elysium native) file onto the Designer window. The importer:

* Extracts every brush in the file
* Writes each as a JSON in `<user dir>/imported/<source stem>/`
* Extracts stamp images into `<user dir>/imported_assets/`
* Reloads the library so the new brushes appear immediately
* Bumps the first imported preset to the front of Recents

`.elybrush-set` (zip-of-zips) auto-unpacks. `.sut` files containing
zipped SQLite databases are auto-extracted before the SQLite walk.

## Engine reference

| Engine | Best for | Distinguishing params |
|--------|----------|----------------------|
| `RoundStamp` | Inking, default workhorse | jitter, spacing |
| `WetMix`     | Watercolor, oil, blendy strokes | wetness, dilution, dry_rate |
| `Bristle`    | Charcoal, dry brushes | strands, scatter, strand_size |
| `Airbrush`   | Soft gradients, spray | density |
| `Pattern`    | Stamping a custom shape along the stroke | pattern_path, rotation, scale_jitter |
| `Texture`    | Pencil, chalk, dry-media grain | grain_path, grain_blend, grain_depth |

Engines are registered at package import time; `from elysium import
brush; brush.list_engines()` returns the full set. Adding a new
engine is one file in `python/elysium/brush/engines/` — no other code
change required.
