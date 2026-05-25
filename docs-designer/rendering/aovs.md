# AOVs

AOV = Arbitrary Output Variable. An AOV is a render pass that
isolates one component of the final image: just diffuse, just
specular, just normals, just depth, etc.

## Why AOVs

Compositors (Nuke, After Effects, Fusion) re-combine AOVs to:

- Boost or dim a single component (more specular, less diffuse).
- Add light effects only on a specific surface type.
- Use depth for depth-of-field in comp.
- Re-light a scene without re-rendering.

For standalone skin export, AOVs are usually not needed. For VFX
pipelines, they are essential.

## The five ship AOVs

`Rendering > AOV > …`:

| AOV | Content |
|---|---|
| Beauty | Final composited image (default; always rendered) |
| Diffuse | Diffuse-only contribution |
| Specular | Specular-only contribution |
| Normal | Per-pixel world-space normal vectors (encoded RGB) |
| Depth | Per-pixel depth-from-camera (Linear, in scene units) |

Beauty is always enabled. The other four are opt-in: tick the
checkboxes in the AOV submenu.

## Enable AOVs

Each AOV's submenu entry toggles it on or off. When at least one
non-Beauty AOV is on, the path tracer accumulates additional
buffers per ray. Cost scales sublinearly: enabling Normal + Depth
adds ~5% to total render time; enabling Diffuse + Specular adds
~15%.

## File layout

When AOVs are enabled, `File > Export > Render` produces one EXR
multi-channel file plus the Beauty PNG:

```
out/butterfly_render.png            (Beauty, sRGB PNG)
out/butterfly_render.exr            (multi-channel EXR with all AOVs)
```

For tools that prefer separate per-AOV files, set
`Preferences > Rendering > AOV Layout` to **Per-AOV Files**:

```
out/butterfly_render.beauty.png
out/butterfly_render.diffuse.exr
out/butterfly_render.specular.exr
out/butterfly_render.normal.exr
out/butterfly_render.depth.exr
```

## Custom AOVs (Hypershade route)

For non-standard AOVs (e.g. material ID, custom mask), add an
**AOV Output** node in [Hypershade](hypershade.md):

1. Drag the **AOV Output** node into the material graph.
2. Connect any signal (a Texture, a Math result, a Mask) to its
   `value` input.
3. Set the AOV's name (e.g. "material_id").

The custom AOV appears in the AOV menu and is included in
exports.

## Depth pass conventions

The Depth AOV stores Linear depth in scene units (pixels by
default). For compositors that expect normalized 0-1 depth:

`Preferences > Rendering > Depth AOV Range`: set Min / Max to
clip the depth range and normalize.

## Limitations

- Cryptomatte support is roadmap, not v1.
- Per-light AOVs (split contributions by light) are roadmap.

## See also

- [Render layers](render-layers.md): combine layers + AOVs for
  full comp control.
- [Color space](color-space.md): what space AOVs are written in
  (Linear by default).
