# `elysium.render`

PBR rendering, texture pipeline, GPU compute, and preview helpers.

## Submodules

Rendering and previews:

| Submodule | Purpose |
|---|---|
| `elysium.render.pbr` | PBR materials, mesh import, path tracer |
| `elysium.render.texture` | Tileable extraction, PaintMask, layer composition |
| `elysium.render.compute` | wgpu compute shader dispatch |
| `elysium.render.preview` | Live preview helpers (render_sphere) |
| `elysium.render.designer_preview` | Faithful preview render of a live Designer state |
| `elysium.render.layout_lighting` | Shared world-space light/transform context for Layout previews |

Mesh documents and topology:

| Submodule | Purpose |
|---|---|
| `elysium.render.mesh_document` | Versioned, lossless mesh assets for authored documents |
| `elysium.render.topology` | Editable polygon/corner topology compiled to the triangle renderer |
| `elysium.render.primitives` | Parameterized native primitives (Cube, Sphere, ...) |
| `elysium.render.mesh_edit` | Native mesh deformations shared by GUI fields and public tools |
| `elysium.render.component_transform` | Selected-component transforms in explicit coordinate frames |
| `elysium.render.mesh_modifiers` | Retained, non-destructive mesh modifier stack |
| `elysium.render.mesh_subdivision` | Catmull-Clark and Simple subdivision |
| `elysium.render.mesh_edge_split` | Retained Edge Split evaluation |

Normals and tangents:

| Submodule | Purpose |
|---|---|
| `elysium.render.mesh_normals` | Mesh/face normal policies and sharp-edge authoring |
| `elysium.render.mesh_tangents` | Derived MikkTSpace corner tangent frames |

UVs:

| Submodule | Purpose |
|---|---|
| `elysium.render.mesh_uv` | Corner-domain UV authoring |
| `elysium.render.mesh_uv_unwrap` | Seam-cut least-squares conformal unwrap with corner pins |
| `elysium.render.mesh_uv_islands` | UV islands, deterministic packing, texture-density normalization |
| `elysium.render.mesh_uv_stitch` | Joining neighboring island edges |
| `elysium.render.mesh_uv_diagnostics` | Read-only UV distortion and validity checks |

Materials:

| Submodule | Purpose |
|---|---|
| `elysium.render.mesh_materials` | Object-local material slots and source-face assignment |
| `elysium.render.material_graph` | Validated constant color DAGs for material surfaces |
| `elysium.render.material_image` | Owned, immutable PNG images for material slots |

Scenes, lighting and animation:

| Submodule | Purpose |
|---|---|
| `elysium.render.scene` | Meter-space transforms and the shared depth-tested scene preview |
| `elysium.render.scene_lighting` | Persistent scene lights and direct-light integration |
| `elysium.render.scene_render_job` | Atomic, cancellable scene-preview jobs |
| `elysium.render.scene_animation` | Persistent object transform keys |
| `elysium.render.animation_curve` | Cubic transform curves with free handles |
| `elysium.render.scene_actions` | Named scene animation actions |
| `elysium.render.scene_export` | Animated scene bundle exporter (.esk + editable geometry) |

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
    options:
      show_submodules: true

## See also

- [PBR](../guides/pbr.md)
- [Textures](../guides/textures.md)
- [Rendering](../guides/rendering.md)
