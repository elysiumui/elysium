# Importing Clip Studio Paint `.sut` files

Clip Studio Paint (CSP) brushes export as `.sut`. The Designer
imports them through the same `File > Import > Brush File…` flow as
`.abr`. CSP's brush model is more sophisticated than Photoshop's,
so the mapping is closer to one-to-one.

## Import

`File > Import > Brush File…` and pick a `.sut`. Drag-drop also
works. Imported presets appear under **Imported (.sut)** in the
Brush Library.

## How CSP brushes map

| CSP concept | Maps to |
|---|---|
| Tip shape | Round Stamp (geometric) or Pattern (image) |
| Sub tool detail > Brush tip > Hardness | Round Stamp `hardness` |
| Stroke > Spacing | `spacing` parameter |
| Anti-aliasing | Internal `aa` setting; off → Round Stamp pixel mode |
| Stabilization | `smoothing` parameter |
| Pressure curve | Direct port to the `pressure → size` curve |
| Tilt influence | Bound to `tilt → angle` (Bristle / Pattern engines) |
| Texture | Texture engine + captured texture |
| Watercolor edge | Wet Mix engine with edge bleed parameter |
| Mixing brush | Wet Mix engine `wet_paint`-on |
| Continuous spray | Repeated stamping with random scatter |

## CSP versions

Tested with CSP 1.10 - 4.x. CSP's `.sut` format has been stable
across major versions; older files import without warnings.

## Per-bristle data

CSP exports per-bristle brush data for some advanced presets. The
Designer's Bristle engine accepts these for fidelity:

- Bristle count (1 - 64).
- Bristle gap (0 - 1, fraction of brush radius).
- Bristle randomness (0 - 1).

When the source `.sut` carries these, they import directly into the
Bristle engine. When it does not (which is most "Pen" presets), the
brush imports as Round Stamp.

## Vector vs raster brushes

CSP has two brush categories. Both import:

- **Raster brushes** (the majority): import to one of the six engines
  by the mapping table above.
- **Vector brushes**: import as Round Stamp with the path stored as
  a stylistic vector hint. The Designer paints rasterized output by
  default; turning on **Vector mode** in the resulting preset's
  Properties pane re-enables vector-style stroke output.

## What does not import

- **CSP's pressure curves with non-monotonic shapes**: the Designer
  requires monotonic `pressure → size` curves. Imports clamp any
  non-monotonic curve to its monotonic envelope.
- **Sub-tool groups**: CSP groups several brushes under one tool
  for easy switching. Each sub-tool becomes a separate `.elybrush`
  preset; the group structure is lost.
- **Touch-only gestures**: CSP can bind two-finger gestures to a
  specific sub-tool. The Designer's gesture system is configured
  in [Touch and dynamics](touch-and-dynamics.md), so these bindings
  are ignored during import.

## Per-locale brush names

CSP supports brush names in multiple languages. The Designer picks
the name in the order of: your system locale → English → first-
defined locale. To switch later, right-click the preset in the
Library > **Localize Name** and pick from the available languages.

## Bulk import

Drop a folder of `.sut` files onto the canvas to import the whole
set in one go. The importer presents a confirmation dialog
listing what it found.

For very large sets (>200 brushes), the Library auto-creates a tag
matching the original folder name, so the imported set stays
together visually.

## Sharing

Like `.abr` imports, every CSP brush becomes a regular `.elybrush`
file in your [user brushes folder](library-tour.md#on-disk). Share
the `.elybrush` files directly: recipients do not need Clip Studio
Paint.

## Reverse-engineering note

CSP's `.sut` format is undocumented but stable. The Designer's
importer matches the reverse-engineered structure published by the
open-source community (the same approach used by Krita, Aseprite,
and others). When CSP ships a new version we verify the format
within ~2 weeks and ship a Designer update if anything moved.
