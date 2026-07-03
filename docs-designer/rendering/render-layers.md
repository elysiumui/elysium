# Render layers

A render layer is a named collection of placements rendered as
one pass. Useful for separating foreground / background, isolating
a subject for comp, or producing multiple variants of the same
scene.

## When to use them

- A hero subject layer + a background layer that you composite
  with different blend modes downstream.
- A shadow-only pass for compositing on a different background.
- Variant renders ("this scene with the props in" / "without").

For one-layer scenes (the default), render layers are invisible.

## Create a render layer

`Rendering > Render Layers > New Layer…`. Name it (e.g.
"background"). The layer appears in the Project Explorer's **Sets**
tab.

## Assign placements to a layer

Right-click a placement > **Add to Render Layer > background**.
Or drag-drop in the Sets tab. A placement can belong to multiple
layers.

## Per-layer overrides

Each layer can override placement properties at render time:

- **Visibility**: a placement assigned to a layer with
  `visible: false` is excluded from that layer's render.
- **Material override**: swap the placement's material for this
  layer (e.g. "render this layer with all matte black materials").
- **Light selection**: render this layer with only a subset of
  scene lights.

Overrides live in the layer's Properties pane.

## Render a layer

`Rendering > Render Layers > Render Active Layer` renders just the
active layer (set by the dropdown in the Render Layers panel).
The View Panel shows only that layer's geometry during render.

`Rendering > Render Layers > Render All Layers` renders each layer
in turn, producing one image per layer.

## Compositing

When rendering all layers, the Designer also writes per-layer
output to separate files:

```
out/butterfly_render.beauty.png
out/butterfly_render.layers/background.png
out/butterfly_render.layers/butterfly.png
out/butterfly_render.layers/shadows.png
```

The beauty image is the composited result. Per-layer files are
straight outputs ready for Nuke / After Effects / Photoshop.

## Per-layer AOVs

Combine render layers with [AOVs](aovs.md): each layer can request
its own AOV set. Useful when you want depth pass only from the
background but normal pass from the subject.

## Common patterns

### Hero subject + soft background

- Layer "hero": the butterfly Mesh3D. Full PBR.
- Layer "background": a blurred photo Image placement. No
  shadows.
- Render All Layers → combine in comp with a slight blur on
  background.

### Variant testing

Three layers all containing the same placements, with different
**material overrides** (matte black, neutral gray, full PBR).
Render once; pick the right look for the final piece.

## See also

- [AOVs](aovs.md): multiple passes from a single render.
- [Sets tab](../interface/project-explorer.md#sets-tab): manage
  the layer membership.
