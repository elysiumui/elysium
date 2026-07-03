# Color management

Reference for the Designer's color pipeline: input texture
interpretation, working space, output transforms.

## Working space

Internally the path tracer always works in **Linear sRGB**. This is
correct for physical light calculations; gamma-encoded values
produce incorrect lighting.

The Designer handles input → working and working → output
conversions automatically.

## Output spaces

| Space | Use case |
|---|---|
| sRGB | Web, social, 8-bit screens (default) |
| Linear sRGB | VFX comp pipelines that grade downstream |
| ACEScg | Cinematic look-dev |
| Rec.709 | HD broadcast |

Picked from `Rendering > Color Space > …`. The active space lands
in the `.esk` bundle's `manifest.json` so the framework matches
at runtime.

## Input transforms

Per-texture role defaults:

| Role | Default input space | Linearize on load? |
|---|---|---|
| Albedo / Diffuse / BaseColor | sRGB | yes |
| Normal | Linear | no |
| Roughness / Metalness / AO / Mask | Linear (single channel) | no |
| HDR environment / IBL | Linear | n/a (already linear) |

Per-texture overrides: select the texture in the Project Explorer,
in the Properties pane set **Input Space** to the correct value.

## OCIO

The Designer ships ACES 1.3 by default. To swap in a custom config:

`Preferences > Rendering > OCIO Config` → pick a `config.ocio`
file. Custom configs unlock additional output transforms in the
`Rendering > Color Space` menu.

## Display gamut

The Designer queries the active monitor's gamut on startup. On
wide-gamut displays (P3, Rec.2020), output is mapped from the
chosen working space using OCIO's display transform.

For deliverables targeting a different display than your authoring
monitor, render through OCIO's "display reference" mode: a flat
output that downstream comp tools can re-grade for the target
device.

## Bit depth and format

| Format | Bit depth | Space |
|---|---|---|
| PNG (8-bit) | 8 | sRGB encoded |
| PNG (16-bit) | 16 | sRGB encoded |
| JPG | 8 | sRGB encoded |
| EXR (half) | 16 float | Linear (chosen output space) |
| EXR (full) | 32 float | Linear (chosen output space) |
| TIFF | 8/16/32 | Any |

For VFX prefer EXR; for delivery prefer PNG.

## Brushwork

The brush system writes into the working space at the working
bit depth. When the result is exported as a PNG, the brush mask is
sRGB-encoded; when exported as EXR, it stays linear.

## See also

- [Color space](../rendering/color-space.md) (Designer)
- [AOVs](../rendering/aovs.md)
