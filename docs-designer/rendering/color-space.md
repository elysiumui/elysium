# Color space

The Designer is color-managed end-to-end. The output color space
is chosen via `Rendering > Color Space > …`; the working space
is fixed to Linear sRGB internally; OCIO transforms map between
input textures, working space, and output.

## Choose an output space

| Space | Use for |
|---|---|
| sRGB | Web, social media, 8-bit screens; the default |
| Linear sRGB | VFX comp pipelines that color-grade downstream |
| ACEScg | Cinematic look-dev; matches feature-film pipelines |
| Rec.709 | HD broadcast |

For standalone skins, sRGB is the right call. For multi-stage
pipelines that go on to a color grade, output Linear sRGB or
ACEScg and apply the final transform downstream.

## Working space

Internally the path tracer always works in Linear sRGB regardless
of output. This is the right space for physical light
calculations; gamma-encoded values produce incorrect lighting.

You do not need to opt into this; the Designer handles the
conversions for you.

## Input transforms

Textures imported into the Designer carry an implicit "space"
based on their content:

| Texture role | Default input space |
|---|---|
| Albedo / Diffuse / BaseColor | sRGB (will be linearized) |
| Normal map | Linear (raw RGB) |
| Roughness / Metalness / AO / Mask | Linear (single-channel) |
| HDR environment / IBL | Linear (already linear, never gamma-encoded) |

Per-texture overrides are in the texture's Properties pane:
**Input Space**. Useful when you have an albedo image that was
mistakenly saved as Linear and needs to be re-tagged.

## Custom OCIO configs

`Preferences > Rendering > OCIO Config` lets you point at an
external `config.ocio` file. Useful when the production
pipeline is using a specific OCIO config (ACES 1.3, AgX, etc.).

The Designer ships ACES 1.3 by default. Custom configs unlock
additional output transforms that show up in the
`Rendering > Color Space` menu.

## Bit depth

The Designer renders internally at 32-bit float. Output bit depth
matches the file format:

| Format | Bit depth | Notes |
|---|---|---|
| PNG | 8 or 16 | sRGB encoded |
| JPG | 8 | sRGB encoded |
| EXR | 16 (half) or 32 (float) | Linear (any of the spaces) |
| TIFF | 8 / 16 / 32 | Any space; OCIO embed available |

For VFX work prefer EXR Linear; for delivery prefer PNG sRGB.

## Color picker

Color pickers throughout the Designer (Channel Box, Properties
pane, Hypershade) show colors in the working space's sRGB
representation by default. Toggle the picker to OKLCH for
perceptually-uniform color adjustments (the framework's themes
use OKLCH math internally).

## What happens at export

`.esk` bundles bundle the output color space in their
`manifest.json`:

```json
"color_space": "srgb"
```

The framework reads this on `load_skin` and configures its own
renderer to match.

## See also

- [Quality presets](quality-presets.md): render quality and bit
  depth.
- [AOVs](aovs.md): multiple pass outputs at full bit depth.
