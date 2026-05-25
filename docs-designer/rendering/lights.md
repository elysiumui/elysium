# Lights

The Designer ships four kinds of light: Directional, Point, Spot,
and IBL (image-based lighting from an HDR). Most scenes use a
single Directional + ambient; IBL is the right choice for hero
PBR renders.

## Light kinds

### Directional

Light from one direction, infinite distance. Like the sun.

`Rendering > Light > Add Directional`. Parameters:

| Parameter | Default | Effect |
|---|---|---|
| color | white | Light color (CSS hex or RGB) |
| intensity | 1.0 | Multiplier |
| direction | (-0.3, -1, -0.3) | Unit vector pointing FROM the light |
| shadows | on | Cast shadows from this light |
| shadow_blur | 1.0 | Soft shadow blur radius (pixels) |

The default direction points "down and slightly forward": usually
flattering for a subject facing the camera.

### Point

Light from a single point, attenuated by distance. Like a bare
bulb.

`Rendering > Light > Add Point`. Parameters:

| Parameter | Default | Effect |
|---|---|---|
| color | warm white | Light color |
| intensity | 100 | Higher than Directional because point lights attenuate |
| position | (cursor) | World position |
| radius | 0.1 | Sphere radius for soft shadows (0 = sharp) |
| range | 500 px | Falloff range |

Point lights are ideal for fairy lights, candles, and any
localized light source.

### Spot

Point light constrained to a cone.

`Rendering > Light > Add Spot`. Parameters:

| Parameter | Default | Effect |
|---|---|---|
| color | white | |
| intensity | 200 | |
| position | (cursor) | |
| direction | (0, -1, 0) | Cone axis |
| inner_angle_deg | 30 | Full intensity inside this cone |
| outer_angle_deg | 45 | Falloff between inner and outer |
| range | 800 px | Falloff range |

Spot lights are stage lights, flashlights, theatrical lighting.

### IBL (Image-Based Lighting)

`Rendering > Light > Add IBL…` opens an HDR picker. Pick a `.hdr`
or `.exr` panorama; the renderer uses it for ambient light and
specular reflections.

The Designer ships a small built-in IBL library (forest noon,
studio, sunset, night street, blueprint), plus accepts any HDR.

IBL is what makes the Blue Morpho's iridescence pop in the tutorial
chapter 7 render.

## Light gizmos

Lights are invisible in the canvas by default. `View > Show
Light Gizmos` draws small icons at light positions and arrows for
directions / spot cones. Click a gizmo to select the light.

## Group lighting

Multiple lights are common. Use the
[Sets tab](../interface/project-explorer.md#sets-tab) to group
related lights, then toggle the set's visibility for A/B
comparisons.

## Shadows

`shadows: on` enables shadow casting from this light. Each light's
shadow has:

- **shadow_blur**: pixels of soft-edge blur. 0 = hard edges, 3+ =
  area-light look.
- **shadow_density**: 0..1 fraction of darkness. 1.0 = fully dark
  shadows, 0.7 = partial.

For multiple shadow-casting lights, the renderer accumulates them
correctly. Production / Final quality presets resolve shadows
without bias artifacts.

## Performance

| Light kind | Per-frame cost (path-traced render) |
|---|---|
| Directional | ~1 ms |
| Point | ~1 ms |
| Spot | ~1.2 ms |
| IBL | ~3 ms |

Costs add roughly linearly. A scene with one Directional + one IBL
is the typical setup.

## See also

- [Hypershade](hypershade.md): how materials interact with lights.
- [Quality presets](quality-presets.md): render-time relationships.
- [Render layers](render-layers.md): render-time grouping of
  placements.
