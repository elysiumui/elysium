# Library tour

The Brush Library ships with 30 built-in presets across six engines.
This page walks through every one with thumbnails and use cases so
you can pick a starting brush without guessing.

Open the panel with `Window > Brush Library` or click the library
icon in the [Tool Properties dock](../interface/tool-properties-dock.md).

![Brush Library panel showing the 30 built-in presets with thumbnails](../assets/brush-library.png)

## Round Stamp family (5)

Hard-edge or near-hard nibs. The workhorse engine.

| Preset | Look | Best for |
|---|---|---|
| Pencil | 4 px hard, low opacity | Sketching, line work |
| Felt Tip | 8 px medium-hard, full opacity | Outlines, marker fills |
| Hard Edge | 32 px max-hard, full opacity | Pixel-perfect fills, masks |
| Calligraphy | 12 px with tilt-driven angle | Ink lettering, hand-rendered titles |
| Soft Pencil | 6 px low-hardness, low opacity | Cross-hatching, gentle shading |

## Airbrush family (5)

Soft falloff for tone and atmosphere.

| Preset | Look | Best for |
|---|---|---|
| Airbrush | 40 px Gaussian | Skin, gradients, gentle masking |
| Soft Glow | 60 px wide falloff | Halos, light bleed |
| Spray | Fine grainy spray | Texture overlays, stippling |
| Cloud | Very large soft brush | Cloud forms, atmosphere |
| Vignette | 200 px very soft | Edge darkening, framing |

## Bristle family (5)

Multi-tip strokes with per-bristle paint flow.

| Preset | Look | Best for |
|---|---|---|
| Oil Round | 24 px round bristle | Painterly fills, scumbling |
| Oil Flat | 28 px flat bristle | Square edges, plane painting |
| Fan | Wide flat fan | Foliage, fur, hair |
| Hog Bristle | Rough multi-clump | Dry-brush, texture |
| Sumi | Tapered ink brush | East-Asian ink work, gestural lines |

## Texture family (5)

Repeating texture overlays.

| Preset | Look | Best for |
|---|---|---|
| Canvas | Linen warp-weft texture | Painterly grounds |
| Paper | Cold-press paper | Watercolor backgrounds |
| Concrete | Rough concrete grain | Industrial surfaces |
| Foliage Stamp | Photographic leaves | Tree masses, hedges |
| Noise Dapple | Procedural noise | Random texture overlays |

## Pattern family (5)

Single-image stamps along the stroke.

| Preset | Look | Best for |
|---|---|---|
| Star | Pointed star glyph | Sparkle highlights, magic |
| Heart | Outlined heart | Decorative borders |
| Confetti | Multi-color confetti scatter | Celebration FX |
| Snowflake | White six-arm flake | Winter ambience |
| Petal | Pink petal scatter | Spring scenes, romance UI |

## Wet Mix family (5)

Real wet-on-wet color blending.

| Preset | Look | Best for |
|---|---|---|
| Watercolor Wet | High water, low pigment | Loose wash gradients |
| Watercolor Dry | Low water, high pigment | Detail strokes after a wash |
| Smudge | Pure smudge, no new paint | Soften edges, blur color |
| Pull Color | Drags pigment forward | Streaks, smears |
| Drip | Adds gravity-following drips | Wet drips, weathering |

## Search and filter

The library panel's top bar has:

- **Search** field (matches name, tag, engine).
- **Engine** dropdown (filter to one of the six).
- **Tag** filter (every preset has 1-4 tags: `dry`, `wet`, `texture`,
  `sketch`, `paint`, `mask`, `fx`).
- **Source** dropdown: **Built-in**, **My Presets**, **Imported
  (.abr / .sut)**.

## Save / star / delete

| Action | How |
|---|---|
| Apply a preset | Click its thumbnail |
| Star (favorite) | Click the ★ corner of any thumbnail |
| Save current brush as preset | "Save Current…" button |
| Rename | Right-click > Rename |
| Delete (user presets only) | Right-click > Delete |

## On disk

User presets live in:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Elysium Designer/brushes/user/` |
| Windows | `%AppData%\Elysium Designer\brushes\user\` |
| Linux | `~/.config/elysium-designer/brushes/user/` |

Files are `.elybrush` JSON (see [Native .elybrush format](native-elybrush-format.md)).
The directory is safe to symlink across machines.
