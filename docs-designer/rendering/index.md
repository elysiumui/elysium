# Rendering and Lookdev

The Designer renders in two layers: the live View Panel
preview (Skia + wgpu, real time), and the production renderer (a
GPU-accelerated path tracer for stills and AOVs). This section
covers both, plus the texture transfer pipelines that bridge
Designer-authored geometry to PBR-ready surfaces.

## Two render paths

| Path | Used for | Quality | Speed |
|---|---|---|---|
| View Panel (Skia + wgpu) | Live editing | Approximate PBR | 60+ fps |
| Production (path tracer) | Stills, hero shots, .esk previews | Reference PBR | Seconds to minutes |

Switching is automatic: scrub the time slider and you see live;
`Rendering > Render Selected` triggers the path tracer.

## Pages in this section

- [Hypershade](hypershade.md): material editor (node-graph).
- [Quality presets](quality-presets.md): Draft / Preview /
  Production / Final.
- [Lights](lights.md): directional, point, spot, IBL.
- [Render layers](render-layers.md): grouping placements for
  multi-pass rendering.
- [Color space](color-space.md): sRGB / Linear / ACEScg / Rec.709
  workflows.
- [AOVs](aovs.md): Beauty / Diffuse / Specular / Normal / Depth
  passes.
- [Texture transfer pipelines](texture-transfer-pipelines.md)  
  the eight algorithms + two starred recommended pipelines.

## Materials

Each Mesh3D placement has a **material**. Materials store the PBR
inputs (albedo, normal, roughness, metalness, IBL contribution).
Edit in the Properties pane, or open the Hypershade for a node
graph.

Most authoring needs the simple Properties pane; reach for
Hypershade when chaining shaders, blending materials, or wiring
procedural inputs.

## Lights

A scene with no lights uses the framework's default ambient (the
flat headlight you see by default). Add `Rendering > Light >
Directional` for shadows + specular highlights. See [Lights](lights.md).

## Quality

`Rendering > Render Quality > …` picks a samples-per-pixel preset:

- Draft (4 spp): scrub-friendly previews.
- Preview (12 spp): tutorial-grade renders.
- Production (64 spp): marketing screenshots.
- Final (256 spp): hero shots, print, logo gifs.

See [Quality presets](quality-presets.md) for timing benchmarks.

## Color management

The Designer is color-managed end-to-end with OCIO. The default
working space is sRGB (8-bit unorm output), with three other
output transforms shipped:

- Linear sRGB (for VFX comp pipelines).
- ACEScg (for cinematic look-dev).
- Rec.709 (for HD broadcast).

See [Color space](color-space.md).

## See also

- [Texture transfer pipelines](texture-transfer-pipelines.md)  
  the heart of the Designer-to-skin authoring workflow.
- [Hypershade](hypershade.md): material node graph.
- [Blue Morpho tutorial](../getting-started/butterfly/index.md)  
  end-to-end render and export.
