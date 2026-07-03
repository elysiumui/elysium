# Hypershade

Hypershade is the Designer's node-graph material editor. It is
named after Maya's panel of the same role for parity reasons: same
mental model, simpler scope.

## Open

`Hypershade > Open Hypershade…` or `Window > Hypershade`. The
panel opens as a tab; drag its title bar to dock.

## Layout

- **Node graph (left, large)**: nodes + connections. Drag from a
  node's output port to another node's input port.
- **Node library (right, narrow)**: searchable list of node kinds.
- **Preview (bottom)**: a small live-rendered sphere or your
  selected geometry showing the active material.

## Node kinds

The library groups nodes into folders:

| Folder | Nodes |
|---|---|
| Inputs | Color, Float, Vector, Texture, Procedural Texture (Noise, Voronoi, Checker) |
| Math | Add, Subtract, Multiply, Divide, Lerp, Clamp, Pow, Smoothstep |
| Color | Mix, Hue/Saturation, Levels, Gamma |
| Geometry | UV, Normal, Position, Tangent |
| Lighting | Fresnel, Layer Weight (view-angle blend) |
| Output | PBR Surface (the final node) |

A material is a graph terminating in one **PBR Surface** node.

## A minimum material

The simplest material is one PBR Surface node with an Albedo
color input:

1. Drag **PBR Surface** from the library to the graph.
2. Drag **Color** to the graph; pick a hex value.
3. Connect Color's `out` to PBR Surface's `albedo` port.
4. Assign the material: right-click the PBR Surface > **Assign to
   Selection**.

The selected Mesh3D placement now renders with that color.

## Common patterns

### Texture into albedo

1. **Texture** node → set its file path.
2. Connect its `rgb` to PBR Surface's `albedo`.

The Mesh3D's UV is used by default; override by adding a UV node
in front.

### Roughness from a grayscale texture

1. **Texture** node with a grayscale roughness map.
2. Connect its `r` (just the red channel) to PBR Surface's
   `roughness`.

### Fresnel-driven specular

1. **Fresnel** node with an exponent of 5.
2. Connect to PBR Surface's `specular_intensity`.

The surface gets glossier at grazing angles. Useful for car paint
or iridescent wings.

## Live preview

The bottom preview sphere updates every node change. If your
material has UV-mapped textures, the sphere shows them spherically
mapped; toggle the preview shape to **Selected** to see the
material on your actual geometry.

## Saving materials

`Hypershade > Save Material As…` writes the material's node graph
to a `.elymaterial` file (JSON, similar in spirit to `.elybrush`).
Reuse across projects via `Load Material…`.

## Limitations (v1)

- Subsurface scattering is not exposed as a node; use the SSS
  attributes on the PBR Surface directly.
- No volumetric / emissive node graph in v1; PBR Surface's
  `emissive` input handles solid color emission only.
- No custom shader code injection; node-graph only.

## See also

- [Lights](lights.md): light scenes for material preview.
- [Color space](color-space.md): how textures + materials
  interact with the working color space.
- [Texture transfer pipelines](texture-transfer-pipelines.md)  
  generate textures the material consumes.
