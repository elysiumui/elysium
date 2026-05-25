# Importing Photoshop brushes

Time: 20 minutes. Difficulty: Intermediate.

Bring a `.abr` brush pack into the Designer's Brush Library,
audition each preset, and tweak the imported brushes for the
Designer's engines.

## Prerequisites

- A `.abr` file (Kyle T. Webster, Adobe Creative Cloud, or any
  pack you bought).
- Designer installed.

## Import

`File > Import > Brush File…` and pick the `.abr`. A progress
strip shows each brush being imported:

```
[1/24] Diluted Watercolor
[2/24] Diluted Wash
…
[24/24] Wet Sponge
```

Each brush becomes one `.elybrush` preset under **Imported (.abr)**
in the Brush Library.

## Audition

`B` to activate Brush. Open the Library; filter by **Source >
Imported (.abr)**. Click each thumbnail to apply.

Make a quick stroke on a scratch placement. The imported brush
should produce strokes close to the Photoshop original.

## Inspect the mapping

Photoshop's brush format is older and richer than the Designer's;
the importer makes pragmatic choices. To see what mapped:

1. Right-click a preset > **Open in Studio**.
2. Note the engine the importer picked (Round Stamp, Wet Mix,
   Bristle, etc.).
3. See [Importing .abr](../brush/importing-photoshop-abr.md) for
   the full mapping table.

## Tweak

For Photoshop brushes that don't quite work after import, common
fixes:

- **Stamps too sparse**: lower spacing.
- **Wet edges missing**: switch engine to Wet Mix.
- **No dynamics**: rebind `pressure → size` and `pressure →
  opacity` in the dynamics grid.

Save back via the Studio's **Save** button. The original `.abr`
file is untouched; only your `.elybrush` copy changes.

## Bulk import

For a folder of `.abr` files, drag the folder onto the canvas.
The Designer imports each in turn. A Library tag matching the
folder name is auto-added so the set stays grouped.

## Sharing

After importing, the resulting `.elybrush` files in your user
library are standalone. Share by zipping the relevant files;
recipients drop them into their user library and the brushes
appear in their Designer.

## What you exercised

- `File > Import > Brush File…`.
- Library filtering by Source.
- Brush Studio for post-import tweaks.
- The `.abr` → engine mapping table.

## See also

- [Importing Photoshop .abr](../brush/importing-photoshop-abr.md)
- [Importing CSP .sut](../brush/importing-csp-sut.md)
- [Custom brush from a photo](04-custom-brush-from-photo.md)
