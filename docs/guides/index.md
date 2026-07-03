# Guides

Topic-shaped deep dives. Each guide covers one cross-cutting
concern: borderless windows, animation, theming, accessibility,
packaging: that a typical app exercises. Read after the
[Getting Started tutorials](../getting-started/index.md); reach
for the [API Reference](../api/index.md) for class-by-class
details.

## Reading order

A useful order if you have time:

1. [Architecture](architecture.md): App / Window / Canvas / Skin
   model and the render thread vs Python thread split.
2. [Borderless and shaped](borderless-and-shaped.md): the headline
   feature.
3. [Components overview](components-overview.md): the 30 shipping
   components.
4. [Layout](layout.md): Stack / Row / Col / Grid / Form.
5. [Reactive](reactive.md): signal / computed / effect.
6. [Animation](animation.md): Tween / Timeline / Spring / Clock.
7. [Theming](theming.md): five built-in themes + custom.
8. [Events](events.md): `@window.on` + dotted hooks.
9. [Skins](skins.md): `.esk` bundles, the designer-developer
   contract.
10. [Hot reload](hot-reload.md): live iteration.

The remaining guides (PBR, brush, AI, Aether, accessibility,
Code Link, packaging, auto-update, webview, CLI, marketplace) are
topic-specific. Read when you reach the feature.

## Guide clusters

**Windowing and shape**
[Borderless and shaped](borderless-and-shaped.md) ·
[Windowing](windowing.md)

**Visuals**
[Components overview](components-overview.md) ·
[Layout](layout.md) · [Theming](theming.md) ·
[Rendering](rendering.md) · [PBR](pbr.md) ·
[Textures](textures.md) · [Brush](brush.md)

**Behavior**
[Reactive](reactive.md) · [Animation](animation.md) ·
[Events](events.md) · [Focus](focus.md)

**Authoring tools**
[Skins](skins.md) · [Code Link](code-link.md) ·
[Hot reload](hot-reload.md)

**Intelligence**
[AI](ai.md) · [Aether](aether.md)

**Quality and shipping**
[Accessibility](accessibility.md) · [Packaging](packaging.md) ·
[Auto-update](auto-update.md) · [Marketplace](marketplace.md)

**Integration**
[Webview](webview.md) · [CLI](cli.md)

## How to read a guide

Each guide:

- Opens with one paragraph framing the topic.
- Documents the public API with copy-pasteable examples.
- Covers performance characteristics and gotchas.
- Closes with see-also links to related guides and recipes.

For "I need to solve a specific small problem right now", the
[Recipes](../recipes/index.md) cookbook is the better entry point.
