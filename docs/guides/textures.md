# Textures

`elysium.render.texture` is the framework's texture pipeline:
extract tileable textures from images, layer them, paint masks,
upscale via AI. Used by the brush system, PBR materials, and the
Designer's transfer pipelines.

## Extract a tileable texture

```python
from elysium.render import texture as tex
out, info = tex.extract_from_file("butterfly.png", name="wing")
# out is a Path under ~/.elysium/textures/
```

Or via Designer: `File > Extract Texture from Image…`. The
extractor finds a seamless tile and writes it to the user texture
library at `~/.elysium/textures/`.

## Apply to a placement

```python
placement.texture_path = str(out)
placement.texture_scale = 1.0
placement.texture_offset = (0, 0)
placement.texture_rotation_deg = 0
placement.texture_tint = "#ffffff"
placement.texture_blend = "normal"
placement.texture_opacity = 1.0
```

Or via Designer: `File > Apply Texture from Library…`.

## Multi-layer stacks

```python
from elysium.render.texture import TextureLayer, composite_layers

layers = [
    TextureLayer(path="wood.png", scale=1.0),
    TextureLayer(path="grain.png", opacity=0.4, blend="multiply"),
    TextureLayer(path="dust.png",  opacity=0.2, blend="screen"),
]
rgba = composite_layers(layers, w=512, h=512)
```

Blend modes: `normal`, `multiply`, `screen`, `overlay`,
`soft_light`, `add`, `subtract`.

## Brush painting

Painting writes into a per-placement `PaintMask`. From code:

```python
from elysium.render.texture import PaintMask
m = PaintMask(256, 256)
m.stroke(
    x0=10, y0=10, x1=250, y1=250,
    radius=12,
    color=(220, 60, 60, 255),
    opacity=0.8, hardness=0.55,
)
```

The mask round-trips through the `.esk` save: with
`texture_export_mode = "embedded"` the mask lands at
`assets/masks/<placement_id>.png` and the skin compiler re-applies
it as an image overlay at load time.

For the full Designer-side brush workflow see the
[Brush system](https://designer.elysiumui.com/brush/) section.

## AI Enhance

```python
from elysium.render.texture import enhance
out = enhance("low_res.png", scale=4)
```

`File > AI Enhance Selection (×4)` in the Designer. Runs
Real-ESRGAN if installed, otherwise falls back to Lanczos +
UnsharpMask. Useful for upscaling source photos before a transfer
pipeline.

## Texture transfer pipelines

The two starred Designer pipelines (Polar + Bake + Normal Map; and
BBox + Landmark Gaps + Bake + Normal Map) are documented in detail
in the [Designer's transfer pipelines reference](https://designer.elysiumui.com/rendering/texture-transfer-pipelines/).
The framework consumes the bakes; the Designer authors them.

## Procedural textures

The shipping procedural set:

```python
from elysium.render.texture import procedural

noise = procedural.perlin_noise(size=512, scale=1.0, octaves=4)
voronoi = procedural.voronoi(size=512, cells=50, jitter=1.0)
checker = procedural.checker(size=256, tile=16)
gradient = procedural.linear_gradient(
    size=(512, 64),
    colors=[(0,0,0,255), (255,255,255,255)],
)
```

Each returns a numpy-like buffer ready for use as a texture map.

## Compute shaders

For custom procedural generation that needs to be fast (per-frame
or large textures), drop to wgpu compute:

```python
from elysium.render import compute
rgba = compute.dispatch(shader_wgsl, w=1024, h=1024, entry="main")
```

The wgpu compute pipeline returns the rendered RGBA buffer. Cost
scales with shader complexity; trivial shaders run in <1 ms at
1024².

## Mipmaps

The framework auto-generates mipmaps for every texture used as a
PBR map. Disable per-texture via the `mipmap=False` flag if you
need point-sampled crisp pixels.

## See also

- [PBR](pbr.md): materials that consume textures.
- [Brush](brush.md): brush engines + presets.
- [Rendering](rendering.md): composition pipeline.
- [Designer > Texture transfer pipelines](https://designer.elysiumui.com/rendering/texture-transfer-pipelines/)
