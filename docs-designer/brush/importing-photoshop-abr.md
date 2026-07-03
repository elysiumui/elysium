# Importing Photoshop `.abr` files

Photoshop brush sets ship as `.abr` archive files. The Designer
imports them in one step, mapping Photoshop's brush concepts onto
the Designer's six engines.

## Import

`File > Import > Brush File…` and pick a `.abr`. Or drag-drop the
file anywhere onto the canvas. A progress bar shows the import:

```
[1/24] Diluted Watercolor
[2/24] Diluted Wash
[3/24] Loose Strokes
…
[24/24] Wet Sponge
```

Each Photoshop brush becomes one `.elybrush` preset under
**Imported (.abr)** in the Library.

## How brushes map

Photoshop's brush format is much older than the Designer's engines.
The importer makes pragmatic choices:

| Photoshop concept | Maps to |
|---|---|
| Brush tip shape (round / oval / custom image) | Round Stamp (round / oval) or Pattern (custom image) engine |
| Scattering | Spacing + random dynamics on x / y offset |
| Shape dynamics | Dynamics curves on size, roundness, angle |
| Color dynamics | Dynamics curves on hue / sat / brightness |
| Wet edges | Wet Mix engine when both wet edges + dual brush are on |
| Texture | Texture engine + the captured texture |
| Dual brush | Single brush with the dual brush texture composited |
| Smoothing (CS6+) | smoothing parameter on the resulting brush |

The mapping is best-effort but consistent. The
[Engines reference](engines-reference.md) explains each engine's
parameter ranges so you can hand-tune after import.

## Photoshop versions

Tested with:

| Version | Status |
|---|---|
| Photoshop CS5 - CC 2024 | Full support |
| Photoshop CS3 - CS4 | Partial: dual brush data ignored |
| Photoshop CS2 and earlier | Tip shapes import; dynamics are reset |

For unsupported `.abr` versions, the importer surfaces a clear
error and writes a partial Library entry with reset dynamics so
the brush is still usable.

## Custom tip images

Brushes that use a custom image as the tip (Photoshop's "Sample
Brush") map to the Pattern engine. The tip image is extracted
losslessly from the `.abr` and stored alongside the preset.

If the tip image is large (>512 px), the importer asks whether to
downsample to 512 px. This trades fidelity for stroke performance;
512 px tips stamp at ~3000 stamps/sec, full-res at ~500 stamps/sec.

## Where files land

The imported presets and any extracted tip images go under your
[user brushes directory](library-tour.md#on-disk). Each
`.elybrush` carries a `source: { kind: "abr", file: "name.abr" }`
field so you can find which set a brush came from.

## Re-importing

To update from a newer version of a `.abr`, re-import it. The
Designer offers three options when an existing preset matches by
name:

- **Overwrite**: replace the preset with the new import.
- **Keep both**: add the new one with a "(2)" suffix.
- **Skip**: leave the existing preset.

Per-preset choice is shown in a small modal. You can also bulk-
apply: "Overwrite all" / "Keep both for all".

## Sharing

Imported presets are stored as regular `.elybrush` files in your
user folder. To share them with a teammate (without re-bundling the
original `.abr`), zip the relevant `.elybrush` files. They drop in
on the recipient's side with no Photoshop install required.

## What does not import

- Photoshop's mixer brush wet/dry mixing is **not** ported: Wet
  Mix engine has its own wet model. Wet-edges Photoshop brushes
  map to Wet Mix with sensible defaults but are not pixel-perfect.
- Photoshop legacy "noise" and "airbrush mode" toggles map to
  hardcoded Airbrush defaults.
- Color presets attached to a brush import as the brush's default
  color but do not bring along Photoshop's swatch panel.
