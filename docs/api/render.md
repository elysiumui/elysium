# `elysium.render`

PBR rendering, texture pipeline, GPU compute, and preview helpers.

## Submodules

| Submodule | Purpose |
|---|---|
| `elysium.render.pbr` | PBR materials, mesh import, path tracer |
| `elysium.render.texture` | Tileable extraction, PaintMask, layer composition |
| `elysium.render.compute` | wgpu compute shader dispatch |
| `elysium.render.preview` | Live preview helpers (render_sphere) |

## pbr

| Symbol | Purpose |
|---|---|
| `Material` | PBR material |
| `MeshObject` | Mesh + materials bundle |
| `import_mesh_from_file(path)` | Load `.3ds` / `.obj` / `.gltf` / `.glb` |
| `to_environment(studio)` | Convert a studio dict to an environment |
| `load_hdri(path, intensity)` | Load `.hdr` / `.exr` |
| `render_mesh(w, h, obj, env, ...)` | CPU BVH render |
| `render_path_traced(w, h, obj, env, samples, ...)` | Monte Carlo path tracer |
| `STUDIOS` | Dict of 8 light-studio presets |
| `PRESETS` | Dict of ~20 material presets |

## texture

| Symbol | Purpose |
|---|---|
| `extract_from_file(path, name)` | Make a tileable from an image |
| `PaintMask(w, h)` | Per-placement paint surface |
| `TextureLayer(path, ...)` | One layer in a composite |
| `composite_layers(layers, w, h)` | Composite layers to RGBA |
| `enhance(path, scale)` | AI / Lanczos upscaler |
| `procedural.perlin_noise`, `.voronoi`, `.checker`, `.linear_gradient` | Procedural tile generators |

## compute

| Symbol | Purpose |
|---|---|
| `dispatch(shader_wgsl, w, h, entry='main')` | Dispatch a compute shader; return RGBA |
| `render_mesh_gpu(w, h, obj, env)` | GPU PBR preview path |

## preview

| Symbol | Purpose |
|---|---|
| `render_sphere(material, env, size)` | Lit sphere thumbnail |
| `designer_preview(...)` | Preview helpers for the Hypershade panel |

## Auto-rendered details

::: elysium.render

## See also

- [PBR](../guides/pbr.md)
- [Textures](../guides/textures.md)
- [Rendering](../guides/rendering.md)
