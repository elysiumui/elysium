# Erase and Fill

Two paint-family tools that round out brushwork: Erase (subtractive
brushing) and Fill (flood-fill a connected region).

## Erase

The Erase tool is the inverse of Brush. Same engines, same engine
parameters, same dynamics curves; the only difference is the
composite mode (write zero alpha instead of accumulating color).

| Path | Action |
|---|---|
| Toolbox > Tools > Erase | Click the icon |
| Keyboard | `Shift+B` from Brush, or `Shift+B` from anywhere |

`Shift+B` toggles between Brush and Erase. Hold `B` to enter the
Quick Wheel even from Erase; the picked engine becomes the active
**Brush** engine and toggling restores the matching Erase engine.

### Why share engines

Erasing with a hard Round Stamp leaves crisp gaps; erasing with
the Airbrush feathers them; erasing with Wet Mix softens edges
toward the underlying color (great for reducing oversaturation
without going to gray). The shared engine surface keeps the
mechanics identical so users do not learn twice.

### Hardness and pressure

A pressure-sensitive Erase respects the same `pressure → opacity`
curve as Brush. Light press leaves faint traces of the underlying
paint; full press deletes to fully transparent.

### Erase only on the active layer

Erase, by default, only affects the active layer. Toggle "All
layers" in the
[Tool Properties dock](../interface/tool-properties-dock.md) to
erase through every layer.

## Fill

Flood-fill the connected region the cursor is over. Picks up the
target color from the current pixel and replaces every adjacent
pixel matching the source within a configurable tolerance.

| Path | Action |
|---|---|
| Toolbox > Tools > Fill | Click the icon |
| Keyboard | `G` |

### Tolerance

The Tool Properties dock shows the tolerance slider (0 - 1.0). 0
means "only exactly this color"; 1.0 means "everything connected".
Most fills work well at 0.05 - 0.15.

### Anti-alias

For soft-edged fills (where the boundary is a gradient, not a hard
line), enable **Anti-alias fill** in the dock. The flood ramps
opacity at the boundary instead of hard-clipping.

### Sample mode

| Mode | Source pixel |
|---|---|
| Active Layer | The clicked layer's pixel (default) |
| All Layers | The composited pixel from every layer above + below |
| Mask Only | The mask alpha (paints into mask, ignores RGB) |

Fill with Mask Only is the right mode when authoring a render-part
mask by clicking inside the desired region.

### Contiguous

`Contiguous: on` (default) fills only the touching region.
`Contiguous: off` fills every pixel that matches the source color
on the entire layer: useful for swapping a single color across
the whole canvas.

## Common patterns

### Erase the soft edge after Airbrush

After overshoot on an Airbrush stroke, switch to a Round Stamp
Erase at low opacity to clean up the soft halo without nuking the
core color.

### Fill the body, then paint the wings

For a Monarch-style butterfly: Fill with `Mask Only` + `Contiguous`
to mask the body region, then paint only the wings: paint outside
the mask is ignored.

### Replace a single color across the canvas

Set Contiguous off, click anywhere in the source color, and Fill
swaps every matching pixel to the new color. Faster than
re-painting.

## See also

- [Brush > Quick start](../brush/quick-start.md): the rest of
  the brush family.
- [Render part mask](../modeling/render-part-mask.md): the
  natural follow-on for Fill-as-mask.
