# Quality presets

`Rendering > Render Quality` picks the samples-per-pixel (spp)
preset used by the production path tracer. Higher spp = less
noise = longer renders. The four presets cover the practical range.

## The four presets

| Preset | spp | Best for | Time per 1024×1024 (M2, RTX 4070) |
|---|---|---|---|
| Draft | 4 | Live preview while tweaking | ~0.4 s / 0.3 s |
| Preview | 12 | Tutorial-grade stills | ~1.2 s / 0.9 s |
| Production | 64 | Marketing screenshots | ~6.0 s / 4.5 s |
| Final | 256 | Hero shots, print, the logo gif | ~24 s / 18 s |

Times scale linearly with resolution (4x area → 4x time).

## Custom spp

For a one-off render at a non-preset value:

`Rendering > Render Quality > Custom…` opens a small dialog with a
spp slider (1 - 1024). Useful when you want 128 spp because 64
shows residual noise but 256 is overkill.

## Adaptive sampling

By default the tracer uses **adaptive sampling**: each pixel
samples until its variance falls below a threshold, then stops.
Plain regions converge fast, hot spots (specular highlights,
caustics) get more samples.

Configure in `Preferences > Rendering > Adaptive Sampling`:

- **Variance threshold**: default 0.005. Lower = stricter = more
  samples on hot spots.
- **Min spp**: default 4. Every pixel runs at least this many.
- **Max spp**: cap; 256 by default for Preview, 1024 for Final.

For deterministic spp (every pixel exactly N samples), disable
adaptive sampling.

## Render Selected vs Render All

| Action | Effect |
|---|---|
| `Rendering > Render Selected` | Path-trace just the selected placement, render into the canvas |
| `Rendering > Render All` | Path-trace the whole scene |
| `Rendering > Render Region` | Drag-box a region to render |

Render Selected is the fastest way to audition lighting on a
single hero subject without re-rendering the rest of the scene.

## Batch render

`Rendering > Batch Render…` opens a dialog to render a frame range
to disk:

- **Frame range**: start / end / step.
- **Output**: directory + filename pattern.
- **Format**: PNG / EXR / JPG.
- **Notify on complete**: ping you via system notification.

Batch renders in the background. Continue editing while it runs;
the View Panel might lag slightly during heavy frames.

## GPU vs CPU

The tracer prefers GPU (wgpu compute shaders). On a GPU-less
machine (or with `Preferences > Rendering > Force CPU`) it falls
back to a multithreaded CPU path; expect ~4-8x slower runtimes.

## Recommendations

- Authoring: Draft.
- Reviewing: Preview.
- Sharing on the team: Preview or Production.
- Shipping: Final.

If you cannot tell the difference between Production and Final on
your screen, use Production. Final exists mainly for print and for
slow-motion logo gifs where lingering noise is conspicuous.

## See also

- [Lights](lights.md): what the path tracer is sampling.
- [AOVs](aovs.md): multiple output passes from a single render.
- [Color space](color-space.md): the format pipeline.
