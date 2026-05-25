# How do I render a PBR sphere as a thumbnail?

`elysium.render.preview.render_sphere(...)` returns RGBA bytes for
a small lit sphere.

```python
from elysium.render import preview, pbr

material = pbr.PRESETS["Metal: Gold"]
env = pbr.to_environment(pbr.STUDIOS["Default Soft Studio"])
rgba = preview.render_sphere(material=material, env=env, size=128)

# Use the bytes:
img = ely.Image.from_bytes(rgba, width=128, height=128, format="rgba8")
window.thumb.image = img
```

Useful for material pickers, brush thumbnails, and material
library preview tiles. The size argument controls resolution
(typically 64-256).

For finer control or animated previews, use the full PBR pipeline
in [PBR](../guides/pbr.md).
