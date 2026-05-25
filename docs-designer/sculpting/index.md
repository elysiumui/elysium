# Sculpting and Painting

The Sculpting menu set is the umbrella for surface-altering work:
brush-painted color, brush-painted masks, smudge, blur, fill, and
the eraser. The big-six toolbox entries here are **Brush**,
**Erase**, **Fill**, **Eyedrop**, **Pen**, and **Bezier**.

This section covers the operating model: when to paint, when to
sculpt, and how the painted result becomes part of the `.esk`.

## Two surfaces, one canvas

The Designer paints into one of two surfaces, chosen automatically
by what is selected:

| Selection | Paint target |
|---|---|
| Image placement | The image's RGBA pixels (destructive) |
| Mesh3D placement | The mesh's albedo texture (destructive) |
| Path / Rectangle / Ellipse / Region | The placement's **mask** (additive) |
| Nothing selected | The active layer or a default scratch layer |

Mask-painting is the gentle path: it does not modify the
placement's color, just its alpha. Albedo-painting is destructive
but produces real surface paint.

## Pages in this section

- [Painting workflow](painting-workflow.md): end-to-end paint
  pass from a fresh canvas to an exported texture.
- [Erase and Fill](erase-and-fill.md): the two tools that round
  out the brush family.

The actual brush mechanics (six engines, 30 presets, dynamics,
imports) live in the [Brush system](../brush/index.md) section.

## When to paint vs not

Paint when:

- You want hand-tuned highlights or shadows that no algorithm can
  produce.
- You are localizing a texture transfer's result (the bake gave
  you 90% of the way; brush touches up the last 10%).
- You are authoring custom masks for a render-part workflow.

Skip painting and reach for a transfer pipeline when:

- You can describe the result as "warp this image to fit this
  geometry". Use [Texture transfer pipelines](../rendering/texture-transfer-pipelines.md).
- You can express the result as a procedural texture
  (`elysium.render.texture` shaders) or a Photoshop-style filter
  (Magic Polish).

## Layer model

The Designer is layer-aware: each placement carries up to 8 paint
layers, each with its own opacity, blend mode, and visibility
toggle. The Properties pane's **Layers** section is the editor.
Painting always writes into the **active** layer (highlighted in
the layer list).

For most authoring you will use one layer per placement. Multi-
layer workflows are common when:

- Iterating on a destructive edit (work on a new layer; toggle off
  if it does not work out).
- Mixing brush styles for a single look (oil base + watercolor
  glaze + final detail in Round Stamp).

## See also

- [Brush > Quick start](../brush/quick-start.md): paint your
  first stroke in 3 minutes.
- [Texture transfer pipelines](../rendering/texture-transfer-pipelines.md)
 : algorithmic alternative.
- [Magic Polish](../ai/magic-polish.md): AI cleanup of painted
  results.
