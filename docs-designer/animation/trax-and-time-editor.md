# Trax and Time editor

Trax (the "track editor") and the Time Editor are the Designer's
two surfaces for **clip-level** animation: composing reusable
animation clips rather than authoring keys.

## Why clip-level

A single 24-frame "wing flap" is a clip. So is a 60-frame
"banner unfurl". When you have several clips, layering them
together produces complex behavior without authoring more keys.

Examples:

- Loop a wing flap while overlaying a one-shot wing-fold pose.
- Cross-fade between a walk cycle and a run cycle.
- Trigger a clip on a UI event ("when the button is clicked, play
  the bounce clip").

## Trax editor

`Animate > Trax Editor` opens Trax. Layout:

- **Track list (left)**: stacked tracks per placement.
- **Timeline (right)**: clip bars on each track.

Drop a clip on a track by dragging from the Project Explorer's
**Animation Clips** group. Resize a clip by dragging its right
edge (stretches or scales the underlying curve). Move by dragging
the middle.

Tracks blend top-down by their weight. The result is the sum
(weighted) of every track on the row.

## Time Editor

`Animate > Time Editor` opens the larger Time Editor view. It
adds:

- **Clip nesting**: clips can contain other clips, so you can
  build "phrases".
- **Per-clip retiming**: warp a clip's internal timeline without
  scaling its duration.
- **Bake out**: collapse the time editor stack to per-frame keys.

For simple authoring stay in Trax; jump to Time Editor when a clip
graph gets large enough to warrant nesting.

## Create a clip from existing keys

1. Select the range of keys (Dope Sheet, time slider, or Graph
   Editor).
2. `Animate > Create Clip from Selection`.
3. Name it.

The keys move into the new clip's internal timeline; the original
positions on the placement timeline are replaced by a clip
reference. Subsequent edits inside the clip update everywhere the
clip is used.

## Clip blending

Each clip on a track has a weight (0..1) and a blend mode:

| Mode | Effect |
|---|---|
| Replace | Clip's values overwrite the lower tracks at this point |
| Add | Clip's offsets stack on top of lower tracks |
| Multiply | Clip's values multiplied with lower (useful for masks) |

A typical wing-flap rig uses one Add track with "flap_base"
(looping) plus a Replace track with "flap_freeze" (one-shot for the
flapless moments).

## Bake

`Animate > Time Editor > Bake to Keys` collapses the stack into
per-frame keys on the placement. Use to:

- Hand off to a renderer that does not understand clip layering.
- Lock in the final composition before export.

After bake, the clips are gone and only keys remain.

## See also

- [Dope sheet](dope-sheet.md): key-level timing within a clip.
- [Motion paths](motion-paths.md): visualize the translate
  trajectory of an animated placement.
