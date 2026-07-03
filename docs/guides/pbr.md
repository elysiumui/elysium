# PBR materials and path tracing

Elysium ships a complete physically-based renderer for 3D content
embedded in your UI: Cook-Torrance BRDF, GGX microfacet specular,
image-based lighting, BVH-accelerated ray-triangle intersection,
and a Monte-Carlo path tracer for "Render Final" stills.

## Quick render

```python
from elysium.render import pbr

mesh = pbr.import_mesh_from_file("path/to/model.3ds")
obj  = pbr.MeshObject(mesh=mesh, materials=[pbr.PRESETS["Metal: Gold"]])
env  = pbr.to_environment(pbr.STUDIOS["Default Soft Studio"])
rgba = pbr.render_mesh(
    384, 384, obj, env,
    cam_yaw=0.4, cam_pitch=0.25,
)
```

Returns `bytes` (RGBA8). Load any `.3ds`, `.obj`, `.gltf`, `.glb`
via `import_mesh_from_file`; BVH-accelerated intersection keeps
few-thousand-face models in the sub-second range at 384².

## Lighting studios

Eight presets in `pbr.STUDIOS`:

| Preset | Vibe |
|---|---|
| Default Soft Studio | Neutral fill light |
| Three-Point Hero | Cinematic three-point |
| Sunset Window | Warm directional + bounce |
| Overcast | Soft full-dome |
| Studio Grayscale | High-contrast B&W study |
| Studio Frosted Glass | Diffused softbox |
| Studio Warm Wax | Tungsten + amber |
| Outdoor Field | Sunlit grass + sky |

## HDRI

```python
env = pbr.load_hdri("path/to/env.hdr", intensity=1.0)
```

Supports Radiance RGBE `.hdr` and OpenEXR `.exr`.

## Materials

```python
mat = pbr.Material(
    base_color=(0.85, 0.10, 0.10),
    metallic=0.0,
    roughness=0.30,
    clear_coat=1.0,
    clear_coat_roughness=0.04,
)
```

Texture maps:

```python
mat.albedo_map         = "wing.png"
mat.metallic_rough_map = "wing_mr.png"
mat.normal_map         = "wing_n.png"
```

Maps sample in OKLCH-aware sRGB → linear pipeline. Normal maps are
expected as tangent-space RGB (X = R, Y = G, Z = B).

## Material presets

`pbr.PRESETS` ships ~20 ready-to-use materials:

- Metal: Gold, Silver, Copper, Aluminum, Iron, Brushed Steel.
- Plastic: Glossy, Matte, Translucent Glass.
- Skin / Cloth: Wax, Velvet, Silk.
- Stylized: Iridescent Wing, Holographic Foil, Toon Shaded.

Use as starting points; modify properties to taste.

## Path-traced Render Final

```python
rgba = pbr.render_path_traced(
    1024, 1024, obj, env,
    samples=12, max_bounces=3,
    denoise=True,
)
```

Monte Carlo bounces, sun NEE (next event estimation), Russian
roulette termination, edge-avoiding À-Trous denoiser. Use for
hero stills, marketing screenshots, and the `.esk` preview render.

`samples` maps to the Designer's quality presets: Draft=4,
Preview=12, Production=64, Final=256. Time scales linearly with
samples.

## GPU compute path

```python
from elysium.render.compute import render_mesh_gpu
rgba = render_mesh_gpu(512, 512, obj, env)
```

Runs the same PBR pipeline in a headless wgpu compute pipeline  
direct light + IBL on the GPU. Faster than the CPU path tracer for
real-time previews; not yet feature-equivalent (no full bounces).

## Designer preview

For the Designer's live-preview spheres in the Hypershade panel:

```python
from elysium.render import preview
rgba = preview.render_sphere(material=mat, env=env, size=128)
```

A 128×128 sphere reference suitable for thumbnail use.

## Animating PBR materials

Material properties are signal-able:

```python
roughness = reactive.signal(0.3)
mat.roughness = roughness

# later
roughness.set(0.05)   # the next render reads the new value
```

For per-frame animation, the framework's `Tween` handles
material properties the same as any other channel.

## Performance

| Resolution | Render Mesh (CPU BVH) | Path-traced 12 spp | Path-traced 256 spp |
|---|---|---|---|
| 384x384 | ~0.4 s | ~1.2 s | ~24 s |
| 1024x1024 | ~3 s | ~9 s | ~3 min |

Numbers from an M2 with a moderate (10k-face) mesh and the Default
Soft Studio environment.

## See also

- [Rendering](rendering.md): the underlying Skia + wgpu hybrid.
- [Textures](textures.md): texture pipeline that feeds PBR maps.
- [Recipes: render a PBR sphere as a thumbnail](../recipes/18-pbr-thumbnail.md)
