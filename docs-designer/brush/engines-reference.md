# Engines reference

Every parameter on every engine, plus the stroke math and
performance characteristics. This is the deep reference for brush
authors; for picking a brush start with the [Library tour](library-tour.md).

## Round Stamp

The simplest and fastest engine. A circle (or oval) per stamp.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 1 - 500 | 20 | Diameter |
| opacity | float | 0 - 1 | 1.0 | Stamp alpha |
| hardness | float | 0 - 1 | 0.8 | Edge falloff (1 = pixel-hard, 0 = pure airbrush) |
| spacing | float | 0 - 1 | 0.25 | Fraction of size between stamps |
| angle_deg | float | -180 - 180 | 0 | Ovality rotation |
| roundness | float | 0 - 1 | 1.0 | 1 = circle, <1 = oval |

Stroke step: `size_px * spacing`. Performance: ~5,000 stamps/sec on
baseline GPUs.

## Airbrush

Gaussian falloff with a continuous-spray model.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 1 - 1000 | 40 | Outer 3σ radius |
| opacity | float | 0 - 1 | 0.6 | Per-stamp peak |
| flow | float | 0 - 1 | 0.25 | Paint flow per ms held |
| sigma | float | 0.1 - 1.0 | 0.35 | Falloff width (fraction of size) |
| spacing | float | 0 - 1 | 0.05 | Tighter than Round Stamp |

Continuously stamps while you hold; flow accumulates over time
even on a stationary cursor. Performance: ~5,000 stamps/sec.

## Bristle

Multi-tip stroke with per-bristle paint flow. The expensive engine.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 4 - 400 | 24 | Brush width |
| opacity | float | 0 - 1 | 1.0 | Per-bristle alpha |
| bristle_count | int | 1 - 64 | 24 | Bristles per stamp |
| bristle_gap | float | 0 - 1 | 0.2 | Spacing across the head |
| randomness | float | 0 - 1 | 0.3 | Per-bristle jitter |
| ink_load | float | 0 - 1 | 0.8 | How much paint a bristle carries |
| ink_decay | float | 0 - 1 | 0.05 | Decay over stroke distance |
| angle_deg | float | -180 - 180 | 0 | Flat-brush angle |
| flatness | float | 0 - 1 | 0.0 | 0 = round, 1 = flat |
| spacing | float | 0 - 1 | 0.15 | Tighter for smooth strokes |

Performance: ~1,500 stamps/sec. Bristles paint into the canvas with
a tiny offset and individual alpha. Ink decay simulates running out
of paint near the stroke's end.

## Texture

Repeating texture overlay stamped along the stroke.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 4 - 800 | 60 | Stamp size |
| opacity | float | 0 - 1 | 0.8 | Stamp alpha |
| texture_scale | float | 0.1 - 4.0 | 1.0 | Sample tile size |
| texture_rotation | float | -180 - 180 | 0 | Rotation per stamp |
| texture_jitter | float | 0 - 1 | 0.0 | Random rotation jitter |
| spacing | float | 0 - 1 | 0.20 | |
| tint_strength | float | 0 - 1 | 0.5 | Mix texture toward brush color |
| invert | bool | | false | Invert texture before composite |

Performance: ~2,500 stamps/sec. The texture is uploaded once per
preset and bound as a wgpu sampler.

## Pattern

Single non-tiled image stamped along the stroke.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 4 - 800 | 60 | Stamp size |
| opacity | float | 0 - 1 | 1.0 | Stamp alpha |
| spacing | float | 0 - 1 | 1.0 | Whole-stamp gaps |
| follow_path | bool | | true | Rotate stamps to follow the stroke tangent |
| jitter_pos | float | 0 - 1 | 0.0 | Per-stamp position scatter |
| jitter_rot | float | 0 - 1 | 0.0 | Per-stamp rotation jitter |
| jitter_scale | float | 0 - 1 | 0.0 | Per-stamp scale jitter |
| color_mode | enum | replace/tint/preserve | preserve | How brush color interacts with pattern |

Performance: ~2,500 stamps/sec. With `follow_path: true`, this is
the engine for confetti, foliage, and decals.

## Wet Mix

Real wet-on-wet color mixing. The slowest engine because each
stamp reads the destination pixels.

| Parameter | Type | Range | Default | Effect |
|---|---|---|---|---|
| size_px | float | 4 - 400 | 32 | Stamp size |
| opacity | float | 0 - 1 | 0.7 | Paint deposit |
| water | float | 0 - 1 | 0.4 | More water = wider mixing region |
| wet_paint | float | 0 - 1 | 0.5 | How much existing color to pull |
| smear | float | 0 - 1 | 0.3 | Drag-along strength |
| dry_rate | float | 0 - 1 | 0.0 | Per-stroke decay of wetness |
| edge_bleed | float | 0 - 1 | 0.2 | Watercolor-style darker edges |
| spacing | float | 0 - 1 | 0.10 | Very tight for smooth mixing |

Performance: ~800 stamps/sec. Reads + writes per stamp; the engine
keeps a wet-buffer separate from the canvas so re-strokes can blend
without lifting earlier dry layers.

## Comparison table

| Engine | Speed | Reads pixels | Texture used | Mixing model |
|---|---|---|---|---|
| Round Stamp | 5000 | no | no | replace / add |
| Airbrush | 5000 | no | no | add (continuous) |
| Bristle | 1500 | no | no | per-bristle composite |
| Texture | 2500 | no | yes | composite |
| Pattern | 2500 | no | yes (single image) | composite |
| Wet Mix | 800 | yes | no | wet-on-wet |

## ParamSpec (for custom engines)

Custom Python engines declare their parameters with `ParamSpec`:

```python
ParamSpec(
    name="size_px",
    min=1,
    max=500,
    default=20,
    kind="float",         # float | int | bool | color | vec2 | enum
    label="Size",
    hint="Diameter in pixels",
    accepts_dynamics=True,
    enum_values=None,     # for kind="enum"
)
```

See [Authoring custom brushes](authoring-custom-brushes.md) for a
walkthrough.

## Common gotchas

- **Spacing < ~0.05** on Round Stamp can saturate the GPU on a fast
  stroke. The engine clamps to a per-frame stamp budget; you may
  see strokes lag fast hand motion at very tight spacings.
- **Wet Mix water = 0** disables mixing entirely; the engine
  degrades to a Round Stamp with a Bristle-like spread. Use values
  ≥ 0.1 for the intended wet behavior.
- **Bristle randomness = 1.0** can produce visible per-bristle dots
  on slow strokes. Lower to 0.3 for smoother results.

## See also

- [Library tour](library-tour.md): see each engine in action with
  the built-in presets.
- [Brush Studio](brush-studio.md): author parameters and dynamics.
- [Authoring custom brushes](authoring-custom-brushes.md): write a
  new engine in Python.
