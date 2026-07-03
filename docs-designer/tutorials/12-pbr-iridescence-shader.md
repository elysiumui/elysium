# PBR iridescence shader

Time: 45 minutes. Difficulty: Intermediate.

Author an iridescent material in Hypershade for a Blue Morpho-style
look. Useful for wings, oil slicks, soap bubbles, and any surface
with view-angle-dependent color.

## Prerequisites

- Designer installed.
- Mesh3D + a directional light in your scene (see
  [Blue Morpho chapter 7](../getting-started/butterfly/07-render-and-export.md)).

## Open Hypershade

`Hypershade > Open Hypershade…`. Drag your mesh's material into
the graph view.

## The pattern

Iridescence is the **same texture sampled at two hues with a
fresnel mix**. Where the surface faces the camera, color A
dominates; at grazing angles, color B.

## Build the graph

1. Drop a **Texture** node, load your albedo PNG.
2. Drop a **Color** node, set to `#9333eaff` (deep purple).
3. Drop a **Color** node, set to `#22d3eeff` (cyan).
4. Drop a **Mix** node. Connect:
   - input A: the purple Color.
   - input B: the cyan Color.
   - factor: a **Fresnel** node (exponent 4-6).
5. Drop a **Multiply** node. Connect:
   - input A: the Mix output.
   - input B: the Texture's rgb output.
6. Connect the Multiply result to **PBR Surface > albedo**.

Set the PBR Surface's roughness to 0.15 (slight gloss) and
metallic to 0.0.

## Add specular shift

Iridescent surfaces also shift specular highlights. Add a second
Mix node feeding **PBR Surface > specular_tint** from the same
Fresnel. The tint shifts blue → magenta with view angle.

## Preview

The Hypershade preview sphere shows the material live. Orbit (Alt
+ middle drag): the color sweeps purple → cyan as the sphere
rotates.

## Apply to the mesh

Right-click PBR Surface > **Assign to Selection**. The mesh in the
View Panel updates.

## Render

`Rendering > Render Quality > Preview (12 spp)`, `Rendering >
Render Selected`. The render captures the iridescence at one
specific angle: orbit the camera and re-render for different
looks.

## Save the material

`Hypershade > Save Material As…` → `iridescence.elymaterial`.
Reuse across projects via `Load Material…`.

## Tuning

- **More vibrant**: raise both Colors' saturation in OKLab; use
  `lighten` and `darken` to keep perceptual balance.
- **Sharper transition**: raise the Fresnel exponent (6 → 12).
- **Bandwidth**: add a third Color and a second Mix for a
  three-band iridescence (oil-slick rainbow look).

## Export

`File > Export > .esk Bundle`. The material ships with the skin.

## What you exercised

- Hypershade node graph authoring.
- Fresnel + Mix as the iridescence pattern.
- `.elymaterial` save / load.
- Specular tint as a second iridescence channel.

## See also

- [Hypershade](../rendering/hypershade.md)
- [Lights](../rendering/lights.md)
