# Cloth flag with wind

Time: 35 minutes. Difficulty: Intermediate.

Author a flag-on-pole skin where the flag is a nCloth patch
animated by a wind force. Ships as a `.esk` with the simulation
baked to per-frame keys.

## Prerequisites

- Designer installed.
- Familiarity with [Simulation index](../simulation/index.md).

## Author the pole

1. `File > New Skin`, 320 x 240.
2. Drop a thin rectangle (`M`) at (40, 20), width 6, height 200,
   fill `#8b5a2bff` (brown).
3. Drop a small ellipse (`F`) at (40, 18), width 12, height 12,
   fill `#fcd34dff` (gold finial).

## Create the cloth

1. F5 (FX menu set).
2. `Simulation > Create nCloth Patch (8×10)`.
3. Move the patch so its leftmost edge sits against the pole at
   (46, 30).
4. Scale to 200 wide, 120 tall in the Channel Box.

## Pin the left edge

1. With the cloth selected, press `V` to enter vertex mode.
2. Lasso the left column of vertices.
3. `Simulation > Cloth > Pin Selected Vertices`. Select the pole
   as the "Pin to Placement" target so they follow the pole.

## Add a wind force

1. `Simulation > Forces > Add Wind…`.
2. Set: direction = (1, 0, 0), strength = 200 px/s², turbulence
   = 0.3.
3. Ensure the cloth's `affected_by_wind: true`.

## Style the flag

Select the cloth; in the Properties pane:

- `fill`: a horizontal red-white-blue stripe gradient (or an image
  via `texture_path` if you have a national flag PNG).
- `stretch_stiffness`: 0.95.
- `bend_stiffness`: 0.4 (a flag flutters; raise for stiffer fabric).

## Run the sim

Press `Space` on the time slider. The flag flutters for 240 frames
(default project length). Adjust the wind direction or strength
to taste.

## Bake to keys

`Simulation > Bake to Keys`. The cloth's per-vertex positions
become per-frame keys; the sim solver disappears.

## Export

`File > Export > .esk Bundle`. The bundle ships the flag-and-pole
skin with the baked animation; runtime needs no simulator.

## What you exercised

- nCloth patch creation.
- Pinning to another placement.
- Wind force.
- Sim parameters (stretch_stiffness, bend_stiffness).
- Bake to keys for shipping.

## See also

- [Cloth](../simulation/cloth.md)
- [Hair](../simulation/hair.md): for rope variants.
