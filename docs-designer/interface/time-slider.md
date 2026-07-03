# Time slider

The time slider runs across the bottom of the View Panel and is the
primary control surface for animation. It shows the timeline, the
current frame, every key on the active channel, and the playback
range.

![Time slider with keyframes visible on two channels and the playback range marked](../assets/interface-time-slider.png)

## Anatomy

| Region | Position | Purpose |
|---|---|---|
| Transport | Left edge | Rewind, Step Back, Play, Step Forward, Fast Forward |
| Current-frame readout | Just right of transport | Click to type a frame number |
| Timeline track | Center, full width | Drag the playhead to scrub; keyframes appear as diamonds |
| Start / End fields | Right edge | Set the playback range; default 1 to 24 |
| Auto Key indicator | Far right | Small red dot when `Animate > Toggle Auto Key` is on |
| Playback speed dropdown | Far right | 24 / 30 / 60 fps; defaults follow project settings |

## Scrubbing

Drag the playhead horizontally to scrub. The View Panel updates
every frame; keyboard arrows step one frame at a time (Shift+arrow
steps to the next key).

## Adding and editing keys

- **Set a key on the current channel**: `S` or `Animate > Set Key`.
- **Set a breakdown** (interpolation hint between two keys):
  `Shift+S` or `Animate > Set Breakdown`.
- **Delete a key**: select the diamond, press Backspace.
- **Move a key**: drag it horizontally. Hold Shift to clamp to
  whole frames.

Multi-selection (drag a box across diamonds) lets you move several
keys together.

## Auto Key

When the red dot is on, any property change at any frame creates a
key automatically. Useful for blocking. Turn off before doing
spacing or polish passes so a stray nudge does not accidentally key
a new pose.

## The range selectors

Drag the small slim brackets at the start and end of the timeline
to set a sub-range for playback. The playhead loops inside the sub-
range; the rest of the timeline grays out. Right-click the timeline
and choose **Reset Range** to clear the sub-range.

## Deeper editing

For curve-level work move to the [Graph Editor](../animation/graph-editor.md);
for clip-level work to the [Trax Editor](../animation/trax-and-time-editor.md);
for layout the [Dope Sheet](../animation/dope-sheet.md). All three
are panels you can dock alongside the time slider.

## Hide / show

`Window > Toggle Time Slider` hides it (useful when you are only
authoring static skins). Auto-shows again when you set the first
key.
