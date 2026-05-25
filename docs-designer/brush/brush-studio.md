# Brush Studio

The Brush Studio is the full-screen editor where you author a brush
from scratch (or modify a Library preset). It is the in-app
equivalent of Procreate's "Edit Brush" panel and Photoshop's
"Brush Settings" panel combined.

Open with `Window > Brush Studio` or click the **Studio** button at
the bottom of the Brush Library panel.

![Brush Studio split into engine params (left), dynamics curves (center), live preview (right)](../assets/brush-studio.png)

## Three columns

The Studio is split vertically into three columns.

### 1. Engine and parameters (left)

Top: engine selector. Picking an engine reveals its
[parameter set](engines-reference.md). For Round Stamp:

| Parameter | Range | Default |
|---|---|---|
| size_px | 1 - 500 | 20 |
| opacity | 0.0 - 1.0 | 1.0 |
| hardness | 0.0 - 1.0 | 0.8 |
| spacing | 0.0 - 1.0 | 0.25 |
| angle_deg | -180 - 180 | 0 |
| roundness | 0.0 - 1.0 | 1.0 |

Engines like Bristle and Wet Mix add ~10 more parameters each
(bristle count, ink load, water amount, etc.).

### 2. Dynamics curves (center)

For each parameter, a small graph shows how the parameter responds
to an **input channel**. The input channels are:

| Channel | Source |
|---|---|
| Pressure | Tablet pen pressure (0 - 1) |
| Tilt | Pen tilt magnitude (0 - 1) |
| Rotation | Pen barrel rotation (0 - 360°) |
| Velocity | Cursor speed (normalized) |
| Altitude | Pen vertical angle (0 - 90°) |
| Distance | Distance from stroke start |
| Random | Per-stamp uniform random |

Click any cell in the grid to bind: e.g. **size × pressure** opens
a small curve editor where the X axis is pressure (0 - 1) and the Y
axis is the multiplier applied to size. Drag points to shape the
curve.

The default `pressure → size` curve is a gentle ease-in (a flat
floor up to ~0.1 pressure, then ramps to 1.0). Adjust to taste.

### 3. Live preview (right)

The preview canvas shows a sample stroke updated in real time as
you tweak parameters. Three controls under the canvas:

- **Pressure simulation**: when no tablet is connected, mock
  pressure with a slider so you can audition the curve.
- **Stroke pattern**: straight / S-curve / loop. Useful for hunting
  for spacing issues only visible on tight curves.
- **Background**: white / black / mid-gray / your last sampled
  swatch.

Strokes accumulate in the preview canvas until you press **Clear
Preview** so you can compare two stroke runs side by side.

## Texture

For Texture and Pattern engines a fourth column appears with the
texture picker. Drop any PNG / JPG, or pick from the bundled set of
40 photographic textures. Scale, rotate, and offset the texture
inside the stroke.

## Save

The Studio's footer:

- **Apply**: apply current settings to the live brush without
  saving.
- **Save**: write the preset to the Library (asks for a name,
  tags, and a thumbnail capture).
- **Reset**: revert to the preset's saved state.
- **Cancel**: close the Studio without applying.

## Comparing two brushes

Open two presets side by side: drag a second Library thumbnail into
the Studio's split header. The Studio splits into two preview
columns; tweaks affect whichever side you have focused. Useful for
A/B'ing dynamics tweaks.

## Reset all dynamics

A common workflow is "I love this brush's stamp but the dynamics
are wrong for me." The **Reset Dynamics** button under the
dynamics-curves column drops every channel binding back to no-op
(identity curves). You can then build up only the channels you
want.

## Exporting

A saved preset can be exported to a `.elybrush` file for sharing.
Right-click in the Library panel > **Export to .elybrush…**. See
[Native .elybrush format](native-elybrush-format.md) for the file
spec.

## Where to next

- [Authoring custom brushes](authoring-custom-brushes.md): when
  the Studio is not enough and you need to drop down to Python.
- [Touch and dynamics](touch-and-dynamics.md): full mapping table
  for tablet / pen.
