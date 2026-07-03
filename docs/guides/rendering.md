# Rendering

Elysium's renderer is a hybrid: **Skia** for vector and text
rasterization, **wgpu** for GPU composition. Most apps never
think about this; for high-performance custom drawing you drop
down to `Canvas` and `DisplayList`.

## The render path

```
Skin placements / display lists
  ↓
Skia rasterizes vector + text into intermediate textures
  ↓
wgpu compositor blends layers, lighting, and effects
  ↓
swap chain → present
```

Skia is good at the things vector renderers are good at (paths,
text, gradients). wgpu is good at the things GPUs are good at
(blending many layers, applying compute effects, parallel
sampling). The hybrid plays each tool to its strength.

## Canvas

A `Canvas` is a GPU surface inside a placement. The runtime
treats it as a single quad textured with whatever DisplayList you
publish to it.

```python
canvas = window.eq_canvas         # a placement with kind="canvas"
canvas.publish_display_list(dl)
```

The DisplayList is consumed on the next frame. Old lists are
released; canvases hold only their most recent list.

## DisplayList

```python
import elysium as ely

dl = ely.DisplayList()
dl.fill_color((1.0, 0.5, 0.3, 1.0))
path = ely.Path()
path.move_to(10, 10)
path.line_to(100, 10)
path.line_to(100, 100)
path.close()
dl.fill_path(path)
dl.draw_text("Hello", x=20, y=80, size=18)
```

A DisplayList is an immutable list of draw commands. Once
published it cannot be edited; publish a new one to update.

### Operations

| Op | Effect |
|---|---|
| `fill_color(rgba)` | Set the current fill |
| `stroke_color(rgba)` | Set the current stroke |
| `fill_path(path, gradient=…)` | Fill a path |
| `stroke_path(path, width=…)` | Stroke a path |
| `draw_text(text, x, y, size=…, font=…)` | Render text |
| `draw_image(image, x, y, w=…, h=…)` | Stamp an image |
| `push_transform(x, y, scale=…, rotation=…, anim_slot=…)` | Push a transform |
| `pop_transform()` | Pop the transform |
| `clip(path)` | Clip subsequent ops to a path |
| `shadow(path, color, blur, x=0, y=0)` | Drop shadow |

## Path

```python
path = ely.Path()
path.move_to(0, 0)
path.line_to(100, 0)
path.curve_to(150, 50, 150, 150, 100, 200)
path.rect(10, 10, 80, 80, radius=8)
path.circle(50, 50, r=25)
path.close()
```

Paths are mutable until consumed by a DisplayList op. They mirror
SVG path semantics.

## When to use Canvas vs placements

| Use Canvas (DisplayList) | Use placements |
|---|---|
| Many small shapes that change every frame (equalizer bars, particles) | Mostly-static UI |
| Custom shaders / effects | Built-in components |
| Real-time generative drawing | Designer-authored layouts |

Placements pay a small per-frame cost per placement. DisplayLists
batch into one draw call. For 100+ small shapes that update every
frame, DisplayList is 10x faster.

## SkiaLayer

`SkiaLayer` is a placement kind that owns its own internal
DisplayList. Use when you want a layered canvas-like region
inside a Skin without an explicit Python-side publish.

## Compositing

The wgpu compositor blends each layer with the others. Per-layer
properties:

- **opacity**: 0..1.
- **blend_mode**: `normal`, `add`, `multiply`, `screen`, `overlay`.
- **filter**: `blur`, `saturate`, `brightness`.
- **mask**: a sibling placement used as alpha mask.

These let you build photoshop-style layer stacks without dropping
to a shader.

## Custom shaders

For one-off effects (a particle simulation, an SDF text effect),
wgpu compute shaders integrate via:

```python
canvas.compute(shader_wgsl, x=0, y=0, w=512, h=512, entry="main")
```

See [Brush > Authoring custom brushes](https://designer.elysiumui.com/brush/authoring-custom-brushes/)
for a full example.

## Frame budget

Per-frame budget at 60 fps: 16.67 ms.

- Render thread paint typically ~2-4 ms on a baseline GPU.
- Python event handlers + effects target <1 ms.
- The animation thread sits at ~1 ms when many tweens are
  active.

For tight budgets, the debug overlay (`View > Toggle HUD` in
Designer; `window.show_hud()` in code) surfaces per-thread time
histograms.

## See also

- [PBR](pbr.md): physically-based rendering for 3D scenes.
- [Textures](textures.md): texture pipeline.
- [Recipes: draw on a Canvas with a Path](../recipes/16-canvas-with-path.md)
