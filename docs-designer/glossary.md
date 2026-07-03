# Glossary

Designer-specific terms. For framework concepts (signals, effects,
Tweens) see the [Framework glossary](https://docs.elysiumui.com/resources/glossary/).

## A

**Action id**: Machine-readable identifier for a menu / toolbox /
shortcut. Looks like `mesh.transfer_polar_normal`. Used by Aether
and by scripting.

**Aether**: The in-app AI agent. Chat panel; 123 tools across 15
modules.

**Animation Clip**: A reusable animation track. See
[Trax and Time Editor](animation/trax-and-time-editor.md).

**AOV**: Arbitrary Output Variable: a render pass isolating one
component (diffuse / specular / depth / normal / etc.).

## B

**Bake**: Commit a derived result into a baked texture or
per-frame keys. The texture transfer pipelines bake albedos +
normals; sims bake to keys.

**BBox-warp**: A texture transfer pipeline that maps the source
photo's bounding box onto the target mesh's UV bounding box.

**Brush Library**: Searchable panel of brush presets.

**Brush Studio**: Full editor for authoring a brush from scratch.

## C

**Channel Box**: Right-column numeric editor for the selection.

**Code Link**: Two-way wiring between the Designer and your
editor.

## D

**Dope Sheet**: Per-key timing editor.

## E

**`.esk`**: The skin bundle format. See
[`.esk` bundle format](reference/esk-bundle-format.md).

**Eyedrop**: Tool that samples a color (or tileable swatch) from
the canvas.

## H

**HUD**: Heads-up display overlay on the View Panel.

**Hypershade**: Node-graph material editor.

## L

**Landmark**: One half of a paired source ↔ target point used by
the texture transfer pipelines. Six pairs is the sweet spot for
butterflies.

**Loft**: Build a surface from a sequence of input curves.

## M

**MASH**: Procedural duplication system; scatter copies of a
source in a grid / random / curve / mesh distribution.

**Menu set**: Maya-style mode switching the menu bar's contents
(Modeling, Rigging, Animation, FX, Rendering).

**Mesh3D**: A 3D model placement.

## N

**NURBS**: Non-Uniform Rational B-Spline curve.

## O

**Orient Joint**: Align a joint's local axes (X toward child, Y
up, Z cross).

## P

**Path**: A 2D vector shape placement.

**Pivot Edit**: Tool that moves a placement's pivot point without
moving its content.

**Placement**: One item in a skin's `document.json`. Has an `id`
and a `kind`.

**Polar pipeline**: A texture transfer pipeline using polar
coordinates centered on the model body. Fast, smooth.

**Preview Skin**: `Run > Preview Skin` opens a borderless
transparent window loading the live `.esk` as the framework would
load it.

**Project Explorer**: Right-column tree view of the project
(Objects, Assets, History, Sets).

## R

**Render Layer**: A named collection of placements rendered as
one pass.

**Render Part Mask**: A per-placement region that narrows
operations (paint, bake, deform) to a subset of vertices.

## S

**Shelf**: Customizable toolbar below the menu bar.

**Snapshot**: A named scene state restore point. Aether
references snapshots for rollback.

**spp**: Samples per pixel. Render quality measure.

## T

**Toolbox**: Left-edge column of 17 tools.

**Trax Editor**: Clip-level animation editor.

## V

**View Panel**: The big center region. Where you actually edit.

## See also

- [Framework glossary](https://docs.elysiumui.com/resources/glossary/)
- [Manual index](manual-index.md)
