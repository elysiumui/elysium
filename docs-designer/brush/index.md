# Brush system

The brush system is the Designer's painting surface. Six engines
produce strokes; thirty built-in presets cover the most common
looks; a Library manages your own presets and imported brushes; and
the Brush Studio lets you author from scratch. The whole stack is
also exposed to Python so you can extend it in code.

![Brush system overview: engines, presets, Studio, Library, painting surface](../assets/brush-overview.png)

## The six engines

| Engine | Best for | Built on |
|---|---|---|
| Round Stamp | Pencil, marker, hard-edge | Tight rounded nib, no texture |
| Airbrush | Soft falloff, gradients, glow | Gaussian falloff |
| Bristle | Oil, ink, gestural | Multi-tip with per-bristle paint flow |
| Texture | Concept art, photo-based | Repeating texture overlay |
| Pattern | Decals, stamps, stickers | Single non-tiled image stamped along the stroke |
| Wet Mix | Watercolor, smudge, blend | Real wet-on-wet color mixing |

The full engine internals (parameters, math, performance notes)
live in [Engines reference](engines-reference.md).

## Three ways to get a brush

1. **Library**: pick a preset from the [Library tour](library-tour.md).
2. **Studio**: author your own in the [Brush Studio](brush-studio.md).
3. **Import**: bring in `.abr` (Photoshop), `.sut` (Clip Studio), or
   `.elybrush` (native) files via the
   [importing pages](importing-photoshop-abr.md).

## Where each surface lives

| Surface | Where | What it does |
|---|---|---|
| Quick Wheel | Hold `B` for 0.4 s | 6-engine radial picker; quickly switch engine without leaving the canvas |
| Brush palette panel | Bottom of the toolbox column | 12 color + 12 texture slots; left-click to apply, right-click to manage. See [quick-start](quick-start.md#the-brush-palette-panel). |
| Tool Properties dock | Below the View Panel | Engine + preset + size + opacity + dynamics for the active brush |
| Brush Library panel | `Window > Brush Library` | Searchable, taggable preset list with thumbnails |
| Brush Studio | `Window > Brush Studio` | Full editor: engine params, dynamics curves, texture pick, preview |
| Aether chat | `Cmd+/` | Talk to the agent to make brushes; "give me a soft watercolor wash" |

## Stroke pipeline (top to bottom)

```
Input device (mouse / pen / touch)
  ↓
elysium.brush.engine.apply_dynamics(params, dynamics, sample)
  ↓
BrushEngine.stamp(canvas, x, y, params, color)
  ↓
Canvas DisplayList (Skia paths + textures)
  ↓
wgpu compositor → final pixels
```

Dynamics is where pressure, tilt, rotation, velocity, and altitude
get folded into the stamp parameters. The output is a list of stamps
that the engine renders.

## Performance defaults

- Round Stamp + Airbrush: ~5,000 stamps/sec on baseline GPU.
- Bristle: ~1,500 stamps/sec (more expensive per stamp).
- Wet Mix: ~800 stamps/sec (involves a wet-buffer read each stamp).
- Pattern / Texture: ~2,500 stamps/sec.

These are floors. A modern discrete GPU easily 4-10x's these.

## Where to next

- [Quick start](quick-start.md): paint your first stroke in 3
  minutes.
- [Library tour](library-tour.md): the 30 built-in presets.
- [Brush Studio](brush-studio.md): author from scratch.
- [Authoring custom brushes](authoring-custom-brushes.md): when
  the Studio is not enough and you drop down to Python.
- [Engines reference](engines-reference.md): every parameter on
  every engine.
