# Texture transfer pipelines

The texture transfer pipelines are the algorithmic heart of the
Designer's "take a reference photo and a 3D model, produce a baked
texture that fits" workflow. The Blue Morpho tutorial drives the
two starred recommended pipelines; this page documents every
method.

## The eight standalone methods

Each is reachable from `Mesh > Transfer Texture > <method>`:

| Method | Strength | Weakness |
|---|---|---|
| POLAR | Smooth, fast, body-centered | Loses fine alignment at the periphery |
| REGIONS | Honors authored region masks | Requires hand-painted regions |
| FLOW | Optical-flow-driven; captures direction | Needs two related source images |
| TPS | Thin-plate spline through landmarks | Quality is landmark-quality dependent |
| BBOX_WARP | Maps bounding box → bounding box | Coarse; needs follow-up |
| SWEEP | Sweeps along a curve | Curve must be authored |
| LANDMARK | Direct landmark warp without bake | Diagnostic / debug |
| (Apply) LANDMARK_APPLY_FULL | TPS + per-region weighting in one shot | Slower |

## The two starred recommended pipelines

The pipelines are the "do everything" combinations the Designer
recommends. Both produce a baked albedo + a derived normal map as
their last step.

### Polar + Bake + Normal Map (PBR)

Used in chapter 5 of the Blue Morpho tutorial.

1. **Polar warp**: maps the source onto the model's UV space
   using polar coordinates centered on the model's body.
2. **Bake**: writes the warped result to
   `textures/<placement>_albedo.png` inside the `.esk`.
3. **Normal map**: derives a high-frequency normal map from the
   source's luminance.

Strengths:

- Closed-form math → fast (~3-5 seconds on baseline hardware).
- Body acts as a stable center; non-flat surfaces handle well.
- Smooth gradients; right for iridescence, gradients, and
  pattern continuity.

Weaknesses:

- Wing-tip detail is approximate; fine alignment at peripheries
  drifts.
- Not ideal for hard-edge text or sharp small features.

### BBox-Warp then Landmark Gaps + Bake + Normal Map

Used in chapter 6.

1. **BBox-Warp**: maps source bounding box onto model UV bounding
   box.
2. **Landmark Gaps**: identifies where BBox loses accuracy
   (typically wing tips, body-wing junction) and re-runs a
   thin-plate spline locally over those regions using the
   landmark pairs.
3. **Bake**: writes the combined result.
4. **Normal map**: derives normals from the result.

Strengths:

- Precise pattern alignment on small features (eye spots, veins,
  text).
- Honors hand-placed landmarks; matches author intent more
  closely.

Weaknesses:

- Slower (~8-10 seconds).
- Quality depends on landmark count and accuracy; 6 well-placed
  pairs is the sweet spot.

## How to choose

Use **Polar** when:

- The source photo and the model are close in proportions.
- You want smooth, iridescent / gradient looks.
- You want fast iteration.

Use **BBox + Landmark Gaps** when:

- Source and model differ in proportions.
- Sharp pattern alignment matters (text, symbols, sharp features).
- You will hand-touch up afterward (the bake is the starting
  point, not the finish).

Chapter 6 of the tutorial demonstrates running both and A/B-ing.

## Standalone methods (manual pipelines)

The eight standalone methods are reachable without the
bake-and-normal-map post-steps. Useful when:

- You want to compose a custom pipeline (e.g. TPS into a separate
  layer, hand-tune, then bake yourself).
- You are debugging a recommended pipeline that did something
  unexpected.
- You are porting an existing wing texture from another tool.

Run a standalone method, inspect the result, then either bake
manually with `Mesh > Transfer Texture > Bake to Albedo` or move
on to another method.

## Performance and texture sizes

The baked output's resolution is configurable in
`Preferences > Texture Transfer > Bake Resolution`. Default 2048
× 2048 (8 MB at sRGB 8-bit). Drop to 1024 for tutorial-grade
output, raise to 4096 for marketing-quality.

Re-baking is destructive on the placement's albedo channel.
Bookmark the project's history state before re-baking so you can
revert.

## See also

- [Blue Morpho tutorial chapter 5](../getting-started/butterfly/05-run-polar-pipeline.md)
 : Polar pipeline in action.
- [Blue Morpho tutorial chapter 6](../getting-started/butterfly/06-compare-bbox-pipeline.md)
 : BBox + Landmark Gaps in action.
- [Hypershade](hypershade.md): materials that consume the baked
  textures.
- [AOVs](aovs.md): bake textures as render passes from a custom
  shader graph.
