# Render quality table

Quick reference for the four render quality presets, the spp they
use, and expected render times.

## Presets

| Preset | spp | Adaptive cap | Best for |
|---|---|---|---|
| Draft | 4 | 8 | Live tweaking |
| Preview | 12 | 32 | Tutorial / share-grade |
| Production | 64 | 256 | Marketing screenshots |
| Final | 256 | 1024 | Print / hero / logos |

## Time per resolution

Times on an M2 MacBook Air (CPU path tracer):

| Preset | 384×384 | 768×768 | 1024×1024 | 2048×2048 |
|---|---|---|---|---|
| Draft | 0.15 s | 0.5 s | 0.85 s | 3.3 s |
| Preview | 0.45 s | 1.6 s | 2.7 s | 10.5 s |
| Production | 2.0 s | 7.5 s | 12.5 s | 49 s |
| Final | 8.0 s | 30 s | 50 s | 200 s |

On an RTX 4070 (GPU compute path):

| Preset | 384 | 768 | 1024 | 2048 |
|---|---|---|---|---|
| Draft | 0.06 s | 0.20 s | 0.35 s | 1.4 s |
| Preview | 0.18 s | 0.65 s | 1.1 s | 4.2 s |
| Production | 1.0 s | 3.8 s | 6.5 s | 25 s |
| Final | 4.0 s | 15 s | 25 s | 100 s |

Time scales linearly with pixel area. Doubling resolution
quadruples render time.

## Memory

Each render uses ~`width * height * 4` bytes for the beauty buffer
plus ~`width * height * 4` per enabled AOV.

Example: 2048x2048 with Beauty + Diffuse + Specular + Normal +
Depth = ~80 MB peak.

## Adaptive sampling

Adaptive sampling lets the tracer stop sampling once a pixel's
variance falls below a threshold:

| Parameter | Default | Effect |
|---|---|---|
| Variance threshold | 0.005 | Lower = stricter |
| Min spp | 4 | Floor per pixel |
| Max spp | 256-1024 | Per preset (see above) |

Disable for deterministic spp: `Preferences > Rendering > Adaptive
Sampling = off`.

## Custom spp

`Rendering > Render Quality > Custom…` opens a slider. Use when
you specifically want, e.g., 96 spp because 64 still shows residual
noise on a particular subject.

## See also

- [Quality presets](../rendering/quality-presets.md)
- [AOVs](../rendering/aovs.md)
